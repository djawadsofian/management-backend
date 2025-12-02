# apps/projects/signals.py
"""
Signal handlers for Project and Maintenance models - IMMEDIATE notifications
"""
from django.db.models.signals import post_save, pre_delete, pre_save, m2m_changed
from django.dispatch import receiver
from django.utils import timezone
from apps.projects.models import Project, Maintenance
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification
import logging

logger = logging.getLogger(__name__)


# ========== PROJECT SIGNALS ==========

@receiver(pre_save, sender=Project)
def track_project_changes(sender, instance, **kwargs):
    """
    Track previous project state before save for immediate notifications
    """
    if instance.pk:
        try:
            previous = Project.objects.get(pk=instance.pk)
            instance._previous_is_verified = previous.is_verified
            instance._previous_start_date = previous.start_date
            instance._previous_end_date = previous.end_date
            instance._previous_assigned_employers = set(previous.assigned_employers.values_list('id', flat=True))
        except Project.DoesNotExist:
            instance._previous_is_verified = False
            instance._previous_start_date = None
            instance._previous_end_date = None
            instance._previous_assigned_employers = set()
    else:
        instance._previous_is_verified = False
        instance._previous_start_date = None
        instance._previous_end_date = None
        instance._previous_assigned_employers = set()


@receiver(post_save, sender=Project)
def project_immediate_notifications(sender, instance, created, **kwargs):
    """
    Send immediate notifications for project changes
    """
    print(f"🔄 Project signal triggered - Created: {created}, Verified: {instance.is_verified}")

    if created:
        # New project created - notify admins/assistants if verified
        if instance.is_verified:
            _notify_new_verified_project(instance)
        return

    # Existing project modified
    if hasattr(instance, '_previous_is_verified'):
        previous_verified = instance._previous_is_verified
        current_verified = instance.is_verified
        
        # Project just got verified - immediate notification to assigned employers
        if not previous_verified and current_verified:
            print(f"✅ Project verified: {instance.name}")
            _notify_project_verified(instance)
        
        # Project just got UNverified - remove all notifications
        elif previous_verified and not current_verified:
            print(f"❌ Project unverified: {instance.name}")
            _remove_all_project_notifications(instance)
        
        # Project modified (dates changed, etc.) - notify assigned employers
        elif (current_verified and 
              (instance._previous_start_date != instance.start_date or
               instance._previous_end_date != instance.end_date)):
            print(f"✏️ Project modified: {instance.name}")
            _notify_project_modified_immediate(instance)


@receiver(m2m_changed, sender=Project.assigned_employers.through)
def project_employers_changed_immediate(sender, instance, action, pk_set, **kwargs):
    """
    Immediate notification when employers are assigned/unassigned to/from a verified project
    """
    if not instance.is_verified:
        return  # Only notify for verified projects
    
    if action == "post_add" and pk_set:
        from apps.users.models import CustomUser
        new_employers = CustomUser.objects.filter(pk__in=pk_set)
        
        # Send assignment notifications to newly assigned employers
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
                    'trigger': 'immediate_assignment'
                }
            )
            logger.info(f"Immediate assignment notification sent for project {instance.name} to {employer.username}")
    
    elif action == "post_remove" and pk_set:
        from apps.users.models import CustomUser
        removed_employers = CustomUser.objects.filter(pk__in=pk_set)
        
        # Send unassignment notifications to removed employers
        for employer in removed_employers:
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
                    'trigger': 'immediate_unassignment'
                }
            )
            logger.info(f"Unassignment notification sent for project {instance.name} to {employer.username}")
            
            # Remove all notifications of this project for the removed employer
            _remove_project_notifications_for_employer(instance, employer)
    
    elif action == "post_clear":
        # All employers removed - handled by the view
        pass


@receiver(pre_delete, sender=Project)
def project_deleted_immediate(sender, instance, **kwargs):
    """
    Immediate notification when project is deleted
    """
    print(f"🗑️ Project deleted: {instance.name}")
    
    # First, send deletion notifications to assigned employers
    _notify_project_deletion_to_employers(instance)
    
    # Then remove all project notifications from database
    _remove_all_project_notifications(instance)


# ========== MAINTENANCE SIGNALS ==========

@receiver(post_save, sender=Maintenance)
def maintenance_immediate_notifications(sender, instance, created, **kwargs):
    """
    Immediate notifications for maintenance changes
    """
    # Only notify for MANUAL maintenances immediately
    if instance.maintenance_type != Maintenance.TYPE_MANUAL:
        return
    
    # Get the user who made the change
    user = getattr(instance, '_created_by', None) or getattr(instance, '_modified_by', None)
    
    if not user:
        return
    
    if created:
        # New manual maintenance added - immediate notification
        _notify_maintenance_added_immediate(instance, user)
    else:
        # Maintenance modified - immediate notification (DO NOT remove previous ones)
        _notify_maintenance_modified_immediate(instance, user)


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
        _notify_maintenance_deleted_immediate(maintenance_data, deleted_by)


# ========== HELPER FUNCTIONS ==========

def _remove_all_project_notifications(project):
    """Remove all notifications for a specific project"""
    deleted_count, _ = Notification.objects.filter(
        related_project=project
    ).delete()
    
    if deleted_count > 0:
        print(f"🧹 Removed {deleted_count} notifications for project: {project.name}")
        logger.info(f"Removed {deleted_count} notifications for project: {project.name}")


def _remove_project_notifications_for_employer(project, employer):
    """Remove all notifications for a specific project and employer"""
    deleted_count, _ = Notification.objects.filter(
        recipient=employer,
        related_project=project
    ).delete()
    
    if deleted_count > 0:
        print(f"🧹 Removed {deleted_count} notifications for {employer.username} on project {project.name}")


def _remove_project_assignment_notifications(project, employers):
    """Remove assignment notifications for specific employers and project"""
    for employer in employers:
        deleted_count, _ = Notification.objects.filter(
            recipient=employer,
            related_project=project,
            notification_type=Notification.TYPE_PROJECT_ASSIGNED
        ).delete()
        
        if deleted_count > 0:
            print(f"🧹 Removed {deleted_count} assignment notifications for {employer.username} on project {project.name}")


def _notify_project_deletion_to_employers(project):
    """Send deletion notification to assigned employers before removing all notifications"""
    # Collect project data before deletion
    project_data = {
        'project_id': project.id,
        'name': project.name,
        'client_name': project.client.name,
        'start_date': project.start_date.isoformat(),
        'end_date': project.end_date.isoformat() if project.end_date else None,
        'assigned_employer_ids': list(project.assigned_employers.values_list('id', flat=True)),
    }
    
    # Get the user who deleted it (should be set in view)
    deleted_by = getattr(project, '_deleted_by', None)
    
    if deleted_by:
        # Notify assigned employers immediately
        for employer in project.assigned_employers.all():
            if employer != deleted_by:  # Don't notify the person who deleted
                NotificationService.create_notification(
                    recipient=employer,
                    notification_type=Notification.TYPE_PROJECT_DELETED,
                    title=f"🗑️ Projet Supprimé: {project.name}",
                    message=f"Le projet '{project.name}' a été supprimé par {deleted_by.get_full_name() or deleted_by.username}.",
                    priority=Notification.PRIORITY_HIGH,
                    related_project=None,  # Project is being deleted
                    data={
                        **project_data,
                        'deleted_by': deleted_by.get_full_name() or deleted_by.username,
                        'deleted_at': timezone.now().isoformat(),
                        'trigger': 'immediate_deletion'
                    }
                )
                print(f"📤 Sent deletion notification for project {project.name} to {employer.username}")
        
        logger.info(f"Immediate deletion notification sent for project {project.name}")


def _notify_new_verified_project(project):
    """Notify admins/assistants when a new project is created and verified"""
    from apps.users.models import CustomUser
    admins_assistants = CustomUser.objects.filter(
        role__in=[CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT],
        is_active=True
    )
    
    for user in admins_assistants:
        NotificationService.create_notification(
            recipient=user,
            notification_type=Notification.TYPE_PROJECT_MODIFIED,
            title=f"🆕 Nouveau Projet Vérifié: {project.name}",
            message=f"Un nouveau projet '{project.name}' a été créé et vérifié pour le client {project.client.name}.",
            priority=Notification.PRIORITY_MEDIUM,
            related_project=project,
            data={
                'project_id': project.id,
                'project_name': project.name,
                'client_name': project.client.name,
                'start_date': project.start_date.isoformat(),
                'trigger': 'immediate_new_verified'
            }
        )


def _notify_project_verified(project):
    """Immediate notification when project is verified - send PROJECT_ASSIGNED to employers"""
    for employer in project.assigned_employers.all():
        NotificationService.create_notification(
            recipient=employer,
            notification_type=Notification.TYPE_PROJECT_ASSIGNED,
            title=f"✅ Projet Vérifié et Assigné: {project.name}",
            message=f"Le projet '{project.name}' a été vérifié et vous êtes assigné. Date de début: {project.start_date.strftime('%d/%m/%Y')}",
            priority=Notification.PRIORITY_HIGH,
            related_project=project,
            data={
                'project_id': project.id,
                'project_name': project.name,
                'client_name': project.client.name,
                'verified_at': timezone.now().isoformat(),
                'trigger': 'immediate_verification'
            }
        )
        print(f"📤 Sent verification notification for project {project.name} to {employer.username}")


def _notify_project_modified_immediate(project):
    """Immediate notification for project modifications - DO NOT remove previous notifications"""
    modified_by = getattr(project, '_modified_by', None)
    
    if modified_by:
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
                    'modified_by': modified_by.get_full_name() or modified_by.username,
                    'modified_at': timezone.now().isoformat(),
                    'trigger': 'immediate_modification'
                }
            )
            print(f"📤 Sent modification notification for project {project.name} to {employer.username}")


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
                'created_by': created_by.get_full_name() or created_by.username,
                'trigger': 'immediate_maintenance_added'
            }
        )


def _notify_maintenance_modified_immediate(maintenance, modified_by):
    """Immediate notification when manual maintenance is modified - DO NOT remove previous ones"""
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
                'modified_by': modified_by.get_full_name() or modified_by.username,
                'trigger': 'immediate_maintenance_modified'
            }
        )


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
                    'trigger': 'immediate_maintenance_deleted'
                }
            )
    except Project.DoesNotExist:
        pass