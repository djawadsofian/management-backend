# invoices/models.py
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils import timezone
from stock.services import process_invoice_line_stock


class Invoice(models.Model):
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

    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='invoices')
    
    # Your requested fields - all optional
    bon_de_commande = models.CharField(max_length=100, blank=True, null=True)
    bon_de_versement = models.CharField(max_length=100, blank=True, null=True)
    bon_de_reception = models.CharField(max_length=100, blank=True, null=True)
    facture = models.CharField(max_length=100, blank=True, null=True)
    
    issued_date = models.DateField(auto_now_add=True)
    due_date = models.DateField(blank=True, null=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    deposit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def calculate_total(self):
        total = sum([line.line_total for line in self.lines.all()])
        self.total = total
        self.save(update_fields=['total'])
        return self.total

    def __str__(self):
        return f"Invoice {self.facture or self.bon_de_commande or 'No Number'} (project={self.project.name})"
    
    @property
    def subtotal(self):
        """Calculate subtotal before deposit"""
        return sum([line.line_total for line in self.lines.all()])
    
    @property
    def total_after_deposit(self):
        """Calculate total after deposit deduction"""
        return self.total - self.deposit_price
    
    @property
    def amount_due(self):
        """Calculate current amount due based on status"""
        if self.status in [self.STATUS_PAID, self.STATUS_CANCELLED]:
            return Decimal('0.00')
        return self.total_after_deposit
    
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
        """Days overdue (negative if not overdue)"""
        if not self.is_overdue:
            return 0
        return (timezone.now().date() - self.due_date).days
    
    def calculate_total(self):
        """Enhanced total calculation with validation"""
        total = sum([line.line_total for line in self.lines.all()])
        
        # Validate that total is reasonable
        if total < 0:
            raise ValidationError("Invoice total cannot be negative")
        
        self.total = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.save(update_fields=['total'])
        return self.total
    
    def apply_discount_percentage(self, percentage):
        """Apply percentage discount to all lines"""
        if percentage < 0 or percentage > 100:
            raise ValidationError("Discount percentage must be between 0 and 100")
        
        for line in self.lines.all():
            discount_amount = (line.line_total * Decimal(percentage)) / Decimal(100)
            line.discount = discount_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            line.save()
        
        self.calculate_total()
    
    def can_be_issued(self):
        """Check if invoice can be issued (business rules)"""
        if self.status != self.STATUS_DRAFT:
            return False, "Invoice is not in draft status"
        
        if not self.lines.exists():
            return False, "Invoice has no line items"
        
        if self.total <= 0:
            return False, "Invoice total must be greater than 0"
        
        return True, "Invoice can be issued"


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('stock.Product', on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)

    def compute_line_total(self):
        total = (self.quantity * self.unit_price) - self.discount
        return total.quantize(Decimal('0.01'))

    def save(self, *args, **kwargs):
        """
        Override save to handle stock updates
        """
        is_new = self.pk is None
        old_quantity = None
        
        if not is_new:
            # Get old quantity for existing line
            try:
                old_line = InvoiceLine.objects.get(pk=self.pk)
                old_quantity = old_line.quantity
            except InvoiceLine.DoesNotExist:
                pass
        
        # First save to get PK
        self.line_total = self.compute_line_total()
        super().save(*args, **kwargs)
        
        # Process stock changes after save
        if self.product:
            try:
                process_invoice_line_stock(self, old_quantity)
            except ValidationError as e:
                # If stock update fails, we might want to handle this
                # For now, we'll let it raise the exception
                raise e
        
        # Update invoice total
        self.invoice.calculate_total()

    def delete(self, *args, **kwargs):
        """
        Override delete to restore stock
        """
        invoice = self.invoice
        
        if self.product:
            # Restore stock when line is deleted
            from stock.services import update_product_stock
            try:
                update_product_stock(self.product, float(self.quantity), 'increment')
            except ValidationError as e:
                raise e
        
        super().delete(*args, **kwargs)
        
        # Update invoice total after deletion
        invoice.calculate_total()

    def __str__(self):
        return f"{self.invoice.facture or self.invoice.bon_de_commande or 'No Number'} - {self.description or self.product.name if self.product else 'No product'}"