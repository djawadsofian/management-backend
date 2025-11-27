# apps/notifications/management/commands/check_and_send_notifications.py
"""
Django management command to check and send recurring notifications
Run this command via cron job 3 times a day (8 AM, 2 PM, 8 PM):
0 8,14,20 * * * cd /path/to/project && python manage.py check_and_send_notifications
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
    help = 'Check and send recurring notifications for low stock, upcoming projects, and maintenances'
    
    def handle(self, *args, **options):
        now = timezone.now()
        
        self.stdout.write(self.style.HTTP_INFO(
            f"🔔 Checking notifications at {now.strftime('%Y-%m-%d %H:%M:%S')}"
        ))
        
        # Get all admins and assistants
        admins_and_assistants = CustomUser.objects.filter(
            role__in=[CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT],
            is_active=True
        )
        
        if not admins_and_assistants.exists():
            self.stdout.write(self.style.WARNING("⚠️  No active admins or assistants found"))
            return
        
        # ========== 1. CHECK LOW STOCK PRODUCTS ==========
        self.stdout.write(self.style.HTTP_INFO("\n📦 Checking low stock products..."))
        low_stock_count = self._check_low_stock_products(admins_and_assistants)
        
        # ========== 2. CHECK OUT OF STOCK PRODUCTS ==========
        self.stdout.write(self.style.HTTP_INFO("\n❌ Checking out of stock products..."))
        out_of_stock_count = self._check_out_of_stock_products(admins_and_assistants)
        
        # ========== 3. CHECK PROJECTS STARTING IN 24H ==========
        self.stdout.write(self.style.HTTP_INFO("\n🏗️  Checking projects starting in 24 hours..."))
        projects_count = self._check_upcoming_projects(admins_and_assistants)
        
        # ========== 4. CHECK MAINTENANCES STARTING IN 24H ==========
        self.stdout.write(self.style.HTTP_INFO("\n🔧 Checking maintenances starting in 24 hours..."))
        maintenances_count = self._check_upcoming_maintenances(admins_and_assistants)
        
        # ========== 5. RESEND UNCONFIRMED NOTIFICATIONS TO EMPLOYERS ==========
        self.stdout.write(self.style.HTTP_INFO("\n🔄 Resending unconfirmed notifications to employers..."))
        resent_count = self._resend_unconfirmed_to_employers()
        
        # ========== SUMMARY ==========
        self.stdout.write(self.style.SUCCESS(
            f"\n📊 Summary:\n"
            f"   • Low stock alerts: {low_stock_count}\n"
            f"   • Out of stock alerts: {out_of_stock_count}\n"
            f"   • Projects starting soon: {projects_count}\n"
            f"   • Maintenances starting soon: {maintenances_count}\n"
            f"   • Resent unconfirmed (employers): {resent_count}\n"
        ))
    
    def _check_low_stock_products(self, recipients):
        """Check and notify about low stock products"""
        low_stock_products = Product.objects.filter(
            quantity__gt=0,
            quantity__lte=models.F('reorder_threshold')
        )
        
        count = 0
        for product in low_stock_products:
            for user in recipients:
                # Check if unconfirmed notification already exists
                existing = Notification.objects.filter(
                    recipient=user,
                    notification_type=Notification.TYPE_LOW_STOCK_ALERT,
                    related_product=product,
                    is_confirmed=False
                ).first()
                
                if existing:
                    # Update last sent time
                    existing.mark_as_sent()
                    self.stdout.write(f"   🔄 Resent low stock alert for {product.name} to {user.username}")
                else:
                    # Create new notification
                    notification = NotificationService.create_notification(
                        recipient=user,
                        notification_type=Notification.TYPE_LOW_STOCK_ALERT,
                        title=f"Stock Faible: {product.name}",
                        message=f"Le produit '{product.name}' est en stock faible. Quantité actuelle: {product.quantity}, Seuil: {product.reorder_threshold}",
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
                        self.stdout.write(f"   ✅ Created low stock alert for {product.name} to {user.username}")
        
        return count
    
    def _check_out_of_stock_products(self, recipients):
        """Check and notify about out of stock products"""
        out_of_stock_products = Product.objects.filter(quantity=0)
        
        count = 0
        for product in out_of_stock_products:
            for user in recipients:
                # Check if unconfirmed notification already exists
                existing = Notification.objects.filter(
                    recipient=user,
                    notification_type=Notification.TYPE_OUT_OF_STOCK_ALERT,
                    related_product=product,
                    is_confirmed=False
                ).first()
                
                if existing:
                    # Update last sent time
                    existing.mark_as_sent()
                    self.stdout.write(f"   🔄 Resent out of stock alert for {product.name} to {user.username}")
                else:
                    # Create new notification
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
                            'reorder_threshold': product.reorder_threshold,
                        }
                    )
                    if notification:
                        count += 1
                        self.stdout.write(f"   ✅ Created out of stock alert for {product.name} to {user.username}")
        
        return count
    
    def _check_upcoming_projects(self, recipients):
        """Check and notify about projects starting in 24 hours"""
        now = timezone.now()
        tomorrow = now + timedelta(hours=24)
        
        # Find projects starting between now and 24 hours from now
        upcoming_projects = Project.objects.filter(
            start_date__gte=now.date(),
            start_date__lte=tomorrow.date(),
            is_verified=True
        ).select_related('client')
        
        count = 0
        for project in upcoming_projects:
            for user in recipients:
                # Check if unconfirmed notification already exists
                existing = Notification.objects.filter(
                    recipient=user,
                    notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
                    related_project=project,
                    is_confirmed=False
                ).first()
                
                if existing:
                    # Update last sent time
                    existing.mark_as_sent()
                    self.stdout.write(f"   🔄 Resent project alert for {project.name} to {user.username}")
                else:
                    # Create new notification
                    notification = NotificationService.create_notification(
                        recipient=user,
                        notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
                        title=f"Projet Démarre Demain: {project.name}",
                        message=f"Le projet '{project.name}' pour le client {project.client.name} commence demain ({project.start_date.strftime('%d/%m/%Y')}).",
                        priority=Notification.PRIORITY_URGENT,
                        related_project=project,
                        data={
                            'project_id': project.id,
                            'project_name': project.name,
                            'client_name': project.client.name,
                            'start_date': project.start_date.isoformat(),
                            'hours_until_start': 24,
                        }
                    )
                    if notification:
                        count += 1
                        self.stdout.write(f"   ✅ Created project alert for {project.name} to {user.username}")
        
        return count
    
    def _check_upcoming_maintenances(self, recipients):
        """Check and notify about maintenances starting in 24 hours"""
        now = timezone.now()
        tomorrow = now + timedelta(hours=24)
        
        # Find maintenances starting between now and 24 hours from now
        upcoming_maintenances = Maintenance.objects.filter(
            start_date__gte=now.date(),
            start_date__lte=tomorrow.date()
        ).select_related('project', 'project__client')
        
        count = 0
        for maintenance in upcoming_maintenances:
            for user in recipients:
                # Check if unconfirmed notification already exists
                existing = Notification.objects.filter(
                    recipient=user,
                    notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON,
                    related_maintenance=maintenance,
                    is_confirmed=False
                ).first()
                
                if existing:
                    # Update last sent time
                    existing.mark_as_sent()
                    self.stdout.write(f"   🔄 Resent maintenance alert for {maintenance.project.name} to {user.username}")
                else:
                    # Create new notification
                    notification = NotificationService.create_notification(
                        recipient=user,
                        notification_type=Notification.TYPE_MAINTENANCE_STARTING_SOON,
                        title=f"Maintenance Demain: {maintenance.project.name}",
                        message=f"La maintenance du projet '{maintenance.project.name}' est prévue demain ({maintenance.start_date.strftime('%d/%m/%Y')}).",
                        priority=Notification.PRIORITY_URGENT,
                        related_project=maintenance.project,
                        related_maintenance=maintenance,
                        data={
                            'maintenance_id': maintenance.id,
                            'project_id': maintenance.project.id,
                            'project_name': maintenance.project.name,
                            'start_date': maintenance.start_date.isoformat(),
                            'end_date': maintenance.end_date.isoformat(),
                            'maintenance_type': maintenance.maintenance_type,
                            'hours_until_start': 24,
                        }
                    )
                    if notification:
                        count += 1
                        self.stdout.write(f"   ✅ Created maintenance alert for {maintenance.project.name} to {user.username}")
        
        return count
    
    def _resend_unconfirmed_to_employers(self):
        """Resend unconfirmed notifications to employers"""
        # Get all unconfirmed notifications for employers (PROJECT_ASSIGNED)
        unconfirmed = Notification.objects.filter(
            is_confirmed=False,
            notification_type=Notification.TYPE_PROJECT_ASSIGNED,
            recipient__role=CustomUser.ROLE_EMPLOYER
        )
        
        count = 0
        for notification in unconfirmed:
            notification.mark_as_sent()
            count += 1
            self.stdout.write(f"   🔄 Resent project assignment to {notification.recipient.username}")
        
        return count