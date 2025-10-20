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