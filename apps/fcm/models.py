# apps/fcm/models.py
from django.db import models
from django.conf import settings

class FCMDevice(models.Model):
    """
    Store FCM device tokens for users
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='fcm_devices'
    )
    registration_id = models.TextField(
        verbose_name="FCM Token",
        unique=True
    )
    device_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Unique device identifier"
    )
    device_type = models.CharField(
        max_length=50,
        default='android',
        choices=[
            ('android', 'Android'),
            ('ios', 'iOS'),
            ('web', 'Web'),
        ]
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'FCM Device'
        verbose_name_plural = 'FCM Devices'
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['registration_id']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.device_type} ({self.device_id or 'N/A'})"