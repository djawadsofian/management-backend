# invoices/models.py
from decimal import Decimal
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


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
        self.line_total = self.compute_line_total()
        super().save(*args, **kwargs)
        
        # Update invoice total
        self.invoice.calculate_total()

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        # Update invoice total after deletion
        invoice.calculate_total()

    def __str__(self):
        return f"{self.invoice.facture or self.invoice.bon_de_commande or 'No Number'} - {self.description or self.product.name if self.product else 'No product'}"