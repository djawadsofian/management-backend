from rest_framework import serializers
from stock.models import Product


class ProductSerializer(serializers.ModelSerializer):
    profit_margin = serializers.ReadOnlyField()  # New computed field
    profit_per_unit = serializers.ReadOnlyField()  # New computed field
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'quantity', 'unit', 'reorder_threshold',
            'buying_price', 'selling_price', 'profit_margin', 'profit_per_unit',  # New fields
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'profit_margin', 'profit_per_unit']

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity cannot be negative.")
        return value

    def validate_reorder_threshold(self, value):
        if value < 0:
            raise serializers.ValidationError("Reorder threshold cannot be negative.")
        return value

    def validate_buying_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Buying price cannot be negative.")
        return value

    def validate_selling_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Selling price cannot be negative.")
        return value

    def validate(self, data):
        """
        Additional validation to ensure selling price is not less than buying price
        """
        buying_price = data.get('buying_price', self.instance.buying_price if self.instance else 0)
        selling_price = data.get('selling_price', self.instance.selling_price if self.instance else 0)
        
        if buying_price and selling_price and selling_price < buying_price:
            raise serializers.ValidationError({
                'selling_price': 'Selling price cannot be less than buying price.'
            })
        
        return data

    def to_representation(self, instance):
        """
        Add computed fields to the representation
        """
        representation = super().to_representation(instance)
        representation['profit_margin'] = instance.calculate_profit_margin()
        representation['profit_per_unit'] = float(instance.calculate_profit_per_unit())
        return representation