# apps/projects/views.py
"""
Refactored project views with cleaner structure and better organization.
"""
from datetime import timedelta
from django.utils.dateparse import parse_date
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.core.middleware import get_current_user


from apps.core.mixins import (
    StandardFilterMixin,
    TimestampOrderingMixin,
    SetCreatedByMixin
)
from apps.core.pagination import StaticPagination
from apps.core.permissions import IsAdminOrReadOnly
from .models import Project, Maintenance
from .serializers import (
    ProjectListSerializer,
    ProjectDetailSerializer,
    MaintenanceSerializer
)


class ProjectViewSet(
    StandardFilterMixin,
    TimestampOrderingMixin,
    SetCreatedByMixin,
    viewsets.ModelViewSet
):
    """
    ViewSet for managing projects.
    """


   
    queryset = Project.objects.select_related(
        'client', 'verified_by', 'created_by'
    ).prefetch_related('assigned_employers', 'maintenances')
    
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    pagination_class = StaticPagination
    
    filterset_fields = ['start_date', 'end_date', 'is_verified', 'client', 'invoices__facture']
    search_fields = ['name', 'client__name', 'description', 'invoices__facture','client__address__province', 'client__address__city','client__address__postal_code'] 
    ordering_fields = ['start_date', 'created_at', 'name']
    ordering = ['-created_at']

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        
        # Handle multiple city filter
        cities = self.request.query_params.getlist('city')
        if cities:
            queryset = queryset.filter(client__address__city__in=cities)
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            # Filter based on status logic
            today = timezone.now().date()
            
            if status_filter == Project.STATUS_DRAFT:
                queryset = queryset.filter(is_verified=False)
            elif status_filter == Project.STATUS_UPCOMING:
                queryset = queryset.filter(
                    is_verified=True,
                    start_date__gt=today
                )
            elif status_filter == Project.STATUS_ACTIVE:
                queryset = queryset.filter(
                    is_verified=True,
                    start_date__lte=today,
                    end_date__gte=today
                )
            elif status_filter == Project.STATUS_COMPLETED:
                queryset = queryset.filter(
                    is_verified=True,
                    end_date__lt=today
                )
        
        return queryset


   

    def get_serializer_class(self):
        if self.action == 'list':
            return ProjectDetailSerializer
        return ProjectDetailSerializer

    def create(self, request, *args, **kwargs):
        """Handle project creation with custom error format"""
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {"message": f"Erreur lors de la création du projet: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    def update(self, request, *args, **kwargs):
        """Handle project update with custom error format"""
        try:
            return super().update(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {"message": f"Erreur lors de la mise à jour du projet: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def verify(self, request, pk=None):
        """
        Mark project as verified.
        Only admins can verify projects.
        """
        project = self.get_object()
        
        if project.is_verified:
            return Response(
                {"message": "Le projet est déjà vérifié"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            project._modified_by = request.user 
            project.verify(by_user=request.user)
            serializer = self.get_serializer(project)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"message": f"Erreur lors de la vérification du projet: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def unverify(self, request, pk=None):
        """Mark project as unverified (return to draft)"""
        project = self.get_object()
        
        if not project.is_verified:
            return Response(
                {"message": "Le projet n'est pas vérifié"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            project._modified_by = request.user 
            project.unverify()
            serializer = self.get_serializer(project)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"message": f"Erreur lors de la dé-vérification du projet: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    # In ProjectViewSet.perform_update()
    def perform_update(self, serializer):
        """Track who modified the project"""
        # Set user BEFORE saving
        serializer.instance._modified_by = self.request.user
        instance = serializer.save()
        return instance

    def perform_destroy(self, instance):
        """Track who deleted the project"""
        # Set user for signal handler
        instance._deleted_by = get_current_user() or self.request.user
        instance.delete()

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def assign(self, request, pk=None):
        """
        Assign employers to project.
        UPDATED to trigger assignment notifications
        """
        from apps.users.models import CustomUser
        
        project = self.get_object()
        user_ids = request.data.get('user_ids', [])
        
        if not isinstance(user_ids, list):
            return Response(
                {"message": "user_ids doit être une liste"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get employers to assign
            users = CustomUser.objects.filter(
                id__in=user_ids,
                role=CustomUser.ROLE_EMPLOYER
            )
            
            if not users.exists():
                return Response(
                    {"message": "Aucun employeur valide trouvé"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get currently assigned employers
            current_employers = set(project.assigned_employers.values_list('id', flat=True))
            
            # Add new employers
            project.assigned_employers.add(*users)
            
            # Find newly assigned employers (for notification)
            new_employer_ids = set(user_ids) - current_employers
            if new_employer_ids and project.is_verified:
                new_employers = CustomUser.objects.filter(id__in=new_employer_ids)
                # Notification will be sent by m2m_changed signal
                
            serializer = self.get_serializer(project)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"message": f"Erreur lors de l'assignation des employeurs: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def my_projects(self, request):
        """Get projects assigned to the current user"""
        try:
            projects = self.get_queryset().filter(
                assigned_employers=request.user
            )
            
            page = self.paginate_queryset(projects)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(projects, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"message": f"Erreur lors de la récupération des projets: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'])
    def calendar(self, request, pk=None):
        """
        Get calendar events for project (start, end, maintenance dates).
        """
        try:
            project = self.get_object()
            events = []
            
            # Project start event
            events.append({
                'id': f'project-{project.id}-start',
                'title': f'Start: {project.name}',
                'start': project.start_date.isoformat(),
                'type': 'project_start',
                'project_id': project.id,
            })
            
            # Project end event
            if project.end_date:
                events.append({
                    'id': f'project-{project.id}-end',
                    'title': f'End: {project.name}',
                    'start': project.end_date.isoformat(),
                    'type': 'project_end',
                    'project_id': project.id,
                })
            
            # Maintenance events
            for maintenance in project.maintenances.all():
                type_display = "Auto" if maintenance.maintenance_type == Maintenance.TYPE_AUTO else "Manual"
                events.append({
                    'id': f'maintenance-{maintenance.id}',
                    'title': f'Maintenance ({type_display}): {project.name}',
                    'start': maintenance.start_date.isoformat(),
                    'end': maintenance.end_date.isoformat(),
                    'type': 'maintenance',
                    'project_id': project.id,
                    'maintenance_id': maintenance.id,
                })
            
            return Response(events)
        except Exception as e:
            return Response(
                {"message": f"Erreur lors de la récupération du calendrier: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
class MaintenanceViewSet(
    StandardFilterMixin,
    TimestampOrderingMixin,
    viewsets.ModelViewSet
):
    """
    ViewSet for managing maintenance schedules.
    """
    queryset = Maintenance.objects.select_related('project__client')
    serializer_class = MaintenanceSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    pagination_class = StaticPagination
    
    filterset_fields = ['start_date', 'end_date', 'project', 'maintenance_type']
    search_fields = ['project__name']
    ordering_fields = ['start_date', 'end_date', 'created_at', 'maintenance_type']
    ordering = ['start_date']
    
    def create(self, request, *args, **kwargs):
        """Handle maintenance creation with custom error format"""
        try:
            # If maintenance_type is not provided in request, set it to MANUAL
            if 'maintenance_type' not in request.data:
                request.data['maintenance_type'] = Maintenance.TYPE_MANUAL
            
            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {"message": f"Erreur lors de la création de la maintenance: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    def update(self, request, *args, **kwargs):
        """Handle maintenance update with custom error format"""
        try:
            return super().update(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {"message": f"Erreur lors de la mise à jour de la maintenance: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
    def perform_create(self, serializer):
        """Track who created the maintenance"""
        instance = serializer.save()
        # Set user for signal handler
        instance._created_by = get_current_user() or self.request.user
        return instance

    def perform_update(self, serializer):
        """Track who modified the maintenance"""
        serializer.instance._modified_by = self.request.user
        instance = serializer.save()
        return instance

    def perform_destroy(self, instance):
        """Track who deleted the maintenance"""
        # Set user for signal handler
        instance._deleted_by = get_current_user() or self.request.user
        instance.delete()