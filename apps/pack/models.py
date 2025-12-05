# apps/pack/models.py
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from apps.core.models import TimeStampedModel


class Pack(TimeStampedModel):
    """
    Simple pack model with just a name.
    """
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Line(TimeStampedModel):
    """
    Line item for a pack - similar to InvoiceLine but simpler.
    """
    pack = models.ForeignKey(
        Pack,
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
        return f"{self.pack.name} - {product_name}"