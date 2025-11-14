# apps/invoices/tests.py
"""
Invoices app tests - CRITICAL testing for stock management and invoice workflows
This is the most important test file as invoices directly affect stock
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from decimal import Decimal
from datetime import date, timedelta
from django.db import transaction
from django.core.exceptions import ValidationError

from apps.invoices.models import Invoice, InvoiceLine
from apps.projects.models import Project
from apps.clients.models import Client
from apps.stock.models import Product

User = get_user_model()


class InvoiceModelTests(TestCase):
    """Test Invoice model - CRITICAL stock management tests"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        self.client = Client.objects.create(
            name='Test Client',
            phone_number='0555123456'
        )
        
        self.project = Project.objects.create(
            name='Test Project',
            client=self.client,
            start_date=date.today(),
            created_by=self.user
        )
        
        self.product = Product.objects.create(
            name='Test Product',
            sku='SKU-001',
            quantity=100,
            buying_price=Decimal('50.00'),
            selling_price=Decimal('75.00')
        )
    
    def test_create_invoice_draft(self):
        """Test creating invoice in DRAFT status"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        self.assertEqual(invoice.status, Invoice.STATUS_DRAFT)
        self.assertTrue(invoice.is_draft)
        self.assertTrue(invoice.is_editable)
        self.assertFalse(invoice.stock_is_affected)
    
    def test_invoice_calculate_totals(self):
        """Test invoice total calculations"""
        invoice = Invoice.objects.create(
            project=self.project,
            tva=Decimal('19.00'),
            created_by=self.user
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('10'),
            unit_price=Decimal('100.00'),
            discount=Decimal('50.00')
        )
        
        invoice.calculate_totals()
        
        # (10 * 100) - 50 = 950
        self.assertEqual(invoice.subtotal, Decimal('950.00'))
        # 950 * 0.19 = 180.50
        self.assertEqual(invoice.tax_amount, Decimal('180.50'))
        # 950 + 180.50 = 1130.50
        self.assertEqual(invoice.total, Decimal('1130.50'))
    
    def test_invoice_status_issue_success(self):
        """Test issuing invoice - CRITICAL stock test"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('30'),
            unit_price=Decimal('75.00')
        )
        
        initial_stock = self.product.quantity
        
        invoice.issue()
        
        self.assertEqual(invoice.status, Invoice.STATUS_ISSUED)
        self.assertTrue(invoice.stock_is_affected)
        
        # Check stock was deducted
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, initial_stock - 30)
    
    def test_invoice_issue_insufficient_stock(self):
        """Test issuing invoice with insufficient stock - CRITICAL"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        # Try to use more than available
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('150'),  # More than 100 available
            unit_price=Decimal('75.00')
        )
        
        with self.assertRaises(ValidationError):
            invoice.issue()
        
        # Stock should not be affected
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 100)
    
    def test_invoice_mark_paid(self):
        """Test marking invoice as paid"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('10'),
            unit_price=Decimal('75.00')
        )
        
        invoice.issue()
        invoice.mark_paid()
        
        self.assertEqual(invoice.status, Invoice.STATUS_PAID)
        self.assertTrue(invoice.is_paid)
        self.assertFalse(invoice.is_editable)
    
    def test_invoice_revert_to_draft(self):
        """Test reverting invoice to draft - CRITICAL stock restore test"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('20'),
            unit_price=Decimal('75.00')
        )
        
        invoice.issue()
        
        # Stock should be 80 now
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 80)
        
        # Revert to draft
        invoice.revert_to_draft()
        
        self.assertEqual(invoice.status, Invoice.STATUS_DRAFT)
        
        # Stock should be restored to 100
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 100)
    
    def test_invoice_delete_restores_stock(self):
        """Test deleting issued invoice restores stock - CRITICAL"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('25'),
            unit_price=Decimal('75.00')
        )
        
        invoice.issue()
        
        # Stock should be 75
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 75)
        
        # Delete invoice
        invoice.delete()
        
        # Stock should be restored to 100
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 100)
    
    def test_invoice_cannot_mark_paid_from_draft(self):
        """Test cannot mark DRAFT invoice as paid"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        with self.assertRaises(ValidationError):
            invoice.mark_paid()
    
    def test_invoice_without_lines_cannot_issue(self):
        """Test cannot issue invoice without lines"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        with self.assertRaises(ValidationError):
            invoice.issue()


class InvoiceLineModelTests(TestCase):
    """Test InvoiceLine model - CRITICAL stock interaction tests"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        self.client = Client.objects.create(
            name='Test Client',
            phone_number='0555123456'
        )
        
        self.project = Project.objects.create(
            name='Test Project',
            client=self.client,
            start_date=date.today(),
            created_by=self.user
        )
        
        self.product = Product.objects.create(
            name='Test Product',
            sku='SKU-001',
            quantity=100,
            buying_price=Decimal('50.00'),
            selling_price=Decimal('75.00')
        )
    
    def test_create_line_on_draft_invoice(self):
        """Test creating line on DRAFT invoice - no stock change"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        initial_stock = self.product.quantity
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('10'),
            unit_price=Decimal('75.00')
        )
        
        # Stock should not change on DRAFT
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, initial_stock)
    
    def test_create_line_on_issued_invoice(self):
        """Test creating line on ISSUED invoice - immediate stock change"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        
        # First line - subtracts 20
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('20'),
            unit_price=Decimal('75.00')
        )
        
        invoice.issue()  # Stock becomes 80 (100-20)
        
        initial_stock = self.product.quantity  # This is 80, not 100!
        
        # Add second line - subtracts 15 more
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('15'),
            unit_price=Decimal('75.00')
        )
        
        # Stock should be 80 - 15 = 65 (CORRECT!)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 65)  # Fix the assertion
    
    def test_update_line_on_issued_invoice(self):
        """Test updating line on ISSUED invoice - stock adjustment"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        line = InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('20'),
            unit_price=Decimal('75.00')
        )
        
        invoice.issue()
        
        # Stock should be 80
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 80)
        
        # Increase quantity
        line.quantity = Decimal('30')
        line.save()
        
        # Stock should decrease by 10 more
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 70)
    
    def test_decrease_line_quantity_on_issued_invoice(self):
        """Test decreasing line quantity on ISSUED invoice"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        line = InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('50'),
            unit_price=Decimal('75.00')
        )
        
        invoice.issue()
        
        # Stock should be 50
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 50)
        
        # Decrease quantity
        line.quantity = Decimal('30')
        line.save()
        
        # Stock should increase by 20
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 70)
    
    def test_delete_line_from_issued_invoice(self):
        """Test deleting line from ISSUED invoice restores stock"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        line = InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('40'),
            unit_price=Decimal('75.00')
        )
        
        invoice.issue()
        
        # Stock should be 60
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 60)
        
        # Delete line
        line.delete()
        
        # Stock should be restored
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 100)
    
    def test_cannot_modify_line_on_paid_invoice(self):
        """Test cannot modify line on PAID invoice"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        line = InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('10'),
            unit_price=Decimal('75.00')
        )
        
        invoice.issue()
        invoice.mark_paid()
        
        # Try to update
        line.quantity = Decimal('20')
        
        with self.assertRaises(ValidationError):
            line.save()
    
    def test_line_total_calculation(self):
        """Test line total calculation with discount"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.user
        )
        
        line = InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('10'),
            unit_price=Decimal('100.00'),
            discount=Decimal('150.00')
        )
        
        # (10 * 100) - 150 = 850
        self.assertEqual(line.line_total, Decimal('850.00'))


class InvoiceViewSetTests(APITestCase):
    """Test InvoiceViewSet endpoints - CRITICAL API tests"""
    
    def setUp(self):
        """Set up test data"""
        self.client_api = APIClient()
        
        self.admin = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        self.employer = User.objects.create_user(
            username='employer',
            password='pass123',
            role=User.ROLE_EMPLOYER
        )
        
        self.test_client = Client.objects.create(
            name='Test Client',
            phone_number='0555123456'
        )
        
        self.project = Project.objects.create(
            name='Test Project',
            client=self.test_client,
            start_date=date.today(),
            created_by=self.admin
        )
        
        self.product = Product.objects.create(
            name='Test Product',
            sku='SKU-001',
            quantity=100,
            buying_price=Decimal('50.00'),
            selling_price=Decimal('75.00')
        )
        
        self.url = reverse('invoice-list')
    
    def test_create_invoice_as_admin(self):
        """Test creating invoice as admin"""
        self.client_api.force_authenticate(user=self.admin)
        data = {
            'project': self.project.id,
            'tva': '19.00',
            'due_date': (date.today() + timedelta(days=30)).isoformat()
        }
        
        response = self.client_api.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Invoice.objects.count(), 1)
        invoice = Invoice.objects.first()
        self.assertEqual(invoice.status, Invoice.STATUS_DRAFT)
    
    def test_create_invoice_with_lines(self):
        """Test creating invoice with lines"""
        self.client_api.force_authenticate(user=self.admin)
        data = {
            'project': self.project.id,
            'tva': '19.00',
            'lines': [
                {
                    'product': self.product.id,
                    'quantity': '10',
                    'unit_price': '75.00',
                    'discount': '0.00'
                }
            ]
        }
        
        response = self.client_api.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        invoice = Invoice.objects.first()
        self.assertEqual(invoice.lines.count(), 1)
    
    def test_issue_invoice_endpoint(self):
        """Test issuing invoice via API"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('20'),
            unit_price=Decimal('75.00')
        )
        
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('invoice-update-status', kwargs={'pk': invoice.id})
        data = {'action': 'issue'}
        
        response = self.client_api.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.STATUS_ISSUED)
        
        # Check stock
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 80)
    
    def test_mark_paid_endpoint(self):
        """Test marking invoice as paid via API"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('10'),
            unit_price=Decimal('75.00')
        )
        
        invoice.issue()
        
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('invoice-update-status', kwargs={'pk': invoice.id})
        data = {'action': 'mark_paid'}
        
        response = self.client_api.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.STATUS_PAID)
    
    def test_add_line_to_invoice_endpoint(self):
        """Test adding line to invoice via API"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('invoice-add-line', kwargs={'pk': invoice.id})
        data = {
            'product': self.product.id,
            'quantity': '15',
            'unit_price': '75.00'
        }
        
        response = self.client_api.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(invoice.lines.count(), 1)
    
    def test_add_bulk_lines_endpoint(self):
        """Test adding multiple lines at once"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        
        product2 = Product.objects.create(
            name='Product 2',
            sku='SKU-002',
            quantity=50
        )
        
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('invoice-add-lines', kwargs={'pk': invoice.id})
        data = [
            {
                'product': self.product.id,
                'quantity': '10',
                'unit_price': '75.00'
            },
            {
                'product': product2.id,
                'quantity': '5',
                'unit_price': '100.00'
            }
        ]
        
        response = self.client_api.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(invoice.lines.count(), 2)
    
    def test_cannot_add_line_to_paid_invoice(self):
        """Test cannot add line to PAID invoice"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('10'),
            unit_price=Decimal('75.00')
        )
        
        invoice.issue()
        invoice.mark_paid()
        
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('invoice-add-line', kwargs={'pk': invoice.id})
        data = {
            'product': self.product.id,
            'quantity': '5',
            'unit_price': '75.00'
        }
        
        response = self.client_api.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class InvoiceCriticalEdgeCaseTests(APITestCase):
    """CRITICAL edge case tests - potential 500 errors"""
    
    def setUp(self):
        """Set up test data"""
        self.client_api = APIClient()
        
        self.admin = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        self.test_client = Client.objects.create(
            name='Test Client',
            phone_number='0555123456'
        )
        
        self.project = Project.objects.create(
            name='Test Project',
            client=self.test_client,
            start_date=date.today(),
            created_by=self.admin
        )
        
        self.product = Product.objects.create(
            name='Test Product',
            quantity=10,
            buying_price=Decimal('50.00'),
            selling_price=Decimal('75.00')
        )
    
    def test_issue_invoice_exact_stock_match(self):
        """Test issuing invoice with exact stock amount"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('10'),  # Exactly all stock
            unit_price=Decimal('75.00')
        )
        
        invoice.issue()
        
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 0)
    
    def test_issue_invoice_one_more_than_stock(self):
        """Test issuing invoice with one unit more than stock"""
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('11'),  # One more than available
            unit_price=Decimal('75.00')
        )
        
        with self.assertRaises(ValidationError):
            invoice.issue()
    
    def test_concurrent_invoice_issuing_same_product(self):
        """Test concurrent invoice issuing depleting same stock"""
        invoice1 = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        invoice2 = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        
        InvoiceLine.objects.create(
            invoice=invoice1,
            product=self.product,
            quantity=Decimal('6'),
            unit_price=Decimal('75.00')
        )
        
        InvoiceLine.objects.create(
            invoice=invoice2,
            product=self.product,
            quantity=Decimal('6'),
            unit_price=Decimal('75.00')
        )
        
        # First should succeed
        invoice1.issue()
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 4)
        
        # Second should fail (not enough stock)
        with self.assertRaises(ValidationError):
            invoice2.issue()
    
    def test_delete_issued_invoice_multiple_products(self):
        """Test deleting invoice with multiple products restores all stock"""
        product2 = Product.objects.create(
            name='Product 2',
            quantity=20
        )
        
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=Decimal('5'),
            unit_price=Decimal('75.00')
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            product=product2,
            quantity=Decimal('10'),
            unit_price=Decimal('100.00')
        )
        
        invoice.issue()
        
        # Check stocks
        self.product.refresh_from_db()
        product2.refresh_from_db()
        self.assertEqual(self.product.quantity, 5)
        self.assertEqual(product2.quantity, 10)
        
        # Delete invoice
        invoice.delete()
        
        # All stock should be restored
        self.product.refresh_from_db()
        product2.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)
        self.assertEqual(product2.quantity, 20)
    
    def test_invoice_with_zero_quantity_line(self):
        """Test creating line with zero quantity"""
        self.client_api.force_authenticate(user=self.admin)
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        
        url = reverse('invoice-add-line', kwargs={'pk': invoice.id})
        data = {
            'product': self.product.id,
            'quantity': '0',
            'unit_price': '75.00'
        }
        
        response = self.client_api.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_invoice_with_negative_discount(self):
        """Test creating line with negative discount"""
        self.client_api.force_authenticate(user=self.admin)
        invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.admin
        )
        
        url = reverse('invoice-add-line', kwargs={'pk': invoice.id})
        data = {
            'product': self.product.id,
            'quantity': '5',
            'unit_price': '75.00',
            'discount': '-10.00'
        }
        
        response = self.client_api.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)