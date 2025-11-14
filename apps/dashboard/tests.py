# apps/dashboard/tests.py
"""
Dashboard app tests - Testing analytics endpoints and data aggregation
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from decimal import Decimal
from datetime import date, timedelta

from apps.projects.models import Project, Maintenance
from apps.clients.models import Client
from apps.stock.models import Product
from apps.invoices.models import Invoice, InvoiceLine

User = get_user_model()


class DashboardSummaryTests(APITestCase):
    """Test Dashboard Summary endpoint"""
    
    def setUp(self):
        """Set up comprehensive test data"""
        self.client_api = APIClient()
        
        self.admin = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        # Create test clients
        self.test_client1 = Client.objects.create(
            name='Client 1',
            phone_number='0555111111',
            is_corporate=True
        )
        
        self.test_client2 = Client.objects.create(
            name='Client 2',
            phone_number='0555222222',
            is_corporate=False
        )
        
        # Create test products
        self.product1 = Product.objects.create(
            name='Product 1',
            quantity=50,
            reorder_threshold=10,
            buying_price=Decimal('100.00'),
            selling_price=Decimal('150.00')
        )
        
        self.product2 = Product.objects.create(
            name='Product 2',
            quantity=5,  # Low stock
            reorder_threshold=10,
            buying_price=Decimal('50.00'),
            selling_price=Decimal('75.00')
        )
        
        self.product3 = Product.objects.create(
            name='Product 3',
            quantity=0,  # Out of stock
            reorder_threshold=10
        )
        
        # Create test projects
        self.project1 = Project.objects.create(
            name='Active Project',
            client=self.test_client1,
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() + timedelta(days=20),
            created_by=self.admin,
            is_verified=True
        )
        
        self.project2 = Project.objects.create(
            name='Upcoming Project',
            client=self.test_client2,
            start_date=date.today() + timedelta(days=30),
            end_date=date.today() + timedelta(days=120),
            created_by=self.admin,
            is_verified=True
        )
        
        # Create test invoices
        self.invoice1 = Invoice.objects.create(
            project=self.project1,
            created_by=self.admin,
            status=Invoice.STATUS_ISSUED,
            tva=Decimal('19.00')
        )
        
        InvoiceLine.objects.create(
            invoice=self.invoice1,
            product=self.product1,
            quantity=Decimal('10'),
            unit_price=Decimal('150.00')
        )
        
        self.invoice1.calculate_totals()
        
        self.url = reverse('dashboard-summary')
    
    def test_dashboard_summary_authenticated(self):
        """Test accessing dashboard summary as authenticated user"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('projects', response.data)
        self.assertIn('financial', response.data)
        self.assertIn('inventory', response.data)
        self.assertIn('clients', response.data)
    
    def test_dashboard_summary_unauthenticated(self):
        """Test accessing dashboard without authentication"""
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_dashboard_project_counts(self):
        """Test project statistics in dashboard"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        projects = response.data['projects']
        
        self.assertEqual(projects['total'], 2)
        self.assertGreater(projects['verified'], 0)
    
    def test_dashboard_inventory_stats(self):
        """Test inventory statistics in dashboard"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        inventory = response.data['inventory']
        
        self.assertEqual(inventory['total_products'], 3)
        self.assertEqual(inventory['out_of_stock'], 1)
        self.assertEqual(inventory['low_stock'], 1)
    
    def test_dashboard_financial_stats(self):
        """Test financial statistics in dashboard"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        financial = response.data['financial']
        
        self.assertGreater(financial['total_revenue'], 0)
        self.assertIn('total_invoices', financial)
    
    def test_dashboard_kpis(self):
        """Test KPI calculations in dashboard"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        kpis = response.data['kpis']
        
        self.assertIn('revenue_per_project', kpis)
        self.assertIn('revenue_per_client', kpis)


class ProjectAnalyticsTests(APITestCase):
    """Test Project Analytics endpoint"""
    
    def setUp(self):
        """Set up test data"""
        self.client_api = APIClient()
        
        self.admin = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        self.test_client = Client.objects.create(
            name='Analytics Client',
            phone_number='0555123456'
        )
        
        # Create multiple projects for analytics
        for i in range(5):
            Project.objects.create(
                name=f'Project {i}',
                client=self.test_client,
                start_date=date.today() - timedelta(days=90 - i*10),
                end_date=date.today() + timedelta(days=i*30),
                created_by=self.admin,
                is_verified=True
            )
        
        self.url = reverse('projects-analytics')
    
    def test_project_analytics_authenticated(self):
        """Test accessing project analytics as authenticated user"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('monthly_trend', response.data)
        self.assertIn('duration_analysis', response.data)
    
    def test_project_analytics_top_clients(self):
        """Test top clients data in analytics"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('top_clients', response.data)
        self.assertGreater(len(response.data['top_clients']), 0)


class FinancialAnalyticsTests(APITestCase):
    """Test Financial Analytics endpoint"""
    
    def setUp(self):
        """Set up test data"""
        self.client_api = APIClient()
        
        self.admin = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        self.test_client = Client.objects.create(
            name='Finance Client',
            phone_number='0555123456'
        )
        
        self.project = Project.objects.create(
            name='Finance Project',
            client=self.test_client,
            start_date=date.today(),
            created_by=self.admin
        )
        
        # Create invoice with revenue
        self.invoice = Invoice.objects.create(
            project=self.project,
            created_by=self.admin,
            status=Invoice.STATUS_ISSUED
        )
        
        self.url = reverse('financial-analytics')
    
    def test_financial_analytics_authenticated(self):
        """Test accessing financial analytics as authenticated user"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('revenue_trend', response.data)
        self.assertIn('payment_metrics', response.data)
    
    def test_financial_analytics_date_range(self):
        """Test financial analytics with different date ranges"""
        self.client_api.force_authenticate(user=self.admin)
        
        # Test weekly range
        response = self.client_api.get(self.url, {'range': 'week'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test monthly range
        response = self.client_api.get(self.url, {'range': 'month'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test yearly range
        response = self.client_api.get(self.url, {'range': 'year'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class InventoryAnalyticsTests(APITestCase):
    """Test Inventory Analytics endpoint"""
    
    def setUp(self):
        """Set up test data"""
        self.client_api = APIClient()
        
        self.admin = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        # Create products with different stock levels
        Product.objects.create(
            name='Critical Stock',
            quantity=0,
            reorder_threshold=10,
            buying_price=Decimal('100.00'),
            selling_price=Decimal('150.00')
        )
        
        Product.objects.create(
            name='Low Stock',
            quantity=5,
            reorder_threshold=10,
            buying_price=Decimal('50.00'),
            selling_price=Decimal('75.00')
        )
        
        self.url = reverse('inventory-analytics')
    
    def test_inventory_analytics_authenticated(self):
        """Test accessing inventory analytics as authenticated user"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('critical_stock_alerts', response.data)
        self.assertIn('inventory_health', response.data)
    
    def test_inventory_critical_alerts(self):
        """Test critical stock alerts in analytics"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        alerts = response.data['critical_stock_alerts']
        
        self.assertGreater(len(alerts), 0)


class RecentActivityTests(APITestCase):
    """Test Recent Activity endpoint"""
    
    def setUp(self):
        """Set up test data"""
        self.client_api = APIClient()
        
        self.admin = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        self.test_client = Client.objects.create(
            name='Activity Client',
            phone_number='0555123456'
        )
        
        self.project = Project.objects.create(
            name='Activity Project',
            client=self.test_client,
            start_date=date.today(),
            created_by=self.admin
        )
        
        self.url = reverse('recent-activity')
    
    def test_recent_activity_authenticated(self):
        """Test accessing recent activity as authenticated user"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('activities', response.data)
        self.assertIn('total', response.data)
    
    def test_recent_activity_limit(self):
        """Test activity limit parameter"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url, {'limit': '5'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(response.data['activities']), 5)
    
    def test_recent_activity_max_limit(self):
        """Test activity max limit enforcement"""
        self.client_api.force_authenticate(user=self.admin)
        response = self.client_api.get(self.url, {'limit': '1000'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should enforce max limit of 50
        self.assertLessEqual(len(response.data['activities']), 50)


class DashboardEdgeCaseTests(APITestCase):
    """Test dashboard edge cases and error handling"""
    
    def setUp(self):
        """Set up minimal test data"""
        self.client_api = APIClient()
        
        self.admin = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
    
    def test_dashboard_with_no_data(self):
        """Test dashboard with empty database"""
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('dashboard-summary')
        
        response = self.client_api.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should handle empty data gracefully
        self.assertEqual(response.data['projects']['total'], 0)
        self.assertEqual(response.data['clients']['total'], 0)
    
    def test_analytics_with_no_data(self):
        """Test analytics endpoints with no data"""
        self.client_api.force_authenticate(user=self.admin)
        
        # Project analytics
        url = reverse('projects-analytics')
        response = self.client_api.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Financial analytics
        url = reverse('financial-analytics')
        response = self.client_api.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Inventory analytics
        url = reverse('inventory-analytics')
        response = self.client_api.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_dashboard_cache_behavior(self):
        """Test dashboard caching behavior"""
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('dashboard-summary')
        
        # First request
        response1 = self.client_api.get(url)
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertFalse(response1.data.get('from_cache', False))
        
        # Second request (should be cached)
        response2 = self.client_api.get(url)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        # Note: Cache behavior depends on cache configuration