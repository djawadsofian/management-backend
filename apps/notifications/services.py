# apps/notifications/services.py
"""
Service layer for creating and managing notifications
"""
from django.db import transaction
from django.utils import timezone
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.signals import notification_created
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Centralized service for creating notifications
    """
    
    @staticmethod
    def _get_or_create_preferences(user):
        """Get or create notification preferences for user"""
        prefs, created = NotificationPreference.objects.get_or_create(user=user)
        return prefs
    
    @staticmethod
    def _should_send_notification(user, notification_type):
        """Check if notification should be sent based on user preferences"""
        prefs = NotificationService._get_or_create_preferences(user)
        
        # Check if notification type is enabled
        if not prefs.is_notification_enabled(notification_type):
            return False
        
        # Check quiet hours
        if prefs.is_in_quiet_hours():
            return False
        
        return True
    
    @staticmethod
    @transaction.atomic
    def create_notification(
        recipient,
        notification_type,
        title,
        message,
        priority=Notification.PRIORITY_MEDIUM,
        related_project=None,
        related_maintenance=None,
        related_product=None,
        data=None
    ):
        """
        Create a new notification
        
        Args:
            recipient: User to receive notification
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            priority: Priority level
            related_project: Related project (optional)
            related_maintenance: Related maintenance (optional)
            data: Additional JSON data (optional)
        
        Returns:
            Notification instance or None if not created
        """
        # Check if notification should be sent
        if not NotificationService._should_send_notification(recipient, notification_type):
            logger.info(f"Notification {notification_type} not sent to {recipient.username} (preferences)")
            return None
        
        try:
            notification = Notification.objects.create(
                recipient=recipient,
                notification_type=notification_type,
                title=title,
                message=message,
                priority=priority,
                related_project=related_project,
                related_maintenance=related_maintenance,
                related_product=related_product,
                data=data or {}
            )
            
            # Send signal for SSE
            notification_created.send(
                sender=Notification,
                notification=notification,
                recipient=recipient
            )
            
            logger.info(f"Notification created: {notification.id} for {recipient.username}")
            return notification
            
        except Exception as e:
            logger.error(f"Error creating notification: {e}")
            return None
    
    # ========== PROJECT NOTIFICATIONS ==========
    
    @staticmethod
    def notify_project_assigned(project, employers):
        """
        Notify employers when assigned to a project
        
        Args:
            project: Project instance
            employers: List of User instances
        """
        for employer in employers:
            NotificationService.create_notification(
                recipient=employer,
                notification_type=Notification.TYPE_PROJECT_ASSIGNED,
                title=f"Nouveau projet assigné: {project.name}",
                message=f"Vous avez été assigné au projet '{project.name}' pour le client {project.client.name}.",
                priority=Notification.PRIORITY_HIGH,
                related_project=project,
                data={
                    'project_id': project.id,
                    'project_name': project.name,
                    'client_name': project.client.name,
                    'start_date': project.start_date.isoformat(),
                    'end_date': project.end_date.isoformat() if project.end_date else None,
                }
            )
    
    @staticmethod
    def notify_project_starting_soon(project):
        """
        Notify assigned employers that project starts in 48h
        
        Args:
            project: Project instance
        """
        employers = project.assigned_employers.all()
        
        for employer in employers:
            NotificationService.create_notification(
                recipient=employer,
                notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
                title=f"Le projet '{project.name}' démarre dans 48h",
                message=f"Le projet '{project.name}' pour le client {project.client.name} commence le {project.start_date.strftime('%d/%m/%Y')}.",
                priority=Notification.PRIORITY_URGENT,
                related_project=project,
                data={
                    'project_id': project.id,
                    'project_name': project.name,
                    'client_name': project.client.name,
                    'start_date': project.start_date.isoformat(),
                    'hours_until_start': 48,
                }
            )
    
    @staticmethod
    def notify_project_modified(project, modified_by, changes=None):
        """
        Notify assigned employers when project is modified
        
        Args:
            project: Project instance
            modified_by: User who modified the project
            changes: Dict of changes (optional)
        """
        employers = project.assigned_employers.exclude(id=modified_by.id)
        
        for employer in employers:
            NotificationService.create_notification(
                recipient=employer,
                notification_type=Notification.TYPE_PROJECT_MODIFIED,
                title=f"Projet modifié: {project.name}",
                message=f"Le projet '{project.name}' a été modifié par {modified_by.get_full_name() or modified_by.username}.",
                priority=Notification.PRIORITY_MEDIUM,
                related_project=project,
                data={
                    'project_id': project.id,
                    'project_name': project.name,
                    'modified_by': modified_by.get_full_name() or modified_by.username,
                    'changes': changes or {},
                }
            )
    
    @staticmethod
    def notify_project_deleted(project_data, deleted_by):
        """
        Notify assigned employers when project is deleted
        
        Args:
            project_data: Dict with project info (project already deleted)
            deleted_by: User who deleted the project
        """
        employer_ids = project_data.get('assigned_employer_ids', [])
        
        from apps.users.models import CustomUser
        employers = CustomUser.objects.filter(id__in=employer_ids).exclude(id=deleted_by.id)
        
        for employer in employers:
            NotificationService.create_notification(
                recipient=employer,
                notification_type=Notification.TYPE_PROJECT_DELETED,
                title=f"Projet supprimé: {project_data['name']}",
                message=f"Le projet '{project_data['name']}' a été supprimé par {deleted_by.get_full_name() or deleted_by.username}.",
                priority=Notification.PRIORITY_HIGH,
                related_project=None,
                data=project_data
            )
    
    # ========== MAINTENANCE NOTIFICATIONS ==========
    
    @staticmethod
    def notify_maintenance_starting_soon(maintenance):
        """
        Notify assigned employers that maintenance starts in 48h
        
        Args:
            maintenance: Maintenance instance
        """
        employers = maintenance.project.assigned_employers.all()
        
        for employer in employers:
            NotificationService.create_notification(
                recipient=employer,
                notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON,
                title=f"Maintenance dans 48h: {maintenance.project.name}",
                message=f"La maintenance du projet '{maintenance.project.name}' est prévue le {maintenance.start_date.strftime('%d/%m/%Y')}.",
                priority=Notification.PRIORITY_URGENT,
                related_project=maintenance.project,
                related_maintenance=maintenance,
                data={
                    'maintenance_id': maintenance.id,
                    'project_id': maintenance.project.id,
                    'project_name': maintenance.project.name,
                    'start_date': maintenance.start_date.isoformat(),
                    'end_date': maintenance.end_date.isoformat(),
                    'maintenance_type': maintenance.maintenance_type,
                    'hours_until_start': 48,
                }
            )
    
    @staticmethod
    def notify_maintenance_added(maintenance, created_by):
        """
        Notify assigned employers when maintenance is added
        
        Args:
            maintenance: Maintenance instance
            created_by: User who created the maintenance
        """
        employers = maintenance.project.assigned_employers.exclude(id=created_by.id)
        
        for employer in employers:
            NotificationService.create_notification(
                recipient=employer,
                notification_type=Notification.TYPE_MAINTENANCE_ADDED,
                title=f"Nouvelle maintenance: {maintenance.project.name}",
                message=f"Une maintenance a été ajoutée au projet '{maintenance.project.name}' le {maintenance.start_date.strftime('%d/%m/%Y')}.",
                priority=Notification.PRIORITY_MEDIUM,
                related_project=maintenance.project,
                related_maintenance=maintenance,
                data={
                    'maintenance_id': maintenance.id,
                    'project_id': maintenance.project.id,
                    'project_name': maintenance.project.name,
                    'start_date': maintenance.start_date.isoformat(),
                    'end_date': maintenance.end_date.isoformat(),
                    'maintenance_type': maintenance.maintenance_type,
                    'created_by': created_by.get_full_name() or created_by.username,
                }
            )
    
    @staticmethod
    def notify_maintenance_modified(maintenance, modified_by, changes=None):
        """
        Notify assigned employers when maintenance is modified
        
        Args:
            maintenance: Maintenance instance
            modified_by: User who modified the maintenance
            changes: Dict of changes (optional)
        """
        employers = maintenance.project.assigned_employers.exclude(id=modified_by.id)
        
        for employer in employers:
            NotificationService.create_notification(
                recipient=employer,
                notification_type=Notification.TYPE_MAINTENANCE_MODIFIED,
                title=f"Maintenance modifiée: {maintenance.project.name}",
                message=f"La maintenance du projet '{maintenance.project.name}' a été modifiée par {modified_by.get_full_name() or modified_by.username}.",
                priority=Notification.PRIORITY_MEDIUM,
                related_project=maintenance.project,
                related_maintenance=maintenance,
                data={
                    'maintenance_id': maintenance.id,
                    'project_id': maintenance.project.id,
                    'project_name': maintenance.project.name,
                    'modified_by': modified_by.get_full_name() or modified_by.username,
                    'changes': changes or {},
                }
            )
    
    @staticmethod
    def notify_maintenance_deleted(maintenance_data, deleted_by):
        """
        Notify assigned employers when maintenance is deleted
        
        Args:
            maintenance_data: Dict with maintenance info
            deleted_by: User who deleted the maintenance
        """
        project_id = maintenance_data.get('project_id')
        
        from apps.projects.models import Project
        try:
            project = Project.objects.get(id=project_id)
            employers = project.assigned_employers.exclude(id=deleted_by.id)
            
            for employer in employers:
                NotificationService.create_notification(
                    recipient=employer,
                    notification_type=Notification.TYPE_MAINTENANCE_DELETED,
                    title=f"Maintenance supprimée: {maintenance_data['project_name']}",
                    message=f"Une maintenance du projet '{maintenance_data['project_name']}' a été supprimée par {deleted_by.get_full_name() or deleted_by.username}.",
                    priority=Notification.PRIORITY_MEDIUM,
                    related_project=project,
                    related_maintenance=None,
                    data=maintenance_data
                )
        except Project.DoesNotExist:
            pass
    
    # ========== UTILITY METHODS ==========
    
    @staticmethod
    def mark_all_as_read(user):
        """Mark all notifications as read for a user"""
        return Notification.objects.filter(
            recipient=user,
            is_read=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )
    
    @staticmethod
    def get_unread_count(user):
        """Get count of unread notifications for a user"""
        return Notification.objects.filter(
            recipient=user,
            is_read=False
        ).count()
    
    @staticmethod
    def delete_old_notifications(days=30):
        """Delete notifications older than specified days"""
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        return Notification.objects.filter(
            created_at__lt=cutoff_date
        ).delete()