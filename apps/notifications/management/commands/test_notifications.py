# apps/notifications/management/commands/test_notifications.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification
from apps.notifications.signals import notification_created  # ADD THIS
from apps.projects.models import Project
from apps.stock.models import Product


User = get_user_model()

class Command(BaseCommand):
    help = "Test notification system by creating sample notifications"

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Username to send notifications to (defaults to first admin)'
        )
        parser.add_argument(  # ADD THIS OPTION
            '--send-existing',
            action='store_true',
            help='Send existing unread notifications through SSE'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO("🔔 Testing Notification System"))
        self.stdout.write("=" * 60)
        

        # Get target user
        username = options.get('user')
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User '{username}' not found"))
                return
        else:
            # Get first admin or create one
            user = User.objects.filter(role=User.ROLE_ADMIN).first()
            if not user:
                self.stdout.write(self.style.WARNING("No admin user found, creating test user..."))
                user = User.objects.create_user(
                    username='test_admin',
                    password='test123',
                    role=User.ROLE_ADMIN,
                    email='test@example.com'
                )

        self.stdout.write(f"Target user: {user.username} (ID: {user.id})")
        self.stdout.write("")

        # Option to send existing notifications
        if options.get('send_existing'):
            self.stdout.write(self.style.HTTP_INFO("Sending existing notifications through SSE..."))
            unread_notifications = Notification.objects.filter(recipient=user, is_read=False)
            count = 0
            
            for notification in unread_notifications:
                # Directly call the signal handler (bypassing signal)
                from apps.notifications.sse_views import notification_signal_handler
                notification_signal_handler(
                    sender=Notification,
                    notification=notification,
                    recipient=user
                )
                count += 1
            
            self.stdout.write(self.style.SUCCESS(f"   ✅ Sent {count} existing notifications through SSE"))
            self.stdout.write("")

        # Test 1: Simple notification
        self.stdout.write(self.style.HTTP_INFO("Test 1: Creating simple notification..."))
        notif1 = NotificationService.create_notification(
            recipient=user,
            notification_type=Notification.TYPE_PROJECT_MODIFIED,
            title="Test Notification",
            message="This is a test notification to verify the system works",
            priority=Notification.PRIORITY_MEDIUM
        )
        if notif1:
            self.stdout.write(self.style.SUCCESS(f"   ✅ Created notification ID: {notif1.id}"))
        else:
            self.stdout.write(self.style.ERROR("   ❌ Failed to create notification"))

        # Test 2: Urgent notification
        self.stdout.write(self.style.HTTP_INFO("Test 2: Creating urgent notification..."))
        notif2 = NotificationService.create_notification(
            recipient=user,
            notification_type=Notification.TYPE_PROJECT_STARTING_SOON,
            title="URGENT: Project Starting Tomorrow",
            message="Important project requires your immediate attention",
            priority=Notification.PRIORITY_URGENT
        )
        if notif2:
            self.stdout.write(self.style.SUCCESS(f"   ✅ Created urgent notification ID: {notif2.id}"))

        # Test 3: Stock alert notification
        self.stdout.write(self.style.HTTP_INFO("Test 3: Creating stock alert notification..."))
        
        # Try to get a real product, or create a test one
        product = Product.objects.first()
        if not product:
            
            product = Product.objects.create(
                name='Test Product',
                quantity=5,
                reorder_threshold=10
            )
        
        notif3 = NotificationService.create_notification(
            recipient=user,
            notification_type=Notification.TYPE_LOW_STOCK_ALERT,
            title=f"Low Stock: {product.name}",
            message=f"Product '{product.name}' is running low. Current: {product.quantity}, Threshold: {product.reorder_threshold}",
            priority=Notification.PRIORITY_HIGH,
            related_product=product,
            data={
                'product_id': product.id,
                'current_quantity': product.quantity,
                'reorder_threshold': product.reorder_threshold
            }
        )
        if notif3:
            self.stdout.write(self.style.SUCCESS(f"   ✅ Created stock alert ID: {notif3.id}"))

        # Test 4: Project notification (if project exists)
        self.stdout.write(self.style.HTTP_INFO("Test 4: Creating project notification..."))
        project = Project.objects.first()
        if project:
            notif4 = NotificationService.create_notification(
                recipient=user,
                notification_type=Notification.TYPE_PROJECT_ASSIGNED,
                title=f"Assigned to Project: {project.name}",
                message=f"You have been assigned to project '{project.name}' for client {project.client.name}",
                priority=Notification.PRIORITY_HIGH,
                related_project=project,
                data={
                    'project_id': project.id,
                    'project_name': project.name,
                    'client_name': project.client.name
                }
            )
            if notif4:
                self.stdout.write(self.style.SUCCESS(f"   ✅ Created project notification ID: {notif4.id}"))
        else:
            self.stdout.write(self.style.WARNING("   ⚠️  No projects found, skipping"))

        # Summary
        self.stdout.write("")
        self.stdout.write("=" * 60)
        total_notifs = Notification.objects.filter(recipient=user).count()
        unread_notifs = Notification.objects.filter(recipient=user, is_read=False).count()
        
        self.stdout.write(self.style.SUCCESS("✅ Notification Test Complete!"))
        self.stdout.write("")
        self.stdout.write(f"📊 Statistics for {user.username}:")
        self.stdout.write(f"   • Total notifications: {total_notifs}")
        self.stdout.write(f"   • Unread: {unread_notifs}")
        self.stdout.write("")
        self.stdout.write("💡 Tip: Run with --send-existing to push existing notifications through SSE")
        self.stdout.write("")
        self.stdout.write(f"📝 SSE Endpoint: http://localhost:8000/api/notifications/stream/")