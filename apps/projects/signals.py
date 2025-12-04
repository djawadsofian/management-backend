# apps/projects/signals.py
"""
Enhanced Signal handlers with detailed change tracking
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
    """Track previous project state with detailed field tracking"""
    if not hasattr(instance, '_modified_by'):
        instance._modified_by = get_current_user()
    
    if instance.pk:
        try:
            previous = Project.objects.get(pk=instance.pk)
            # Store all previous values for comparison
            instance._previous_is_verified = previous.is_verified
            instance._previous_start_date = previous.start_date
            instance._previous_end_date = previous.end_date
            instance._previous_name = previous.name
            instance._previous_description = previous.description
            instance._previous_duration_maintenance = previous.duration_maintenance
            instance._previous_interval_maintenance = previous.interval_maintenance
            
            # Store previous employers for comparison
            instance._previous_employers = set(previous.assigned_employers.values_list('id', flat=True))
            
            instance._has_changes = True
        except Project.DoesNotExist:
            instance._has_changes = False
    else:
        instance._previous_is_verified = False
        instance._previous_employers = set()
        instance._has_changes = False


@receiver(post_save, sender=Project)
def project_immediate_notifications(sender, instance, created, **kwargs):
    """Send notifications with detailed change information"""
    print(f"🔄 Project signal triggered - Created: {created}, Verified: {instance.is_verified}")

    if created:
        return

    if not hasattr(instance, '_has_changes') or not instance._has_changes:
        return

    modified_by = getattr(instance, '_modified_by', None)
    if not modified_by:
        print("⚠️ No modified_by user found, skipping notifications")
        return

    previous_verified = getattr(instance, '_previous_is_verified', False)
    current_verified = instance.is_verified
    
    # Project verified
    if not previous_verified and current_verified:
        print(f"✅ Project verified: {instance.name}")
        _notify_project_verified_as_assigned(instance)
    
    # Project unverified - remove notifications AND upcoming event notifications
    elif previous_verified and not current_verified:
        print(f"❌ Project unverified: {instance.name}")
        _remove_all_project_notifications(instance)
    
    # Project modified - track detailed changes
    elif current_verified:
        changes = _detect_project_changes(instance)
        if changes:
            print(f"✏️ Project modified: {instance.name} - Changes: {list(changes.keys())}")
            _notify_project_modified_with_changes(instance, modified_by, changes)


def _detect_project_changes(instance):
    """Detect and categorize all changes in the project"""
    changes = {}
    
    # Start date changed
    prev_start = getattr(instance, '_previous_start_date', None)
    if prev_start and prev_start != instance.start_date:
        changes['start_date'] = {
            'old': prev_start.isoformat(),
            'new': instance.start_date.isoformat(),
            'message': f"Date de début modifiée: {prev_start.strftime('%d/%m/%Y')} → {instance.start_date.strftime('%d/%m/%Y')}"
        }
    
    # End date changed
    prev_end = getattr(instance, '_previous_end_date', None)
    if prev_end != instance.end_date:
        if prev_end and instance.end_date:
            changes['end_date'] = {
                'old': prev_end.isoformat(),
                'new': instance.end_date.isoformat(),
                'message': f"Date de fin modifiée: {prev_end.strftime('%d/%m/%Y')} → {instance.end_date.strftime('%d/%m/%Y')}"
            }
    
    # Name changed
    prev_name = getattr(instance, '_previous_name', None)
    if prev_name and prev_name != instance.name:
        changes['name'] = {
            'old': prev_name,
            'new': instance.name,
            'message': f"Nom modifié: '{prev_name}' → '{instance.name}'"
        }
    
    # Description changed
    prev_desc = getattr(instance, '_previous_description', None)
    if prev_desc != instance.description:
        changes['description'] = {
            'message': "Description modifiée"
        }
    
    # Maintenance settings changed
    prev_duration = getattr(instance, '_previous_duration_maintenance', None)
    prev_interval = getattr(instance, '_previous_interval_maintenance', None)
    
    if (prev_duration != instance.duration_maintenance or 
        prev_interval != instance.interval_maintenance):
        changes['maintenance_settings'] = {
            'message': "⚠️ Paramètres de maintenance modifiés - Les dates de maintenance ont été recalculées"
        }
    
    return changes


def _notify_project_modified_with_changes(project, modified_by, changes):
    """Send detailed modification notifications"""
    
    # Check if start date changed - remove upcoming notifications
    if 'start_date' in changes:
        _remove_upcoming_project_notifications(project)
    
    # Build detailed message
    change_messages = [change['message'] for change in changes.values()]
    detailed_message = "\n• ".join([""] + change_messages)
    
    for employer in project.assigned_employers.exclude(id=modified_by.id):
        NotificationService.create_notification(
            recipient=employer,
            notification_type=Notification.TYPE_PROJECT_MODIFIED,
            title=f"✏️ Projet Modifié: {project.name}",
            message=f"Le projet '{project.name}' a été modifié par {modified_by.get_full_name() or modified_by.username}.{detailed_message}",
            priority=Notification.PRIORITY_MEDIUM,
            related_project=project,
            data={
                'project_id': project.id,
                'project_name': project.name,
                'client_name': project.client.name,
                'modified_by': modified_by.get_full_name() or modified_by.username,
                'modified_at': timezone.now().isoformat(),
                'changes': changes,
                'trigger': 'project_modified'
            }
        )
        print(f"📤 Sent PROJECT_MODIFIED with changes to {employer.username}")


def _remove_upcoming_project_notifications(project):
    """Remove upcoming event notifications when start date changes"""
    deleted_count, _ = Notification.objects.filter(
        related_project=project,
        notification_type=Notification.TYPE_PROJECT_STARTING_SOON
    ).delete()
    
    if deleted_count > 0:
        print(f"🧹 Removed {deleted_count} upcoming notifications for project: {project.name} (start date changed)")


@receiver(m2m_changed, sender=Project.assigned_employers.through)
def project_employers_changed_immediate(sender, instance, action, pk_set, **kwargs):
    """Handle employer changes with team notification"""
    if not instance.is_verified:
        return
    
    if action == "post_add" and pk_set:
        from apps.users.models import CustomUser
        new_employers = CustomUser.objects.filter(pk__in=pk_set)
        
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
            print(f"📤 Sent PROJECT_ASSIGNED to {employer.username}")
        
        # Notify existing team members about team change
        existing_employers = instance.assigned_employers.exclude(id__in=pk_set)
        if existing_employers.exists():
            new_names = ", ".join([e.get_full_name() or e.username for e in new_employers])
            for employer in existing_employers:
                NotificationService.create_notification(
                    recipient=employer,
                    notification_type=Notification.TYPE_PROJECT_MODIFIED,
                    title=f"👥 Équipe Modifiée: {instance.name}",
                    message=f"Nouveaux membres ajoutés au projet '{instance.name}': {new_names}",
                    priority=Notification.PRIORITY_LOW,
                    related_project=instance,
                    data={
                        'project_id': instance.id,
                        'project_name': instance.name,
                        'team_change': 'members_added',
                        'new_members': [e.username for e in new_employers]
                    }
                )
    
    elif action == "post_remove" and pk_set:
        from apps.users.models import CustomUser
        removed_employers = CustomUser.objects.filter(pk__in=pk_set)
        
        for employer in removed_employers:
            NotificationService.create_notification(
                recipient=employer,
                notification_type=Notification.TYPE_PROJECT_MODIFIED,
                title=f"⚠️ Projet Retiré: {instance.name}",
                message=f"Vous n'êtes plus assigné au projet '{instance.name}'.",
                priority=Notification.PRIORITY_MEDIUM,
                related_project=instance,
                data={
                    'project_id': instance.id,
                    'project_name': instance.name,
                    'unassigned_at': timezone.now().isoformat(),
                    'trigger': 'employer_removed'
                }
            )
            _remove_project_notifications_for_employer(instance, employer)
        
        # Notify remaining team members
        remaining_employers = instance.assigned_employers.all()
        if remaining_employers.exists():
            removed_names = ", ".join([e.get_full_name() or e.username for e in removed_employers])
            for employer in remaining_employers:
                NotificationService.create_notification(
                    recipient=employer,
                    notification_type=Notification.TYPE_PROJECT_MODIFIED,
                    title=f"👥 Équipe Modifiée: {instance.name}",
                    message=f"Membres retirés du projet '{instance.name}': {removed_names}",
                    priority=Notification.PRIORITY_LOW,
                    related_project=instance,
                    data={
                        'project_id': instance.id,
                        'project_name': instance.name,
                        'team_change': 'members_removed',
                        'removed_members': [e.username for e in removed_employers]
                    }
                )


@receiver(pre_delete, sender=Project)
def project_deleted_immediate(sender, instance, **kwargs):
    """Notification when project is deleted"""
    deleted_by = getattr(instance, '_deleted_by', None)
    if deleted_by:
        _notify_project_deletion_to_employers(instance, deleted_by)


# ========== MAINTENANCE SIGNALS ==========

@receiver(pre_save, sender=Maintenance)
def track_maintenance_changes(sender, instance, **kwargs):
    """Track maintenance changes with detailed field tracking"""
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
    """Send notifications with detailed changes"""
    if instance.maintenance_type != Maintenance.TYPE_MANUAL:
        return
    
    if created:
        created_by = getattr(instance, '_created_by', None)
        if created_by:
            print(f"🛠️ New maintenance created by {created_by.username}")
            _notify_maintenance_added_immediate(instance, created_by)
        else:
            print("⚠️ No created_by user found for maintenance")
    else:
        if hasattr(instance, '_has_changes') and instance._has_changes:
            changes = _detect_maintenance_changes(instance)
            if changes:
                modified_by = getattr(instance, '_modified_by', None)
                if modified_by:
                    print(f"✏️ Maintenance modified by {modified_by.username}")
                    _notify_maintenance_modified_with_changes(instance, modified_by, changes)


def _detect_maintenance_changes(instance):
    """Detect changes in maintenance"""
    changes = {}
    
    prev_start = getattr(instance, '_previous_start_date', None)
    if prev_start and prev_start != instance.start_date:
        changes['start_date'] = {
            'old': prev_start.isoformat(),
            'new': instance.start_date.isoformat(),
            'message': f"Date de début modifiée: {prev_start.strftime('%d/%m/%Y')} → {instance.start_date.strftime('%d/%m/%Y')}"
        }
    
    prev_end = getattr(instance, '_previous_end_date', None)
    if prev_end and prev_end != instance.end_date:
        changes['end_date'] = {
            'old': prev_end.isoformat(),
            'new': instance.end_date.isoformat(),
            'message': f"Date de fin modifiée: {prev_end.strftime('%d/%m/%Y')} → {instance.end_date.strftime('%d/%m/%Y')}"
        }
    
    return changes


def _notify_maintenance_modified_with_changes(maintenance, modified_by, changes):
    """Send detailed maintenance modification notifications"""
    
    # Remove upcoming notifications if start date changed
    if 'start_date' in changes:
        _remove_upcoming_maintenance_notifications(maintenance)
    
    change_messages = [change['message'] for change in changes.values()]
    detailed_message = "\n• ".join([""] + change_messages)
    
    for employer in maintenance.project.assigned_employers.exclude(id=modified_by.id):
        NotificationService.create_notification(
            recipient=employer,
            notification_type=Notification.TYPE_MAINTENANCE_MODIFIED,
            title=f"✏️ Maintenance Modifiée: {maintenance.project.name}",
            message=f"La maintenance du projet '{maintenance.project.name}' a été modifiée par {modified_by.get_full_name() or modified_by.username}.{detailed_message}",
            priority=Notification.PRIORITY_MEDIUM,
            related_project=maintenance.project,
            related_maintenance=maintenance,
            data={
                'maintenance_id': maintenance.id,
                'project_id': maintenance.project.id,
                'project_name': maintenance.project.name,
                'modified_by': modified_by.get_full_name() or modified_by.username,
                'modified_at': timezone.now().isoformat(),
                'changes': changes,
                'trigger': 'maintenance_modified'
            }
        )
        print(f"📤 Sent MAINTENANCE_MODIFIED with changes to {employer.username}")


def _remove_upcoming_maintenance_notifications(maintenance):
    """Remove upcoming notifications when maintenance start date changes"""
    deleted_count, _ = Notification.objects.filter(
        related_maintenance=maintenance,
        notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON
    ).delete()
    
    if deleted_count > 0:
        print(f"🧹 Removed {deleted_count} upcoming notifications for maintenance (start date changed)")


@receiver(pre_delete, sender=Maintenance)
def maintenance_deleted_immediate(sender, instance, **kwargs):
    """Notification when maintenance is deleted"""
    if instance.maintenance_type != Maintenance.TYPE_MANUAL:
        return
    
    # NEW: Remove all existing notifications for this maintenance
    deleted_count, _ = Notification.objects.filter(
        related_maintenance=instance
    ).delete()
    
    if deleted_count > 0:
        print(f"🧹 Removed {deleted_count} notifications for deleted maintenance")
    
    maintenance_data = {
        'maintenance_id': instance.id,
        'project_id': instance.project.id,
        'project_name': instance.project.name,
        'start_date': instance.start_date.isoformat(),
        'end_date': instance.end_date.isoformat(),
        'maintenance_type': instance.maintenance_type,
    }
    
    deleted_by = getattr(instance, '_deleted_by', None)
    if deleted_by:
        _notify_maintenance_deleted_immediate(maintenance_data, deleted_by)


# ========== HELPER FUNCTIONS ==========

def _remove_all_project_notifications(project):
    """Remove ALL notifications for a project"""
    deleted_count, _ = Notification.objects.filter(
        related_project=project
    ).delete()
    
    if deleted_count > 0:
        print(f"🧹 Removed {deleted_count} notifications for project: {project.name}")


def _remove_project_notifications_for_employer(project, employer):
    """Remove all project notifications for specific employer"""
    deleted_count, _ = Notification.objects.filter(
        recipient=employer,
        related_project=project
    ).delete()
    
    if deleted_count > 0:
        print(f"🧹 Removed {deleted_count} notifications for {employer.username}")


def _notify_project_deletion_to_employers(project, deleted_by):
    """Notify employers about project deletion"""
    for employer in project.assigned_employers.all():
        if employer != deleted_by:
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
                    'deleted_at': timezone.now().isoformat()
                }
            )


def _notify_project_verified_as_assigned(project):
    """Notify when project is verified"""
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
                'verified_at': timezone.now().isoformat()
            }
        )


def _notify_maintenance_added_immediate(maintenance, created_by):
    """Notify when maintenance is added"""
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
                'created_by': created_by.get_full_name() or created_by.username
            }
        )


def _notify_maintenance_deleted_immediate(maintenance_data, deleted_by):
    """Notify when maintenance is deleted"""
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
                    'deleted_at': timezone.now().isoformat()
                }
            )
    except Project.DoesNotExist:
        pass