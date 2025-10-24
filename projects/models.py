from django.db import models
from django.conf import settings
from django.utils import timezone
from clients.models import Client
from dateutil.relativedelta import relativedelta


class Project(models.Model):
    name = models.CharField(max_length=255)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='projects')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True, null=True)

 
    warranty_years = models.PositiveIntegerField(default=0)
    warranty_months = models.PositiveIntegerField(default=0)
    warranty_days = models.PositiveIntegerField(default=0)

    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_projects'
    )
    assigned_employers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='projects',
        blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_projects'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.client.name})"

    def verify(self, by_user):
        """Mark project as verified"""
        self.is_verified = True
        self.verified_at = timezone.now()
        self.verified_by = by_user
        self.save()

    @property
    def status(self):
        """Calculate project status based on dates"""
        today = timezone.now().date()
        if self.start_date > today:
            return "Upcoming"
        elif self.end_date and self.end_date < today:
            return "Completed"
        else:
            return "Active"

    @property
    def warranty_end_date(self):
        """Compute warranty end date based on start date + duration"""
        if not self.start_date:
            return None
        return self.start_date + relativedelta(
            years=self.warranty_years,
            months=self.warranty_months,
            days=self.warranty_days
        )

    @property
    def warranty_duration_display(self):
        """Human-readable display of warranty"""
        parts = []
        if self.warranty_years:
            parts.append(f"{self.warranty_years} year{'s' if self.warranty_years > 1 else ''}")
        if self.warranty_months:
            parts.append(f"{self.warranty_months} month{'s' if self.warranty_months > 1 else ''}")
        if self.warranty_days:
            parts.append(f"{self.warranty_days} day{'s' if self.warranty_days > 1 else ''}")
        return " ".join(parts) if parts else "No warranty"


class Maintenance(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='maintenances')
    duration = models.PositiveIntegerField(help_text="Duration in months")
    interval = models.PositiveIntegerField(help_text="Interval in months between maintenances")
    next_maintenance_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Maintenance for {self.project.name} (Next: {self.next_maintenance_date})"

    def save(self, *args, **kwargs):
        """Calculate next_maintenance_date if not set"""
        if not self.next_maintenance_date and self.project.start_date:
            self.next_maintenance_date = self.project.start_date + relativedelta(months=self.interval)
        super().save(*args, **kwargs)
