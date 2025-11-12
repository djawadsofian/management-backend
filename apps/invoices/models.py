# apps/invoices/models.py
"""
Strict Invoice models with controlled stock management.
Stock is only affected when invoice is ISSUED or PAID.
"""
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import TimeStampedModel
from apps.stock.services import StockService


class Invoice(TimeStampedModel):
    """
    Invoice model with strict stock control.
    
    Status Flow:
    - DRAFT: Lines can be created/edited, stock NOT affected
    - ISSUED: Lines can be edited, stock IS affected
    - PAID: Lines locked, no more changes allowed
    """
    
    # Status constants (removed CANCELLED)
    STATUS_DRAFT = 'DRAFT'
    STATUS_ISSUED = 'ISSUED'
    STATUS_PAID = 'PAID'
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_ISSUED, 'Issued'),
        (STATUS_PAID, 'Paid'),
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
    
    # Subtotal before tax
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # TVA (Tax) - percentage
    tva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('00.00'),  # Default 19% TVA in Algeria
        validators=[
            MinValueValidator(Decimal('0.00')),
            MaxValueValidator(Decimal('100.00'))
        ],
        help_text="Tax percentage (TVA)"
    )
    
    # Tax amount (calculated)
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Total with tax
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

    # Status Check Properties
    @property
    def is_draft(self):
        """Check if invoice is in draft status"""
        return self.status == self.STATUS_DRAFT

    @property
    def is_issued(self):
        """Check if invoice is issued"""
        return self.status == self.STATUS_ISSUED

    @property
    def is_paid(self):
        """Check if invoice is paid"""
        return self.status == self.STATUS_PAID

    @property
    def is_editable(self):
        """Check if invoice can be edited (not paid)"""
        return self.status in [self.STATUS_DRAFT, self.STATUS_ISSUED]

    @property
    def stock_is_affected(self):
        """Check if stock is currently affected by this invoice"""
        return self.status in [self.STATUS_ISSUED, self.STATUS_PAID]

    # Financial Calculations
    def calculate_totals(self):
        """
        Calculate subtotal, tax, and total from invoice lines.
        Does NOT save, call save() separately.
        """
        with transaction.atomic():
            # Lock the invoice
            locked_invoice = Invoice.objects.select_for_update().get(pk=self.pk)

            lines = locked_invoice.lines.select_for_update().all()
            lines_total = sum(line.line_total for line in lines)

             # Convert to Decimal to ensure quantize method exists
            lines_total = Decimal(lines_total)
            
            if lines_total < 0:
                raise ValidationError("Invoice subtotal cannot be negative")
            
            
            # Calculate tax amount
            tax_amount = (lines_total * locked_invoice.tva / Decimal('100.00')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            
            # Calculate total
            total = (lines_total + tax_amount).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            
            # Update values
            locked_invoice.subtotal = lines_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            locked_invoice.tax_amount = tax_amount
            locked_invoice.total = total
            locked_invoice.save(update_fields=['subtotal', 'tax_amount', 'total', 'updated_at'])
            
            # Refresh current instance
            self.refresh_from_db()

    @property
    def total_after_deposit(self):
        """Total amount after deposit deduction"""
        return self.total - self.deposit_price

    @property
    def amount_due(self):
        """Current amount due based on status"""
        if self.status == self.STATUS_PAID:
            return Decimal('0.00')
        return self.total_after_deposit

    @property
    def is_overdue(self):
        """Check if invoice is overdue"""
        if self.status == self.STATUS_PAID:
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

    # Status Transition Methods
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
        
        # Check if all products have sufficient stock
        for line in self.lines.all():
            if line.product and line.product.quantity < line.quantity:
                return False, f"Insufficient stock for {line.product.name}"
        
        return True, "Invoice can be issued"

    @transaction.atomic
    def issue(self):
        """
        Issue a draft invoice and affect stock.
        This is when stock gets deducted.
        """
        can_issue, message = self.can_be_issued()
        if not can_issue:
            raise ValidationError(message)
        
        old_status = self.status
        self.status = self.STATUS_ISSUED
        self.save(update_fields=['status', 'updated_at'])
        
        # Affect stock for all lines
        for line in self.lines.all():
            if line.product:
                StockService.adjust_stock(
                    line.product,
                    float(line.quantity),
                    'subtract'
                )

    @transaction.atomic
    def mark_paid(self):
        """Mark invoice as paid (locks editing)"""
        if self.status not in [self.STATUS_ISSUED]:
            raise ValidationError("Only issued invoices can be marked as paid")
        
        self.status = self.STATUS_PAID
        self.save(update_fields=['status', 'updated_at'])

    @transaction.atomic
    def revert_to_draft(self):
        """
        Revert invoice from ISSUED to DRAFT.
        Restores all stock that was deducted.
        """
        if self.status != self.STATUS_ISSUED:
            raise ValidationError("Only issued invoices can be reverted to draft")
        
        # Restore stock for all lines
        for line in self.lines.all():
            if line.product:
                StockService.adjust_stock(
                    line.product,
                    float(line.quantity),
                    'add'
                )
        
        self.status = self.STATUS_DRAFT
        self.save(update_fields=['status', 'updated_at'])

    def delete(self, *args, **kwargs):
        """
        Override delete to restore stock if invoice was issued/paid.
        """
        if self.stock_is_affected:
            # Restore stock before deletion
            for line in self.lines.all():
                if line.product:
                    StockService.adjust_stock(
                        line.product,
                        float(line.quantity),
                        'add'
                    )
        
        super().delete(*args, **kwargs)


class InvoiceLine(TimeStampedModel):
    """
    Individual line items on an invoice.
    Stock management depends on parent invoice status.
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

    def clean(self):
        """Validate before save"""
        # Check if invoice is editable
        if self.invoice and not self.invoice.is_editable:
            raise ValidationError("Cannot modify lines on a paid invoice")
        
        # Check stock availability if invoice is issued
        if self.invoice and self.invoice.is_issued and self.product:
            if self.pk:  # Editing existing line
                old_line = InvoiceLine.objects.get(pk=self.pk)
                old_qty = float(old_line.quantity)
                new_qty = float(self.quantity)
                qty_increase = new_qty - old_qty
                
                if qty_increase > 0:
                    # Need more stock
                    if self.product.quantity < qty_increase:
                        raise ValidationError(
                            f"Insufficient stock for {self.product.name}. "
                            f"Available: {self.product.quantity}, Additional needed: {qty_increase}"
                        )
            else:  # New line
                if self.product.quantity < float(self.quantity):
                    raise ValidationError(
                        f"Insufficient stock for {self.product.name}. "
                        f"Available: {self.product.quantity}, Requested: {self.quantity}"
                    )

    @transaction.atomic
    def save(self, *args, **kwargs):
        """
        Save line and handle stock based on invoice status.
        
        - DRAFT: No stock changes
        - ISSUED: Adjust stock immediately
        - PAID: Should not be called (validation prevents this)
        """
        self.clean()  # Validate first
        
        is_new = self.pk is None
        old_quantity = None
        
        if not is_new:
            try:
                old_line = InvoiceLine.objects.select_for_update().get(pk=self.pk)
                old_quantity = old_line.quantity
            except InvoiceLine.DoesNotExist:
                pass
        
        # Calculate line total
        self.line_total = self.calculate_line_total()
        
        # Save the line
        super().save(*args, **kwargs)
        
        # Handle stock if invoice is issued
        if self.invoice.is_issued and self.product:
            if is_new:
                # New line on issued invoice - subtract stock
                StockService.adjust_stock(
                    self.product,
                    float(self.quantity),
                    'subtract'
                )
            elif old_quantity is not None:
                # Updated line on issued invoice - adjust difference
                old_qty = float(old_quantity)
                new_qty = float(self.quantity)
                qty_diff = new_qty - old_qty
                
                if qty_diff > 0:
                    # Quantity increased - subtract more
                    StockService.adjust_stock(
                        self.product,
                        abs(qty_diff),
                        'subtract'
                    )
                elif qty_diff < 0:
                    # Quantity decreased - add back
                    StockService.adjust_stock(
                        self.product,
                        abs(qty_diff),
                        'add'
                    )
        
        # Update invoice totals
        self.invoice.calculate_totals()

    @transaction.atomic
    def delete(self, *args, **kwargs):
        """
        Delete line and restore stock if invoice is issued.
        """
        # Check if line can be deleted
        if self.invoice and not self.invoice.is_editable:
            raise ValidationError("Cannot delete lines from a paid invoice")
        
        invoice = self.invoice
        
        # Restore stock if invoice is issued
        if invoice.is_issued and self.product:
            StockService.adjust_stock(
                self.product,
                float(self.quantity),
                'add'
            )
        
        # Delete the line
        super().delete(*args, **kwargs)
        
        # Update invoice totals
        invoice.calculate_totals()