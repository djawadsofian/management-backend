# apps/invoices/models.py
"""
Refactored Invoice models with cleaner structure and better validation.
"""
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.core.models import TimeStampedModel
from apps.stock.services import StockService


class Invoice(TimeStampedModel):
    """
    Invoice model for tracking sales and payments.
    Supports various Algerian document types.
    """
    
    # Status constants
    STATUS_DRAFT = 'DRAFT'
    STATUS_ISSUED = 'ISSUED'
    STATUS_PAID = 'PAID'
    STATUS_CANCELLED = 'CANCELLED'
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_ISSUED, 'Issued'),
        (STATUS_PAID, 'Paid'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='invoices'
    )
    
    # Algerian document numbers
    bon_de_commande = models.CharField(max_length=100, blank=True, null=True)
    bon_de_versement = models.CharField(max_length=100, blank=True, null=True)
    bon_de_reception = models.CharField(max_length=100, blank=True, null=True)
    facture = models.CharField(max_length=100, blank=True, null=True)
    
    # Financial fields
    issued_date = models.DateField(auto_now_add=True, db_index=True)
    due_date = models.DateField(null=True, blank=True, db_index=True)
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    deposit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True
    )
    
    created_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'issued_date']),
            models.Index(fields=['due_date']),
        ]

    def __str__(self):
        doc_number = self.facture or self.bon_de_commande or f"INV-{self.id}"
        return f"{doc_number} - {self.project.name}"

    # Financial Calculations
    @property
    def subtotal(self):
        """Sum of all line items before deposit"""
        return sum(line.line_total for line in self.lines.all())

    @property
    def total_after_deposit(self):
        """Total amount after deposit deduction"""
        return self.total - self.deposit_price

    @property
    def amount_due(self):
        """Current amount due based on status"""
        if self.status in [self.STATUS_PAID, self.STATUS_CANCELLED]:
            return Decimal('0.00')
        return self.total_after_deposit

    def calculate_total(self):
        """Recalculate and save total from line items"""
        total = self.subtotal
        
        if total < 0:
            raise ValidationError("Invoice total cannot be negative")
        
        self.total = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.save(update_fields=['total', 'updated_at'])
        return self.total

    # Status Properties
    @property
    def is_overdue(self):
        """Check if invoice is overdue"""
        if self.status in [self.STATUS_PAID, self.STATUS_CANCELLED]:
            return False
        if not self.due_date:
            return False
        return self.due_date < timezone.now().date()

    @property
    def days_overdue(self):
        """Number of days overdue (0 if not overdue)"""
        if not self.is_overdue:
            return 0
        return (timezone.now().date() - self.due_date).days

    # Business Logic Methods
    def can_be_issued(self):
        """
        Validate if invoice can be issued.
        Returns (bool, str) - success flag and message
        """
        if self.status != self.STATUS_DRAFT:
            return False, "Invoice is not in draft status"
        
        if not self.lines.exists():
            return False, "Invoice has no line items"
        
        if self.total <= 0:
            return False, "Invoice total must be greater than 0"
        
        return True, "Invoice can be issued"

    def issue(self):
        """Issue a draft invoice"""
        can_issue, message = self.can_be_issued()
        if not can_issue:
            raise ValidationError(message)
        
        self.status = self.STATUS_ISSUED
        self.save(update_fields=['status', 'updated_at'])

    def mark_paid(self):
        """Mark invoice as paid"""
        if self.status not in [self.STATUS_ISSUED]:
            raise ValidationError("Only issued invoices can be marked as paid")
        
        self.status = self.STATUS_PAID
        self.save(update_fields=['status', 'updated_at'])

    def cancel(self):
        """Cancel invoice"""
        if self.status == self.STATUS_PAID:
            raise ValidationError("Cannot cancel paid invoices")
        
        self.status = self.STATUS_CANCELLED
        self.save(update_fields=['status', 'updated_at'])


class InvoiceLine(TimeStampedModel):
    """
    Individual line items on an invoice.
    Automatically manages stock when created/updated/deleted.
    """
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    product = models.ForeignKey(
        'stock.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    description = models.TextField(blank=True)
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        product_name = self.product.name if self.product else "No product"
        return f"{self.invoice} - {product_name}"

    def calculate_line_total(self):
        """Calculate line total with discount"""
        total = (self.quantity * self.unit_price) - self.discount
        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        """
        Override save to:
        1. Calculate line total
        2. Process stock changes
        3. Update invoice total
        """
        is_new = self.pk is None
        old_quantity = None
        
        # Get old quantity for existing lines
        if not is_new:
            try:
                old_line = InvoiceLine.objects.get(pk=self.pk)
                old_quantity = old_line.quantity
            except InvoiceLine.DoesNotExist:
                pass
        
        # Calculate line total
        self.line_total = self.calculate_line_total()
        
        # Save the line
        super().save(*args, **kwargs)
        
        # Process stock changes
        if self.product:
            StockService.process_invoice_line_stock(self, old_quantity)
        
        # Update invoice total
        self.invoice.calculate_total()

    def delete(self, *args, **kwargs):
        """
        Override delete to:
        1. Restore stock
        2. Update invoice total
        """
        invoice = self.invoice
        
        # Restore stock
        if self.product:
            StockService.restore_invoice_line_stock(self)
        
        # Delete the line
        super().delete(*args, **kwargs)
        
        # Update invoice total
        invoice.calculate_total()