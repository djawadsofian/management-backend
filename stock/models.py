from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=50, blank=True, null=True)
    reorder_threshold = models.PositiveIntegerField(default=10)  # alert when quantity <= threshold
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

    def __str__(self):
        return f"{self.name} (qty={self.quantity})"

