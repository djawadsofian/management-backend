# apps/projects/models.py
"""
Refactored Project and Maintenance models.
Improved property methods and removed redundant logic.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from apps.core.models import TimeStampedModel
from apps.clients.models import Client


class Project(TimeStampedModel):
    """
    Project model for tracking client projects.
    Includes warranty tracking and employer assignments.
    """
    
    # Status choices (derived from dates, not stored)
    STATUS_DRAFT = 'DRAFT'
    STATUS_UPCOMING = 'UPCOMING'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_COMPLETED = 'COMPLETED'

    name = models.CharField(max_length=255, db_index=True)
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='projects'
    )
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)
    description = models.TextField(blank=True,null=True)

    # Maintenance settings
    duration_maintenance = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Maintenance contract duration in months"
    )
    interval_maintenance = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Months between maintenance visits"
    )

    # Warranty period components
    warranty_years = models.PositiveIntegerField(default=0)
    warranty_months = models.PositiveIntegerField(default=0)
    warranty_days = models.PositiveIntegerField(default=0)

    # Verification tracking
    is_verified = models.BooleanField(default=False, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_projects'
    )

    # Team assignment
    assigned_employers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='assigned_projects',
        blank=True
    )

    # Audit fields
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_projects'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['is_verified', 'start_date']),
        ]

    def __str__(self):
        return f"{self.name} - {self.client.name}"

    def save(self, *args, **kwargs):
        """Override save to handle maintenance creation/update"""
        is_new = self.pk is None
        
        # Call original save first to get PK
        super().save(*args, **kwargs)
        
        # Handle maintenance creation/update
        if self.duration_maintenance and self.interval_maintenance and self.end_date:
            self._update_maintenances()

    def _update_maintenances(self):
        """Delete existing maintenances and create new ones based on current settings"""
        # Delete all existing maintenances
        self.maintenances.all().delete()
        
        # Calculate number of maintenance instances needed
        if self.interval_maintenance > 0:
            num_maintenances = self.duration_maintenance // self.interval_maintenance
        else:
            num_maintenances = 0
            
        # Create maintenance instances
        for i in range(num_maintenances):
            maintenance_number = i + 1
            months_after_project_end = self.interval_maintenance * maintenance_number
            
            start_date = self.end_date + relativedelta(months=months_after_project_end)
            
            Maintenance.objects.create(
                project=self,
                start_date=start_date,
                end_date=start_date,  # Same as start date as specified
                maintenance_number=maintenance_number
            )

    # Verification Methods
    def verify(self, by_user):
        """Mark project as verified"""
        self.is_verified = True
        self.verified_at = timezone.now()
        self.verified_by = by_user
        self.save(update_fields=['is_verified', 'verified_at', 'verified_by', 'updated_at'])

    # Status Properties
    @property
    def status(self):
        """Calculate current project status based on dates"""
        if not self.is_verified:
            return self.STATUS_DRAFT
        
        today = timezone.now().date()
        
        if self.start_date > today:
            return self.STATUS_UPCOMING
        elif self.end_date and self.end_date < today:
            return self.STATUS_COMPLETED
        else:
            return self.STATUS_ACTIVE

    @property
    def is_active(self):
        """Check if project is currently active"""
        return self.status == self.STATUS_ACTIVE

    @property
    def is_completed(self):
        """Check if project is completed"""
        return self.status == self.STATUS_COMPLETED

    # Date Calculations
    @property
    def days_until_start(self):
        """Days until project starts (negative if started)"""
        return (self.start_date - timezone.now().date()).days

    @property
    def days_until_end(self):
        """Days until project ends (negative if ended, None if no end date)"""
        if not self.end_date:
            return None
        return (self.end_date - timezone.now().date()).days

    @property
    def duration_days(self):
        """Total project duration in days"""
        if not self.end_date:
            return None
        return (self.end_date - self.start_date).days

    @property
    def progress_percentage(self):
        """Calculate project progress (0-100)"""
        if not self.end_date or self.status != self.STATUS_ACTIVE:
            return 100 if self.is_completed else 0
        
        total_days = self.duration_days
        if total_days <= 0:
            return 100
        
        days_passed = (timezone.now().date() - self.start_date).days
        return min(100, max(0, round((days_passed / total_days) * 100, 1)))

    # Warranty Properties
    @property
    def warranty_end_date(self):
        """Calculate warranty expiration date"""
        if not self.start_date:
            return None
        
        return self.start_date + relativedelta(
            years=self.warranty_years,
            months=self.warranty_months,
            days=self.warranty_days
        )

    @property
    def warranty_active(self):
        """Check if warranty is still active"""
        if not self.warranty_end_date:
            return False
        return timezone.now().date() <= self.warranty_end_date

    @property
    def warranty_display(self):
        """Human-readable warranty duration"""
        parts = []
        if self.warranty_years:
            parts.append(f"{self.warranty_years}y")
        if self.warranty_months:
            parts.append(f"{self.warranty_months}m")
        if self.warranty_days:
            parts.append(f"{self.warranty_days}d")
        return " ".join(parts) if parts else "No warranty"

    # Alert Methods
    def is_starting_soon(self, days_threshold=7):
        """Check if project starts within threshold days"""
        days = self.days_until_start
        return 0 <= days <= days_threshold

    def is_ending_soon(self, days_threshold=7):
        """Check if project ends within threshold days"""
        days = self.days_until_end
        return days is not None and 0 <= days <= days_threshold


class Maintenance(TimeStampedModel):
    """
    Maintenance schedule tracking for projects.
    Simple model with start and end dates.
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='maintenances'
    )
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    maintenance_number = models.PositiveIntegerField(
        help_text="Maintenance sequence number"
    )

    class Meta:
        ordering = ['start_date']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
        ]

    def __str__(self):
        return f"Maintenance #{self.maintenance_number} for {self.project.name}"

    @property
    def is_overdue(self):
        """Check if maintenance is overdue"""
        return self.end_date < timezone.now().date()

    @property
    def days_until_maintenance(self):
        """Days until maintenance (negative if overdue)"""
        return (self.start_date - timezone.now().date()).days