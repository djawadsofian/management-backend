# apps/notifications/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

class Notification(models.Model):
    """
    Notification model for real-time alerts
    """
    # Notification types
    TYPE_PROJECT_ASSIGNED = 'PROJECT_ASSIGNED'
    TYPE_PROJECT_STARTING_SOON = 'PROJECT_STARTING_SOON'
    TYPE_PROJECT_MODIFIED = 'PROJECT_MODIFIED'
    TYPE_PROJECT_DELETED = 'PROJECT_DELETED'
    TYPE_MAINTENANCE_STARTING_SOON = 'MAINTENANCE_STARTING_SOON'
    TYPE_MAINTENANCE_ADDED = 'MAINTENANCE_ADDED'
    TYPE_MAINTENANCE_MODIFIED = 'MAINTENANCE_MODIFIED'
    TYPE_MAINTENANCE_DELETED = 'MAINTENANCE_DELETED'
    
    TYPE_CHOICES = [
        (TYPE_PROJECT_ASSIGNED, 'Assigned to Project'),
        (TYPE_PROJECT_STARTING_SOON, 'Project Starting Soon'),
        (TYPE_PROJECT_MODIFIED, 'Project Modified'),
        (TYPE_PROJECT_DELETED, 'Project Deleted'),
        (TYPE_MAINTENANCE_STARTING_SOON, 'Maintenance Starting Soon'),
        (TYPE_MAINTENANCE_ADDED, 'Maintenance Added'),
        (TYPE_MAINTENANCE_MODIFIED, 'Maintenance Modified'),
        (TYPE_MAINTENANCE_DELETED, 'Maintenance Deleted'),
    ]
    
    # Priority levels
    PRIORITY_LOW = 'LOW'
    PRIORITY_MEDIUM = 'MEDIUM'
    PRIORITY_HIGH = 'HIGH'
    PRIORITY_URGENT = 'URGENT'
    
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_MEDIUM, 'Medium'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_URGENT, 'Urgent'),
    ]
    
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notification_type = models.CharField(
        max_length=50,
        choices=TYPE_CHOICES,
        db_index=True
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM,
        db_index=True
    )
    
    # Related objects
    related_project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    related_maintenance = models.ForeignKey(
        'projects.Maintenance',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    
    # Metadata
    data = models.JSONField(
        null=True,
        blank=True,
        help_text="Additional data in JSON format"
    )
    
    # Status
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['recipient', 'created_at']),
            models.Index(fields=['notification_type', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_notification_type_display()} for {self.recipient.username}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
    
    def mark_as_sent(self):
        """Mark notification as sent"""
        if not self.sent_at:
            self.sent_at = timezone.now()
            self.save(update_fields=['sent_at'])
    
    @property
    def age_in_seconds(self):
        """Get notification age in seconds"""
        return (timezone.now() - self.created_at).total_seconds()
    
    @property
    def is_urgent(self):
        """Check if notification is urgent"""
        return self.priority == self.PRIORITY_URGENT


class NotificationPreference(models.Model):
    """
    User preferences for notifications
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    
    # Notification type preferences
    enable_project_assigned = models.BooleanField(default=True)
    enable_project_starting_soon = models.BooleanField(default=True)
    enable_project_modified = models.BooleanField(default=True)
    enable_project_deleted = models.BooleanField(default=True)
    enable_maintenance_starting_soon = models.BooleanField(default=True)
    enable_maintenance_added = models.BooleanField(default=True)
    enable_maintenance_modified = models.BooleanField(default=True)
    enable_maintenance_deleted = models.BooleanField(default=True)
    
    # Sound preferences
    enable_sound = models.BooleanField(default=True)
    
    # Time preferences
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Notification Preference'
        verbose_name_plural = 'Notification Preferences'
    
    def __str__(self):
        return f"Preferences for {self.user.username}"
    
    def is_notification_enabled(self, notification_type):
        """Check if a specific notification type is enabled"""
        type_map = {
            Notification.TYPE_PROJECT_ASSIGNED: self.enable_project_assigned,
            Notification.TYPE_PROJECT_STARTING_SOON: self.enable_project_starting_soon,
            Notification.TYPE_PROJECT_MODIFIED: self.enable_project_modified,
            Notification.TYPE_PROJECT_DELETED: self.enable_project_deleted,
            Notification.TYPE_MAINTENANCE_STARTING_SOON: self.enable_maintenance_starting_soon,
            Notification.TYPE_MAINTENANCE_ADDED: self.enable_maintenance_added,
            Notification.TYPE_MAINTENANCE_MODIFIED: self.enable_maintenance_modified,
            Notification.TYPE_MAINTENANCE_DELETED: self.enable_maintenance_deleted,
        }
        return type_map.get(notification_type, True)
    
    def is_in_quiet_hours(self):
        """Check if current time is in quiet hours"""
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        
        now = timezone.now().time()
        
        if self.quiet_hours_start < self.quiet_hours_end:
            return self.quiet_hours_start <= now <= self.quiet_hours_end
        else:
            # Quiet hours span midnight
            return now >= self.quiet_hours_start or now <= self.quiet_hours_end