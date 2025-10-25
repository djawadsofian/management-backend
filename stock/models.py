from decimal import ROUND_HALF_UP, Decimal
from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=50, blank=True, null=True)
    reorder_threshold = models.PositiveIntegerField(default=10)  # alert when quantity <= threshold
    buying_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # New field
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # New field
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def decrement(self, amount: int):
        if amount < 0:
            raise ValueError("Amount must be non-negative")
        if amount > self.quantity:
            raise ValueError("Not enough stock")
        self.quantity -= amount
        self.save(update_fields=['quantity', 'updated_at'])

    def increment(self, amount: int):
        if amount < 0:
            raise ValueError("Amount must be non-negative")
        self.quantity += amount
        self.save(update_fields=['quantity', 'updated_at'])

    def is_low_stock(self):
        return self.quantity <= self.reorder_threshold

    def calculate_profit_margin(self):
        """Calculate profit margin percentage"""
        if self.buying_price == 0:
            return 0
        return ((self.selling_price - self.buying_price) / self.buying_price) * 100

    def calculate_profit_per_unit(self):
        """Calculate profit per unit"""
        return self.selling_price - self.buying_price

    def __str__(self):
        return f"{self.name} (qty={self.quantity})"
    @property
    def stock_value(self):
        """Calculate total stock value"""
        return self.quantity * self.buying_price
    
    @property
    def potential_revenue(self):
        """Calculate potential revenue if all stock sold"""
        return self.quantity * self.selling_price
    
    @property
    def potential_profit(self):
        """Calculate potential profit if all stock sold"""
        return self.potential_revenue - self.stock_value
    
    def calculate_profit_margin(self):
        """Calculate profit margin percentage with validation"""
        if self.buying_price == 0:
            return Decimal('0.00')
        
        margin = ((self.selling_price - self.buying_price) / self.buying_price) * 100
        return margin.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def calculate_profit_per_unit(self):
        """Calculate profit per unit with validation"""
        profit = self.selling_price - self.buying_price
        return profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def update_pricing(self, new_buying_price=None, new_selling_price=None, margin_percentage=None):
        """Update pricing with different strategies"""
        if new_buying_price is not None:
            self.buying_price = new_buying_price
        
        if new_selling_price is not None:
            self.selling_price = new_selling_price
        elif margin_percentage is not None and new_buying_price is not None:
            # Calculate selling price based on desired margin
            self.selling_price = new_buying_price * (1 + Decimal(margin_percentage) / 100)
            self.selling_price = self.selling_price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        self.save(update_fields=['buying_price', 'selling_price', 'updated_at'])
    
    def get_stock_status(self):
        """Get detailed stock status"""
        if self.quantity == 0:
            return "out_of_stock"
        elif self.quantity <= self.reorder_threshold:
            return "low_stock"
        else:
            return "in_stock"