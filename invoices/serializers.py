# invoices/serializers.py
from rest_framework import serializers
from .models import Invoice, InvoiceLine
from stock.models import Product
from stock.serializers import ProductSerializer


class InvoiceLineSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source='product', read_only=True)
    
    class Meta:
        model = InvoiceLine
        fields = [
            'id', 'product', 'product_details', 'description', 
            'quantity', 'unit_price', 'discount', 'line_total', 'created_at'
        ]
        read_only_fields = ['line_total', 'created_at']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be positive")
        return value

    def validate_unit_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Unit price cannot be negative")
        return value

    def validate_discount(self, value):
        if value < 0:
            raise serializers.ValidationError("Discount cannot be negative")
        return value


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    client_name = serializers.CharField(source='project.client.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'project', 'project_name', 'client_name',
            'bon_de_commande', 'bon_de_versement', 'bon_de_reception', 'facture',
            'issued_date', 'due_date', 'total', 'deposit_price', 'status',
            'created_by', 'created_by_name', 'created_at', 'lines'
        ]
        read_only_fields = ['total', 'created_at']


class InvoiceCreateSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, required=False)
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'project', 'bon_de_commande', 'bon_de_versement', 
            'bon_de_reception', 'facture', 'due_date', 'deposit_price', 
            'status', 'lines'
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        invoice = Invoice.objects.create(**validated_data)
        
        for line_data in lines_data:
            InvoiceLine.objects.create(invoice=invoice, **line_data)
            
        invoice.calculate_total()
        return invoice


class InvoiceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            'project', 'bon_de_commande', 'bon_de_versement', 
            'bon_de_reception', 'facture', 'due_date', 'deposit_price', 
            'status'
        ]