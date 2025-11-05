# apps/stock/models.py
"""
Refactored Product model with cleaner property methods.
Removed redundant methods and improved code organization.
"""
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.core.validators import MinValueValidator
from apps.core.models import TimeStampedModel


class Product(TimeStampedModel):
    """
    Product model for inventory management.
    Tracks stock levels, pricing, and automatically calculates profit metrics.
    """
    name = models.CharField(max_length=255, db_index=True)
    sku = models.CharField(max_length=100, unique=True, null=True, blank=True, db_index=True)
    quantity = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=50, blank=True)
    reorder_threshold = models.PositiveIntegerField(
        default=10,
        help_text="Alert when quantity falls below this threshold"
    )
    buying_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['quantity', 'reorder_threshold']),
        ]

    def __str__(self):
        return f"{self.name} (qty={self.quantity})"

    # Stock Management Methods
    def adjust_quantity(self, amount: int, operation: str = 'add'):
        """
        Adjust stock quantity with validation.
        
        Args:
            amount: Quantity to adjust (positive integer)
            operation: 'add' or 'subtract'
        
        Raises:
            ValueError: If amount is invalid or insufficient stock
        """
        if amount < 0:
            raise ValueError("Amount must be non-negative")
        
        if operation == 'subtract':
            if amount > self.quantity:
                raise ValueError(
                    f"Insufficient stock. Available: {self.quantity}, Requested: {amount}"
                )
            self.quantity -= amount
        elif operation == 'add':
            self.quantity += amount
        else:
            raise ValueError("Operation must be 'add' or 'subtract'")
        
        self.save(update_fields=['quantity', 'updated_at'])

    # Stock Status Properties
    @property
    def is_low_stock(self):
        """Check if stock is at or below reorder threshold"""
        return self.quantity <= self.reorder_threshold

    @property
    def is_out_of_stock(self):
        """Check if completely out of stock"""
        return self.quantity == 0

    @property
    def stock_status(self):
        """Get human-readable stock status"""
        if self.is_out_of_stock:
            return 'OUT_OF_STOCK'
        elif self.is_low_stock:
            return 'LOW_STOCK'
        return 'IN_STOCK'

    # Financial Properties
    @property
    def profit_per_unit(self):
        """Calculate profit per unit sold"""
        return (self.selling_price - self.buying_price).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    @property
    def profit_margin_percentage(self):
        """Calculate profit margin as percentage"""
        if self.buying_price == 0:
            return Decimal('0.00')
        
        margin = ((self.selling_price - self.buying_price) / self.buying_price) * 100
        return margin.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def stock_value(self):
        """Calculate total value of current stock at buying price"""
        return (self.quantity * self.buying_price).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    @property
    def potential_revenue(self):
        """Calculate potential revenue if all stock sold"""
        return (self.quantity * self.selling_price).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    @property
    def potential_profit(self):
        """Calculate potential profit if all stock sold"""
        return self.potential_revenue - self.stock_value

    # Pricing Management
    def update_prices(self, buying_price=None, selling_price=None, margin_percentage=None):
        """
        Update product pricing with validation.
        
        Args:
            buying_price: New buying price
            selling_price: New selling price
            margin_percentage: Calculate selling price from margin
        """
        if buying_price is not None:
            self.buying_price = Decimal(str(buying_price))
        
        if selling_price is not None:
            self.selling_price = Decimal(str(selling_price))
        elif margin_percentage is not None and buying_price is not None:
            self.selling_price = (
                self.buying_price * (1 + Decimal(str(margin_percentage)) / 100)
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        self.save(update_fields=['buying_price', 'selling_price', 'updated_at'])