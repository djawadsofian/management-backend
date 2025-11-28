# apps/notifications/management/commands/check_upcoming_events.py
"""
Django management command to check for upcoming projects and maintenances
Run this command via cron job every 30 seconds:
* * * * * cd /path/to/project && python manage.py check_upcoming_events
* * * * * sleep 30; cd /path/to/project && python manage.py check_upcoming_events
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.projects.models import Project, Maintenance
from apps.notifications.services import NotificationService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check for events starting soon and send immediate notifications'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--check-window',
            type=int,
            default=2,
            help='Check window in hours (default: 2)'
        )
    
    def handle(self, *args, **options):
        now = timezone.now()
        check_window = options['check_window']
        target_time = now + timedelta(hours=check_window)
        
        self.stdout.write(self.style.HTTP_INFO(
            f"🔍 Checking for events starting within {check_window}h (until {target_time})"
        ))
        
        total_count = 0
        
        # ========== CHECK PROJECTS STARTING SOON ==========
        projects_count = self._check_projects_starting_soon(check_window)
        total_count += projects_count
        
        # ========== CHECK MAINTENANCES STARTING SOON ==========
        maintenances_count = self._check_maintenances_starting_soon(check_window)
        total_count += maintenances_count
        
        # ========== CLEANUP OLD NOTIFICATIONS ==========
        deleted_count = NotificationService.delete_old_notifications(days=7)  # Clean older ones
        
        if total_count > 0:
            self.stdout.write(self.style.SUCCESS(
                f"✅ Sent {total_count} immediate event notifications!"
            ))
        else:
            self.stdout.write("⏭️  No upcoming events to notify")
        
        self.stdout.write(f"🧹 Cleaned {deleted_count[0] if deleted_count else 0} old notifications")
    
    def _check_projects_starting_soon(self, check_window):
        """Check for projects starting within the check window"""
        now = timezone.now()
        window_end = now + timedelta(hours=check_window)
        
        projects_to_notify = Project.objects.filter(
            start_date__gte=now.date(),
            start_date__lte=window_end.date(),
            is_verified=True
        ).select_related('client').prefetch_related('assigned_employers')
        
        count = 0
        for project in projects_to_notify:
            # Calculate exact hours until start
            start_datetime = timezone.make_aware(
                timezone.datetime.combine(project.start_date, timezone.datetime.min.time())
            )
            hours_until = int((start_datetime - now).total_seconds() / 3600)
            
            # Only notify if within the check window
            if 0 <= hours_until <= check_window:
                # Check if we already notified recently (last 15 minutes)
                from apps.notifications.models import Notification
                recent_threshold = timezone.now() - timedelta(minutes=15)
                
                existing_notification = Notification.objects.filter(
                    related_project=project,
                    notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
                    created_at__gte=recent_threshold,
                ).exists()
                
                if not existing_notification:
                    NotificationService.notify_project_starting_soon(project)
                    count += 1
                    self.stdout.write(
                        f"   ✅ Project: {project.name} (starts in {hours_until}h)"
                    )
        
        return count
    
    def _check_maintenances_starting_soon(self, check_window):
        """Check for maintenances starting within the check window"""
        now = timezone.now()
        window_end = now + timedelta(hours=check_window)
        
        maintenances_to_notify = Maintenance.objects.filter(
            start_date__gte=now.date(),
            start_date__lte=window_end.date()
        ).select_related('project', 'project__client').prefetch_related('project__assigned_employers')
        
        count = 0
        for maintenance in maintenances_to_notify:
            # Calculate exact hours until start
            start_datetime = timezone.make_aware(
                timezone.datetime.combine(maintenance.start_date, timezone.datetime.min.time())
            )
            hours_until = int((start_datetime - now).total_seconds() / 3600)
            
            # Only notify if within the check window
            if 0 <= hours_until <= check_window:
                from apps.notifications.models import Notification
                recent_threshold = timezone.now() - timedelta(minutes=15)
                
                existing_notification = Notification.objects.filter(
                    related_maintenance=maintenance,
                    notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON,
                    created_at__gte=recent_threshold,
                ).exists()
                
                if not existing_notification:
                    NotificationService.notify_maintenance_starting_soon(maintenance)
                    count += 1
                    self.stdout.write(
                        f"   ✅ Maintenance: {maintenance.project.name} (starts in {hours_until}h)"
                    )
        
        return count