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
        """
        Calculate project status based on dates with business rules
        """
        today = timezone.now().date()
        
        if not self.is_verified:
            return "Draft"
        elif self.start_date > today:
            return "Upcoming"
        elif self.end_date and self.end_date < today:
            return "Completed"
        elif self.start_date <= today <= (self.end_date or today):
            return "Active"
        else:
            return "Unknown"
    
    @property
    def days_until_start(self):
        """Days until project starts (negative if already started)"""
        today = timezone.now().date()
        return (self.start_date - today).days
    
    @property
    def days_until_end(self):
        """Days until project ends (negative if already ended)"""
        if not self.end_date:
            return None
        today = timezone.now().date()
        return (self.end_date - today).days
    
    @property
    def duration_days(self):
        """Project duration in days"""
        if not self.end_date:
            return None
        return (self.end_date - self.start_date).days
    
    @property
    def progress_percentage(self):
        """Calculate project progress percentage based on timeline"""
        if not self.end_date or self.status != "Active":
            return 0 if self.status != "Completed" else 100
        
        total_duration = (self.end_date - self.start_date).days
        if total_duration <= 0:
            return 100
        
        days_passed = (timezone.now().date() - self.start_date).days
        progress = min(100, max(0, (days_passed / total_duration) * 100))
        return round(progress, 1)
    
    def is_starting_soon(self, days_threshold=2):
        """Check if project starts within specified days"""
        return 0 <= self.days_until_start <= days_threshold
    
    def is_ending_soon(self, days_threshold=2):
        """Check if project ends within specified days"""
        if not self.end_date:
            return False
        return 0 <= self.days_until_end <= days_threshold

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

    def calculate_next_maintenance_date(self):
        """Calculate next maintenance date based on interval"""
        if not self.project.start_date:
            return None
        
        # Start from project start date or last maintenance date
        base_date = self.project.start_date
        
        # If we have a next_maintenance_date that's in the past, 
        # calculate from there instead
        if self.next_maintenance_date and self.next_maintenance_date < timezone.now().date():
            base_date = self.next_maintenance_date
        
        next_date = base_date + relativedelta(months=self.interval)
        return next_date
    
    def save(self, *args, **kwargs):
        """Calculate next_maintenance_date if not set or needs update"""
        if not self.next_maintenance_date or self._should_update_maintenance_date():
            self.next_maintenance_date = self.calculate_next_maintenance_date()
        
        super().save(*args, **kwargs)
    
    def _should_update_maintenance_date(self):
        """Check if maintenance date needs to be updated"""
        if not self.next_maintenance_date:
            return True
        
        # Update if the calculated date doesn't match current date
        calculated_date = self.calculate_next_maintenance_date()
        return calculated_date != self.next_maintenance_date
    
    @property
    def is_overdue(self):
        """Check if maintenance is overdue"""
        if not self.next_maintenance_date:
            return False
        return self.next_maintenance_date < timezone.now().date()
    
    @property
    def days_until_maintenance(self):
        """Days until next maintenance (negative if overdue)"""
        if not self.next_maintenance_date:
            return None
        return (self.next_maintenance_date - timezone.now().date()).days
    
    def reschedule_maintenance(self, new_date):
        """Reschedule maintenance to a new date"""
        self.next_maintenance_date = new_date
        self.save(update_fields=['next_maintenance_date', 'updated_at'])
    
    def complete_maintenance(self):
        """Mark maintenance as completed and schedule next one"""
        self.next_maintenance_date = self.calculate_next_maintenance_date()
        self.save(update_fields=['next_maintenance_date', 'updated_at'])
