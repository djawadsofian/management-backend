from django.db import models
from django.conf import settings

class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    related_project = models.ForeignKey('projects.Project', on_delete=models.SET_NULL, null=True, blank=True)
    related_invoice = models.ForeignKey('invoices.Invoice', on_delete=models.SET_NULL, null=True, blank=True)
    message = models.TextField()  # messages will be stored in French
    is_read = models.BooleanField(default=False)
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivery_method = models.CharField(max_length=20, default='IN_APP')  # IN_APP | EMAIL | PUSH

    def mark_read(self):
        self.is_read = True
        self.save(update_fields=['is_read'])

    def __str__(self):
        return f"Notif to {self.recipient.username}: {self.message[:40]}"

