# apps/pack/serializers.py
from rest_framework import serializers
from .models import Pack, Line
from apps.stock.serializers import ProductSerializer


class LineSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source='product', read_only=True)
    
    class Meta:
        model = Line
        fields = [
            'id', 'product', 'product_details', 'description', 
            'quantity', 'unit_price', 'discount', 'line_total', 'created_at'
        ]
        read_only_fields = ['line_total', 'created_at']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError({"message": "La quantité doit être positive"})
        return value

    def validate_unit_price(self, value):
        if value < 0:
            raise serializers.ValidationError({"message": "Le prix unitaire ne peut pas être négatif"})
        return value

    def validate_discount(self, value):
        if value < 0:
            raise serializers.ValidationError({"message": "La remise ne peut pas être négative"})
        return value


class PackSerializer(serializers.ModelSerializer):
    lines = LineSerializer(many=True, read_only=True)
    line_count = serializers.IntegerField(source='lines.count', read_only=True)
    
    class Meta:
        model = Pack
        fields = ['id', 'name', 'line_count', 'lines', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def validate_name(self, value):
        # Check for unique name
        instance = self.instance
        if instance:
            # For updates, exclude current instance
            if Pack.objects.exclude(pk=instance.pk).filter(name=value).exists():
                raise serializers.ValidationError({"message": "Un pack avec ce nom existe déjà"})
        else:
            # For creates
            if Pack.objects.filter(name=value).exists():
                raise serializers.ValidationError({"message": "Un pack avec ce nom existe déjà"})
        return value


class PackCreateSerializer(serializers.ModelSerializer):
    lines = LineSerializer(many=True, required=False)
    
    class Meta:
        model = Pack
        fields = ['id', 'name', 'lines']

    def validate_name(self, value):
        if Pack.objects.filter(name=value).exists():
            raise serializers.ValidationError({"message": "Un pack avec ce nom existe déjà"})
        return value

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        pack = Pack.objects.create(**validated_data)
        
        for line_data in lines_data:
            Line.objects.create(pack=pack, **line_data)
        
        return pack