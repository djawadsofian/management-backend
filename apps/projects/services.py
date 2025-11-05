# apps/projects/calendar_services.py
"""
Service layer for calendar operations.
Handles event generation and filtering logic.
"""
from django.utils import timezone
from datetime import timedelta

from apps.core import models
from .models import Project, Maintenance


class CalendarService:
    """
    Service for generating calendar events from projects and maintenances.
    """
    
    # Color scheme for different event types
    COLORS = {
        'project_start': '#4CAF50',      # Green
        'project_end': '#2196F3',        # Blue
        'project_active': '#FF9800',     # Orange
        'maintenance': '#9C27B0',        # Purple
        'warranty_start': '#00BCD4',     # Cyan
        'warranty_end': '#F44336',       # Red
    }
    
    @staticmethod
    def generate_project_events(project, include_warranty=True):
        """
        Generate all calendar events for a single project.
        
        Args:
            project: Project instance
            include_warranty: Whether to include warranty events
        
        Returns:
            List of event dictionaries
        """
        events = []
        today = timezone.now().date()
        
        # Project start event
        events.append({
            'id': f'project-start-{project.id}',
            'title': f'🚀 Start: {project.name}',
            'start': project.start_date,
            'end': project.start_date,
            'type': 'project_start',
            'color': CalendarService.COLORS['project_start'],
            'description': f'Project start date for {project.client.name}',
            'project_id': project.id,
            'client_id': project.client.id,
            'client_name': project.client.name,
            'all_day': True,
            'editable': False,
            'is_upcoming': project.start_date > today,
            'days_difference': (project.start_date - today).days,
            'is_verified': project.is_verified,
        })
        
        # Project end event (if end date exists)
        if project.end_date:
            events.append({
                'id': f'project-end-{project.id}',
                'title': f'🏁 End: {project.name}',
                'start': project.end_date,
                'end': project.end_date,
                'type': 'project_end',
                'color': CalendarService.COLORS['project_end'],
                'description': f'Project end date for {project.client.name}',
                'project_id': project.id,
                'client_id': project.client.id,
                'client_name': project.client.name,
                'all_day': True,
                'editable': False,
                'is_upcoming': project.end_date > today,
                'days_difference': (project.end_date - today).days,
                'is_verified': project.is_verified,
            })
        
        # Active project span (shows as a continuous event)
        if project.is_active:
            events.append({
                'id': f'project-active-{project.id}',
                'title': f'📊 Active: {project.name}',
                'start': max(project.start_date, today),
                'end': project.end_date or (today + timedelta(days=365)),
                'type': 'project_active',
                'color': CalendarService.COLORS['project_active'],
                'description': f'Active project period for {project.client.name}',
                'project_id': project.id,
                'client_id': project.client.id,
                'client_name': project.client.name,
                'all_day': True,
                'editable': False,
                'is_upcoming': False,
                'days_difference': 0,
                'is_verified': project.is_verified,
            })
        
        # Warranty events
        if include_warranty and project.warranty_end_date:
            # Warranty start (same as project start)
            events.append({
                'id': f'warranty-start-{project.id}',
                'title': f'🛡️ Warranty Start: {project.name}',
                'start': project.start_date,
                'end': project.start_date,
                'type': 'warranty_start',
                'color': CalendarService.COLORS['warranty_start'],
                'description': f'Warranty begins for {project.client.name} ({project.warranty_display})',
                'project_id': project.id,
                'client_id': project.client.id,
                'client_name': project.client.name,
                'all_day': True,
                'editable': False,
                'is_upcoming': project.start_date > today,
                'days_difference': (project.start_date - today).days,
                'is_verified': project.is_verified,
            })
            
            # Warranty end
            events.append({
                'id': f'warranty-end-{project.id}',
                'title': f'⚠️ Warranty End: {project.name}',
                'start': project.warranty_end_date,
                'end': project.warranty_end_date,
                'type': 'warranty_end',
                'color': CalendarService.COLORS['warranty_end'],
                'description': f'Warranty expires for {project.client.name} ({project.warranty_display})',
                'project_id': project.id,
                'client_id': project.client.id,
                'client_name': project.client.name,
                'all_day': True,
                'editable': False,
                'is_upcoming': project.warranty_end_date > today,
                'is_overdue': project.warranty_end_date < today,
                'days_difference': (project.warranty_end_date - today).days,
                'is_verified': project.is_verified,
            })
        
        return events
    
    @staticmethod
    def generate_maintenance_event(maintenance):
        """
        Generate calendar event for a maintenance.
        
        Args:
            maintenance: Maintenance instance
        
        Returns:
            Event dictionary or None if no next_maintenance_date
        """
        if not maintenance.next_maintenance_date:
            return None
        
        today = timezone.now().date()
        days_diff = maintenance.days_until_maintenance or 0
        
        return {
            'id': f'maintenance-{maintenance.id}',
            'title': f'🔧 Maintenance: {maintenance.project.name}',
            'start': maintenance.next_maintenance_date,
            'end': maintenance.next_maintenance_date,
            'type': 'maintenance',
            'color': CalendarService.COLORS['maintenance'],
            'description': f'Scheduled maintenance for {maintenance.project.client.name} (Every {maintenance.interval} months)',
            'project_id': maintenance.project.id,
            'client_id': maintenance.project.client.id,
            'client_name': maintenance.project.client.name,
            'maintenance_id': maintenance.id,
            'all_day': True,
            'editable': False,
            'is_overdue': maintenance.is_overdue,
            'is_upcoming': maintenance.next_maintenance_date > today and days_diff <= 30,
            'days_difference': days_diff,
            'is_verified': maintenance.project.is_verified,
        }
    
    @staticmethod
    def get_employer_calendar(user, start_date=None, end_date=None):
        """
        Get calendar events for an employer (only assigned projects).
        
        Args:
            user: CustomUser instance (employer)
            start_date: Optional start date filter
            end_date: Optional end date filter
        
        Returns:
            List of calendar events
        """
        events = []
        
        # Get projects assigned to this employer
        projects = Project.objects.filter(
            assigned_employers=user,
            is_verified=True
        ).select_related('client').prefetch_related('maintenances')
        
        # Apply date filters if provided
        if start_date and end_date:
            projects = projects.filter(
                start_date__lte=end_date
            ).filter(
                models.Q(end_date__gte=start_date) | models.Q(end_date__isnull=True)
            )
        
        # Generate events for each project
        for project in projects:
            # Add project events (without warranty for employers)
            project_events = CalendarService.generate_project_events(
                project, 
                include_warranty=False
            )
            events.extend(project_events)
            
            # Add maintenance events
            for maintenance in project.maintenances.all():
                if maintenance.next_maintenance_date:
                    # Filter by date range if provided
                    if start_date and end_date:
                        if start_date <= maintenance.next_maintenance_date <= end_date:
                            event = CalendarService.generate_maintenance_event(maintenance)
                            if event:
                                events.append(event)
                    else:
                        event = CalendarService.generate_maintenance_event(maintenance)
                        if event:
                            events.append(event)
        
        return events
    
    @staticmethod
    def get_admin_calendar(start_date=None, end_date=None):
        """
        Get calendar events for admin (all projects and maintenances).
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
        
        Returns:
            List of calendar events
        """
        from django.db import models
        
        events = []
        
        # Get all verified projects
        projects = Project.objects.filter(
            is_verified=True
        ).select_related('client').prefetch_related('maintenances')
        
        # Apply date filters if provided
        if start_date and end_date:
            projects = projects.filter(
                start_date__lte=end_date
            ).filter(
                models.Q(end_date__gte=start_date) | models.Q(end_date__isnull=True)
            )
        
        # Generate events for each project
        for project in projects:
            # Add project events (including warranty for admins)
            project_events = CalendarService.generate_project_events(
                project,
                include_warranty=True
            )
            events.extend(project_events)
            
            # Add maintenance events
            for maintenance in project.maintenances.all():
                if maintenance.next_maintenance_date:
                    # Filter by date range if provided
                    if start_date and end_date:
                        if start_date <= maintenance.next_maintenance_date <= end_date:
                            event = CalendarService.generate_maintenance_event(maintenance)
                            if event:
                                events.append(event)
                    else:
                        event = CalendarService.generate_maintenance_event(maintenance)
                        if event:
                            events.append(event)
        
        return events
    
    @staticmethod
    def get_upcoming_events(events, days=30):
        """
        Filter events to only upcoming ones within specified days.
        
        Args:
            events: List of event dictionaries
            days: Number of days to look ahead
        
        Returns:
            Filtered list of upcoming events
        """
        today = timezone.now().date()
        cutoff_date = today + timedelta(days=days)
        
        upcoming = []
        for event in events:
            event_date = event.get('start')
            if event_date and today <= event_date <= cutoff_date:
                upcoming.append(event)
        
        return sorted(upcoming, key=lambda x: x['start'])
    
    @staticmethod
    def get_overdue_events(events):
        """
        Filter events to only overdue ones.
        
        Args:
            events: List of event dictionaries
        
        Returns:
            Filtered list of overdue events
        """
        return [e for e in events if e.get('is_overdue', False)]
    

    # Ajouter ces méthodes dans la classe CalendarService dans services.py

@staticmethod
def filter_events_by_client(events, client_id):
    """Filter events by client ID"""
    return [e for e in events if e.get('client_id') == client_id]

@staticmethod
def filter_events_by_project(events, project_id):
    """Filter events by project ID"""
    return [e for e in events if e.get('project_id') == project_id]

@staticmethod
def filter_events_by_type(events, event_types):
    """Filter events by type(s)"""
    if isinstance(event_types, str):
        event_types = [t.strip() for t in event_types.split(',')]
    return [e for e in events if e.get('type') in event_types]

@staticmethod
def filter_events_by_status(events, status_filter):
    """Filter events by status (upcoming, overdue, active)"""
    today = timezone.now().date()
    
    if status_filter == 'upcoming':
        return [e for e in events if e.get('start') > today and not e.get('is_overdue', False)]
    elif status_filter == 'overdue':
        return [e for e in events if e.get('is_overdue', False)]
    elif status_filter == 'today':
        return [e for e in events if e.get('start') == today]
    elif status_filter == 'active':
        return [e for e in events if e.get('type') == 'project_active']
    return events

@staticmethod
def filter_events_by_date_range(events, start_date, end_date):
    """Filter events by date range"""
    filtered = []
    for event in events:
        event_date = event.get('start')
        if event_date:
            if start_date and end_date:
                if start_date <= event_date <= end_date:
                    filtered.append(event)
            elif start_date and event_date >= start_date:
                filtered.append(event)
            elif end_date and event_date <= end_date:
                filtered.append(event)
            else:
                filtered.append(event)
    return filtered