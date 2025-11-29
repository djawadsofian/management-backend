# apps/stock/services.py
"""
Service layer for stock management operations.
Handles business logic and database transactions for stock operations.
"""
from django.db import transaction
from django.db.models import F
from decimal import Decimal
from apps.core.exceptions import InsufficientStockError


class StockService:
    """
    Service class for managing product stock operations.
    Centralizes stock management logic with proper error handling.
    """

    @staticmethod
    @transaction.atomic
    def adjust_stock(product, quantity, operation='subtract'):
        """
        Adjust product stock with row-level locking to prevent race conditions.
        
        Args:
            product: Product instance or product ID
            quantity: Amount to adjust (float/int)
            operation: 'subtract' or 'add'
        
        Returns:
            Updated Product instance
        
        Raises:
            InsufficientStockError: If trying to subtract more than available
            ValueError: If invalid parameters provided
        """
        from apps.stock.models import Product
        from django.db.models import F
        
        # Convert quantity to absolute value
        quantity = abs(Decimal(str(quantity)))
        
        if quantity == 0:
            return product
        
        # Get product with lock
        if isinstance(product, int):
            product = Product.objects.select_for_update().get(pk=product)
        else:
            product = Product.objects.select_for_update().get(pk=product.pk)
        
        # Perform operation using direct update to avoid F expression issues
        if operation == 'subtract':
            if product.quantity < quantity:
                raise InsufficientStockError(
                    f"Insufficient stock for {product.name}. "
                    f"Available: {product.quantity}, Requested: {quantity}"
                )
            
            # Use direct update instead of F expression
            if quantity > 0:
                Product.objects.filter(pk=product.pk).update(
                    quantity=F('quantity') - quantity
                )
            
        elif operation == 'add':
            # Use direct update instead of F expression
            if quantity > 0:
                Product.objects.filter(pk=product.pk).update(
                    quantity=F('quantity') + quantity
                )
        else:
            raise ValueError("Operation must be 'subtract' or 'add'")
        
        product.refresh_from_db()
        
        return product

    @staticmethod
    @transaction.atomic
    def process_invoice_line_stock(invoice_line, old_quantity=None):
        """
        Process stock changes for an invoice line.
        Handles creation, updates, and quantity adjustments.
        
        Args:
            invoice_line: InvoiceLine instance
            old_quantity: Previous quantity (for updates)
        """
        if not invoice_line.product:
            return
        
        current_quantity = float(invoice_line.quantity)
        
        if old_quantity is None:
            # New invoice line - subtract stock
            StockService.adjust_stock(
                invoice_line.product,
                current_quantity,
                'subtract'
            )
        else:
            # Updated invoice line - adjust the difference
            old_quantity = float(old_quantity)
            quantity_diff = current_quantity - old_quantity
            
            if quantity_diff > 0:
                # Quantity increased - subtract more
                StockService.adjust_stock(
                    invoice_line.product,
                    abs(quantity_diff),
                    'subtract'
                )
            elif quantity_diff < 0:
                # Quantity decreased - add back
                StockService.adjust_stock(
                    invoice_line.product,
                    abs(quantity_diff),
                    'add'
                )

    @staticmethod
    @transaction.atomic
    def restore_invoice_line_stock(invoice_line):
        """
        Restore stock when an invoice line is deleted.
        
        Args:
            invoice_line: InvoiceLine instance being deleted
        """
        if invoice_line.product:
            StockService.adjust_stock(
                invoice_line.product,
                float(invoice_line.quantity),
                'add'
            )

    @staticmethod
    def get_low_stock_products(threshold=None):
        """
        Get products with low stock levels.
        
        Args:
            threshold: Custom threshold (uses product's reorder_threshold if None)
        
        Returns:
            QuerySet of low stock products
        """
        from apps.stock.models import Product
        
        if threshold:
            return Product.objects.filter(quantity__lte=threshold)
        return Product.objects.filter(quantity__lte=F('reorder_threshold'))

    @staticmethod
    def get_out_of_stock_products():
        """Get products that are completely out of stock"""
        from apps.stock.models import Product
        return Product.objects.filter(quantity=0)

    @staticmethod
    def bulk_update_prices(products_data):
        """
        Bulk update product prices.
        
        Args:
            products_data: List of dicts with 'id', 'buying_price', 'selling_price'
        
        Returns:
            List of updated Product instances
        """
        from apps.stock.models import Product
        
        updated_products = []
        for data in products_data:
            product = Product.objects.get(pk=data['id'])
            product.update_prices(
                buying_price=data.get('buying_price'),
                selling_price=data.get('selling_price'),
                margin_percentage=data.get('margin_percentage')
            )
            updated_products.append(product)
        
        return updated_products