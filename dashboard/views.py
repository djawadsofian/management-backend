# dashboard/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.db.models import Count, Sum, Q, Avg
from django.utils import timezone
from datetime import timedelta, datetime
from decimal import Decimal

from projects.models import Project, Maintenance
from invoices.models import Invoice, InvoiceLine
from stock.models import Product
from apps.clients.models import Client
from apps.users.models import CustomUser

class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        Get overall dashboard summary statistics
        """
        # Projects statistics
        total_projects = Project.objects.count()
        active_projects = Project.objects.filter(
            start_date__lte=timezone.now().date(),
            end_date__gte=timezone.now().date()
        ).count()
        
        upcoming_projects = Project.objects.filter(
            start_date__gt=timezone.now().date()
        ).count()
        
        completed_projects = Project.objects.filter(
            end_date__lt=timezone.now().date()
        ).count()

        # Revenue statistics
        revenue_data = Invoice.objects.filter(
            status__in=[Invoice.STATUS_ISSUED, Invoice.STATUS_PAID]
        ).aggregate(
            total_revenue=Sum('total'),
            paid_revenue=Sum('total', filter=Q(status=Invoice.STATUS_PAID)),
            total_invoices=Count('id')
        )

        # Stock statistics
        low_stock_products = Product.objects.filter(
            quantity__lte=models.F('reorder_threshold')
        )
        low_stock_count = low_stock_products.count()
        
        out_of_stock_count = Product.objects.filter(quantity=0).count()
        total_products = Product.objects.count()

        # Client statistics
        total_clients = Client.objects.count()
        corporate_clients = Client.objects.filter(is_corporate=True).count()

        # User statistics
        total_employers = CustomUser.objects.filter(role=CustomUser.ROLE_EMPLOYER).count()
        total_assistants = CustomUser.objects.filter(role=CustomUser.ROLE_ASSISTANT).count()

        return Response({
            'projects': {
                'total': total_projects,
                'active': active_projects,
                'upcoming': upcoming_projects,
                'completed': completed_projects,
                'verified': Project.objects.filter(is_verified=True).count(),
            },
            'revenue': {
                'total': revenue_data['total_revenue'] or Decimal('0.00'),
                'paid': revenue_data['paid_revenue'] or Decimal('0.00'),
                'pending': revenue_data['total_revenue'] - revenue_data['paid_revenue'] if revenue_data['total_revenue'] else Decimal('0.00'),
                'invoice_count': revenue_data['total_invoices'] or 0,
            },
            'inventory': {
                'total_products': total_products,
                'low_stock': low_stock_count,
                'out_of_stock': out_of_stock_count,
                'healthy_stock': total_products - low_stock_count - out_of_stock_count,
            },
            'clients': {
                'total': total_clients,
                'corporate': corporate_clients,
                'individual': total_clients - corporate_clients,
            },
            'team': {
                'employers': total_employers,
                'assistants': total_assistants,
                'admins': CustomUser.objects.filter(role=CustomUser.ROLE_ADMIN).count(),
            }
        })