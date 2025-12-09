# apps/invoices/serializers.py
from rest_framework import serializers
from .models import Invoice, InvoiceLine
from apps.stock.serializers import ProductSerializer
from apps.clients.serializers import ClientSerializer


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

    def validate(self, data):
        """Check if invoice is editable"""
        # Get invoice from context or instance
        invoice = self.context.get('invoice')
        if not invoice and self.instance:
            invoice = self.instance.invoice
        
        if invoice and not invoice.is_editable:
            raise serializers.ValidationError({
                "message": "Impossible de modifier les lignes d'une facture payée"
            })
        
        return data


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    client_name = serializers.CharField(source='project.client.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    client = ClientSerializer(source='project.client', read_only=True) 
    
    # Status flags
    is_draft = serializers.BooleanField(read_only=True)
    is_issued = serializers.BooleanField(read_only=True)
    is_paid = serializers.BooleanField(read_only=True)
    is_editable = serializers.BooleanField(read_only=True)
    stock_is_affected = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'project', 'project_name', 'client_name','client',
            'bon_de_commande', 'bon_de_versement', 'bon_de_reception', 'facture',
            'issued_date', 'due_date', 'paid_date',
            'subtotal', 'tva', 'tax_amount', 'total', 'deposit_price', 
            'status', 'created_by', 'created_by_name', 'created_at',
            'is_draft', 'is_issued', 'is_paid', 'is_editable', 'stock_is_affected',
            'lines','deposit_date' ,'payment_method'
        ]
        read_only_fields = ['subtotal', 'tax_amount', 'total', 'created_at', 
                           'is_draft', 'is_issued', 'is_paid', 'is_editable', 'stock_is_affected','paid_date','issued_date']


class InvoiceCreateSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, required=False)
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'project', 'bon_de_commande', 'bon_de_versement', 
            'bon_de_reception', 'facture', 'due_date', 'tva', 'deposit_price', 
            'status', 'lines','deposit_date', 'payment_method'
        ]
        read_only_fields = ['status','facture']  # Always starts as DRAFT

    def validate_status(self, value):
        """Ensure new invoices start as DRAFT"""
        if value != Invoice.STATUS_DRAFT:
            raise serializers.ValidationError({"message": "Les nouvelles factures doivent commencer en brouillon"})
        return value

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        
        # Force status to DRAFT
        validated_data['status'] = Invoice.STATUS_DRAFT
        validated_data['facture'] = Invoice.get_next_facture_number()
        
        invoice = Invoice.objects.create(**validated_data)
        
        # Create lines (won't affect stock since invoice is DRAFT)
        for line_data in lines_data:
            InvoiceLine.objects.create(invoice=invoice, **line_data)
        
        # Calculate totals
        invoice.calculate_totals()
        return invoice


class InvoiceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            'project', 'bon_de_commande', 'bon_de_versement', 
            'bon_de_reception', 'facture', 'due_date', 'tva', 'deposit_price', 'deposit_date', 'payment_method'
        ]

    def validate(self, data):
        """Validate that invoice is editable"""
        if self.instance and not self.instance.is_editable:
            raise serializers.ValidationError({
                "message": "Impossible de modifier une facture payée"
            })
        return data

    def update(self, instance, validated_data):
        """Update invoice and recalculate totals if TVA changed"""
        tva_changed = 'tva' in validated_data and validated_data['tva'] != instance.tva
        
        instance = super().update(instance, validated_data)
        
        if tva_changed:
            instance.calculate_totals()
        
        return instance


class InvoiceStatusUpdateSerializer(serializers.Serializer):
    """Serializer for status transition actions"""
    action = serializers.ChoiceField(
        choices=['issue', 'mark_paid', 'revert_to_draft'],
        help_text="Action à effectuer: issue (BROUILLON->ÉMISE), mark_paid (ÉMISE->PAYÉE), revert_to_draft (ÉMISE->BROUILLON)"
    )
    
    def validate_action(self, value):
        invoice = self.context.get('invoice')
        
        if not invoice:
            raise serializers.ValidationError({"message": "Facture non trouvée"})
        
        # Validate transitions
        if value == 'issue' and invoice.status != Invoice.STATUS_DRAFT:
            raise serializers.ValidationError({"message": "Seules les factures en brouillon peuvent être émises"})
        
        if value == 'mark_paid' and invoice.status != Invoice.STATUS_ISSUED:
            raise serializers.ValidationError({"message": "Seules les factures émises peuvent être marquées comme payées"})
        
        if value == 'revert_to_draft' and invoice.status != Invoice.STATUS_ISSUED:
            raise serializers.ValidationError({"message": "Seules les factures émises peuvent revenir au brouillon"})
        
        return value