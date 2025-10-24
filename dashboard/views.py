# dashboard/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.db.models import Count, Sum, Q, F
from django.utils import timezone
from datetime import timedelta, datetime
from decimal import Decimal

from projects.models import Project, Maintenance
from invoices.models import Invoice, InvoiceLine
from stock.models import Product
from clients.models import Client
from users.models import CustomUser

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
            quantity__lte=F('reorder_threshold')
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
    


class ProjectAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        Get project analytics and timeline data
        """
        # Project status distribution
        today = timezone.now().date()
        
        status_breakdown = {
            'active': Project.objects.filter(
                start_date__lte=today,
                end_date__gte=today
            ).count(),
            'upcoming': Project.objects.filter(
                start_date__gt=today
            ).count(),
            'completed': Project.objects.filter(
                end_date__lt=today
            ).count(),
            'without_end_date': Project.objects.filter(
                end_date__isnull=True
            ).count(),
        }

        # Projects by month (last 6 months)
        six_months_ago = today - timedelta(days=180)
        
        monthly_projects = Project.objects.filter(
            created_at__date__gte=six_months_ago
        ).extra({
            'month': "strftime('%%Y-%%m', created_at)"
        }).values('month').annotate(
            count=Count('id')
        ).order_by('month')

        # Projects verification rate
        total_projects = Project.objects.count()
        verified_projects = Project.objects.filter(is_verified=True).count()
        verification_rate = (verified_projects / total_projects * 100) if total_projects > 0 else 0

        # Recent projects (last 10)
        recent_projects = Project.objects.select_related('client').order_by('-created_at')[:10]
        recent_projects_data = [
            {
                'id': project.id,
                'name': project.name,
                'client': project.client.name,
                'start_date': project.start_date,
                'status': project.status,
                'is_verified': project.is_verified,
                'created_at': project.created_at
            }
            for project in recent_projects
        ]

        return Response({
            'status_breakdown': status_breakdown,
            'monthly_trend': list(monthly_projects),
            'verification_rate': round(verification_rate, 2),
            'recent_projects': recent_projects_data,
        })
    



# dashboard/views.py (continued)
class FinancialAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        Get financial analytics and revenue data
        """
        # Date range parameters
        range_param = request.GET.get('range', 'month')  # week, month, year
        today = timezone.now().date()
        
        if range_param == 'week':
            start_date = today - timedelta(days=7)
        elif range_param == 'month':
            start_date = today - timedelta(days=30)
        else:  # year
            start_date = today - timedelta(days=365)

        # Revenue by status
        revenue_by_status = Invoice.objects.filter(
            issued_date__gte=start_date
        ).values('status').annotate(
            total=Sum('total'),
            count=Count('id')
        ).order_by('status')

        # Monthly revenue trend
        monthly_revenue = Invoice.objects.filter(
            issued_date__gte=start_date,
            status__in=[Invoice.STATUS_ISSUED, Invoice.STATUS_PAID]
        ).extra({
            'month': "strftime('%%Y-%%m', issued_date)"
        }).values('month').annotate(
            revenue=Sum('total')
        ).order_by('month')

        # Top clients by revenue
        top_clients = Invoice.objects.filter(
            status__in=[Invoice.STATUS_ISSUED, Invoice.STATUS_PAID]
        ).values(
            'project__client__name'
        ).annotate(
            total_revenue=Sum('total'),
            project_count=Count('project__id')
        ).order_by('-total_revenue')[:10]

        # Invoice status distribution
        invoice_status = Invoice.objects.values('status').annotate(
            count=Count('id')
        ).order_by('status')

        return Response({
            'revenue_by_status': list(revenue_by_status),
            'monthly_revenue_trend': list(monthly_revenue),
            'top_clients': list(top_clients),
            'invoice_status_distribution': list(invoice_status),
            'date_range': {
                'start': start_date,
                'end': today,
                'range': range_param
            }
        })
    



class InventoryAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        Get inventory and stock analytics
        """
        # Low stock alerts
        low_stock_products = Product.objects.filter(
            quantity__lte=F('reorder_threshold')
        ).order_by('quantity')[:10]
        
        low_stock_data = [
            {
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'quantity': product.quantity,
                'reorder_threshold': product.reorder_threshold,
                'unit': product.unit,
                'is_out_of_stock': product.quantity == 0
            }
            for product in low_stock_products
        ]

        # Stock value calculation
        stock_value = Product.objects.aggregate(
            total_value=Sum(F('quantity') * F('buying_price'))
        )['total_value'] or Decimal('0.00')

        # Products with highest profit margin
        profitable_products = Product.objects.filter(
            selling_price__gt=0,
            buying_price__gt=0
        ).annotate(
            profit_margin=((F('selling_price') - F('buying_price')) / F('buying_price')) * 100
        ).order_by('-profit_margin')[:10]

        profitable_products_data = [
            {
                'id': product.id,
                'name': product.name,
                'buying_price': float(product.buying_price),
                'selling_price': float(product.selling_price),
                'profit_margin': float(product.profit_margin),
                'quantity': product.quantity
            }
            for product in profitable_products
        ]

        # Stock turnover (products with recent activity)
        recent_invoice_lines = InvoiceLine.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        ).values('product__name').annotate(
            total_sold=Sum('quantity')
        ).order_by('-total_sold')[:10]

        return Response({
            'low_stock_alerts': low_stock_data,
            'total_stock_value': float(stock_value),
            'most_profitable_products': profitable_products_data,
            'recently_sold_products': list(recent_invoice_lines),
            'stock_health': {
                'total_products': Product.objects.count(),
                'out_of_stock': Product.objects.filter(quantity=0).count(),
                'low_stock': Product.objects.filter(
                    quantity__lte=F('reorder_threshold'),
                    quantity__gt=0
                ).count(),
                'healthy_stock': Product.objects.filter(
                    quantity__gt=F('reorder_threshold')
                ).count(),
            }
        })
    

# dashboard/views.py (continued)
class RecentActivityView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        Get recent activity across all modules
        """
        # Recent projects
        recent_projects = Project.objects.select_related('client').order_by('-created_at')[:5]
        
        # Recent invoices
        recent_invoices = Invoice.objects.select_related('project', 'project__client').order_by('-created_at')[:5]
        
        # Recent clients
        recent_clients = Client.objects.order_by('-created_at')[:5]
        
        # Recent low stock products
        recent_low_stock = Product.objects.filter(
            quantity__lte=F('reorder_threshold')
        ).order_by('-updated_at')[:5]

        projects_data = [
            {
                'type': 'project',
                'id': project.id,
                'name': project.name,
                'client': project.client.name,
                'status': project.status,
                'timestamp': project.created_at,
                'action': 'created'
            }
            for project in recent_projects
        ]

        invoices_data = [
            {
                'type': 'invoice',
                'id': invoice.id,
                'number': invoice.facture or invoice.bon_de_commande or 'No Number',
                'project': invoice.project.name,
                'total': float(invoice.total),
                'status': invoice.status,
                'timestamp': invoice.created_at,
                'action': 'created'
            }
            for invoice in recent_invoices
        ]

        clients_data = [
            {
                'type': 'client',
                'id': client.id,
                'name': client.name,
                'is_corporate': client.is_corporate,
                'timestamp': client.created_at,
                'action': 'created'
            }
            for client in recent_clients
        ]

        stock_data = [
            {
                'type': 'stock_alert',
                'id': product.id,
                'name': product.name,
                'quantity': product.quantity,
                'threshold': product.reorder_threshold,
                'timestamp': product.updated_at,
                'action': 'low_stock' if product.quantity > 0 else 'out_of_stock'
            }
            for product in recent_low_stock
        ]

        # Combine and sort all activities by timestamp
        all_activities = projects_data + invoices_data + clients_data + stock_data
        all_activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Return only the 10 most recent activities
        return Response(all_activities[:10])