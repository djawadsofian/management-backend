# apps/supplier/serializers.py
from rest_framework import serializers
from django.db.models import Sum, Count, Q
from .models import Supplier, Debt
from decimal import Decimal


# In apps/supplier/serializers.py - update the DebtSerializer validate method

class DebtSerializer(serializers.ModelSerializer):
    remaining_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    payment_progress = serializers.FloatField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    days_overdue = serializers.IntegerField(read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)

    class Meta:
        model = Debt
        fields = [
            'id', 'supplier', 'supplier_name', 'description', 'date', 'due_date',
            'total_price', 'paid_price', 'remaining_amount',
            'payment_progress', 'is_paid', 'is_overdue', 'days_overdue',
            'reference_number', 'created_at', 'updated_at'
        ]
        read_only_fields = ['is_paid', 'created_at', 'updated_at']

    def validate(self, data):
        """Validate debt data with proper instance handling"""
        # Get the current instance for partial updates
        instance = getattr(self, 'instance', None)
        
        # For partial updates (PATCH), use existing values if not provided
        total_price = data.get('total_price', getattr(instance, 'total_price', None))
        paid_price = data.get('paid_price', getattr(instance, 'paid_price', Decimal('0.00')))
        
        if total_price and paid_price > total_price:
            raise serializers.ValidationError({
                "message": "Le montant payé ne peut pas dépasser le montant total"
            })
        
        due_date = data.get('due_date', getattr(instance, 'due_date', None))
        date = data.get('date', getattr(instance, 'date', None))
        
        if due_date and date and due_date < date:
            raise serializers.ValidationError({
                "message": "La date d'échéance ne peut pas être antérieure à la date de la dette"
            })
        
        return data


class SupplierSerializer(serializers.ModelSerializer):
    # Calculate these efficiently using annotations in the view
    debt_count = serializers.IntegerField(read_only=True)
    paid_debt_count = serializers.IntegerField(read_only=True)
    pending_debt_count = serializers.IntegerField(read_only=True)
    total_debt_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    total_paid_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    total_remaining_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    has_outstanding_debts = serializers.BooleanField(read_only=True)

    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'company', 'email', 'phone', 'address',
            'city', 'wilaya', 'postal_code', 'tax_id', 'website',
            'notes', 'is_active', 'debt_count', 'paid_debt_count',
            'pending_debt_count', 'total_debt_amount', 'total_paid_amount',
            'total_remaining_amount', 'has_outstanding_debts',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class SupplierDetailSerializer(SupplierSerializer):
    """Supplier serializer with debt details"""
    debts = DebtSerializer(many=True, read_only=True)

    class Meta(SupplierSerializer.Meta):
        fields = SupplierSerializer.Meta.fields + ['debts']


class DebtCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Debt
        fields = [
            'supplier', 'description', 'date', 'due_date',
            'total_price', 'paid_price', 'reference_number'
        ]

    def validate_paid_price(self, value):
        """Ensure paid_price doesn't exceed total_price"""
        total_price = self.initial_data.get('total_price')
        if total_price:
            # Convert to Decimal for proper comparison
            from decimal import Decimal
            try:
                total_price_decimal = Decimal(str(total_price))
                if value > total_price_decimal:
                    raise serializers.ValidationError(
                        "Le montant payé ne peut pas dépasser le montant total"
                    )
            except (ValueError, TypeError):
                pass  # Let other validations handle invalid data
        return value

    def validate(self, data):
        """Validate debt data with proper Decimal conversion"""
        paid_price = data.get('paid_price', Decimal('0.00'))
        total_price = data.get('total_price')
        
        if total_price and paid_price > total_price:
            raise serializers.ValidationError({
                "message": "Le montant payé ne peut pas dépasser le montant total"
            })
        
        if data.get('due_date') and data.get('date'):
            if data['due_date'] < data['date']:
                raise serializers.ValidationError({
                    "message": "La date d'échéance ne peut pas être antérieure à la date de la dette"
                })
        
        return data


class PaymentSerializer(serializers.Serializer):
    """Serializer for adding payments to debts"""
    amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        min_value=0.01
    )

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le montant doit être positif")
        return value