# apps/notifications/management/commands/check_and_send_notifications.py
"""
Django management command to check and send recurring notifications
Run this command via cron job every 30 seconds for immediate notifications:
* * * * * cd /path/to/project && python manage.py check_and_send_notifications
* * * * * sleep 30; cd /path/to/project && python manage.py check_and_send_notifications
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, datetime
from apps.projects.models import Project, Maintenance
from apps.stock.models import Product
from apps.users.models import CustomUser
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from django.db import models
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check and send recurring notifications every 30 seconds for immediate delivery'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--check-interval',
            type=int,
            default=30,
            help='Check interval in seconds (default: 30)'
        )
    
    def handle(self, *args, **options):
        now = timezone.now()
        check_interval = options['check_interval']
        
        self.stdout.write(self.style.HTTP_INFO(
            f"🔔 Checking notifications at {now.strftime('%Y-%m-%d %H:%M:%S')} (interval: {check_interval}s)"
        ))
        
        # Get all admins and assistants
        admins_and_assistants = CustomUser.objects.filter(
            role__in=[CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT],
            is_active=True
        )
        
        if not admins_and_assistants.exists():
            self.stdout.write(self.style.WARNING("⚠️  No active admins or assistants found"))
            return
        
        total_count = 0
        
        # ========== 1. CHECK LOW STOCK PRODUCTS (IMMEDIATE) ==========
        low_stock_count = self._check_low_stock_products(admins_and_assistants, check_interval)
        total_count += low_stock_count
        
        # ========== 2. CHECK OUT OF STOCK PRODUCTS (IMMEDIATE) ==========
        out_of_stock_count = self._check_out_of_stock_products(admins_and_assistants, check_interval)
        total_count += out_of_stock_count
        
        # ========== 3. CHECK PROJECTS STARTING SOON ==========
        projects_count = self._check_upcoming_projects(admins_and_assistants, check_interval)
        total_count += projects_count
        
        # ========== 4. CHECK MAINTENANCES STARTING SOON ==========
        maintenances_count = self._check_upcoming_maintenances(admins_and_assistants, check_interval)
        total_count += maintenances_count
        
        # ========== 5. CHECK RECENT PROJECT ASSIGNMENTS ==========
        assignments_count = self._check_recent_assignments(check_interval)
        total_count += assignments_count
        
        # ========== 6. RESEND UNSENT NOTIFICATIONS ==========
        unsent_count = self._resend_unsent_notifications(check_interval)
        total_count += unsent_count
        
        if total_count > 0:
            self.stdout.write(self.style.SUCCESS(
                f"✅ Sent {total_count} notifications immediately!"
            ))
        else:
            self.stdout.write("⏭️  No new notifications to send")
    
    def _check_low_stock_products(self, recipients, check_interval):
        """Check for low stock products that changed recently"""
        recent_threshold = timezone.now() - timedelta(seconds=check_interval * 2)
        
        low_stock_products = Product.objects.filter(
            quantity__gt=0,
            quantity__lte=models.F('reorder_threshold'),
            updated_at__gte=recent_threshold  # Only recently updated products
        )
        
        count = 0
        for product in low_stock_products:
            for user in recipients:
                # Check if notification was already sent recently
                recent_notification = Notification.objects.filter(
                    recipient=user,
                    notification_type=Notification.TYPE_LOW_STOCK_ALERT,
                    related_product=product,
                    created_at__gte=recent_threshold
                ).exists()
                
                if not recent_notification:
                    notification = NotificationService.create_notification(
                        recipient=user,
                        notification_type=Notification.TYPE_LOW_STOCK_ALERT,
                        title=f"Stock Faible: {product.name}",
                        message=f"Le produit '{product.name}' est en stock faible. Quantité: {product.quantity}",
                        priority=Notification.PRIORITY_HIGH,
                        related_product=product,
                        data={
                            'product_id': product.id,
                            'product_name': product.name,
                            'current_quantity': product.quantity,
                            'reorder_threshold': product.reorder_threshold,
                        }
                    )
                    if notification:
                        count += 1
                        self.stdout.write(f"   📦 Low stock: {product.name} → {user.username}")
        
        return count
    
    def _check_out_of_stock_products(self, recipients, check_interval):
        """Check for out of stock products that changed recently"""
        recent_threshold = timezone.now() - timedelta(seconds=check_interval * 2)
        
        out_of_stock_products = Product.objects.filter(
            quantity=0,
            updated_at__gte=recent_threshold  # Only recently went out of stock
        )
        
        count = 0
        for product in out_of_stock_products:
            for user in recipients:
                # Check if notification was already sent recently
                recent_notification = Notification.objects.filter(
                    recipient=user,
                    notification_type=Notification.TYPE_OUT_OF_STOCK_ALERT,
                    related_product=product,
                    created_at__gte=recent_threshold
                ).exists()
                
                if not recent_notification:
                    notification = NotificationService.create_notification(
                        recipient=user,
                        notification_type=Notification.TYPE_OUT_OF_STOCK_ALERT,
                        title=f"Rupture de Stock: {product.name}",
                        message=f"Le produit '{product.name}' est en rupture de stock!",
                        priority=Notification.PRIORITY_URGENT,
                        related_product=product,
                        data={
                            'product_id': product.id,
                            'product_name': product.name,
                            'current_quantity': 0,
                        }
                    )
                    if notification:
                        count += 1
                        self.stdout.write(f"   ❌ Out of stock: {product.name} → {user.username}")
        
        return count
    
    def _check_upcoming_projects(self, recipients, check_interval):
        """Check for projects starting very soon (within next 2 hours)"""
        now = timezone.now()
        soon_threshold = now + timedelta(hours=2)
        
        upcoming_projects = Project.objects.filter(
            start_date__gte=now.date(),
            start_date__lte=soon_threshold.date(),
            is_verified=True
        ).select_related('client')
        
        count = 0
        for project in upcoming_projects:
            for user in recipients:
                # Check if notification was sent in last check interval
                recent_threshold = timezone.now() - timedelta(seconds=check_interval)
                recent_notification = Notification.objects.filter(
                    recipient=user,
                    notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
                    related_project=project,
                    created_at__gte=recent_threshold
                ).exists()
                
                if not recent_notification:
                    hours_until = int((project.start_date - now.date()).days * 24)
                    notification = NotificationService.create_notification(
                        recipient=user,
                        notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
                        title=f"Projet Bientôt: {project.name}",
                        message=f"Le projet '{project.name}' commence dans {hours_until}h",
                        priority=Notification.PRIORITY_HIGH,
                        related_project=project,
                        data={
                            'project_id': project.id,
                            'project_name': project.name,
                            'hours_until_start': hours_until,
                        }
                    )
                    if notification:
                        count += 1
                        self.stdout.write(f"   🏗️  Project soon: {project.name} → {user.username}")
        
        return count
    
    def _check_upcoming_maintenances(self, recipients, check_interval):
        """Check for maintenances starting very soon (within next 2 hours)"""
        now = timezone.now()
        soon_threshold = now + timedelta(hours=2)
        
        upcoming_maintenances = Maintenance.objects.filter(
            start_date__gte=now.date(),
            start_date__lte=soon_threshold.date()
        ).select_related('project', 'project__client')
        
        count = 0
        for maintenance in upcoming_maintenances:
            for user in recipients:
                recent_threshold = timezone.now() - timedelta(seconds=check_interval)
                recent_notification = Notification.objects.filter(
                    recipient=user,
                    notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON,
                    related_maintenance=maintenance,
                    created_at__gte=recent_threshold
                ).exists()
                
                if not recent_notification:
                    hours_until = int((maintenance.start_date - now.date()).days * 24)
                    notification = NotificationService.create_notification(
                        recipient=user,
                        notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON,
                        title=f"Maintenance Bientôt: {maintenance.project.name}",
                        message=f"Maintenance prévue dans {hours_until}h",
                        priority=Notification.PRIORITY_HIGH,
                        related_project=maintenance.project,
                        related_maintenance=maintenance,
                        data={
                            'maintenance_id': maintenance.id,
                            'project_name': maintenance.project.name,
                            'hours_until_start': hours_until,
                        }
                    )
                    if notification:
                        count += 1
                        self.stdout.write(f"   🔧 Maintenance soon: {maintenance.project.name} → {user.username}")
        
        return count
    
    def _check_recent_assignments(self, check_interval):
        """Check for recently assigned projects"""
        recent_threshold = timezone.now() - timedelta(seconds=check_interval * 2)
        
        # Get projects with recent assignments
        recent_projects = Project.objects.filter(
            assigned_employers__isnull=False,
            updated_at__gte=recent_threshold
        ).distinct()
        
        count = 0
        for project in recent_projects:
            for employer in project.assigned_employers.all():
                # Check if assignment notification was sent recently
                recent_notification = Notification.objects.filter(
                    recipient=employer,
                    notification_type=Notification.TYPE_PROJECT_ASSIGNED,
                    related_project=project,
                    created_at__gte=recent_threshold
                ).exists()
                
                if not recent_notification:
                    notification = NotificationService.create_notification(
                        recipient=employer,
                        notification_type=Notification.TYPE_PROJECT_ASSIGNED,
                        title=f"Nouveau Projet: {project.name}",
                        message=f"Vous êtes assigné au projet '{project.name}'",
                        priority=Notification.PRIORITY_HIGH,
                        related_project=project,
                        data={
                            'project_id': project.id,
                            'project_name': project.name,
                        }
                    )
                    if notification:
                        count += 1
                        self.stdout.write(f"   👥 Assignment: {project.name} → {employer.username}")
        
        return count
    
    def _resend_unsent_notifications(self, check_interval):
        """Resend notifications that haven't been sent via SSE yet"""
        unsent_threshold = timezone.now() - timedelta(seconds=check_interval)
        
        unsent_notifications = Notification.objects.filter(
            sent_at__isnull=True,
            created_at__lte=unsent_threshold,  # Created before last check
            created_at__gte=timezone.now() - timedelta(minutes=5)  # But not too old
        )
        
        count = 0
        for notification in unsent_notifications:
            # Mark as sent to trigger SSE delivery
            notification.mark_as_sent()
            count += 1
            self.stdout.write(f"   🔄 Resent unsent: {notification.title}")
        
        return count