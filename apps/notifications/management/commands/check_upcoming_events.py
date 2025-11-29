# apps/notifications/management/commands/check_upcoming_events.py
"""
Django management command to check for upcoming projects and maintenances
Run this command via cron job every 2 hours for 24h/48h notifications
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.projects.models import Project, Maintenance
from apps.users.models import CustomUser
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check for events starting in 24h/48h and send notifications to appropriate users'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate without sending notifications'
        )
    
    def handle(self, *args, **options):
        now = timezone.now()
        dry_run = options.get('dry_run', False)
        
        self.stdout.write(self.style.HTTP_INFO(
            f"🔍 Checking for events starting in 24h/48h at {now.strftime('%Y-%m-%d %H:%M:%S')}"
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING("🚧 DRY RUN MODE - No notifications will be sent"))
        
        # ========== CLEANUP PHASE ==========
        self._cleanup_old_notifications()
        self._cleanup_started_events()
        
        # ========== NOTIFICATION PHASE ==========
        total_count = 0
        
        # Check upcoming projects and maintenances
        projects_count = self._check_upcoming_projects(dry_run)
        total_count += projects_count
        
        maintenances_count = self._check_upcoming_maintenances(dry_run)
        total_count += maintenances_count
        
        if total_count > 0:
            self.stdout.write(self.style.SUCCESS(
                f"✅ Created {total_count} upcoming event notifications!"
            ))
        else:
            self.stdout.write("⏭️  No upcoming events to notify")
    
    def _cleanup_old_notifications(self):
        """Remove notifications older than 7 days"""
        cutoff_date = timezone.now() - timedelta(days=7)
        deleted_count, _ = Notification.objects.filter(
            created_at__lt=cutoff_date
        ).delete()
        
        if deleted_count > 0:
            self.stdout.write(f"🧹 Cleaned up {deleted_count} notifications older than 7 days")
    
    def _cleanup_started_events(self):
        """Remove notifications for events that have already started"""
        today = timezone.now().date()
        
        # Remove notifications for projects that have started
        started_projects = Project.objects.filter(start_date__lt=today)
        project_notifications_deleted, _ = Notification.objects.filter(
            related_project__in=started_projects,
            notification_type=Notification.TYPE_PROJECT_STARTING_SOON
        ).delete()
        
        # Remove notifications for maintenances that have started
        started_maintenances = Maintenance.objects.filter(start_date__lt=today)
        maintenance_notifications_deleted, _ = Notification.objects.filter(
            related_maintenance__in=started_maintenances,
            notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON
        ).delete()
        
        total_deleted = project_notifications_deleted + maintenance_notifications_deleted
        if total_deleted > 0:
            self.stdout.write(f"🧹 Cleaned up {total_deleted} notifications for started events ({project_notifications_deleted} projects, {maintenance_notifications_deleted} maintenances)")

    # ... rest of the _check_upcoming_projects and _check_upcoming_maintenances methods remain the same ...
    def _check_upcoming_projects(self, dry_run=False):
        """Check for projects starting in 24h and 48h"""
        now = timezone.now().date()
        tomorrow = now + timedelta(days=1)  # 24h from now
        day_after_tomorrow = now + timedelta(days=2)  # 48h from now
        
        # Get projects starting tomorrow or day after tomorrow
        upcoming_projects = Project.objects.filter(
            start_date__in=[tomorrow, day_after_tomorrow],
            is_verified=True
        ).select_related('client').prefetch_related('assigned_employers')
        
        count = 0
        
        for project in upcoming_projects:
            days_until_start = (project.start_date - now).days
            
            if days_until_start == 1:  # 24h from now
                # Remove any existing 48h notifications for this project
                self._remove_48h_project_notifications(project)
                
                # Send to admins, assistants AND assigned employers
                recipients = CustomUser.objects.filter(
                    role__in=[CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT],
                    is_active=True
                ).union(
                    project.assigned_employers.all()
                ).distinct()
                
                for user in recipients:
                    # Check if 24h notification already exists for this project and user
                    existing_notification = Notification.objects.filter(
                        recipient=user,
                        notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
                        related_project=project,
                        data__notification_tier='admin_assistant_employer_24h'
                    ).exists()
                    
                    if not existing_notification:
                        if not dry_run:
                            notification = NotificationService.create_notification(
                                recipient=user,
                                notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
                                title=f"🚀 Projet Demain: {project.name}",
                                message=f"Le projet '{project.name}' commence DEMAIN pour le client {project.client.name}. Préparez-vous!",
                                priority=Notification.PRIORITY_HIGH,
                                related_project=project,
                                data={
                                    'project_id': project.id,
                                    'project_name': project.name,
                                    'client_name': project.client.name,
                                    'start_date': project.start_date.isoformat(),
                                    'hours_until_start': 24,
                                    'notification_tier': 'admin_assistant_employer_24h',
                                    'event_type': 'project_24h'
                                }
                            )
                            if notification:
                                count += 1
                                user_type = "Admin/Assistant" if user.role in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT] else "Employer"
                                self.stdout.write(
                                    f"   ✅ 24h Project Alert ({user_type}): {project.name} → {user.username}"
                                )
                        else:
                            count += 1
                            user_type = "Admin/Assistant" if user.role in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT] else "Employer"
                            self.stdout.write(
                                f"   🔸 24h Project Alert ({user_type}): {project.name} → {user.username} [DRY RUN]"
                            )
            
            elif days_until_start == 2:  # 48h from now
                # Send to assigned employers only
                for employer in project.assigned_employers.all():
                    # Check if 48h notification already exists for this project and user
                    existing_notification = Notification.objects.filter(
                        recipient=employer,
                        notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
                        related_project=project,
                        data__notification_tier='employer_48h'
                    ).exists()
                    
                    if not existing_notification:
                        if not dry_run:
                            notification = NotificationService.create_notification(
                                recipient=employer,
                                notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
                                title=f"📅 Projet dans 2 Jours: {project.name}",
                                message=f"Le projet '{project.name}' commence dans 2 jours. Date: {project.start_date.strftime('%d/%m/%Y')}",
                                priority=Notification.PRIORITY_MEDIUM,
                                related_project=project,
                                data={
                                    'project_id': project.id,
                                    'project_name': project.name,
                                    'client_name': project.client.name,
                                    'start_date': project.start_date.isoformat(),
                                    'hours_until_start': 48,
                                    'notification_tier': 'employer_48h',
                                    'event_type': 'project_48h'
                                }
                            )
                            if notification:
                                count += 1
                                self.stdout.write(
                                    f"   ✅ 48h Project Alert (Employer): {project.name} → {employer.username}"
                                )
                        else:
                            count += 1
                            self.stdout.write(
                                f"   🔸 48h Project Alert (Employer): {project.name} → {employer.username} [DRY RUN]"
                            )
        
        return count
    
    def _check_upcoming_maintenances(self, dry_run=False):
        """Check for maintenances starting in 24h and 48h"""
        now = timezone.now().date()
        tomorrow = now + timedelta(days=1)  # 24h from now
        day_after_tomorrow = now + timedelta(days=2)  # 48h from now
        
        # Get maintenances starting tomorrow or day after tomorrow
        upcoming_maintenances = Maintenance.objects.filter(
            start_date__in=[tomorrow, day_after_tomorrow]
        ).select_related('project', 'project__client').prefetch_related('project__assigned_employers')
        
        count = 0
        
        for maintenance in upcoming_maintenances:
            days_until_start = (maintenance.start_date - now).days
            
            if days_until_start == 1:  # 24h from now
                # Remove any existing 48h notifications for this maintenance
                self._remove_48h_maintenance_notifications(maintenance)
                
                # Send to admins, assistants AND assigned employers
                recipients = CustomUser.objects.filter(
                    role__in=[CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT],
                    is_active=True
                ).union(
                    maintenance.project.assigned_employers.all()
                ).distinct()
                
                for user in recipients:
                    # Check if 24h notification already exists for this maintenance and user
                    existing_notification = Notification.objects.filter(
                        recipient=user,
                        notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON,
                        related_maintenance=maintenance,
                        data__notification_tier='admin_assistant_employer_24h'
                    ).exists()
                    
                    if not existing_notification:
                        if not dry_run:
                            notification = NotificationService.create_notification(
                                recipient=user,
                                notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON,
                                title=f"🔧 Maintenance Demain: {maintenance.project.name}",
                                message=f"Maintenance prévue DEMAIN pour le projet '{maintenance.project.name}'.",
                                priority=Notification.PRIORITY_HIGH,
                                related_project=maintenance.project,
                                related_maintenance=maintenance,
                                data={
                                    'maintenance_id': maintenance.id,
                                    'project_id': maintenance.project.id,
                                    'project_name': maintenance.project.name,
                                    'start_date': maintenance.start_date.isoformat(),
                                    'hours_until_start': 24,
                                    'maintenance_type': maintenance.maintenance_type,
                                    'notification_tier': 'admin_assistant_employer_24h',
                                    'event_type': 'maintenance_24h'
                                }
                            )
                            if notification:
                                count += 1
                                user_type = "Admin/Assistant" if user.role in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT] else "Employer"
                                self.stdout.write(
                                    f"   ✅ 24h Maintenance Alert ({user_type}): {maintenance.project.name} → {user.username}"
                                )
                        else:
                            count += 1
                            user_type = "Admin/Assistant" if user.role in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT] else "Employer"
                            self.stdout.write(
                                f"   🔸 24h Maintenance Alert ({user_type}): {maintenance.project.name} → {user.username} [DRY RUN]"
                            )
            
            elif days_until_start == 2:  # 48h from now
                # Send to assigned employers only
                for employer in maintenance.project.assigned_employers.all():
                    # Check if 48h notification already exists for this maintenance and user
                    existing_notification = Notification.objects.filter(
                        recipient=employer,
                        notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON,
                        related_maintenance=maintenance,
                        data__notification_tier='employer_48h'
                    ).exists()
                    
                    if not existing_notification:
                        if not dry_run:
                            notification = NotificationService.create_notification(
                                recipient=employer,
                                notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON,
                                title=f"📋 Maintenance dans 2 Jours: {maintenance.project.name}",
                                message=f"Maintenance prévue dans 2 jours pour le projet '{maintenance.project.name}'.",
                                priority=Notification.PRIORITY_MEDIUM,
                                related_project=maintenance.project,
                                related_maintenance=maintenance,
                                data={
                                    'maintenance_id': maintenance.id,
                                    'project_id': maintenance.project.id,
                                    'project_name': maintenance.project.name,
                                    'start_date': maintenance.start_date.isoformat(),
                                    'hours_until_start': 48,
                                    'maintenance_type': maintenance.maintenance_type,
                                    'notification_tier': 'employer_48h',
                                    'event_type': 'maintenance_48h'
                                }
                            )
                            if notification:
                                count += 1
                                self.stdout.write(
                                    f"   ✅ 48h Maintenance Alert (Employer): {maintenance.project.name} → {employer.username}"
                                )
                        else:
                            count += 1
                            self.stdout.write(
                                f"   🔸 48h Maintenance Alert (Employer): {maintenance.project.name} → {employer.username} [DRY RUN]"
                            )
        
        return count
    
    def _remove_48h_project_notifications(self, project):
        """Remove 48h notifications when 24h notifications are being sent"""
        deleted_count, _ = Notification.objects.filter(
            related_project=project,
            notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
            data__notification_tier='employer_48h'
        ).delete()
        
        if deleted_count > 0:
            self.stdout.write(f"   🧹 Removed {deleted_count} 48h project notifications for: {project.name}")
    
    def _remove_48h_maintenance_notifications(self, maintenance):
        """Remove 48h notifications when 24h notifications are being sent"""
        deleted_count, _ = Notification.objects.filter(
            related_maintenance=maintenance,
            notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON,
            data__notification_tier='employer_48h'
        ).delete()
        
        if deleted_count > 0:
            self.stdout.write(f"   🧹 Removed {deleted_count} 48h maintenance notifications for: {maintenance.project.name}")