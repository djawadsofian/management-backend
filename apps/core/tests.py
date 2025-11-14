# apps/core/tests.py
"""
Core app tests - Testing base models, mixins, and utilities
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

User = get_user_model()


class BaseTestCase(APITestCase):
    """Base test case with common setup for all tests"""
    
    def setUp(self):
        """Set up test users and authentication"""
        # Create superuser
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123',
            first_name='Admin',
            last_name='User'
        )
        
        # Create admin user
        self.admin = User.objects.create_user(
            username='admin_user',
            email='admin@example.com',
            password='testpass123',
            role=User.ROLE_ADMIN
        )
        
        # Create employer user
        self.employer = User.objects.create_user(
            username='employer_user',
            email='employer@example.com',
            password='testpass123',
            role=User.ROLE_EMPLOYER
        )
        
        # Create assistant user
        self.assistant = User.objects.create_user(
            username='assistant_user',
            email='assistant@example.com',
            password='testpass123',
            role=User.ROLE_ASSISTANT
        )
        
        self.client = APIClient()
    
    def authenticate(self, user):
        """Helper to authenticate as a specific user"""
        self.client.force_authenticate(user=user)
    
    def unauthenticate(self):
        """Helper to clear authentication"""
        self.client.force_authenticate(user=None)


class PermissionTests(BaseTestCase):
    """Test custom permission classes"""
    
    def test_is_admin_permission_with_superuser(self):
        """Test that superusers pass IsAdmin permission"""
        from apps.core.permissions import IsAdmin
        
        permission = IsAdmin()
        self.authenticate(self.superuser)
        
        # Mock request
        class MockRequest:
            user = self.superuser
        
        request = MockRequest()
        
        # Mock view
        class MockView:
            pass
        
        view = MockView()
        
        self.assertTrue(permission.has_permission(request, view))
    
    def test_is_admin_permission_with_admin_role(self):
        """Test that ADMIN role users pass IsAdmin permission"""
        from apps.core.permissions import IsAdmin
        
        permission = IsAdmin()
        
        class MockRequest:
            user = self.admin
        
        request = MockRequest()
        
        class MockView:
            pass
        
        view = MockView()
        
        self.assertTrue(permission.has_permission(request, view))
    
    def test_is_admin_permission_with_employer(self):
        """Test that employers fail IsAdmin permission"""
        from apps.core.permissions import IsAdmin
        
        permission = IsAdmin()
        
        class MockRequest:
            user = self.employer
        
        request = MockRequest()
        
        class MockView:
            pass
        
        view = MockView()
        
        self.assertFalse(permission.has_permission(request, view))
    
    def test_is_admin_or_assistant_permission(self):
        """Test IsAdminOrAssistant permission"""
        from apps.core.permissions import IsAdminOrAssistant
        
        permission = IsAdminOrAssistant()
        
        class MockRequest:
            pass
        
        class MockView:
            pass
        
        request = MockRequest()
        view = MockView()
        
        # Test admin
        request.user = self.admin
        self.assertTrue(permission.has_permission(request, view))
        
        # Test assistant
        request.user = self.assistant
        self.assertTrue(permission.has_permission(request, view))
        
        # Test employer
        request.user = self.employer
        self.assertFalse(permission.has_permission(request, view))


class ExceptionTests(TestCase):
    """Test custom exception classes"""
    
    def test_insufficient_stock_error(self):
        """Test InsufficientStockError exception"""
        from apps.core.exceptions import InsufficientStockError
        
        with self.assertRaises(InsufficientStockError) as context:
            raise InsufficientStockError("Not enough stock")
        
        self.assertEqual(context.exception.status_code, 400)
    
    def test_invalid_status_transition_error(self):
        """Test InvalidStatusTransitionError exception"""
        from apps.core.exceptions import InvalidStatusTransitionError
        
        with self.assertRaises(InvalidStatusTransitionError) as context:
            raise InvalidStatusTransitionError("Invalid transition")
        
        self.assertEqual(context.exception.status_code, 400)
    
    def test_business_rule_violation_error(self):
        """Test BusinessRuleViolationError exception"""
        from apps.core.exceptions import BusinessRuleViolationError
        
        with self.assertRaises(BusinessRuleViolationError) as context:
            raise BusinessRuleViolationError("Business rule violated")
        
        self.assertEqual(context.exception.status_code, 400)


class PaginationTests(BaseTestCase):
    """Test pagination classes"""
    
    def test_static_pagination_default_page_size(self):
        """Test StaticPagination default page size"""
        from apps.core.pagination import StaticPagination
        
        pagination = StaticPagination()
        self.assertEqual(pagination.page_size, 10)
    
    def test_static_pagination_max_page_size(self):
        """Test StaticPagination max page size"""
        from apps.core.pagination import StaticPagination
        
        pagination = StaticPagination()
        self.assertEqual(pagination.max_page_size, 100)