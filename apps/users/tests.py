# apps/users/tests.py
"""
Users app tests - Testing user models, authentication, and permissions
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse

User = get_user_model()


class UserModelTests(TestCase):
    """Test CustomUser model"""
    
    def test_create_user(self):
        """Test creating a regular user"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.assertEqual(user.username, 'testuser')
        self.assertEqual(user.email, 'test@example.com')
        self.assertTrue(user.check_password('testpass123'))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
    
    def test_create_superuser(self):
        """Test creating a superuser"""
        user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123'
        )
        
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_admin())
    
    def test_user_role_methods(self):
        """Test user role checking methods"""
        admin = User.objects.create_user(
            username='admin',
            password='pass',
            role=User.ROLE_ADMIN
        )
        
        employer = User.objects.create_user(
            username='employer',
            password='pass',
            role=User.ROLE_EMPLOYER
        )
        
        assistant = User.objects.create_user(
            username='assistant',
            password='pass',
            role=User.ROLE_ASSISTANT
        )
        
        self.assertTrue(admin.is_admin())
        self.assertFalse(admin.is_employer())
        self.assertFalse(admin.is_assistant())
        
        self.assertFalse(employer.is_admin())
        self.assertTrue(employer.is_employer())
        self.assertFalse(employer.is_assistant())
        
        self.assertFalse(assistant.is_admin())
        self.assertFalse(assistant.is_employer())
        self.assertTrue(assistant.is_assistant())
    
    def test_user_with_all_fields(self):
        """Test creating user with all optional fields"""
        user = User.objects.create_user(
            username='fulluser',
            email='full@example.com',
            password='pass123',
            first_name='John',
            last_name='Doe',
            phone_number='0555123456',
            role=User.ROLE_EMPLOYER,
            wilaya='Tlemcen',
            group='Group A',
            can_see_selling_price=True,
            can_edit_selling_price=False,
            can_edit_buying_price=False
        )
        
        self.assertEqual(user.first_name, 'John')
        self.assertEqual(user.last_name, 'Doe')
        self.assertEqual(user.phone_number, '0555123456')
        self.assertEqual(user.wilaya, 'Tlemcen')
        self.assertEqual(user.group, 'Group A')
        self.assertTrue(user.can_see_selling_price)
        self.assertFalse(user.can_edit_selling_price)


class EmployerViewSetTests(APITestCase):
    """Test EmployerViewSet endpoints"""
    
    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        self.admin = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        self.assistant = User.objects.create_user(
            username='assistant',
            password='pass123',
            role=User.ROLE_ASSISTANT
        )
        
        self.employer = User.objects.create_user(
            username='employer',
            password='pass123',
            role=User.ROLE_EMPLOYER
        )
        
        self.url = reverse('employers-list')
    
    def test_list_employers_as_admin(self):
        """Test listing employers as admin"""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_list_employers_as_assistant(self):
        """Test listing employers as assistant"""
        self.client.force_authenticate(user=self.assistant)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_list_employers_as_employer(self):
        """Test listing employers as employer (should fail)"""
        self.client.force_authenticate(user=self.employer)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_employer_as_admin(self):
        """Test creating employer as admin"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'username': 'newemployer',
            'email': 'new@example.com',
            'password': 'newpass123',
            'first_name': 'New',
            'last_name': 'Employer',
            'phone_number': '0555111222'
        }
        
        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.filter(username='newemployer').count(), 1)
        
        new_user = User.objects.get(username='newemployer')
        self.assertEqual(new_user.role, User.ROLE_EMPLOYER)
    
    def test_create_employer_without_required_fields(self):
        """Test creating employer without required fields"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'username': 'incomplete'
        }
        
        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_create_employer_with_duplicate_username(self):
        """Test creating employer with duplicate username"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'username': 'employer',  # Already exists
            'email': 'duplicate@example.com',
            'password': 'pass123'
        }
        
        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_deactivate_employer(self):
        """Test deactivating an employer"""
        self.client.force_authenticate(user=self.admin)
        url = reverse('employers-deactivate', kwargs={'pk': self.employer.id})
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.employer.refresh_from_db()
        self.assertFalse(self.employer.is_active)
    
    def test_activate_employer(self):
        """Test activating an employer"""
        self.employer.is_active = False
        self.employer.save()
        
        self.client.force_authenticate(user=self.admin)
        url = reverse('employers-activate', kwargs={'pk': self.employer.id})
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.employer.refresh_from_db()
        self.assertTrue(self.employer.is_active)


class AssistantViewSetTests(APITestCase):
    """Test AssistantViewSet endpoints"""
    
    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        self.admin = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        self.assistant = User.objects.create_user(
            username='assistant',
            password='pass123',
            role=User.ROLE_ASSISTANT
        )
        
        self.url = reverse('assistants-list')
    
    def test_list_assistants_as_admin(self):
        """Test listing assistants as admin"""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_list_assistants_as_assistant(self):
        """Test listing assistants as assistant (should fail)"""
        self.client.force_authenticate(user=self.assistant)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_assistant_as_admin(self):
        """Test creating assistant as admin"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'username': 'newassistant',
            'email': 'assistant@example.com',
            'password': 'pass123',
            'first_name': 'New',
            'last_name': 'Assistant',
            'can_see_selling_price': True,
            'can_edit_selling_price': False,
            'can_edit_buying_price': False
        }
        
        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_user = User.objects.get(username='newassistant')
        self.assertEqual(new_user.role, User.ROLE_ASSISTANT)
        self.assertTrue(new_user.can_see_selling_price)
        self.assertFalse(new_user.can_edit_selling_price)
    
    def test_update_assistant_permissions(self):
        """Test updating assistant permissions"""
        self.client.force_authenticate(user=self.admin)
        url = reverse('assistants-update-permissions', kwargs={'pk': self.assistant.id})
        
        data = {
            'can_see_selling_price': False,
            'can_edit_selling_price': False,
            'can_edit_buying_price': True
        }
        
        response = self.client.patch(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assistant.refresh_from_db()
        self.assertFalse(self.assistant.can_see_selling_price)
        self.assertTrue(self.assistant.can_edit_buying_price)
    
    def test_update_permissions_as_non_admin(self):
        """Test updating permissions as non-admin (should fail)"""
        employer = User.objects.create_user(
            username='employer',
            password='pass123',
            role=User.ROLE_EMPLOYER
        )
        
        self.client.force_authenticate(user=employer)
        url = reverse('assistants-update-permissions', kwargs={'pk': self.assistant.id})
        
        data = {
            'can_see_selling_price': False
        }
        
        response = self.client.patch(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class MyCalendarTests(APITestCase):
    """Test my_calendar endpoint"""
    
    def setUp(self):
        """Set up test data"""
        from apps.clients.models import Client
        from apps.projects.models import Project
        
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
        
        # Create test client
        self.test_client = Client.objects.create(
            name='Test Client',
            phone_number='0555123456',
            address={
                'province': 'Tlemcen',
                'city': 'Tlemcen',
                'postal_code': '13000'
            }
        )
        
        # Create test project
        self.project = Project.objects.create(
            name='Test Project',
            client=self.test_client,
            start_date='2025-01-01',
            end_date='2025-12-31',
            created_by=self.admin,
            is_verified=True
        )
        
        self.project.assigned_employers.add(self.employer)
        
        self.url = reverse('my-calendar')
    
    def test_calendar_as_admin(self):
        """Test calendar view as admin"""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('events', response.data)
        self.assertGreater(len(response.data['events']), 0)
    
    def test_calendar_as_employer(self):
        """Test calendar view as employer (only assigned projects)"""
        self.client.force_authenticate(user=self.employer)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('events', response.data)
    
    def test_calendar_with_filters(self):
        """Test calendar with query filters"""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get(self.url, {
            'event_type': 'project',
            'project_name': 'Test',
            'province': 'Tlemcen'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('applied_filters', response.data)
        self.assertEqual(response.data['applied_filters']['event_type'], 'project')
    
    def test_calendar_unauthenticated(self):
        """Test calendar without authentication (should fail)"""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)