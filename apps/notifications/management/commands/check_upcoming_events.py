# apps/notifications/management/commands/check_upcoming_events.py
"""
Django management command to check for upcoming projects and maintenances
Run this command via cron job every hour:
0 * * * * cd /path/to/project && python manage.py check_upcoming_events
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.projects.models import Project, Maintenance
from apps.notifications.services import NotificationService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check for projects and maintenances starting in 48 hours and send notifications'
    
    def handle(self, *args, **options):
        now = timezone.now()
        target_time = now + timedelta(hours=48)
        
        # Define time window (47-49 hours from now to avoid duplicates)
        window_start = now + timedelta(hours=47)
        window_end = now + timedelta(hours=49)
        
        self.stdout.write(self.style.HTTP_INFO(
            f"🔍 Checking for events starting between {window_start} and {window_end}"
        ))
        
        # ========== CHECK PROJECTS ==========
        projects_to_notify = Project.objects.filter(
            start_date__gte=window_start.date(),
            start_date__lte=window_end.date(),
            is_verified=True
        ).select_related('client').prefetch_related('assigned_employers')
        
        project_count = 0
        for project in projects_to_notify:
            # Check if we've already sent notification for this project
            from apps.notifications.models import Notification
            
            existing_notification = Notification.objects.filter(
                related_project=project,
                notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
                created_at__gte=now - timedelta(hours=49),  # Check last 49 hours
            ).exists()
            
            if not existing_notification:
                NotificationService.notify_project_starting_soon(project)
                project_count += 1
                self.stdout.write(
                    f"   ✅ Notified for project: {project.name} (starts {project.start_date})"
                )
        
        # ========== CHECK MAINTENANCES ==========
        maintenances_to_notify = Maintenance.objects.filter(
            start_date__gte=window_start.date(),
            start_date__lte=window_end.date()
        ).select_related('project', 'project__client').prefetch_related('project__assigned_employers')
        
        maintenance_count = 0
        for maintenance in maintenances_to_notify:
            # Check if we've already sent notification for this maintenance
            from apps.notifications.models import Notification
            
            existing_notification = Notification.objects.filter(
                related_maintenance=maintenance,
                notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON,
                created_at__gte=now - timedelta(hours=49),
            ).exists()
            
            if not existing_notification:
                NotificationService.notify_maintenance_starting_soon(maintenance)
                maintenance_count += 1
                self.stdout.write(
                    f"   ✅ Notified for maintenance: {maintenance.project.name} (starts {maintenance.start_date})"
                )
        
        # ========== CLEANUP OLD NOTIFICATIONS ==========
        # Delete notifications older than 30 days
        deleted_count = NotificationService.delete_old_notifications(days=30)
        
        self.stdout.write(self.style.SUCCESS(
            f"\n📊 Summary:\n"
            f"   • Projects notified: {project_count}\n"
            f"   • Maintenances notified: {maintenance_count}\n"
            f"   • Old notifications cleaned: {deleted_count[0] if deleted_count else 0}\n"
        ))