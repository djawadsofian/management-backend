# apps/stock/tests.py
"""
Stock app tests - Testing product models, stock management, and services
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from decimal import Decimal
from apps.stock.models import Product
from apps.stock.services import StockService
from apps.core.exceptions import InsufficientStockError

User = get_user_model()


class ProductModelTests(TestCase):
    """Test Product model"""
    
    def test_create_product_minimal(self):
        """Test creating product with minimal fields"""
        product = Product.objects.create(
            name='Test Product',
            quantity=100
        )
        
        self.assertEqual(product.name, 'Test Product')
        self.assertEqual(product.quantity, 100)
        self.assertEqual(product.reorder_threshold, 10)
    
    def test_create_product_full(self):
        """Test creating product with all fields"""
        product = Product.objects.create(
            name='Full Product',
            sku='SKU-12345',
            quantity=50,
            unit='pcs',
            reorder_threshold=20,
            buying_price=Decimal('100.00'),
            selling_price=Decimal('150.00')
        )
        
        self.assertEqual(product.sku, 'SKU-12345')
        self.assertEqual(product.unit, 'pcs')
        self.assertEqual(product.buying_price, Decimal('100.00'))
        self.assertEqual(product.selling_price, Decimal('150.00'))
    
    def test_product_profit_calculations(self):
        """Test product profit calculation properties"""
        product = Product.objects.create(
            name='Profit Product',
            quantity=10,
            buying_price=Decimal('100.00'),
            selling_price=Decimal('150.00')
        )
        
        self.assertEqual(product.profit_per_unit, Decimal('50.00'))
        self.assertEqual(product.profit_margin_percentage, Decimal('50.00'))
        self.assertEqual(product.stock_value, Decimal('1000.00'))
        self.assertEqual(product.potential_revenue, Decimal('1500.00'))
        self.assertEqual(product.potential_profit, Decimal('500.00'))
    
    def test_product_stock_status(self):
        """Test product stock status properties"""
        # Out of stock
        product1 = Product.objects.create(
            name='Out of Stock',
            quantity=0
        )
        self.assertTrue(product1.is_out_of_stock)
        self.assertEqual(product1.stock_status, 'OUT_OF_STOCK')
        
        # Low stock
        product2 = Product.objects.create(
            name='Low Stock',
            quantity=5,
            reorder_threshold=10
        )
        self.assertTrue(product2.is_low_stock)
        self.assertEqual(product2.stock_status, 'LOW_STOCK')
        
        # In stock
        product3 = Product.objects.create(
            name='In Stock',
            quantity=50,
            reorder_threshold=10
        )
        self.assertFalse(product3.is_low_stock)
        self.assertEqual(product3.stock_status, 'IN_STOCK')
    
    def test_adjust_quantity_add(self):
        """Test adding quantity to product"""
        product = Product.objects.create(
            name='Test Product',
            quantity=10
        )
        
        product.adjust_quantity(5, 'add')
        
        self.assertEqual(product.quantity, 15)
    
    def test_adjust_quantity_subtract(self):
        """Test subtracting quantity from product"""
        product = Product.objects.create(
            name='Test Product',
            quantity=10
        )
        
        product.adjust_quantity(3, 'subtract')
        
        self.assertEqual(product.quantity, 7)
    
    def test_adjust_quantity_insufficient_stock(self):
        """Test subtracting more than available quantity"""
        product = Product.objects.create(
            name='Test Product',
            quantity=5
        )
        
        with self.assertRaises(ValueError) as context:
            product.adjust_quantity(10, 'subtract')
        
        self.assertIn('Insufficient stock', str(context.exception))
    
    def test_adjust_quantity_invalid_operation(self):
        """Test adjusting quantity with invalid operation"""
        product = Product.objects.create(
            name='Test Product',
            quantity=10
        )
        
        with self.assertRaises(ValueError):
            product.adjust_quantity(5, 'invalid')
    
    def test_update_prices(self):
        """Test updating product prices"""
        product = Product.objects.create(
            name='Test Product',
            quantity=10,
            buying_price=Decimal('100.00'),
            selling_price=Decimal('150.00')
        )
        
        product.update_prices(
            buying_price=Decimal('120.00'),
            selling_price=Decimal('180.00')
        )
        
        self.assertEqual(product.buying_price, Decimal('120.00'))
        self.assertEqual(product.selling_price, Decimal('180.00'))
    
    def test_update_prices_with_margin(self):
        """Test updating prices with margin percentage"""
        product = Product.objects.create(
            name='Test Product',
            quantity=10
        )
        
        product.update_prices(
            buying_price=Decimal('100.00'),
            margin_percentage=50
        )
        
        self.assertEqual(product.buying_price, Decimal('100.00'))
        self.assertEqual(product.selling_price, Decimal('150.00'))


class StockServiceTests(TestCase):
    """Test StockService"""
    
    def test_adjust_stock_subtract(self):
        """Test adjusting stock via service (subtract)"""
        product = Product.objects.create(
            name='Test Product',
            quantity=100
        )
        
        updated = StockService.adjust_stock(product, 30, 'subtract')
        
        self.assertEqual(updated.quantity, 70)
    
    def test_adjust_stock_add(self):
        """Test adjusting stock via service (add)"""
        product = Product.objects.create(
            name='Test Product',
            quantity=50
        )
        
        updated = StockService.adjust_stock(product, 25, 'add')
        
        self.assertEqual(updated.quantity, 75)
    
    def test_adjust_stock_insufficient(self):
        """Test adjusting stock with insufficient quantity"""
        product = Product.objects.create(
            name='Test Product',
            quantity=10
        )
        
        with self.assertRaises(InsufficientStockError):
            StockService.adjust_stock(product, 20, 'subtract')
    
    def test_adjust_stock_zero_quantity(self):
        """Test adjusting stock with zero quantity (should not change)"""
        product = Product.objects.create(
            name='Test Product',
            quantity=50
        )
        
        updated = StockService.adjust_stock(product, 0, 'subtract')
        
        self.assertEqual(updated.quantity, 50)
    
    def test_get_low_stock_products(self):
        """Test getting low stock products"""
        Product.objects.create(name='P1', quantity=5, reorder_threshold=10)
        Product.objects.create(name='P2', quantity=20, reorder_threshold=10)
        Product.objects.create(name='P3', quantity=0, reorder_threshold=10)
        
        low_stock = StockService.get_low_stock_products()
        
        self.assertEqual(low_stock.count(), 2)
    
    def test_get_out_of_stock_products(self):
        """Test getting out of stock products"""
        Product.objects.create(name='P1', quantity=0)
        Product.objects.create(name='P2', quantity=10)
        Product.objects.create(name='P3', quantity=0)
        
        out_of_stock = StockService.get_out_of_stock_products()
        
        self.assertEqual(out_of_stock.count(), 2)


class ProductViewSetTests(APITestCase):
    """Test ProductViewSet endpoints"""
    
    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
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
        
        self.product = Product.objects.create(
            name='Existing Product',
            sku='SKU-001',
            quantity=100,
            buying_price=Decimal('50.00'),
            selling_price=Decimal('75.00')
        )
        
        self.url = reverse('products-list')
    
    def test_list_products_authenticated(self):
        """Test listing products as authenticated user"""
        self.client.force_authenticate(user=self.employer)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_list_products_unauthenticated(self):
        """Test listing products without authentication (should fail)"""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_create_product_as_admin(self):
        """Test creating product as admin"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'name': 'New Product',
            'sku': 'SKU-002',
            'quantity': 50,
            'unit': 'pcs',
            'reorder_threshold': 15,
            'buying_price': '100.00',
            'selling_price': '150.00'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Product.objects.count(), 2)
    
    def test_create_product_as_employer(self):
        """Test creating product as employer (should fail)"""
        self.client.force_authenticate(user=self.employer)
        data = {
            'name': 'New Product',
            'quantity': 50
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_product_with_negative_quantity(self):
        """Test creating product with negative quantity"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'name': 'Invalid Product',
            'quantity': -10
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_create_product_selling_price_less_than_buying(self):
        """Test creating product with selling price < buying price"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'name': 'Invalid Price Product',
            'quantity': 10,
            'buying_price': '100.00',
            'selling_price': '50.00'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_product_as_admin(self):
        """Test updating product as admin"""
        self.client.force_authenticate(user=self.admin)
        url = reverse('products-detail', kwargs={'pk': self.product.id})
        data = {
            'name': 'Updated Product',
            'quantity': 150
        }
        
        response = self.client.patch(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'Updated Product')
    
    def test_delete_product_as_admin(self):
        """Test deleting product as admin"""
        self.client.force_authenticate(user=self.admin)
        url = reverse('products-detail', kwargs={'pk': self.product.id})
        
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Product.objects.count(), 0)
    
    def test_adjust_stock_endpoint(self):
        """Test adjust stock custom action"""
        self.client.force_authenticate(user=self.admin)
        url = reverse('products-adjust-stock', kwargs={'pk': self.product.id})
        data = {
            'quantity': 20,
            'operation': 'add'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 120)
    
    def test_low_stock_endpoint(self):
        """Test low stock custom action"""
        Product.objects.create(
            name='Low Stock Product',
            quantity=5,
            reorder_threshold=10
        )
        
        self.client.force_authenticate(user=self.employer)
        url = reverse('products-low-stock')
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['count'], 0)
    
    def test_out_of_stock_endpoint(self):
        """Test out of stock custom action"""
        Product.objects.create(
            name='Out of Stock Product',
            quantity=0
        )
        
        self.client.force_authenticate(user=self.employer)
        url = reverse('products-out-of-stock')
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)


class ProductEdgeCaseTests(APITestCase):
    """Test edge cases for Product model"""
    
    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        self.admin = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        self.url = reverse('products-list')
    
    def test_create_product_with_duplicate_sku(self):
        """Test creating product with duplicate SKU (should fail)"""
        Product.objects.create(
            name='Product 1',
            sku='SKU-DUP',
            quantity=10
        )
        
        self.client.force_authenticate(user=self.admin)
        data = {
            'name': 'Product 2',
            'sku': 'SKU-DUP',
            'quantity': 20
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_create_product_with_very_large_quantity(self):
        """Test creating product with very large quantity"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'name': 'Large Quantity Product',
            'quantity': 999999999
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_concurrent_stock_adjustments(self):
        """Test concurrent stock adjustments"""
        product = Product.objects.create(
            name='Concurrent Product',
            quantity=100
        )
        
        # Simulate multiple concurrent adjustments
        for i in range(5):
            StockService.adjust_stock(product, 10, 'subtract')
        
        product.refresh_from_db()
        self.assertEqual(product.quantity, 50)