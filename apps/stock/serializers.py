# apps/stock/serializers.py
from rest_framework import serializers
from apps.stock.models import Product


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
            raise serializers.ValidationError({"message": "Quantité ne peut pas être négative"})
        return value

    def validate_reorder_threshold(self, value):
        if value < 0:
            raise serializers.ValidationError({"message": "Seuil de réapprovisionnement ne peut pas être négatif"})
        return value

    def validate_buying_price(self, value):
        if value < 0:
            raise serializers.ValidationError({"message": "Prix d'achat ne peut pas être négatif"})
        return value

    def validate_selling_price(self, value):
        if value < 0:
            raise serializers.ValidationError({"message": "Prix de vente ne peut pas être négatif"})
        return value

    def validate(self, data):
        """
        Additional validation to ensure selling price is not less than buying price
        """
        buying_price = data.get('buying_price', self.instance.buying_price if self.instance else 0)
        selling_price = data.get('selling_price', self.instance.selling_price if self.instance else 0)
        
        if buying_price and selling_price and selling_price < buying_price:
            raise serializers.ValidationError({
                "message": "Prix de vente ne peut pas être inférieur au prix d'achat"
            })
        
        return data

    def to_representation(self, instance):
        """
        Add computed fields to the representation
        """
        representation = super().to_representation(instance)
        representation['profit_margin'] = instance.profit_margin_percentage
        representation['profit_per_unit'] = float(instance.profit_per_unit)
        return representation