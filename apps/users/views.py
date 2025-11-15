# apps/users/views.py
"""
Refactored user management views.
Simplified by removing redundant code and using proper mixins.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.core.pagination import StaticPagination
from apps.core.permissions import IsAdmin, IsAdminOrAssistant
from apps.core.mixins import StandardFilterMixin
from .models import CustomUser
from .serializers import (
    UserSerializer,
    EmployerCreateSerializer,
    AssistantCreateSerializer
)
from apps.projects.models import Project, Maintenance


class BaseUserViewSet(StandardFilterMixin, viewsets.ModelViewSet):
    """
    Base ViewSet for user management with common configuration.
    """
    pagination_class = StaticPagination
    filterset_fields = ['role', 'is_active', 'wilaya', 'group']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone_number']
    ordering_fields = ['username', 'email', 'date_joined']
    ordering = ['username']

    def get_serializer_class(self):
        """Use appropriate serializer for create vs other actions"""
        if self.action == 'create':
            return self.create_serializer_class
        return UserSerializer



class EmployerViewSet(BaseUserViewSet):
    """
    ViewSet for managing employer accounts.
    
    Permissions:
        - Admins and Assistants can manage employers
    
    Endpoints:
        - GET /api/employers/ - List employers
        - POST /api/employers/ - Create employer
        - GET /api/employers/{id}/ - Retrieve employer
        - PUT/PATCH /api/employers/{id}/ - Update employer
        - DELETE /api/employers/{id}/ - Delete employer
        - POST /api/employers/{id}/deactivate/ - Deactivate employer
        - POST /api/employers/{id}/activate/ - Activate employer
        - GET /api/employers/get_my_calendar/ - Get calendar events for current user
    """
    queryset = CustomUser.objects.filter(role=CustomUser.ROLE_EMPLOYER)
    permission_classes = [IsAdminOrAssistant]
    create_serializer_class = EmployerCreateSerializer

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate an employer account"""
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=['is_active'])
        return Response({"message": "Employer désactivé"})

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate an employer account"""
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=['is_active'])
        return Response({"message": "Employer activé"})

class AssistantViewSet(BaseUserViewSet):
    """
    ViewSet for managing assistant accounts.
    
    Permissions:
        - Only admins can manage assistants
    
    Endpoints:
        - GET /api/assistants/ - List assistants
        - POST /api/assistants/ - Create assistant
        - GET /api/assistants/{id}/ - Retrieve assistant
        - PUT/PATCH /api/assistants/{id}/ - Update assistant
        - DELETE /api/assistants/{id}/ - Delete assistant
        - GET /api/assistants/get_my_calendar/ - Get calendar events for current user
    """
    queryset = CustomUser.objects.filter(role=CustomUser.ROLE_ASSISTANT)
    permission_classes = [IsAdmin]
    create_serializer_class = AssistantCreateSerializer


    @action(detail=True, methods=['patch'])
    def update_permissions(self, request, pk=None):
        """Update price permissions for assistant"""
        user = self.get_object()
        
        # Only admins can update permissions
        if not request.user.is_admin():
            return Response(
                {"message": "Accès non autorisé"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Allowed fields to update
        allowed_fields = ['can_see_selling_price', 'can_edit_selling_price', 'can_edit_buying_price']
        
        # Filter only allowed fields
        update_data = {field: request.data[field] for field in allowed_fields if field in request.data}
        
        if not update_data:
            return Response(
                {"message": "Aucune permission valide"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update the fields
        for field, value in update_data.items():
            setattr(user, field, value)
        
        user.save(update_fields=update_data.keys())
        return Response({"message": "Permissions modifiées"})






@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_calendar(request):
    """
    Get calendar events for the currently authenticated user.
    
    - Admins and Assistants: See all projects and maintenances
    - Employers: See only assigned projects and their maintenances
    
    Query Parameters:
        - event_type: Filter by event type (project, maintenance, or all)
        - project_name: Search by project name (case-insensitive partial match)
        - client_name: Search by client name (case-insensitive partial match)
        - start_date: Filter events from this date (YYYY-MM-DD)
        - end_date: Filter events until this date (YYYY-MM-DD)
        - status: Filter by project status (DRAFT, UPCOMING, ACTIVE, COMPLETED)
        - is_verified: Filter by project verification status (true/false)
        - is_overdue: Filter overdue maintenances only (true/false)
        - province: Filter by client's province (case-insensitive)
        - city: Filter by client's city (case-insensitive partial match)
        - postal_code: Filter by client's postal code
    
    Returns:
        List of calendar events with project dates and maintenance schedules
    
    Examples:
        - /api/users/my-calendar/?event_type=maintenance
        - /api/users/my-calendar/?project_name=network&start_date=2025-01-01
        - /api/users/my-calendar/?client_name=acme&status=ACTIVE
        - /api/users/my-calendar/?province=tlemcen&city=tlemcen
        - /api/users/my-calendar/?province=oran&event_type=maintenance
    """
    from datetime import datetime
    from django.db.models import Q
    
    user = request.user
    
    # Get query parameters
    event_type = request.query_params.get('event_type', 'all')
    project_name = request.query_params.get('project_name', '').strip()
    client_name = request.query_params.get('client_name', '').strip()
    start_date = request.query_params.get('start_date', '').strip()
    end_date = request.query_params.get('end_date', '').strip()
    project_status = request.query_params.get('status', '').strip()
    is_verified = request.query_params.get('is_verified', '').strip()
    is_overdue = request.query_params.get('is_overdue', '').strip()
    
    # Address filtering parameters
    province = request.query_params.get('province', '').strip()
    city = request.query_params.get('city', '').strip()
    postal_code = request.query_params.get('postal_code', '').strip()
    
    # Determine which projects the user can see
    if user.role in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT] or user.is_superuser:
        # Admins and assistants see all projects
        projects = Project.objects.select_related('client').prefetch_related('maintenances')
    elif user.role == CustomUser.ROLE_EMPLOYER:
        # Employers see only their assigned projects
        projects = Project.objects.filter(
            assigned_employers=user
        ).select_related('client').prefetch_related('maintenances')
    else:
        # No projects for other roles
        projects = Project.objects.none()
    
    # Apply project filters
    if project_name:
        projects = projects.filter(name__icontains=project_name)
    
    if client_name:
        projects = projects.filter(client__name__icontains=client_name)
    
    if is_verified.lower() in ['true', 'false']:
        projects = projects.filter(is_verified=(is_verified.lower() == 'true'))
    
    # Apply address filters using JSONField lookups
    if province:
        projects = projects.filter(client__address__province__iexact=province)
    
    if city:
        projects = projects.filter(client__address__city__icontains=city)
    
    if postal_code:
        projects = projects.filter(client__address__postal_code=postal_code)
    
    # Build calendar events from projects
    events = []
    
    for project in projects:
        # Apply status filter (computed property)
        if project_status and project.status != project_status:
            continue
        
        # Get client address info for the event
        client_address = {}
        if project.client.address:
            client_address = {
                'province': project.client.address.get('province', ''),
                'city': project.client.address.get('city', ''),
                'postal_code': project.client.address.get('postal_code', ''),
            }
        
        # Single project event (combining start and end)
        if event_type in ['all', 'project']:
            project_event = {
                'id': f'project-{project.id}',
                'title': f'Project: {project.name}',
                'start': project.start_date.isoformat(),
                'type': 'project',
                'project_id': project.id,
                'project_name': project.name,
                'client_name': project.client.name,
                'client_address': client_address,
                'status': project.status,
                'is_verified': project.is_verified,
                'start_date': project.start_date.isoformat(),
                'end_date': project.end_date.isoformat() if project.end_date else None,
                'duration_days': project.duration_days,
                'progress_percentage': project.progress_percentage,
            }
            
            # If project has end date, use it as the end date for the calendar event
            if project.end_date:
                project_event['end'] = project.end_date.isoformat()
            
            events.append(project_event)
        
        # Maintenance events
        if event_type in ['all', 'maintenance']:
            for maintenance in project.maintenances.all():
                # Apply overdue filter if specified
                if is_overdue.lower() == 'true' and not maintenance.is_overdue:
                    continue
                elif is_overdue.lower() == 'false' and maintenance.is_overdue:
                    continue
                
                events.append({
                    'id': f'maintenance-{maintenance.id}',
                    'start': maintenance.start_date.isoformat(),
                    'end': maintenance.end_date.isoformat(),
                    'type': 'maintenance',
                    'maintenance_type': maintenance.maintenance_type,  # Added maintenance type
                    'project_id': project.id,
                    'project_name': project.name,
                    'client_name': project.client.name,
                    'client_address': client_address,
                    'maintenance_id': maintenance.id,
                    'is_overdue': maintenance.is_overdue,
                    'days_until_maintenance': maintenance.days_until_maintenance,
                })
    
    # Apply date range filters
    if start_date:
        try:
            start_date_obj = datetime.fromisoformat(start_date).date()
            events = [e for e in events if datetime.fromisoformat(e['start']).date() >= start_date_obj]
        except ValueError:
            pass
    
    if end_date:
        try:
            end_date_obj = datetime.fromisoformat(end_date).date()
            events = [e for e in events if datetime.fromisoformat(e['start']).date() <= end_date_obj]
        except ValueError:
            pass
    
    # Sort events by date
    events.sort(key=lambda x: x['start'])
    
    # Build filter summary
    applied_filters = {}
    if event_type != 'all':
        applied_filters['event_type'] = event_type
    if project_name:
        applied_filters['project_name'] = project_name
    if client_name:
        applied_filters['client_name'] = client_name
    if start_date:
        applied_filters['start_date'] = start_date
    if end_date:
        applied_filters['end_date'] = end_date
    if project_status:
        applied_filters['status'] = project_status
    if is_verified:
        applied_filters['is_verified'] = is_verified
    if is_overdue:
        applied_filters['is_overdue'] = is_overdue
    if province:
        applied_filters['province'] = province
    if city:
        applied_filters['city'] = city
    if postal_code:
        applied_filters['postal_code'] = postal_code
    
    return Response({
        'user_role': user.role,
        'user_name': user.get_full_name() or user.username,
        'total_events': len(events),
        'applied_filters': applied_filters,
        'events': events
    })