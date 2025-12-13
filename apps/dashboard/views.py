# apps/dashboard/views.py
"""
Optimized Dashboard Views with Aggregation Queries
- Prevents N+1 queries
- Uses database aggregation for performance
- Cached responses for expensive queries
- Professional statistics organization
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.core.permissions import IsAdminOrAssistant
from rest_framework.decorators import action
from django.db.models import (
    Count, Sum, Avg, Q, F, DecimalField, 
    Case, When, IntegerField, ExpressionWrapper
)
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta, datetime
from decimal import Decimal

from apps.projects.models import Project, Maintenance
from apps.invoices.models import Invoice, InvoiceLine
from apps.stock.models import Product
from apps.clients.models import Client
from apps.users.models import CustomUser
from config import settings
from django.db.models.functions import TruncMonth, TruncDate
from django.db.models import Value





class InvoiceNetRevenueView(APIView):
    """
    Calculate net revenue for a specific invoice
    """
    permission_classes = [IsAdminOrAssistant]
    
    def get(self, request, invoice_id):
        """
        Calculate net revenue for a specific invoice
        """
        try:
            invoice = Invoice.objects.get(id=invoice_id)
            
            if invoice.status != Invoice.STATUS_PAID:
                return Response({
                    'error': 'Le revenu net ne peut être calculé que pour les factures payées'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            net_revenue = self.calculate_invoice_net_revenue(invoice_id)
            
            return Response({
                'invoice_id': invoice_id,
                'invoice_number': invoice.facture or invoice.bon_de_commande or f'INV-{invoice.id}',
                'total_revenue': float(invoice.total),
                'net_revenue': float(net_revenue),
                'net_margin_percentage': round(
                    (float(net_revenue) / float(invoice.total) * 100) 
                    if invoice.total > 0 else 0, 
                    1
                )
            })
            
        except Invoice.DoesNotExist:
            return Response({
                'error': 'Facture non trouvée'
            }, status=status.HTTP_404_NOT_FOUND)
    
    def calculate_invoice_net_revenue(self, invoice_id):
        """
        Calculate net revenue for a specific invoice
        """
        from apps.invoices.models import InvoiceLine
        
        invoice_lines = InvoiceLine.objects.filter(
            invoice_id=invoice_id
        ).select_related('product')
        
        net_revenue = Decimal('0.00')
        
        for line in invoice_lines:
            if line.product:
                # For product lines: line_total - (quantity * buying_price)
                cost = line.quantity * line.product.buying_price
                line_net = line.line_total - cost
            else:
                # For description-only lines: use line_total as net revenue
                line_net = line.line_total
            
            net_revenue += line_net
        
        return net_revenue.quantize(Decimal('0.01'))


class DashboardSummaryView(APIView):
    """
    Main dashboard summary with key metrics
    Optimized with single-query aggregations
    """
    permission_classes = [IsAdminOrAssistant]
    
    def get(self, request):

        # For testing, disable cache or clear it
        if getattr(settings, 'TESTING', False):
            cache.delete('dashboard_summary')

        # Check cache first (5 minutes)
        cache_key = 'dashboard_summary'
        cached_data = cache.get(cache_key)
        if cached_data:
            cached_data['from_cache'] = True
            return Response(cached_data)
        
        today = timezone.now().date()
        
        # ===== PROJECT STATISTICS (Single Query) =====
        project_stats = Project.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(
                start_date__lte=today,
                end_date__gte=today
            )),
            upcoming=Count('id', filter=Q(start_date__gt=today)),
            completed=Count('id', filter=Q(end_date__lt=today)),
            without_end_date=Count('id', filter=Q(end_date__isnull=True)),
            verified=Count('id', filter=Q(is_verified=True)),
            unverified=Count('id', filter=Q(is_verified=False)),
            with_maintenance=Count('id', filter=Q(
                duration_maintenance__isnull=False,
                interval_maintenance__isnull=False
            ))
        )
        
        # ===== FINANCIAL STATISTICS (Single Query) =====
        financial_stats = Invoice.objects.aggregate(
            # Revenue metrics
            total_revenue=Sum('total', filter=Q(
                status__in=[Invoice.STATUS_ISSUED, Invoice.STATUS_PAID]
            )),
            paid_revenue=Sum('total', filter=Q(status=Invoice.STATUS_PAID)),
            pending_revenue=Sum('total', filter=Q(status=Invoice.STATUS_ISSUED)),
            draft_value=Sum('total', filter=Q(status=Invoice.STATUS_DRAFT)),
            
            # Invoice counts
            total_invoices=Count('id'),
            draft_invoices=Count('id', filter=Q(status=Invoice.STATUS_DRAFT)),
            issued_invoices=Count('id', filter=Q(status=Invoice.STATUS_ISSUED)),
            paid_invoices=Count('id', filter=Q(status=Invoice.STATUS_PAID)),
            
            # Average metrics
            avg_invoice_value=Avg('total', filter=Q(
                status__in=[Invoice.STATUS_ISSUED, Invoice.STATUS_PAID]
            )),
            
            # Overdue invoices (issued but past due_date)
            overdue_invoices=Count('id', filter=Q(
                status=Invoice.STATUS_ISSUED,
                due_date__lt=today
            )),
            overdue_amount=Sum('total', filter=Q(
                status=Invoice.STATUS_ISSUED,
                due_date__lt=today
            ))
        )
        
        # ===== INVENTORY STATISTICS (Single Query) =====
        inventory_stats = Product.objects.aggregate(
            total_products=Count('id'),
            out_of_stock=Count('id', filter=Q(quantity=0)),
            low_stock=Count('id', filter=Q(
                quantity__gt=0,
                quantity__lte=F('reorder_threshold')
            )),
            healthy_stock=Count('id', filter=Q(quantity__gt=F('reorder_threshold'))),
            
            # Financial inventory metrics
            total_stock_value=Sum(
                ExpressionWrapper(
                    F('quantity') * F('buying_price'),
                    output_field=DecimalField(max_digits=15, decimal_places=2)
                )
            ),
            potential_revenue=Sum(
                ExpressionWrapper(
                    F('quantity') * F('selling_price'),
                    output_field=DecimalField(max_digits=15, decimal_places=2)
                )
            ),
            avg_profit_margin=Avg(
                ExpressionWrapper(
                    ((F('selling_price') - F('buying_price')) / F('buying_price')) * 100,
                    output_field=DecimalField(max_digits=5, decimal_places=2)
                ),
                filter=Q(buying_price__gt=0)
            )
        )
        
        # Calculate potential profit
        stock_value = inventory_stats['total_stock_value'] or Decimal('0')
        potential_revenue = inventory_stats['potential_revenue'] or Decimal('0')
        potential_profit = potential_revenue - stock_value
        
        # ===== CLIENT STATISTICS (Single Query) =====
        client_stats = Client.objects.aggregate(
            total=Count('id'),
            corporate=Count('id', filter=Q(is_corporate=True)),
            individual=Count('id', filter=Q(is_corporate=False)),
            # Clients with active projects
            active_clients=Count(
                'id',
                filter=Q(
                    projects__start_date__lte=today,
                    projects__end_date__gte=today
                ),
                distinct=True
            )
        )
        
        # ===== USER STATISTICS (Single Query) =====
        user_stats = CustomUser.objects.aggregate(
            total_users=Count('id'),
            admins=Count('id', filter=Q(role=CustomUser.ROLE_ADMIN)),
            employers=Count('id', filter=Q(role=CustomUser.ROLE_EMPLOYER)),
            assistants=Count('id', filter=Q(role=CustomUser.ROLE_ASSISTANT)),
            active_users=Count('id', filter=Q(is_active=True))
        )
        
        # ===== MAINTENANCE ALERTS (Single Query) =====
        maintenance_stats = Maintenance.objects.aggregate(
            total_maintenances=Count('id'),
            overdue=Count('id', filter=Q(start_date__lt=today)),
            due_soon=Count('id', filter=Q(
                start_date__gte=today,
                start_date__lte=today + timedelta(days=7)
            )),
            upcoming=Count('id', filter=Q(
                start_date__gt=today + timedelta(days=7)
            ))
        )
        
        # ===== BUILD RESPONSE =====
        response_data = {
            'generated_at': timezone.now().isoformat(),
            'user_role': request.user.role,
            
            # Project Overview
            'projects': {
                'total': project_stats['total'],
                'active': project_stats['active'],
                'upcoming': project_stats['upcoming'],
                'completed': project_stats['completed'],
                'without_end_date': project_stats['without_end_date'],
                'verified': project_stats['verified'],
                'unverified': project_stats['unverified'],
                'with_maintenance': project_stats['with_maintenance'],
                'verification_rate': round(
                    (project_stats['verified'] / project_stats['total'] * 100) 
                    if project_stats['total'] > 0 else 0, 
                    1
                )
            },
            
            # Financial Overview
            'financial': {
                'total_revenue': float(financial_stats['total_revenue'] or 0),
                'paid_revenue': float(financial_stats['paid_revenue'] or 0),
                'pending_revenue': float(financial_stats['pending_revenue'] or 0),
                'draft_value': float(financial_stats['draft_value'] or 0),
                'overdue_amount': float(financial_stats['overdue_amount'] or 0),
                'avg_invoice_value': float(financial_stats['avg_invoice_value'] or 0),
                'total_invoices': financial_stats['total_invoices'],
                'draft_invoices': financial_stats['draft_invoices'],
                'issued_invoices': financial_stats['issued_invoices'],
                'paid_invoices': financial_stats['paid_invoices'],
                'overdue_invoices': financial_stats['overdue_invoices'],
                'collection_rate': round(
                    (financial_stats['paid_revenue'] / financial_stats['total_revenue'] * 100)
                    if financial_stats['total_revenue'] else 0,
                    1
                )
            },
            
            # Inventory Overview
            'inventory': {
                'total_products': inventory_stats['total_products'],
                'out_of_stock': inventory_stats['out_of_stock'],
                'low_stock': inventory_stats['low_stock'],
                'healthy_stock': inventory_stats['healthy_stock'],
                'total_stock_value': float(stock_value),
                'potential_revenue': float(potential_revenue),
                'potential_profit': float(potential_profit),
                'avg_profit_margin': float(inventory_stats['avg_profit_margin'] or 0),
                'stock_health_percentage': round(
                    (inventory_stats['healthy_stock'] / inventory_stats['total_products'] * 100)
                    if inventory_stats['total_products'] > 0 else 0,
                    1
                )
            },
            
            # Client Overview
            'clients': {
                'total': client_stats['total'],
                'corporate': client_stats['corporate'],
                'individual': client_stats['individual'],
                'active_clients': client_stats['active_clients'],
                'corporate_percentage': round(
                    (client_stats['corporate'] / client_stats['total'] * 100)
                    if client_stats['total'] > 0 else 0,
                    1
                )
            },
            
            # Team Overview
            'team': {
                'total_users': user_stats['total_users'],
                'admins': user_stats['admins'],
                'employers': user_stats['employers'],
                'assistants': user_stats['assistants'],
                'active_users': user_stats['active_users']
            },
            
            # Maintenance Alerts
            'maintenance': {
                'total': maintenance_stats['total_maintenances'],
                'overdue': maintenance_stats['overdue'],
                'due_soon': maintenance_stats['due_soon'],
                'upcoming': maintenance_stats['upcoming']
            },
            
            # Key Performance Indicators
            'kpis': {
                'revenue_per_project': round(
                    float(financial_stats['total_revenue'] or 0) / project_stats['total']
                    if project_stats['total'] > 0 else 0,
                    2
                ),
                'revenue_per_client': round(
                    float(financial_stats['total_revenue'] or 0) / client_stats['total']
                    if client_stats['total'] > 0 else 0,
                    2
                ),
                'project_completion_rate': round(
                    (project_stats['completed'] / project_stats['total'] * 100)
                    if project_stats['total'] > 0 else 0,
                    1
                ),
                'stock_turnover_risk': inventory_stats['out_of_stock'] + inventory_stats['low_stock'],
                'maintenance_coverage': round(
                    (project_stats['with_maintenance'] / project_stats['total'] * 100)
                    if project_stats['total'] > 0 else 0,
                    1
                )
            }
        }
        
        # Cache for 5 minutes
        cache.set(cache_key, response_data, 300)
        response_data['from_cache'] = False
        
        return Response(response_data)


class ProjectAnalyticsView(APIView):
    """
    Detailed project analytics with trends
    """
    permission_classes = [IsAdminOrAssistant]
    
    def get(self, request):
        cache_key = 'project_analytics'
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        
        today = timezone.now().date()
        six_months_ago = today - timedelta(days=180)
        
        # ===== PROJECT TIMELINE ANALYSIS =====
        timeline_stats = Project.objects.filter(
            created_at__date__gte=six_months_ago
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            created=Count('id'),
            verified=Count('id', filter=Q(is_verified=True)),
            with_maintenance=Count('id', filter=Q(
                duration_maintenance__isnull=False,
                interval_maintenance__isnull=False
            ))
        ).order_by('month')
        
        # ===== PROJECT DURATION ANALYSIS =====
        duration_stats = Project.objects.filter(
            end_date__isnull=False
        ).annotate(
            duration_days=ExpressionWrapper(
                (F('end_date') - F('start_date')) * Value(1, output_field=IntegerField()),
                output_field=IntegerField()
            )
        ).aggregate(
            avg_duration=Avg('duration_days'),
            min_duration=Count('id', filter=Q(duration_days__lte=30)),
            medium_duration=Count('id', filter=Q(duration_days__gt=30, duration_days__lte=90)),
            long_duration=Count('id', filter=Q(duration_days__gt=90))
        )
        
        # ===== MAINTENANCE COVERAGE =====
        maintenance_coverage = Project.objects.aggregate(
            total_projects=Count('id'),
            with_maintenance=Count('id', filter=Q(
                duration_maintenance__isnull=False,
                interval_maintenance__isnull=False
            )),
            avg_maintenance_duration=Avg('duration_maintenance', filter=Q(
                duration_maintenance__isnull=False
            )),
            avg_maintenance_interval=Avg('interval_maintenance', filter=Q(
                interval_maintenance__isnull=False
            ))
        )
        
        # ===== TOP CLIENTS BY PROJECT COUNT =====
        top_clients = Client.objects.annotate(
            project_count=Count('projects'),
            active_projects=Count('projects', filter=Q(
                projects__start_date__lte=today,
                projects__end_date__gte=today
            )),
            completed_projects=Count('projects', filter=Q(
                projects__end_date__lt=today
            )),
            projects_with_maintenance=Count('projects', filter=Q(
                projects__duration_maintenance__isnull=False,
                projects__interval_maintenance__isnull=False
            ))
        ).filter(project_count__gt=0).order_by('-project_count')[:10]
        
        top_clients_data = [
            {
                'client_id': client.id,
                'client_name': client.name,
                'is_corporate': client.is_corporate,
                'total_projects': client.project_count,
                'active_projects': client.active_projects,
                'completed_projects': client.completed_projects,
                'projects_with_maintenance': client.projects_with_maintenance
            }
            for client in top_clients
        ]
        
        # ===== EMPLOYER WORKLOAD =====
        employer_workload = CustomUser.objects.filter(
            role=CustomUser.ROLE_EMPLOYER
        ).annotate(
            total_projects=Count('assigned_projects'),
            active_projects=Count('assigned_projects', filter=Q(
                assigned_projects__start_date__lte=today,
                assigned_projects__end_date__gte=today
            )),
            projects_with_maintenance=Count('assigned_projects', filter=Q(
                assigned_projects__duration_maintenance__isnull=False,
                assigned_projects__interval_maintenance__isnull=False
            ))
        ).order_by('-total_projects')[:10]
        
        workload_data = [
            {
                'employer_id': emp.id,
                'employer_name': emp.get_full_name() or emp.username,
                'total_projects': emp.total_projects,
                'active_projects': emp.active_projects,
                'projects_with_maintenance': emp.projects_with_maintenance,
                'workload_status': 'High' if emp.active_projects > 5 else 'Medium' if emp.active_projects > 2 else 'Low'
            }
            for emp in employer_workload
        ]
        
        response_data = {
            'generated_at': timezone.now().isoformat(),
            'monthly_trend': list(timeline_stats),
            'duration_analysis': {
                'avg_duration_days': round(duration_stats['avg_duration'] or 0, 1),
                'short_term': duration_stats['min_duration'],  # <= 30 days
                'medium_term': duration_stats['medium_duration'],  # 31-90 days
                'long_term': duration_stats['long_duration']  # > 90 days
            },
            'maintenance_coverage': {
                'total_projects': maintenance_coverage['total_projects'],
                'with_maintenance': maintenance_coverage['with_maintenance'],
                'coverage_rate': round(
                    (maintenance_coverage['with_maintenance'] / maintenance_coverage['total_projects'] * 100)
                    if maintenance_coverage['total_projects'] > 0 else 0,
                    1
                ),
                'avg_duration_months': round(maintenance_coverage['avg_maintenance_duration'] or 0, 1),
                'avg_interval_months': round(maintenance_coverage['avg_maintenance_interval'] or 0, 1)
            },
            'top_clients': top_clients_data,
            'employer_workload': workload_data
        }
        
        cache.set(cache_key, response_data, 600)  # 10 minutes
        return Response(response_data)
    

class FinancialAnalyticsView(APIView):
    """
    Financial analytics with revenue tracking using paid_date
    """
    permission_classes = [IsAdminOrAssistant]

    def calculate_invoice_net_revenue(self, invoices):
        """Calculate net revenue for a set of invoices"""
        total_net = Decimal('0.00')
        for invoice in invoices:
            invoice_net = Decimal('0.00')
            for line in invoice.lines.all():
                if line.product:
                    cost = line.quantity * line.product.buying_price
                    line_net = line.line_total - cost
                else:
                    line_net = line.line_total
                invoice_net += line_net
            total_net += invoice_net
        return total_net
        
    def get(self, request):
        # Get date range from params
        start_date_param = request.GET.get('start_date')
        end_date_param = request.GET.get('end_date')
        today = timezone.now().date()
        
        # Parse dates with validation
        try:
            if start_date_param:
                start_date = datetime.strptime(start_date_param, '%Y-%m-%d').date()
            else:
                start_date = today - timedelta(days=30)  # Default to last 30 days
                
            if end_date_param:
                end_date = datetime.strptime(end_date_param, '%Y-%m-%d').date()
            else:
                end_date = today
                
            # Validate date range
            if start_date > end_date:
                return Response(
                    {"error": "La date de début ne peut pas être après la date de fin"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except (ValueError, TypeError) as e:
            return Response(
                {"error": "Format de date invalide. Utilisez YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate cache key based on date range
        cache_key = f'financial_analytics_{start_date.isoformat()}_{end_date.isoformat()}'
        
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        
        # ===== REVENUE TREND (using paid_date) =====
        revenue_trend = Invoice.objects.filter(
            paid_date__gte=start_date,
            paid_date__lte=end_date,
            status=Invoice.STATUS_PAID
        ).annotate(
            date=TruncDate('paid_date')
        ).values('date').annotate(
            revenue=Sum('total'),
            invoice_count=Count('id'),
        ).order_by('date')

        # Add net revenue to each day
        for day_data in revenue_trend:
            date_obj = day_data['date']
            day_invoices = Invoice.objects.filter(
                paid_date__gte=date_obj,
                paid_date__lt=date_obj + timedelta(days=1),
                status=Invoice.STATUS_PAID
            ).prefetch_related('lines__product')
            day_data['net_revenue'] = float(self.calculate_invoice_net_revenue(day_invoices))
                
        # ===== NET REVENUE CALCULATION =====
        # Get all paid invoices in date range
        paid_invoices = Invoice.objects.filter(
            paid_date__gte=start_date,
            paid_date__lte=end_date,
            status=Invoice.STATUS_PAID
        ).prefetch_related('lines__product')
        
        total_net_revenue = self.calculate_invoice_net_revenue(paid_invoices)
        total_revenue = sum(invoice.total for invoice in paid_invoices) 
        
        # ===== TOP REVENUE CLIENTS (using paid_date) =====
        top_revenue_clients = Client.objects.annotate(
            total_revenue=Sum(
                'projects__invoices__total',
                filter=Q(
                    projects__invoices__status=Invoice.STATUS_PAID,
                    projects__invoices__paid_date__gte=start_date,
                    projects__invoices__paid_date__lte=end_date
                )
            ),
            invoice_count=Count(
                'projects__invoices',
                filter=Q(
                    projects__invoices__status=Invoice.STATUS_PAID,
                    projects__invoices__paid_date__gte=start_date,
                    projects__invoices__paid_date__lte=end_date
                ),
                distinct=True
            ),
            project_count=Count('projects', distinct=True),
        ).filter(total_revenue__gt=0).order_by('-total_revenue')[:10]
        
        top_revenue_data = [
            {
                'client_id': client.id,
                'client_name': client.name,
                'total_revenue': float(client.total_revenue or 0),
                'invoice_count': client.invoice_count,
                'project_count': client.project_count,
                'avg_revenue_per_project': round(
                    float(client.total_revenue or 0) / client.project_count
                    if client.project_count > 0 else 0,
                    2
                )
            }
            for client in top_revenue_clients
        ]
        
        # ===== PAYMENT STATUS ANALYSIS (using paid_date) =====
        payment_stats = Invoice.objects.filter(
            paid_date__gte=start_date,
            paid_date__lte=end_date
        ).aggregate(
            total_paid=Sum('total', filter=Q(status=Invoice.STATUS_PAID)),
            total_invoices_paid=Count('id', filter=Q(status=Invoice.STATUS_PAID)),
            avg_days_to_payment=Avg(
                ExpressionWrapper(
                    F('paid_date') - F('issued_date'),
                    output_field=IntegerField()
                ),
                filter=Q(status=Invoice.STATUS_PAID)
            )
        )
        
        # ===== CURRENT INVOICE STATS (not dependent on date range) =====
        current_invoice_stats = Invoice.objects.aggregate(
            total_issued=Count('id', filter=Q(status=Invoice.STATUS_ISSUED)),
            total_draft=Count('id', filter=Q(status=Invoice.STATUS_DRAFT)),
            total_paid_all_time=Count('id', filter=Q(status=Invoice.STATUS_PAID)),
            total_revenue_issued=Sum('total', filter=Q(status=Invoice.STATUS_ISSUED)),
            total_revenue_paid_all_time=Sum('total', filter=Q(status=Invoice.STATUS_PAID)),
            total_deposit_issued=Sum('deposit_price', filter=Q(status=Invoice.STATUS_ISSUED)), 
        )

        # Add payment method breakdown
        payment_method_stats = Invoice.objects.filter(
            paid_date__gte=start_date,
            paid_date__lte=end_date,
            status=Invoice.STATUS_PAID
        ).values('payment_method').annotate(
            revenue=Sum('total'),
            invoice_count=Count('id'),
        )

        # Initialize metrics for each payment method
        payment_method_metrics = {}
        for method in ['espece', 'chèque', 'ccp']:
            payment_method_metrics[f'revenue_{method}'] = 0
            payment_method_metrics[f'net_revenue_{method}'] = 0
            payment_method_metrics[f'invoice_count_{method}'] = 0

        # Calculate actual values
        for stat in payment_method_stats:
            method = stat.get('payment_method')
            if method in ['espece', 'chèque', 'ccp']:
                # Get invoices for this payment method
                method_invoices = Invoice.objects.filter(
                    paid_date__gte=start_date,
                    paid_date__lte=end_date,
                    status=Invoice.STATUS_PAID,
                    payment_method=method
                ).prefetch_related('lines__product')
                
                # Calculate net revenue for this payment method
                method_net_revenue = self.calculate_invoice_net_revenue(method_invoices)
                
                payment_method_metrics[f'revenue_{method}'] = float(stat['revenue'] or 0)
                payment_method_metrics[f'net_revenue_{method}'] = float(method_net_revenue)
                payment_method_metrics[f'invoice_count_{method}'] = stat['invoice_count'] or 0

        response_data = {
            'generated_at': timezone.now().isoformat(),
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'days': (end_date - start_date).days
            },
            'revenue_trend': list(revenue_trend),
            'revenue_metrics': {
                'total_revenue': float(total_revenue),
                'total_net_revenue': float(total_net_revenue),
                'net_profit_margin': round(
                    (float(total_net_revenue) / float(total_revenue) * 100) 
                    if total_revenue > 0 else 0, 
                    1
                ),
                'total_invoices_paid': payment_stats['total_invoices_paid'] or 0,
                'avg_payment_amount': float(total_revenue / payment_stats['total_invoices_paid']) 
                    if payment_stats['total_invoices_paid'] else 0,
                'avg_days_to_payment': round(payment_stats['avg_days_to_payment'] or 0, 1),
                # Payment method breakdown
                **payment_method_metrics,
            },
            'current_invoice_status': {
                'issued_invoices': current_invoice_stats['total_issued'] or 0,
                'draft_invoices': current_invoice_stats['total_draft'] or 0,
                'paid_invoices_all_time': current_invoice_stats['total_paid_all_time'] or 0,
                'revenue_issued': float(current_invoice_stats['total_revenue_issued'] or 0),
                'revenue_paid_all_time': float(current_invoice_stats['total_revenue_paid_all_time'] or 0),
                'total_deposit_issued': float(current_invoice_stats['total_deposit_issued'] or 0), 
                'total_debts': float((current_invoice_stats['total_revenue_issued'] or 0) -
                        (current_invoice_stats['total_deposit_issued'] or 0)), 
            },
            'top_revenue_clients': top_revenue_data,
        }
        
        cache.set(cache_key, response_data, 300)  # 5 minutes
        return Response(response_data)


class InventoryAnalyticsView(APIView):
    """
    Inventory analytics with stock health
    """
    permission_classes = [IsAdminOrAssistant]
    
    def get(self, request):
        cache_key = 'inventory_analytics'
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        
        # ===== CRITICAL STOCK ALERTS =====
        all_products = Product.objects.all()
        critical_stock = []
        
        for product in all_products:
            if product.quantity == 0:
                stock_status = 'OUT_OF_STOCK'
            elif product.quantity <= product.reorder_threshold:
                stock_status = 'LOW_STOCK'
            else:
                continue  # Skip healthy stock
                
            critical_stock.append({
                'product_id': product.id,
                'name': product.name,
                'sku': product.sku,
                'quantity': product.quantity,
                'reorder_threshold': product.reorder_threshold,
                'status': stock_status,
                'unit': product.unit,
                'buying_price': float(product.buying_price),
                'selling_price': float(product.selling_price)
            })
        
        # Sort by status and quantity
        critical_stock.sort(key=lambda x: (x['status'], x['quantity']))
        critical_data = critical_stock[:20]  # Limit to 20 items
        
        # ===== MOST USED PRODUCTS (Last 30 days) =====
        thirty_days_ago = timezone.now() - timedelta(days=30)
        most_used = Product.objects.annotate(
            usage_count=Count('invoiceline', filter=Q(
                invoiceline__created_at__gte=thirty_days_ago
            )),
            total_quantity_used=Sum('invoiceline__quantity', filter=Q(
                invoiceline__created_at__gte=thirty_days_ago
            )),
            revenue_generated=Sum(
                ExpressionWrapper(
                    F('invoiceline__quantity') * F('invoiceline__unit_price'),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                ),
                filter=Q(invoiceline__created_at__gte=thirty_days_ago)
            )
        ).filter(usage_count__gt=0).order_by('-total_quantity_used')[:15]
        
        most_used_data = [
            {
                'product_id': p.id,
                'name': p.name,
                'sku': p.sku,
                'times_used': p.usage_count,
                'total_quantity_used': float(p.total_quantity_used or 0),
                'revenue_generated': float(p.revenue_generated or 0),
                'current_stock': p.quantity
            }
            for p in most_used
        ]
        
        # ===== PROFITABILITY ANALYSIS =====
        profitability = Product.objects.filter(
            buying_price__gt=0,
            selling_price__gt=0
        ).annotate(
            profit_margin=ExpressionWrapper(
                ((F('selling_price') - F('buying_price')) / F('buying_price')) * 100,
                output_field=DecimalField(max_digits=5, decimal_places=2)
            ),
            potential_profit_value=ExpressionWrapper(  # Change the name
                F('quantity') * (F('selling_price') - F('buying_price')),
                output_field=DecimalField(max_digits=15, decimal_places=2)
            )
        ).order_by('-profit_margin')[:10]
        
        profitability_data = [
            {
                'product_id': p.id,
                'name': p.name,
                'buying_price': float(p.buying_price),
                'selling_price': float(p.selling_price),
                'profit_margin': float(p.profit_margin),
                'quantity': p.quantity,
                'potential_profit': float(p.potential_profit_value)  # Use the new name
            }
            for p in profitability
        ]
        
        # ===== OVERALL INVENTORY HEALTH =====
        inventory_health = Product.objects.aggregate(
            total_value=Sum(
                ExpressionWrapper(
                    F('quantity') * F('buying_price'),
                    output_field=DecimalField(max_digits=15, decimal_places=2)
                )
            ),
            total_potential=Sum(
                ExpressionWrapper(
                    F('quantity') * F('selling_price'),
                    output_field=DecimalField(max_digits=15, decimal_places=2)
                )
            ),
            avg_stock_level=Avg('quantity')
        )
        
        response_data = {
            'generated_at': timezone.now().isoformat(),
            'critical_stock_alerts': critical_data,
            'most_used_products': most_used_data,
            'most_profitable_products': profitability_data,
            'inventory_health': {
                'total_stock_value': float(inventory_health['total_value'] or 0),
                'potential_revenue': float(inventory_health['total_potential'] or 0),
                'potential_profit': float(
                    (inventory_health['total_potential'] or 0) - 
                    (inventory_health['total_value'] or 0)
                ),
                'avg_stock_level': float(inventory_health['avg_stock_level'] or 0)
            }
        }
        
        cache.set(cache_key, response_data, 300)  # 5 minutes
        return Response(response_data)


class RecentActivityView(APIView):
    """
    Recent activity feed with pagination
    Optimized to prevent memory overload
    """
    permission_classes = [IsAdminOrAssistant]
    
    def get(self, request):
        limit = min(int(request.GET.get('limit', 20)), 50)  # Max 50
        
        # Get recent items with single queries (prefetch related)
        recent_projects = Project.objects.select_related(
            'client', 'created_by'
        ).order_by('-created_at')[:limit]
        
        recent_invoices = Invoice.objects.select_related(
            'project', 'project__client', 'created_by'
        ).order_by('-created_at')[:limit]
        
        recent_clients = Client.objects.order_by('-created_at')[:limit]
        
        recent_maintenances = Maintenance.objects.select_related(
            'project', 'project__client'
        ).order_by('-created_at')[:limit]
        
        # Build activity feed
        activities = []
        
        # Projects
        for project in recent_projects:
            activities.append({
                'type': 'project',
                'id': project.id,
                'title': f"Project: {project.name}",
                'description': f"Client: {project.client.name}",
                'status': project.status,
                'is_verified': project.is_verified,
                'has_maintenance': project.duration_maintenance is not None and project.interval_maintenance is not None,
                'timestamp': project.created_at.isoformat(),
                'user': project.created_by.get_full_name() if project.created_by else 'System'
            })
        
        # Invoices
        for invoice in recent_invoices:
            activities.append({
                'type': 'invoice',
                'id': invoice.id,
                'title': f"Invoice: {invoice.facture or invoice.bon_de_commande or f'INV-{invoice.id}'}",
                'description': f"Project: {invoice.project.name}",
                'status': invoice.status,
                'amount': float(invoice.total),
                'timestamp': invoice.created_at.isoformat(),
                'user': invoice.created_by.get_full_name() if invoice.created_by else 'System'
            })
        
        # Clients
        for client in recent_clients:
            activities.append({
                'type': 'client',
                'id': client.id,
                'title': f"Client: {client.name}",
                'description': f"Type: {'Corporate' if client.is_corporate else 'Individual'}",
                'timestamp': client.created_at.isoformat()
            })
        
        # Maintenances
        for maintenance in recent_maintenances:
            activities.append({
                'type': 'maintenance',
                'id': maintenance.id,
                'title': f"Maintenance de : {maintenance.project.name}",
                'description': f"Project: {maintenance.project.name}",
                'start_date': maintenance.start_date.isoformat(),
                'end_date': maintenance.end_date.isoformat(),
                'timestamp': maintenance.created_at.isoformat()
            })
        
        # Sort all activities by timestamp
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return Response({
            'total': len(activities),
            'limit': limit,
            'activities': activities[:limit]
        })