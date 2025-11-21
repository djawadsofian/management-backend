# apps/projects/signals.py
"""
Signal handlers for Project and Maintenance models
"""
from django.db.models.signals import post_save, pre_delete, pre_save, m2m_changed
from django.dispatch import receiver
from apps.projects.models import Project, Maintenance
from apps.notifications.services import NotificationService
import logging

logger = logging.getLogger(__name__)


# ========== PROJECT SIGNALS ==========


@receiver(pre_save, sender=Project)
def track_verification_state(sender, instance, **kwargs):
    """
    Track previous verification state before save
    """
    if instance.pk:
        try:
            previous = Project.objects.get(pk=instance.pk)
            instance._previous_is_verified = previous.is_verified
        except Project.DoesNotExist:
            instance._previous_is_verified = False
    else:
        instance._previous_is_verified = False

@receiver(post_save, sender=Project)
def project_verified(sender, instance, created, **kwargs):
    """
    Notify assigned employers when project is verified
    """
    # For new projects that are created as verified
    if created and instance.is_verified and instance.assigned_employers.exists():
        from apps.notifications.services import NotificationService
        NotificationService.notify_project_assigned(instance, instance.assigned_employers.all())
        logger.info(f"Notified {instance.assigned_employers.count()} employers about new verified project: {instance.name}")
    
    # For existing projects that are being verified
    elif not created and hasattr(instance, '_previous_is_verified'):
        previous_verified = instance._previous_is_verified
        current_verified = instance.is_verified
        
        # Check if project was just verified
        if not previous_verified and current_verified and instance.assigned_employers.exists():
            from apps.notifications.services import NotificationService
            NotificationService.notify_project_assigned(instance, instance.assigned_employers.all())
            logger.info(f"Notified {instance.assigned_employers.count()} employers about project verification: {instance.name}")






@receiver(m2m_changed, sender=Project.assigned_employers.through)
def project_employers_changed(sender, instance, action, pk_set, **kwargs ):
    """
    Notify employers when they are assigned to a project
    """
    if action == "post_add" and pk_set and instance.is_verified:
        # Get newly assigned employers
        from apps.users.models import CustomUser
        new_employers = CustomUser.objects.filter(pk__in=pk_set)
        
        # Notify each employer
        NotificationService.notify_project_assigned(instance, new_employers)
        logger.info(f"Notified {len(new_employers)} employers about project assignment: {instance.name}")


@receiver(post_save, sender=Project)
def project_modified(sender, instance, created, **kwargs):
    """
    Notify assigned employers when project is modified (not created)
    """
    if not created and instance.is_verified:
        # Check if we have update_fields to determine what changed
        update_fields = kwargs.get('update_fields')
        
        # Build changes dict
        changes = {}
        if update_fields:
            changes = {field: getattr(instance, field) for field in update_fields}
        
        # Get the user who made the change from thread local storage
        # You'll need to set this in your views
        modified_by = getattr(instance, '_modified_by', None)
        
        if modified_by:
            NotificationService.notify_project_modified(
                instance,
                modified_by,
                changes
            )
            logger.info(f"Notified employers about project modification: {instance.name}")


@receiver(pre_delete, sender=Project)
def project_deleted(sender, instance, **kwargs):
    """
    Notify assigned employers when project is deleted
    """
    # Collect project data before deletion
    project_data = {
        'project_id': instance.id,
        'name': instance.name,
        'client_name': instance.client.name,
        'start_date': instance.start_date.isoformat(),
        'end_date': instance.end_date.isoformat() if instance.end_date else None,
        'assigned_employer_ids': list(instance.assigned_employers.values_list('id', flat=True)),
    }
    
    # Get the user who deleted it (should be set in view)
    deleted_by = getattr(instance, '_deleted_by', None)
    
    if deleted_by:
        NotificationService.notify_project_deleted(project_data, deleted_by)
        logger.info(f"Notified employers about project deletion: {instance.name}")


# ========== MAINTENANCE SIGNALS ==========

@receiver(post_save, sender=Maintenance)
def maintenance_saved(sender, instance, created, **kwargs):
    """
    Notify assigned employers when maintenance is added or modified
    """
    # Only notify for MANUAL maintenances, not AUTO
    if instance.maintenance_type != Maintenance.TYPE_MANUAL:
        return
    
    # Get the user who made the change
    user = getattr(instance, '_created_by', None) or getattr(instance, '_modified_by', None)
    
    if not user:
        return
    
    if created:
        # New maintenance added
        NotificationService.notify_maintenance_added(instance, user)
        logger.info(f"Notified employers about new maintenance: {instance.project.name}")
    else:
        # Maintenance modified
        update_fields = kwargs.get('update_fields')
        changes = {}
        if update_fields:
            changes = {field: getattr(instance, field) for field in update_fields}
        
        NotificationService.notify_maintenance_modified(instance, user, changes)
        logger.info(f"Notified employers about maintenance modification: {instance.project.name}")


@receiver(pre_delete, sender=Maintenance)
def maintenance_deleted(sender, instance, **kwargs):
    """
    Notify assigned employers when maintenance is deleted
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
        NotificationService.notify_maintenance_deleted(maintenance_data, deleted_by)
        logger.info(f"Notified employers about maintenance deletion: {instance.project.name}")