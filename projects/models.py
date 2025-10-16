from django.db import models
from django.conf import settings

class Project(models.Model):
    name = models.CharField(max_length=255)
    client = models.ForeignKey('clients.Client', on_delete=models.PROTECT, related_name='projects')
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=100, blank=True)  # project type/category
    warranty_duration = models.PositiveIntegerField(default=0)  # months
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_verified = models.BooleanField(default=False)
    assigned_employers = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='assigned_projects', blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def verify(self, verifier=None):
        self.is_verified = True
        self.save(update_fields=['is_verified', 'updated_at'])
        # notifier logic will be implemented in services/signals

    def __str__(self):
        return f"{self.name} ({self.client.name})"

class Maintenance(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='maintenances')
    duration_months = models.PositiveIntegerField()  # total duration
    interval_months = models.PositiveIntegerField()  # e.g., every X months
    next_maintenance_date = models.DateField()
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Maint {self.project.name} next={self.next_maintenance_date}"
