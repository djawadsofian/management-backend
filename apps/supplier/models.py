# apps/supplier/models.py
from django.db import models
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db.models import Q
from apps.core.models import TimeStampedModel


class Supplier(TimeStampedModel):
    """
    Supplier model with optional contact information
    """
    name = models.CharField(max_length=255, db_index=True)
    company = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    wilaya = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    tax_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Tax ID/Matricule")
    website = models.URLField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # Status fields
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['name', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.company})" if self.company else self.name

    @property
    def total_debt_amount(self):
        """Calculate total debt amount for this supplier"""
        return sum(debt.total_price for debt in self.debts.all())

    @property
    def total_paid_amount(self):
        """Calculate total paid amount for this supplier"""
        return sum(debt.paid_price for debt in self.debts.all())

    @property
    def total_remaining_amount(self):
        """Calculate total remaining amount to pay"""
        return self.total_debt_amount - self.total_paid_amount

    @property
    def has_outstanding_debts(self):
        """Check if supplier has any outstanding debts"""
        return any(debt.remaining_amount > 0 for debt in self.debts.all())

    @property
    def debt_count(self):
        """Get total number of debts"""
        return self.debts.count()

    @property
    def paid_debt_count(self):
        """Get number of fully paid debts"""
        # FIX: Use database fields instead of property
        return self.debts.filter(
            Q(paid_price=models.F('total_price')) | 
            Q(total_price=0)
        ).count()

    @property
    def pending_debt_count(self):
        """Get number of pending debts"""
        # FIX: Use database fields instead of property
        return self.debts.filter(
            paid_price__lt=models.F('total_price')
        ).count()


class Debt(TimeStampedModel):
    """
    Debt model representing money owed to suppliers
    """
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='debts'
    )
    
    # Debt information
    description = models.TextField(help_text="Description of the debt/purchase")
    date = models.DateField(db_index=True)
    
    # Financial fields
    total_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Total amount of the debt"
    )
    
    paid_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Amount already paid"
    )
    
    # Optional reference fields
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    due_date = models.DateField(blank=True, null=True, db_index=True)
    
    # Status tracking
    is_paid = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['supplier', 'date']),
            models.Index(fields=['is_paid', 'due_date']),
        ]

    def __str__(self):
        status = "Paid" if self.is_paid else "Pending"
        return f"{self.supplier.name} - {self.description} - {self.total_price} ({status})"

    @property
    def remaining_amount(self):
        """Calculate remaining amount to pay"""
        remaining = self.total_price - self.paid_price
        return max(Decimal('0.00'), remaining)

    @property
    def payment_progress(self):
        """Calculate payment progress percentage"""
        if self.total_price == 0:
            return 100
        return (self.paid_price / self.total_price) * 100

    @property
    def is_overdue(self):
        """Check if debt is overdue"""
        if not self.due_date or self.is_paid:
            return False
        from django.utils import timezone
        return self.due_date < timezone.now().date()

    @property
    def days_overdue(self):
        """Number of days overdue (0 if not overdue)"""
        if not self.is_overdue:
            return 0
        from django.utils import timezone
        return (timezone.now().date() - self.due_date).days

    def clean(self):
        """Validate debt data"""
        from django.core.exceptions import ValidationError
        
        if self.paid_price > self.total_price:
            raise ValidationError("Paid price cannot exceed total price")
        
        if self.due_date and self.date and self.due_date < self.date:
            raise ValidationError("Due date cannot be before debt date")

    def save(self, *args, **kwargs):
        """Override save to update is_paid status and validate"""
        self.clean()
        
        # Update is_paid status
        self.is_paid = self.remaining_amount == 0
        
        super().save(*args, **kwargs)

    def mark_as_paid(self):
        """Mark debt as fully paid"""
        self.paid_price = self.total_price
        self.save()

    def add_payment(self, amount):
        """Add a payment to this debt"""
        from decimal import Decimal
        amount = Decimal(str(amount))
        
        if amount <= 0:
            raise ValueError("Payment amount must be positive")
        
        if self.paid_price + amount > self.total_price:
            raise ValueError("Payment exceeds remaining debt amount")
        
        self.paid_price += amount
        self.save()