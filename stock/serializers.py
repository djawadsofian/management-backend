from rest_framework import serializers
from stock.models import Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'sku', 'quantity', 'unit', 'reorder_threshold', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity cannot be negative.")
        return value

    def validate_reorder_threshold(self, value):
        if value < 0:
            raise serializers.ValidationError("Reorder threshold cannot be negative.")
        return value
