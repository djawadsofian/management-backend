# stock/services.py
from django.db import transaction
from django.db.models import F
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import Product

@transaction.atomic
def update_product_stock(product, quantity_change, action='decrement'):
    """
    Safely update product stock with row locking to prevent race conditions
    """
    if not product:
        return
        
    if quantity_change < 0:
        raise ValueError("Quantity change must be non-negative")
    
    # Lock the product row for update
    locked_product = Product.objects.select_for_update().get(pk=product.pk)
    
    if action == 'decrement':
        if locked_product.quantity < quantity_change:
            raise ValidationError(
                f"Insufficient stock for {locked_product.name}. "
                f"Available: {locked_product.quantity}, Requested: {quantity_change}"
            )
        locked_product.quantity = F('quantity') - quantity_change
    elif action == 'increment':
        locked_product.quantity = F('quantity') + quantity_change
    else:
        raise ValueError("Action must be 'increment' or 'decrement'")
    
    locked_product.save(update_fields=['quantity', 'updated_at'])
    
    # Refresh from database to get updated value
    locked_product.refresh_from_db()
    return locked_product

@transaction.atomic
def process_invoice_line_stock(invoice_line, old_quantity=None):
    """
    Process stock changes for an invoice line
    - When created: decrement stock
    - When updated: adjust stock based on quantity change
    - When deleted: increment stock
    """
    if not invoice_line.product:
        return
    
    current_quantity = float(invoice_line.quantity)
    
    if old_quantity is None:
        # New line - decrement stock
        update_product_stock(invoice_line.product, current_quantity, 'decrement')
    else:
        # Updated line - adjust stock based on difference
        old_quantity = float(old_quantity)
        quantity_diff = current_quantity - old_quantity
        
        if quantity_diff > 0:
            # Quantity increased - decrement the difference
            update_product_stock(invoice_line.product, quantity_diff, 'decrement')
        elif quantity_diff < 0:
            # Quantity decreased - increment the difference
            update_product_stock(invoice_line.product, abs(quantity_diff), 'increment')