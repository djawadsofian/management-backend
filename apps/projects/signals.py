# apps/projects/signals.py
"""
FIXED Signal handlers for Project and Maintenance models
Key fixes:
1. Set _modified_by BEFORE save() so pre_save can access it
2. Properly track changes in pre_save
3. Send notifications in post_save after changes are confirmed
"""
from django.db.models.signals import post_save, pre_delete, pre_save, m2m_changed
from django.dispatch import receiver
from django.utils import timezone
from apps.projects.models import Project, Maintenance
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification
from apps.core.middleware import get_current_user
import logging

logger = logging.getLogger(__name__)


# ========== PROJECT SIGNALS ==========

@receiver(pre_save, sender=Project)
def track_project_changes(sender, instance, **kwargs):
    """
    Track previous project state before save for immediate notifications
    """
    # Get current user if not already set
    if not hasattr(instance, '_modified_by'):
        instance._modified_by = get_current_user()
    
    if instance.pk:
        try:
            previous = Project.objects.get(pk=instance.pk)
            instance._previous_is_verified = previous.is_verified
            instance._previous_start_date = previous.start_date
            instance._previous_end_date = previous.end_date
            instance._previous_name = previous.name
            instance._previous_description = previous.description
            instance._has_changes = True
        except Project.DoesNotExist:
            instance._has_changes = False
    else:
        instance._previous_is_verified = False
        instance._has_changes = False


@receiver(post_save, sender=Project)
def project_immediate_notifications(sender, instance, created, **kwargs):
    """
    Send immediate notifications for project changes
    """
    print(f"🔄 Project signal triggered - Created: {created}, Verified: {instance.is_verified}")

    if created:
        # New project created - no notifications until verified
        return

    if not hasattr(instance, '_has_changes') or not instance._has_changes:
        return

    # Get the user who made the change
    modified_by = getattr(instance, '_modified_by', None)
    
    if not modified_by:
        print("⚠️ No modified_by user found, skipping notifications")
        return

    # Existing project modified
    previous_verified = getattr(instance, '_previous_is_verified', False)
    current_verified = instance.is_verified
    
    # Project just got verified - send PROJECT_ASSIGNED to assigned employers
    if not previous_verified and current_verified:
        print(f"✅ Project verified: {instance.name}")
        _notify_project_verified_as_assigned(instance)
    
    # Project just got UNverified - remove ALL notifications for this project
    elif previous_verified and not current_verified:
        print(f"❌ Project unverified: {instance.name}")
        _remove_all_project_notifications(instance)
    
    # Project modified (dates changed, name, description, etc.) - notify assigned employers
    elif current_verified and (
        getattr(instance, '_previous_start_date', None) != instance.start_date or
        getattr(instance, '_previous_end_date', None) != instance.end_date or
        getattr(instance, '_previous_name', None) != instance.name or
        getattr(instance, '_previous_description', None) != instance.description
    ):
        print(f"✏️ Project modified: {instance.name} by {modified_by.username}")
        _notify_project_modified_immediate(instance, modified_by)


@receiver(m2m_changed, sender=Project.assigned_employers.through)
def project_employers_changed_immediate(sender, instance, action, pk_set, **kwargs):
    """
    Handle employer assignment/unassignment to/from a verified project
    """
    if not instance.is_verified:
        return  # Only notify for verified projects
    
    if action == "post_add" and pk_set:
        # New employers added to the project
        from apps.users.models import CustomUser
        new_employers = CustomUser.objects.filter(pk__in=pk_set)
        
        # Send PROJECT_ASSIGNED notifications to newly assigned employers
        for employer in new_employers:
            NotificationService.create_notification(
                recipient=employer,
                notification_type=Notification.TYPE_PROJECT_ASSIGNED,
                title=f"🎯 Nouveau Projet Assigné: {instance.name}",
                message=f"Vous avez été assigné au projet '{instance.name}' pour le client {instance.client.name}. Date de début: {instance.start_date.strftime('%d/%m/%Y')}",
                priority=Notification.PRIORITY_HIGH,
                related_project=instance,
                data={
                    'project_id': instance.id,
                    'project_name': instance.name,
                    'client_name': instance.client.name,
                    'start_date': instance.start_date.isoformat(),
                    'end_date': instance.end_date.isoformat() if instance.end_date else None,
                    'assigned_at': timezone.now().isoformat(),
                    'trigger': 'employer_added'
                }
            )
            logger.info(f"Assignment notification sent for project {instance.name} to {employer.username}")
            print(f"📤 Sent PROJECT_ASSIGNED to {employer.username} for project {instance.name}")
    
    elif action == "post_remove" and pk_set:
        # Employers removed from the project
        from apps.users.models import CustomUser
        removed_employers = CustomUser.objects.filter(pk__in=pk_set)
        
        for employer in removed_employers:
            # Send unassignment notification
            NotificationService.create_notification(
                recipient=employer,
                notification_type=Notification.TYPE_PROJECT_MODIFIED,
                title=f"⚠️ Projet Retiré: {instance.name}",
                message=f"Vous n'êtes plus assigné au projet '{instance.name}' pour le client {instance.client.name}.",
                priority=Notification.PRIORITY_MEDIUM,
                related_project=instance,
                data={
                    'project_id': instance.id,
                    'project_name': instance.name,
                    'client_name': instance.client.name,
                    'unassigned_at': timezone.now().isoformat(),
                    'trigger': 'employer_removed'
                }
            )
            logger.info(f"Unassignment notification sent for project {instance.name} to {employer.username}")
            print(f"📤 Sent unassignment notification to {employer.username} for project {instance.name}")
            
            # Remove ALL notifications of this project for the removed employer
            _remove_project_notifications_for_employer(instance, employer)


@receiver(pre_delete, sender=Project)
def project_deleted_immediate(sender, instance, **kwargs):
    """
    Immediate notification when project is deleted
    """
    print(f"🗑️ Project deleted: {instance.name}")
    
    # Get the user who deleted it
    deleted_by = getattr(instance, '_deleted_by', None)
    
    if deleted_by:
        # Send deletion notifications to assigned employers
        _notify_project_deletion_to_employers(instance, deleted_by)


# ========== MAINTENANCE SIGNALS ==========

@receiver(pre_save, sender=Maintenance)
def track_maintenance_changes(sender, instance, **kwargs):
    """Track previous maintenance state for modification detection"""
    # Get current user if not already set
    if not hasattr(instance, '_modified_by') and not hasattr(instance, '_created_by'):
        current_user = get_current_user()
        if instance.pk:
            instance._modified_by = current_user
        else:
            instance._created_by = current_user
    
    if instance.pk:
        try:
            previous = Maintenance.objects.get(pk=instance.pk)
            instance._previous_start_date = previous.start_date
            instance._previous_end_date = previous.end_date
            instance._has_changes = True
        except Maintenance.DoesNotExist:
            instance._has_changes = False
    else:
        instance._has_changes = False


@receiver(post_save, sender=Maintenance)
def maintenance_immediate_notifications(sender, instance, created, **kwargs):
    """
    Immediate notifications for maintenance changes
    """
    # Only notify for MANUAL maintenances immediately
    if instance.maintenance_type != Maintenance.TYPE_MANUAL:
        return
    
    if created:
        # New manual maintenance added - immediate notification
        created_by = getattr(instance, '_created_by', None)
        if created_by:
            print(f"🛠️ New maintenance created by {created_by.username}")
            _notify_maintenance_added_immediate(instance, created_by)
        else:
            print("⚠️ No created_by user found for maintenance")
    else:
        # Maintenance modified - check if dates actually changed
        if (hasattr(instance, '_has_changes') and instance._has_changes and
            (getattr(instance, '_previous_start_date', None) != instance.start_date or
             getattr(instance, '_previous_end_date', None) != instance.end_date)):
            
            modified_by = getattr(instance, '_modified_by', None)
            if modified_by:
                print(f"✏️ Maintenance modified by {modified_by.username}")
                _notify_maintenance_modified_immediate(instance, modified_by)
            else:
                print("⚠️ No modified_by user found for maintenance")


@receiver(pre_delete, sender=Maintenance)
def maintenance_deleted_immediate(sender, instance, **kwargs):
    """
    Immediate notification when maintenance is deleted
    """
    # Only notify for MANUAL maintenances
    if instance.maintenance_type != Maintenance.TYPE_MANUAL:
        return
    
    # Collect maintenance data before deletion
    maintenance_data = {
        'maintenance_id': instance.id,
        'project_id': instance.project.id,
        'project_name': instance.project.name,
        'start_date': instance.start_date.isoformat(),
        'end_date': instance.end_date.isoformat(),
        'maintenance_type': instance.maintenance_type,
    }
    
    # Get the user who deleted it
    deleted_by = getattr(instance, '_deleted_by', None)
    
    if deleted_by:
        print(f"🗑️ Maintenance deleted by {deleted_by.username}")
        _notify_maintenance_deleted_immediate(maintenance_data, deleted_by)


# ========== HELPER FUNCTIONS ==========

def _remove_all_project_notifications(project):
    """Remove ALL notifications for a specific project"""
    deleted_count, _ = Notification.objects.filter(
        related_project=project
    ).delete()
    
    if deleted_count > 0:
        print(f"🧹 Removed {deleted_count} notifications for project: {project.name}")
        logger.info(f"Removed {deleted_count} notifications for project: {project.name}")


def _remove_project_notifications_for_employer(project, employer):
    """Remove ALL notifications for a specific project and employer"""
    deleted_count, _ = Notification.objects.filter(
        recipient=employer,
        related_project=project
    ).delete()
    
    if deleted_count > 0:
        print(f"🧹 Removed {deleted_count} notifications for {employer.username} on project {project.name}")


def _notify_project_deletion_to_employers(project, deleted_by):
    """Send deletion notification to assigned employers"""
    for employer in project.assigned_employers.all():
        if employer != deleted_by:  # Don't notify the person who deleted
            NotificationService.create_notification(
                recipient=employer,
                notification_type=Notification.TYPE_PROJECT_DELETED,
                title=f"🗑️ Projet Supprimé: {project.name}",
                message=f"Le projet '{project.name}' a été supprimé par {deleted_by.get_full_name() or deleted_by.username}.",
                priority=Notification.PRIORITY_HIGH,
                related_project=None,
                data={
                    'project_id': project.id,
                    'project_name': project.name,
                    'client_name': project.client.name,
                    'deleted_by': deleted_by.get_full_name() or deleted_by.username,
                    'deleted_at': timezone.now().isoformat(),
                    'trigger': 'project_deleted'
                }
            )
            print(f"📤 Sent deletion notification to {employer.username}")


def _notify_project_verified_as_assigned(project):
    """
    When project is verified, send PROJECT_ASSIGNED to all assigned employers
    """
    for employer in project.assigned_employers.all():
        NotificationService.create_notification(
            recipient=employer,
            notification_type=Notification.TYPE_PROJECT_ASSIGNED,
            title=f"✅ Nouveau Projet Assigné: {project.name}",
            message=f"Le projet '{project.name}' a été vérifié et vous êtes assigné. Date de début: {project.start_date.strftime('%d/%m/%Y')}",
            priority=Notification.PRIORITY_HIGH,
            related_project=project,
            data={
                'project_id': project.id,
                'project_name': project.name,
                'client_name': project.client.name,
                'start_date': project.start_date.isoformat(),
                'end_date': project.end_date.isoformat() if project.end_date else None,
                'verified_at': timezone.now().isoformat(),
                'trigger': 'project_verified'
            }
        )
        print(f"📤 Sent PROJECT_ASSIGNED (verified) to {employer.username}")
        logger.info(f"Project verified notification sent to {employer.username}")


def _notify_project_modified_immediate(project, modified_by):
    """
    Send PROJECT_MODIFIED notification
    """
    for employer in project.assigned_employers.exclude(id=modified_by.id):
        NotificationService.create_notification(
            recipient=employer,
            notification_type=Notification.TYPE_PROJECT_MODIFIED,
            title=f"✏️ Projet Modifié: {project.name}",
            message=f"Le projet '{project.name}' a été modifié par {modified_by.get_full_name() or modified_by.username}.",
            priority=Notification.PRIORITY_MEDIUM,
            related_project=project,
            data={
                'project_id': project.id,
                'project_name': project.name,
                'client_name': project.client.name,
                'modified_by': modified_by.get_full_name() or modified_by.username,
                'modified_at': timezone.now().isoformat(),
                'trigger': 'project_modified'
            }
        )
        print(f"📤 Sent PROJECT_MODIFIED to {employer.username}")


def _notify_maintenance_added_immediate(maintenance, created_by):
    """Immediate notification when manual maintenance is added"""
    for employer in maintenance.project.assigned_employers.exclude(id=created_by.id):
        NotificationService.create_notification(
            recipient=employer,
            notification_type=Notification.TYPE_MAINTENANCE_ADDED,
            title=f"🛠️ Nouvelle Maintenance: {maintenance.project.name}",
            message=f"Une maintenance a été ajoutée au projet '{maintenance.project.name}' pour le {maintenance.start_date.strftime('%d/%m/%Y')}.",
            priority=Notification.PRIORITY_MEDIUM,
            related_project=maintenance.project,
            related_maintenance=maintenance,
            data={
                'maintenance_id': maintenance.id,
                'project_id': maintenance.project.id,
                'project_name': maintenance.project.name,
                'start_date': maintenance.start_date.isoformat(),
                'end_date': maintenance.end_date.isoformat(),
                'created_by': created_by.get_full_name() or created_by.username,
                'trigger': 'maintenance_added'
            }
        )
        print(f"📤 Sent MAINTENANCE_ADDED to {employer.username}")


def _notify_maintenance_modified_immediate(maintenance, modified_by):
    """
    Send MAINTENANCE_MODIFIED notification
    """
    for employer in maintenance.project.assigned_employers.exclude(id=modified_by.id):
        NotificationService.create_notification(
            recipient=employer,
            notification_type=Notification.TYPE_MAINTENANCE_MODIFIED,
            title=f"✏️ Maintenance Modifiée: {maintenance.project.name}",
            message=f"La maintenance du projet '{maintenance.project.name}' a été modifiée par {modified_by.get_full_name() or modified_by.username}.",
            priority=Notification.PRIORITY_MEDIUM,
            related_project=maintenance.project,
            related_maintenance=maintenance,
            data={
                'maintenance_id': maintenance.id,
                'project_id': maintenance.project.id,
                'project_name': maintenance.project.name,
                'start_date': maintenance.start_date.isoformat(),
                'end_date': maintenance.end_date.isoformat(),
                'modified_by': modified_by.get_full_name() or modified_by.username,
                'modified_at': timezone.now().isoformat(),
                'trigger': 'maintenance_modified'
            }
        )
        print(f"📤 Sent MAINTENANCE_MODIFIED to {employer.username}")


def _notify_maintenance_deleted_immediate(maintenance_data, deleted_by):
    """Immediate notification when manual maintenance is deleted"""
    from apps.projects.models import Project
    try:
        project = Project.objects.get(id=maintenance_data['project_id'])
        for employer in project.assigned_employers.exclude(id=deleted_by.id):
            NotificationService.create_notification(
                recipient=employer,
                notification_type=Notification.TYPE_MAINTENANCE_DELETED,
                title=f"🗑️ Maintenance Supprimée: {maintenance_data['project_name']}",
                message=f"Une maintenance du projet '{maintenance_data['project_name']}' a été supprimée par {deleted_by.get_full_name() or deleted_by.username}.",
                priority=Notification.PRIORITY_MEDIUM,
                related_project=project,
                data={
                    **maintenance_data,
                    'deleted_by': deleted_by.get_full_name() or deleted_by.username,
                    'deleted_at': timezone.now().isoformat(),
                    'trigger': 'maintenance_deleted'
                }
            )
            print(f"📤 Sent MAINTENANCE_DELETED to {employer.username}")
    except Project.DoesNotExist:
        pass