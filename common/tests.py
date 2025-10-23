from django.test import TestCase
from django.db import models
from common.models import TimeStampedModel
from common.pagination import StaticPagination
from rest_framework.test import APITestCase
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from django.utils import timezone

# Create a test model that uses TimeStampedModel
class TestModel(TimeStampedModel):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = 'common'

class TimeStampedModelTests(TestCase):
    def setUp(self):
        self.test_obj = TestModel.objects.create(name="Test Object")

    def test_timestamps_creation(self):
        """Test that timestamps are automatically set on creation"""
        self.assertIsNotNone(self.test_obj.created_at)
        self.assertIsNotNone(self.test_obj.updated_at)
        self.assertEqual(self.test_obj.created_at.date(), timezone.now().date())

    def test_updated_at_modification(self):
        """Test that updated_at is modified on save"""
        original_updated_at = self.test_obj.updated_at
        self.test_obj.name = "Modified Name"
        self.test_obj.save()
        self.test_obj.refresh_from_db()
        self.assertGreater(self.test_obj.updated_at, original_updated_at)

class StaticPaginationTests(APITestCase):
    class TestViewSet(ModelViewSet):
        pagination_class = StaticPagination
        
        def list(self, request, *args, **kwargs):
            # Create dummy data for testing pagination
            data = [{'id': i, 'value': f'Item {i}'} for i in range(25)]
            page = self.paginate_queryset(data)
            return self.get_paginated_response(page)

    def setUp(self):
        self.viewset = self.TestViewSet()
        self.viewset.paginator = StaticPagination()

    def test_pagination_page_size(self):
        """Test that pagination respects page size"""
        response = self.viewset.list(None)
        self.assertEqual(len(response.data['results']), 10)  # Default page size
        self.assertEqual(response.data['count'], 25)  # Total items
        self.assertIsNotNone(response.data['next'])
        self.assertIsNone(response.data['previous'])

    def test_pagination_page_navigation(self):
        """Test pagination next/previous links"""
        # First page
        response = self.viewset.list(None)
        next_page = response.data['next']
        self.assertIsNotNone(next_page)
        self.assertIsNone(response.data['previous'])

        # Middle page
        response.data['results'] = [{'id': i, 'value': f'Item {i}'} for i in range(10, 20)]
        self.assertIsNotNone(response.data['next'])
        self.assertIsNotNone(response.data['previous'])

        # Last page
        response.data['results'] = [{'id': i, 'value': f'Item {i}'} for i in range(20, 25)]
        self.assertIsNone(response.data['next'])
        self.assertIsNotNone(response.data['previous'])

    def test_invalid_page_number(self):
        """Test handling of invalid page numbers"""
        # Create a request with an invalid page number
        class MockRequest:
            def __init__(self):
                self.query_params = {'page': '999'}
        
        response = self.viewset.paginator.get_paginated_response([])
        self.assertEqual(len(response.data['results']), 0)
        self.assertEqual(response.data['count'], 0)