# core/business_rules.py
from django.core.exceptions import ValidationError
from decimal import Decimal

from pytz import timezone

class BusinessRules:
    @staticmethod
    def validate_invoice_status_change(current_status, new_status):
        """Validate invoice status transitions"""
        allowed_transitions = {
            'DRAFT': ['ISSUED', 'CANCELLED'],
            'ISSUED': ['PAID', 'CANCELLED'],
            'PAID': ['CANCELLED'],  # Might want to restrict this
            'CANCELLED': []  # Usually final
        }
        
        if new_status not in allowed_transitions.get(current_status, []):
            raise ValidationError(
                f"Cannot change status from {current_status} to {new_status}"
            )
    
    @staticmethod
    def validate_project_dates(start_date, end_date):
        """Validate project date logic"""
        if end_date and end_date < start_date:
            raise ValidationError("End date cannot be before start date")
        
        if start_date < timezone.now().date():
            raise ValidationError("Start date cannot be in the past")
    
    @staticmethod
    def validate_product_quantity(quantity, reorder_threshold):
        """Validate product quantity logic"""
        if quantity < 0:
            raise ValidationError("Quantity cannot be negative")
        
        if reorder_threshold < 0:
            raise ValidationError("Reorder threshold cannot be negative")
    
    @staticmethod
    def validate_pricing(buying_price, selling_price):
        """Validate pricing logic"""
        if buying_price < 0:
            raise ValidationError("Buying price cannot be negative")
        
        if selling_price < 0:
            raise ValidationError("Selling price cannot be negative")
        
        if selling_price < buying_price:
            # Allow this but maybe log as warning
            pass