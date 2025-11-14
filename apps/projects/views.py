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
    
    Permissions:
        - List/Retrieve: Authenticated users
        - Create/Update/Delete: Admins only
    
    Custom Actions:
        - verify: Mark project as verified
        - assign: Assign employers to project
        - my_projects: Get projects assigned to current user
        - calendar: Get calendar events for project
    """
    queryset = Project.objects.select_related(
        'client', 'verified_by', 'created_by'
    ).prefetch_related('assigned_employers', 'maintenances')
    
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    pagination_class = StaticPagination
    
    # Filtering configuration
    filterset_fields = ['start_date', 'end_date', 'is_verified', 'client', 'invoices__facture']
    search_fields = ['name', 'client__name', 'description', 'invoices__facture','client__address__province', 'client__address__city','client__address__postal_code'] 
    ordering_fields = ['start_date', 'created_at', 'name']

    def get_serializer_class(self):
        # Use ProjectDetailSerializer for both list and detail to provide full information
        if self.action == 'list':
            return ProjectDetailSerializer  # Changed from ProjectListSerializer
        return ProjectDetailSerializer

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
                {'detail': 'Project is already verified'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        project.verify(by_user=request.user)
        
        serializer = self.get_serializer(project)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def unverify(self, request, pk=None):
        """Mark project as unverified (return to draft)"""
        project = self.get_object()
        
        if not project.is_verified:
            return Response(
                {'detail': 'Project is already not verified'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        project.unverify()
        serializer = self.get_serializer(project)
        return Response(serializer.data)


    @action(detail=True, methods=['post'])
    @transaction.atomic
    def assign(self, request, pk=None):
        """
        Assign employers to project.
        
        Request body:
            {
                "user_ids": [1, 2, 3]
            }
        """
        from apps.users.models import CustomUser
        
        project = self.get_object()
        user_ids = request.data.get('user_ids', [])
        
        if not isinstance(user_ids, list):
            return Response(
                {'detail': 'user_ids must be a list'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Only assign users with EMPLOYER role
        users = CustomUser.objects.filter(
            id__in=user_ids,
            role=CustomUser.ROLE_EMPLOYER
        )
        
        project.assigned_employers.add(*users)
        
        serializer = self.get_serializer(project)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_projects(self, request):
        """Get projects assigned to the current user"""
        projects = self.get_queryset().filter(
            assigned_employers=request.user
        )
        
        page = self.paginate_queryset(projects)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(projects, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def calendar(self, request, pk=None):
        """
        Get calendar events for project (start, end, maintenance dates).
        Returns data suitable for calendar components.
        """
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
            events.append({
                'id': f'maintenance-{maintenance.id}',
                'title': f'Maintenance #{maintenance.maintenance_number}: {project.name}',
                'start': maintenance.start_date.isoformat(),
                'end': maintenance.end_date.isoformat(),
                'type': 'maintenance',
                'project_id': project.id,
                'maintenance_id': maintenance.id,
            })
        
        return Response(events)


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
    
    filterset_fields = ['start_date', 'end_date', 'project', 'maintenance_type']  # Add maintenance_type
    search_fields = ['project__name']
    ordering_fields = ['start_date', 'end_date', 'created_at', 'maintenance_type']
    ordering = ['start_date']
    
    def create(self, request, *args, **kwargs):
        """Ensure manual maintenances are created with MANUAL type"""
        # If maintenance_type is not provided in request, set it to MANUAL
        if 'maintenance_type' not in request.data:
            request.data['maintenance_type'] = Maintenance.TYPE_MANUAL
        
        return super().create(request, *args, **kwargs)