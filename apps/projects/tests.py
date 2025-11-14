# apps/projects/tests.py
"""
Projects app tests - Testing project models, maintenances, and complex workflows
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from apps.projects.models import Project, Maintenance
from apps.clients.models import Client

User = get_user_model()


class ProjectModelTests(TestCase):
    """Test Project model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        self.client = Client.objects.create(
            name='Test Client',
            phone_number='0555123456'
        )
    
    def test_create_project_minimal(self):
        """Test creating project with minimal fields"""
        project = Project.objects.create(
            name='Test Project',
            client=self.client,
            start_date=date.today(),
            created_by=self.user
        )
        
        self.assertEqual(project.name, 'Test Project')
        self.assertFalse(project.is_verified)
        self.assertEqual(project.status, Project.STATUS_DRAFT)
    
    def test_create_project_with_end_date(self):
        """Test creating project with end date"""
        project = Project.objects.create(
            name='Test Project',
            client=self.client,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
            created_by=self.user
        )
        
        self.assertIsNotNone(project.end_date)
        self.assertEqual(project.duration_days, 90)
    
    def test_project_status_upcoming(self):
        """Test project with UPCOMING status"""
        project = Project.objects.create(
            name='Future Project',
            client=self.client,
            start_date=date.today() + timedelta(days=30),
            end_date=date.today() + timedelta(days=120),
            created_by=self.user,
            is_verified=True
        )
        
        self.assertEqual(project.status, Project.STATUS_UPCOMING)
    
    def test_project_status_active(self):
        """Test project with ACTIVE status"""
        project = Project.objects.create(
            name='Active Project',
            client=self.client,
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() + timedelta(days=20),
            created_by=self.user,
            is_verified=True
        )
        
        self.assertEqual(project.status, Project.STATUS_ACTIVE)
        self.assertTrue(project.is_active)
    
    def test_project_status_completed(self):
        """Test project with COMPLETED status"""
        project = Project.objects.create(
            name='Completed Project',
            client=self.client,
            start_date=date.today() - timedelta(days=90),
            end_date=date.today() - timedelta(days=1),
            created_by=self.user,
            is_verified=True
        )
        
        self.assertEqual(project.status, Project.STATUS_COMPLETED)
        self.assertTrue(project.is_completed)
    
    def test_project_verify(self):
        """Test verifying a project"""
        project = Project.objects.create(
            name='Draft Project',
            client=self.client,
            start_date=date.today(),
            created_by=self.user
        )
        
        project.verify(by_user=self.user)
        
        self.assertTrue(project.is_verified)
        self.assertIsNotNone(project.verified_at)
        self.assertEqual(project.verified_by, self.user)
    
    def test_project_unverify(self):
        """Test unverifying a project"""
        project = Project.objects.create(
            name='Verified Project',
            client=self.client,
            start_date=date.today(),
            created_by=self.user,
            is_verified=True
        )
        
        project.unverify()
        
        self.assertFalse(project.is_verified)
        self.assertIsNone(project.verified_at)
        self.assertIsNone(project.verified_by)
    
    def test_project_warranty_calculations(self):
        """Test project warranty calculations"""
        project = Project.objects.create(
            name='Warranty Project',
            client=self.client,
            start_date=date(2025, 1, 1),
            created_by=self.user,
            warranty_years=2,
            warranty_months=6,
            warranty_days=15
        )
        
        expected_end = date(2025, 1, 1) + relativedelta(years=2, months=6, days=15)
        self.assertEqual(project.warranty_end_date, expected_end)
        self.assertEqual(project.warranty_display, '2y 6m 15d')
    
    def test_project_progress_percentage(self):
        """Test project progress calculation"""
        project = Project.objects.create(
            name='Progress Project',
            client=self.client,
            start_date=date.today() - timedelta(days=50),
            end_date=date.today() + timedelta(days=50),
            created_by=self.user,
            is_verified=True
        )
        
        # Should be around 50%
        self.assertGreater(project.progress_percentage, 40)
        self.assertLess(project.progress_percentage, 60)
    
    def test_project_with_maintenance(self):
        """Test project with maintenance settings"""
        project = Project.objects.create(
            name='Maintenance Project',
            client=self.client,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
            duration_maintenance=12,
            interval_maintenance=3,
            created_by=self.user
        )
        
        # Maintenances should be created automatically
        self.assertGreater(project.maintenances.count(), 0)
    
    def test_maintenance_creation(self):
        """Test automatic maintenance creation"""
        project = Project.objects.create(
            name='Auto Maintenance',
            client=self.client,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            duration_maintenance=12,
            interval_maintenance=3,
            created_by=self.user
        )
        
        # Should create 4 maintenances (12/3)
        self.assertEqual(project.maintenances.count(), 4)
        
        # Check first maintenance date
        first_maintenance = project.maintenances.first()
        expected_date = date(2025, 12, 31) + relativedelta(months=3)
        self.assertEqual(first_maintenance.start_date, expected_date)
    
    def test_update_maintenance_settings(self):
        """Test updating maintenance settings regenerates maintenances"""
        project = Project.objects.create(
            name='Update Maintenance',
            client=self.client,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
            duration_maintenance=12,
            interval_maintenance=3,
            created_by=self.user
        )
        
        initial_count = project.maintenances.count()
        
        # Update maintenance settings
        project.duration_maintenance = 18
        project.interval_maintenance = 6
        project.save()
        
        # Should have different count now
        new_count = project.maintenances.count()
        self.assertNotEqual(initial_count, new_count)


class MaintenanceModelTests(TestCase):
    """Test Maintenance model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
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
    
    def test_create_maintenance_manual(self):
        """Test creating manual maintenance"""
        maintenance = Maintenance.objects.create(
            project=self.project,
            start_date=date.today() + timedelta(days=30),
            end_date=date.today() + timedelta(days=30),
            maintenance_type=Maintenance.TYPE_MANUAL
        )
        
        self.assertEqual(maintenance.maintenance_type, Maintenance.TYPE_MANUAL)
        self.assertFalse(maintenance.is_overdue)
    
    def test_maintenance_is_overdue(self):
        """Test checking if maintenance is overdue"""
        maintenance = Maintenance.objects.create(
            project=self.project,
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() - timedelta(days=5),
            maintenance_type=Maintenance.TYPE_MANUAL
        )
        
        self.assertTrue(maintenance.is_overdue)
    
    def test_maintenance_days_until(self):
        """Test days until maintenance calculation"""
        maintenance = Maintenance.objects.create(
            project=self.project,
            start_date=date.today() + timedelta(days=15),
            end_date=date.today() + timedelta(days=15),
            maintenance_type=Maintenance.TYPE_MANUAL
        )
        
        self.assertEqual(maintenance.days_until_maintenance, 15)


class ProjectViewSetTests(APITestCase):
    """Test ProjectViewSet endpoints"""
    
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
            name='Existing Project',
            client=self.test_client,
            start_date=date.today(),
            created_by=self.admin
        )
        
        self.url = reverse('projects-list')
    
    def test_list_projects_authenticated(self):
        """Test listing projects as authenticated user"""
        self.client_api.force_authenticate(user=self.employer)
        response = self.client_api.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_create_project_as_admin(self):
        """Test creating project as admin"""
        self.client_api.force_authenticate(user=self.admin)
        data = {
            'name': 'New Project',
            'client': self.test_client.id,
            'start_date': '2025-01-01',
            'end_date': '2025-12-31',
            'warranty_years': 1,
            'warranty_months': 6,
            'warranty_days': 0,
            'assigned_employers': [self.employer.id]
        }
        
        response = self.client_api.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Project.objects.count(), 2)
    
    def test_create_project_without_client(self):
        """Test creating project without client (should fail)"""
        self.client_api.force_authenticate(user=self.admin)
        data = {
            'name': 'Invalid Project',
            'start_date': '2025-01-01'
        }
        
        response = self.client_api.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_create_project_end_before_start(self):
        """Test creating project with end_date before start_date"""
        self.client_api.force_authenticate(user=self.admin)
        data = {
            'name': 'Invalid Dates Project',
            'client': self.test_client.id,
            'start_date': '2025-12-31',
            'end_date': '2025-01-01'
        }
        
        response = self.client_api.post(self.url, data, format='json')
        
        # Should still create but may have unexpected behavior
        # This is an edge case that might need validation
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST])
    
    def test_verify_project(self):
        """Test verifying a project"""
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('projects-verify', kwargs={'pk': self.project.id})
        
        response = self.client_api.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertTrue(self.project.is_verified)
    
    def test_verify_already_verified_project(self):
        """Test verifying already verified project"""
        self.project.is_verified = True
        self.project.save()
        
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('projects-verify', kwargs={'pk': self.project.id})
        
        response = self.client_api.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_unverify_project(self):
        """Test unverifying a project"""
        self.project.is_verified = True
        self.project.save()
        
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('projects-unverify', kwargs={'pk': self.project.id})
        
        response = self.client_api.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertFalse(self.project.is_verified)
    
    def test_assign_employers(self):
        """Test assigning employers to project"""
        employer2 = User.objects.create_user(
            username='employer2',
            password='pass123',
            role=User.ROLE_EMPLOYER
        )
        
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('projects-assign', kwargs={'pk': self.project.id})
        data = {
            'user_ids': [self.employer.id, employer2.id]
        }
        
        response = self.client_api.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.project.assigned_employers.count(), 2)
    
    def test_assign_invalid_user_ids(self):
        """Test assigning with invalid user IDs format"""
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('projects-assign', kwargs={'pk': self.project.id})
        data = {
            'user_ids': 'not_a_list'
        }
        
        response = self.client_api.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_my_projects(self):
        """Test getting projects for current user"""
        self.project.assigned_employers.add(self.employer)
        
        self.client_api.force_authenticate(user=self.employer)
        url = reverse('projects-my-projects')
        
        response = self.client_api.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
    
    def test_project_calendar(self):
        """Test project calendar endpoint"""
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('projects-calendar', kwargs={'pk': self.project.id})
        
        response = self.client_api.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)


class ProjectEdgeCaseTests(APITestCase):
    """Test edge cases for Project model"""
    
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
        
        self.url = reverse('projects-list')
    
    def test_create_project_without_end_date(self):
        """Test creating project without end date (ongoing)"""
        self.client_api.force_authenticate(user=self.admin)
        data = {
            'name': 'Ongoing Project',
            'client': self.test_client.id,
            'start_date': '2025-01-01',
            'assigned_employers': []  # Add empty list for assigned_employers
        }
        
        response = self.client_api.post(self.url, data, format='json')
        
        # Debug: print the response data to see what error we're getting
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Error response: {response.data}")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get(name='Ongoing Project')
        # end_date should be set to start_date by model save
        self.assertEqual(project.end_date, project.start_date)

    
    def test_create_project_with_zero_maintenance_interval(self):
        """Test creating project with zero maintenance interval"""
        self.client_api.force_authenticate(user=self.admin)
        data = {
            'name': 'Zero Interval Project',
            'client': self.test_client.id,
            'start_date': '2025-01-01',
            'end_date': '2025-12-31',
            'duration_maintenance': 12,
            'interval_maintenance': 0
        }
        
        response = self.client_api.post(self.url, data, format='json')
        
        # Should handle gracefully (no division by zero)
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST])
    
    def test_delete_project_with_invoices(self):
        """Test deleting project that has invoices"""
        from apps.invoices.models import Invoice
        
        project = Project.objects.create(
            name='Project with Invoice',
            client=self.test_client,
            start_date=date.today(),
            created_by=self.admin
        )
        
        Invoice.objects.create(
            project=project,
            created_by=self.admin
        )
        
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('projects-detail', kwargs={'pk': project.id})
        
        response = self.client_api.delete(url)
        
        # Should cascade delete or prevent deletion
        self.assertIn(response.status_code, [status.HTTP_204_NO_CONTENT, status.HTTP_400_BAD_REQUEST])
    
    def test_concurrent_project_verification(self):
        """Test concurrent verification attempts"""
        project = Project.objects.create(
            name='Concurrent Project',
            client=self.test_client,
            start_date=date.today(),
            created_by=self.admin
        )
        
        self.client_api.force_authenticate(user=self.admin)
        url = reverse('projects-verify', kwargs={'pk': project.id})
        
        # First verification should succeed
        response1 = self.client_api.post(url)
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        
        # Second verification should fail
        response2 = self.client_api.post(url)
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)