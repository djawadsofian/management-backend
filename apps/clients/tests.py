# apps/clients/tests.py
"""
Clients app tests - Testing client models and API endpoints
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from apps.clients.models import Client

User = get_user_model()


class ClientModelTests(TestCase):
    """Test Client model"""
    
    def test_create_client_minimal(self):
        """Test creating client with minimal required fields"""
        client = Client.objects.create(
            name='Test Company',
            phone_number='0555123456'
        )
        
        self.assertEqual(client.name, 'Test Company')
        self.assertEqual(client.phone_number, '0555123456')
        self.assertFalse(client.is_corporate)
    
    def test_create_corporate_client(self):
        """Test creating corporate client with all fields"""
        client = Client.objects.create(
            name='Big Company SARL',
            phone_number='0555123456',
            fax='0213123456',
            email='contact@bigcompany.dz',
            is_corporate=True,
            rc='RC-12345',
            nif='NIF-123456789',
            art='ART-1234',
            account_number='ACCT-1234567890',
            address={
                'street': '123 Main St',
                'city': 'Tlemcen',
                'province': 'Tlemcen',
                'postal_code': '13000'
            },
            notes='Test notes'
        )
        
        self.assertTrue(client.is_corporate)
        self.assertEqual(client.rc, 'RC-12345')
        self.assertEqual(client.nif, 'NIF-123456789')
        self.assertEqual(client.address['province'], 'Tlemcen')
    
    def test_create_individual_client(self):
        """Test creating individual client"""
        client = Client.objects.create(
            name='John Doe',
            phone_number='0555123456',
            is_corporate=False,
            nis='NIS-1234567890',
            ai='AI-12345'
        )
        
        self.assertFalse(client.is_corporate)
        self.assertEqual(client.nis, 'NIS-1234567890')
        self.assertIsNone(client.rc)
        self.assertIsNone(client.nif)
    
    def test_client_string_representation(self):
        """Test client __str__ method"""
        client = Client.objects.create(
            name='Test Client',
            phone_number='0555123456'
        )
        
        self.assertEqual(str(client), 'Test Client')
    
    def test_client_with_json_address(self):
        """Test client with complex JSON address"""
        address_data = {
            'street': '456 Avenue',
            'city': 'Oran',
            'province': 'Oran',
            'postal_code': '31000',
            'building': 'Block A',
            'floor': '3rd Floor'
        }
        
        client = Client.objects.create(
            name='Test Client',
            phone_number='0555123456',
            address=address_data
        )
        
        self.assertEqual(client.address['city'], 'Oran')
        self.assertEqual(client.address['building'], 'Block A')


class ClientViewSetTests(APITestCase):
    """Test ClientViewSet endpoints"""
    
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
        
        self.test_client = Client.objects.create(
            name='Existing Client',
            phone_number='0555111222',
            address={
                'province': 'Tlemcen',
                'city': 'Tlemcen',
                'postal_code': '13000'
            }
        )
        
        self.url = reverse('clients-list')
    
    def test_list_clients_authenticated(self):
        """Test listing clients as authenticated user"""
        self.client.force_authenticate(user=self.employer)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_list_clients_unauthenticated(self):
        """Test listing clients without authentication (should fail)"""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_create_client_as_admin(self):
        """Test creating client as admin"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'name': 'New Client',
            'phone_number': '0555333444',
            'email': 'client@example.dz',
            'is_corporate': True,
            'rc': 'RC-99999',
            'nif': 'NIF-999999999'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Client.objects.count(), 2)
    
    def test_create_client_as_employer(self):
        """Test creating client as employer (should fail)"""
        self.client.force_authenticate(user=self.employer)
        data = {
            'name': 'New Client',
            'phone_number': '0555333444'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_client_without_required_fields(self):
        """Test creating client without required fields"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'name': 'Incomplete Client'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Check for the French message
        self.assertEqual(response.data, {"message": "Champ obligatoire manquant"})


    
    def test_update_client_as_admin(self):
        """Test updating client as admin"""
        self.client.force_authenticate(user=self.admin)
        url = reverse('clients-detail', kwargs={'pk': self.test_client.id})
        data = {
            'name': 'Updated Client Name',
            'phone_number': '0555999888'
        }
        
        response = self.client.patch(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.test_client.refresh_from_db()
        self.assertEqual(self.test_client.name, 'Updated Client Name')
    
    def test_delete_client_as_admin(self):
        """Test deleting client as admin"""
        self.client.force_authenticate(user=self.admin)
        url = reverse('clients-detail', kwargs={'pk': self.test_client.id})
        
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Client.objects.count(), 0)
    
    def test_filter_clients_by_province(self):
        """Test filtering clients by province"""
        # Create another client in different province
        Client.objects.create(
            name='Oran Client',
            phone_number='0555222333',
            address={
                'province': 'Oran',
                'city': 'Oran',
                'postal_code': '31000'
            }
        )
        
        self.client.force_authenticate(user=self.employer)
        response = self.client.get(self.url, {'province': 'Tlemcen'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only return Tlemcen client
        self.assertEqual(response.data['count'], 1)
    
    def test_search_clients_by_name(self):
        """Test searching clients by name"""
        self.client.force_authenticate(user=self.employer)
        response = self.client.get(self.url, {'search': 'Existing'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['count'], 0)
    
    def test_filter_clients_by_corporate(self):
        """Test filtering clients by corporate status"""
        # Create corporate client
        Client.objects.create(
            name='Corporate Client',
            phone_number='0555444555',
            is_corporate=True
        )
        
        self.client.force_authenticate(user=self.employer)
        response = self.client.get(self.url, {'is_corporate': 'true'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)


class ClientEdgeCaseTests(APITestCase):
    """Test edge cases for Client model"""
    
    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        self.admin = User.objects.create_user(
            username='admin',
            password='pass123',
            role=User.ROLE_ADMIN
        )
        
        self.url = reverse('clients-list')
    
    def test_create_client_with_null_address(self):
        """Test creating client with null address"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'name': 'No Address Client',
            'phone_number': '0555123456',
            'address': None
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_client_with_empty_address(self):
        """Test creating client with empty address object"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'name': 'Empty Address Client',
            'phone_number': '0555123456',
            'address': {}
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_client_with_very_long_name(self):
        """Test creating client with name at max length"""
        self.client.force_authenticate(user=self.admin)
        long_name = 'A' * 255
        data = {
            'name': long_name,
            'phone_number': '0555123456'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_client_with_special_characters_in_name(self):
        """Test creating client with special characters"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'name': 'Client & Co. (Société)',
            'phone_number': '0555123456'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_concurrent_client_creation(self):
        """Test creating multiple clients simultaneously"""
        self.client.force_authenticate(user=self.admin)
        
        for i in range(5):
            data = {
                'name': f'Concurrent Client {i}',
                'phone_number': f'055512345{i}'
            }
            response = self.client.post(self.url, data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        self.assertEqual(Client.objects.count(), 5)

    def test_create_client_with_invalid_email(self):
        """Test creating client with invalid email"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'name': 'Client',
            'phone_number': '0555123456',
            'email': 'invalid@invalid.invalid'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['message'], 'Donnée invalide')