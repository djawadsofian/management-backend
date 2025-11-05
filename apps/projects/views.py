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
from apps.projects.services import CalendarService
from .models import Project, Maintenance
from .serializers import (
    CalendarEventSerializer,
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
    filterset_fields = ['start_date', 'end_date', 'is_verified', 'client']
    search_fields = ['name', 'client__name', 'description']
    ordering_fields = ['start_date', 'created_at', 'name']

    def get_serializer_class(self):
        if self.action == 'list':
            return ProjectListSerializer
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
            if maintenance.next_maintenance_date:
                events.append({
                    'id': f'maintenance-{maintenance.id}',
                    'title': f'Maintenance: {project.name}',
                    'start': maintenance.next_maintenance_date.isoformat(),
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
    
    Custom Actions:
        - mark_completed: Mark maintenance as completed and schedule next
    """
    queryset = Maintenance.objects.select_related('project__client')
    serializer_class = MaintenanceSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    pagination_class = StaticPagination
    
    filterset_fields = ['next_maintenance_date', 'project']
    search_fields = ['project__name']
    ordering_fields = ['next_maintenance_date', 'created_at']
    ordering = ['next_maintenance_date']

    @action(detail=True, methods=['post'])
    def mark_completed(self, request, pk=None):
        """
        Mark maintenance as completed and schedule the next one.
        """
        maintenance = self.get_object()
        maintenance.mark_completed()
        
        serializer = self.get_serializer(maintenance)
        return Response(serializer.data)
    


class EmployerCalendarView(APIView):
    """
    Calendar view for employers.
    Shows only projects assigned to the employer.
    
    GET /api/projects/calendar/employer/
    
    Query Parameters:
        - start_date: Filter events from this date (YYYY-MM-DD)
        - end_date: Filter events until this date (YYYY-MM-DD)
        - upcoming_days: Show only upcoming events within N days
        - show_overdue: Include overdue events (default: true)
        - event_types: Comma-separated event types: project_start,project_end,project_active,maintenance
        - project_id: Filter by specific project ID
        - status: Filter by status: upcoming, overdue, today
    
    Returns:
        List of calendar events for assigned projects and their maintenances
    """

    permission_classes = [IsAuthenticated]
    
    # Remplacer la méthode get dans EmployerCalendarView

    def get(self, request):
        user = request.user
        
        # Only employers can access this endpoint
        if not user.is_employer() and not user.is_admin():
            return Response(
                {
                    'error': 'Only employers can access this calendar view',
                    'detail': 'You must have EMPLOYER role to view this calendar'
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get query parameters - FILTRES EMPLOYER
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        upcoming_days = request.query_params.get('upcoming_days')
        show_overdue = request.query_params.get('show_overdue', 'true').lower() == 'true'
        
        # FILTRES SPÉCIFIQUES EMPLOYER
        event_types = request.query_params.get('event_types')
        project_id = request.query_params.get('project_id')
        status_filter = request.query_params.get('status')  # upcoming, overdue, today
        
        # Parse dates
        if start_date:
            start_date = parse_date(start_date)
        if end_date:
            end_date = parse_date(end_date)
        
        # Get events
        events = CalendarService.get_employer_calendar(
            user,
            start_date=start_date,
            end_date=end_date
        )
        
        # APPLIER LES FILTRES EMPLOYER
        # Filtre par type d'événement (employer a accès à moins de types)
        if event_types:
            allowed_types = [t.strip() for t in event_types.split(',')]
            # Employer ne peut voir que ces types
            employer_allowed_types = ['project_start', 'project_end', 'project_active', 'maintenance']
            filtered_types = [t for t in allowed_types if t in employer_allowed_types]
            if filtered_types:
                events = CalendarService.filter_events_by_type(events, filtered_types)
        
        # Filtre par projet (seulement les projets assignés)
        if project_id:
            try:
                # Vérifier que l'employer est bien assigné à ce projet
                from apps.projects.models import Project
                user_projects = Project.objects.filter(
                    assigned_employers=user
                ).values_list('id', flat=True)
                
                if int(project_id) in user_projects:
                    events = CalendarService.filter_events_by_project(events, int(project_id))
            except (ValueError, TypeError):
                pass
        
        # Filtre par statut
        if status_filter:
            events = CalendarService.filter_events_by_status(events, status_filter)
        
        # Apply additional filters
        if upcoming_days:
            try:
                days = int(upcoming_days)
                events = CalendarService.get_upcoming_events(events, days=days)
            except ValueError:
                pass
        
        if not show_overdue:
            today = timezone.now().date()
            events = [e for e in events if e['start'] >= today]
        
        # Serialize events
        serializer = CalendarEventSerializer(events, many=True)
        
        # Add metadata - METTRE À JOUR LES FILTRES
        response_data = {
            'count': len(events),
            'user': {
                'id': user.id,
                'username': user.username,
                'full_name': user.get_full_name(),
                'role': user.role
            },
            'filters': {
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
                'upcoming_days': upcoming_days,
                'show_overdue': show_overdue,
                'event_types': event_types,
                'project_id': project_id,
                'status': status_filter
            },
            'events': serializer.data,
            'summary': self._generate_summary(events)
        }
        
        return Response(response_data)
    
    def _generate_summary(self, events):
        """Generate summary statistics for events"""
        today = timezone.now().date()
        
        summary = {
            'total_events': len(events),
            'upcoming_events': len([e for e in events if e['start'] > today]),
            'overdue_events': len([e for e in events if e.get('is_overdue', False)]),
            'events_by_type': {}
        }
        
        # Count by type
        for event in events:
            event_type = event['type']
            summary['events_by_type'][event_type] = summary['events_by_type'].get(event_type, 0) + 1
        
        return summary


class AdminCalendarView(APIView):
    """
    Calendar view for admins.
    Shows all projects, maintenances, and warranty information.
    
    GET /api/projects/calendar/admin/
    
    Query Parameters:
        - start_date: Filter events from this date (YYYY-MM-DD)
        - end_date: Filter events until this date (YYYY-MM-DD)
        - upcoming_days: Show only upcoming events within N days
        - show_overdue: Include overdue events (default: true)
        - event_types: Comma-separated list of event types to include: project_start,project_end,project_active,maintenance,warranty_start,warranty_end
        - client_id: Filter by client ID
        - project_id: Filter by project ID
        - status: Filter by status: upcoming, overdue, today, active
        - assigned_user_id: Filter by assigned user ID
        - verified_only: Show only verified projects (default: true)
    
    Returns:
        List of all calendar events including warranty information
    """
    permission_classes = [IsAuthenticated]
    
    # Remplacer la méthode get dans AdminCalendarView

    def get(self, request):
        user = request.user
        
        # Only admins can access this endpoint
        if not user.is_admin():
            return Response(
                {
                    'error': 'Admin access required',
                    'detail': 'You must have ADMIN role to view the full calendar'
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get query parameters - AJOUT DES NOUVEAUX FILTRES
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        upcoming_days = request.query_params.get('upcoming_days')
        show_overdue = request.query_params.get('show_overdue', 'true').lower() == 'true'
        event_types = request.query_params.get('event_types')
        
        # NOUVEAUX FILTRES ADMIN
        client_id = request.query_params.get('client_id')
        project_id = request.query_params.get('project_id')
        status_filter = request.query_params.get('status')  # upcoming, overdue, today, active
        assigned_user_id = request.query_params.get('assigned_user_id')
        verified_only = request.query_params.get('verified_only', 'true').lower() == 'true'
        
        # Parse dates
        if start_date:
            start_date = parse_date(start_date)
        if end_date:
            end_date = parse_date(end_date)
        
        # Get events
        events = CalendarService.get_admin_calendar(
            start_date=start_date,
            end_date=end_date
        )
        
        # APPLIER LES FILTRES ADMIN
        # Filtre par client
        if client_id:
            try:
                events = CalendarService.filter_events_by_client(events, int(client_id))
            except (ValueError, TypeError):
                pass
        
        # Filtre par projet
        if project_id:
            try:
                events = CalendarService.filter_events_by_project(events, int(project_id))
            except (ValueError, TypeError):
                pass
        
        # Filtre par type d'événement
        if event_types:
            events = CalendarService.filter_events_by_type(events, event_types)
        
        # Filtre par statut
        if status_filter:
            events = CalendarService.filter_events_by_status(events, status_filter)
        
        # Filtre par utilisateur assigné (nécessite une logique supplémentaire)
        if assigned_user_id:
            try:
                # Filtrer les événements de projets assignés à l'utilisateur
                from apps.projects.models import Project
                user_projects = Project.objects.filter(
                    assigned_employers__id=int(assigned_user_id)
                ).values_list('id', flat=True)
                events = [e for e in events if e.get('project_id') in user_projects]
            except (ValueError, TypeError):
                pass
        
        # Filtre par vérification
        if verified_only:
            # Pour les événements de projet, s'assurer qu'ils proviennent de projets vérifiés
            # Cette logique nécessite d'ajouter is_verified aux événements dans le service
            events = [e for e in events if e.get('is_verified', True)]
        
        # Apply additional filters
        if upcoming_days:
            try:
                days = int(upcoming_days)
                events = CalendarService.get_upcoming_events(events, days=days)
            except ValueError:
                pass
        
        if not show_overdue:
            today = timezone.now().date()
            events = [e for e in events if e['start'] >= today]
        
        # Serialize events
        serializer = CalendarEventSerializer(events, many=True)
        
        # Add metadata - METTRE À JOUR LES FILTRES
        response_data = {
            'count': len(events),
            'user': {
                'id': user.id,
                'username': user.username,
                'full_name': user.get_full_name(),
                'role': user.role
            },
            'filters': {
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
                'upcoming_days': upcoming_days,
                'show_overdue': show_overdue,
                'event_types': event_types,
                'client_id': client_id,
                'project_id': project_id,
                'status': status_filter,
                'assigned_user_id': assigned_user_id,
                'verified_only': verified_only
            },
            'events': serializer.data,
            'summary': self._generate_summary(events),
            'statistics': self._generate_statistics(events)
        }
        
        return Response(response_data)
    
    def _generate_summary(self, events):
        """Generate summary statistics for events"""
        today = timezone.now().date()
        
        summary = {
            'total_events': len(events),
            'upcoming_events': len([e for e in events if e['start'] > today]),
            'overdue_events': len([e for e in events if e.get('is_overdue', False)]),
            'events_by_type': {}
        }
        
        # Count by type
        for event in events:
            event_type = event['type']
            summary['events_by_type'][event_type] = summary['events_by_type'].get(event_type, 0) + 1
        
        return summary
    
    def _generate_statistics(self, events):
        """Generate detailed statistics for admin"""
        today = timezone.now().date()
        next_week = today + timedelta(days=7)
        next_month = today + timedelta(days=30)
        
        statistics = {
            'events_this_week': len([e for e in events if today <= e['start'] <= next_week]),
            'events_this_month': len([e for e in events if today <= e['start'] <= next_month]),
            'maintenance_overdue': len([
                e for e in events 
                if e['type'] == 'maintenance' and e.get('is_overdue', False)
            ]),
            'warranties_expiring_soon': len([
                e for e in events 
                if e['type'] == 'warranty_end' and today <= e['start'] <= next_month
            ]),
            'active_projects': len([
                e for e in events 
                if e['type'] == 'project_active'
            ])
        }
        
        return statistics


class CalendarSummaryView(APIView): 
    """
    Quick summary view for calendar alerts and notifications.
    Works for both employers and admins based on their role.
    
    GET /api/projects/calendar/summary/
    
    Returns:
        Quick summary of upcoming and overdue events
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        # Get appropriate events based on role
        if user.is_admin():
            events = CalendarService.get_admin_calendar()
        elif user.is_employer():
            events = CalendarService.get_employer_calendar(user)
        else:
            return Response(
                {'error': 'Insufficient permissions'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        today = timezone.now().date()
        
        # Categorize events
        upcoming_7_days = CalendarService.get_upcoming_events(events, days=7)
        upcoming_30_days = CalendarService.get_upcoming_events(events, days=30)
        overdue = CalendarService.get_overdue_events(events)
        
        # Get today's events
        today_events = [e for e in events if e['start'] == today]
        
        response_data = {
            'today': {
                'count': len(today_events),
                'events': CalendarEventSerializer(today_events, many=True).data
            },
            'upcoming_week': {
                'count': len(upcoming_7_days),
                'events': CalendarEventSerializer(upcoming_7_days[:5], many=True).data  # Top 5
            },
            'upcoming_month': {
                'count': len(upcoming_30_days),
                'events': CalendarEventSerializer(upcoming_30_days[:10], many=True).data  # Top 10
            },
            'overdue': {
                'count': len(overdue),
                'events': CalendarEventSerializer(overdue[:5], many=True).data  # Top 5
            },
            'alerts': {
                'has_overdue': len(overdue) > 0,
                'has_today': len(today_events) > 0,
                'urgent_count': len(overdue) + len(today_events)
            }
        }
        
        return Response(response_data)