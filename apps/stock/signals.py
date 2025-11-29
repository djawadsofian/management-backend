# apps/stock/signals.py
"""
Signal handlers for Stock models - IMMEDIATE notifications
"""
from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from apps.stock.models import Product
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification
from apps.users.models import CustomUser
import logging

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Product)
def track_stock_changes(sender, instance, **kwargs):
    """
    Track previous stock state before save for immediate notifications
    """
    if instance.pk:
        try:
            previous = Product.objects.get(pk=instance.pk)
            instance._previous_quantity = previous.quantity
            instance._previous_reorder_threshold = previous.reorder_threshold
            instance._previous_is_low_stock = previous.is_low_stock
            instance._previous_is_out_of_stock = previous.is_out_of_stock
        except Product.DoesNotExist:
            instance._previous_quantity = 0
            instance._previous_reorder_threshold = 0
            instance._previous_is_low_stock = False
            instance._previous_is_out_of_stock = False
    else:
        instance._previous_quantity = 0
        instance._previous_reorder_threshold = 0
        instance._previous_is_low_stock = False
        instance._previous_is_out_of_stock = False


@receiver(post_save, sender=Product)
def product_stock_changed(sender, instance, created, **kwargs):
    """
    Send immediate notifications when stock levels change critically
    """
    print(f"🔄 Product signal triggered - Created: {created}, Low Stock: {instance.is_low_stock}, Out of Stock: {instance.is_out_of_stock}")

    if created:
        # New product created - check if it's low stock or out of stock
        if instance.is_out_of_stock:
            print("🆕 New product created - OUT OF STOCK")
            _send_out_of_stock_notification(instance)
        elif instance.is_low_stock:
            print("🆕 New product created - LOW STOCK")
            _send_low_stock_notification(instance)
        return

    # Existing product updated
    if hasattr(instance, '_previous_quantity'):
        previous_quantity = instance._previous_quantity
        previous_is_low_stock = instance._previous_is_low_stock
        previous_is_out_of_stock = instance._previous_is_out_of_stock
        current_quantity = instance.quantity
        
        print(f"📊 Stock change: {previous_quantity} -> {current_quantity}, Low: {previous_is_low_stock}->{instance.is_low_stock}, Out: {previous_is_out_of_stock}->{instance.is_out_of_stock}")

        # If product is currently low stock or out of stock
        if instance.is_low_stock or instance.is_out_of_stock:
            # Remove all existing notifications for this product
            _remove_all_product_notifications(instance)
            
            # Create new notification with current quantity
            if instance.is_out_of_stock:
                print("🔄 Product now OUT OF STOCK - creating new notification")
                _send_out_of_stock_notification(instance)
            elif instance.is_low_stock:
                print("🔄 Product now LOW STOCK - creating new notification")
                _send_low_stock_notification(instance)
        
        # If product was low/out of stock but now is normal
        elif (previous_is_low_stock or previous_is_out_of_stock) and not instance.is_low_stock and not instance.is_out_of_stock:
            print("✅ Product back to NORMAL stock - removing all notifications")
            # Remove all notifications for this product since it's no longer low/out of stock
            _remove_all_product_notifications(instance)
            
            # Optional: Send restocked notification
            if previous_is_out_of_stock:
                _send_restocked_notification(instance)
            elif previous_is_low_stock:
                _send_restocked_from_low_notification(instance)


@receiver(pre_delete, sender=Product)
def product_deleted(sender, instance, **kwargs):
    """
    Remove all notifications when product is deleted
    """
    print(f"🗑️ Product deleted - removing all notifications for product: {instance.name}")
    _remove_all_product_notifications(instance)


def _remove_all_product_notifications(product):
    """Remove all notifications for a specific product"""
    deleted_count, _ = Notification.objects.filter(
        related_product=product
    ).delete()
    
    if deleted_count > 0:
        print(f"🧹 Removed {deleted_count} notifications for product: {product.name}")
        logger.info(f"Removed {deleted_count} notifications for deleted product: {product.name}")


def _send_low_stock_notification(product):
    """Send immediate low stock notification to admins and assistants"""
    admins_assistants = CustomUser.objects.filter(
        role__in=[CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT],
        is_active=True
    )
    
    for user in admins_assistants:
        print(f"📦 Creating LOW STOCK notification for {product.name} to {user.username}")
        NotificationService.create_notification(
            recipient=user,
            notification_type=Notification.TYPE_LOW_STOCK_ALERT,
            title=f"📦 Stock Faible: {product.name}",
            message=f"Le produit '{product.name}' est en stock faible. Quantité: {product.quantity}, Seuil: {product.reorder_threshold}",
            priority=Notification.PRIORITY_HIGH,
            related_product=product,
            data={
                'product_id': product.id,
                'product_name': product.name,
                'current_quantity': product.quantity,
                'reorder_threshold': product.reorder_threshold,
                'stock_status': 'LOW_STOCK',
                'trigger': 'immediate_stock_change'
            }
        )
        logger.info(f"Immediate low stock notification sent for {product.name} to {user.username}")


def _send_out_of_stock_notification(product):
    """Send immediate out of stock notification to admins and assistants"""
    admins_assistants = CustomUser.objects.filter(
        role__in=[CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT],
        is_active=True
    )
    
    for user in admins_assistants:
        print(f"❌ Creating OUT OF STOCK notification for {product.name} to {user.username}")
        NotificationService.create_notification(
            recipient=user,
            notification_type=Notification.TYPE_OUT_OF_STOCK_ALERT,
            title=f"❌ Rupture de Stock: {product.name}",
            message=f"Le produit '{product.name}' est en rupture de stock! Quantité: 0",
            priority=Notification.PRIORITY_URGENT,
            related_product=product,
            data={
                'product_id': product.id,
                'product_name': product.name,
                'current_quantity': 0,
                'stock_status': 'OUT_OF_STOCK',
                'trigger': 'immediate_stock_change'
            }
        )
        logger.info(f"Immediate out of stock notification sent for {product.name} to {user.username}")


def _send_restocked_notification(product):
    """Send notification when product is restocked from out of stock"""
    admins_assistants = CustomUser.objects.filter(
        role__in=[CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT],
        is_active=True
    )
    
    for user in admins_assistants:
        print(f"✅ Creating RESTOCKED notification for {product.name} to {user.username}")
        NotificationService.create_notification(
            recipient=user,
            notification_type=Notification.TYPE_LOW_STOCK_ALERT,  # Use low stock type for positive news
            title=f"✅ Stock Réapprovisionné: {product.name}",
            message=f"Le produit '{product.name}' a été réapprovisionné. Nouvelle quantité: {product.quantity}",
            priority=Notification.PRIORITY_MEDIUM,
            related_product=product,
            data={
                'product_id': product.id,
                'product_name': product.name,
                'current_quantity': product.quantity,
                'reorder_threshold': product.reorder_threshold,
                'stock_status': 'RESTOCKED',
                'trigger': 'immediate_stock_change'
            }
        )


def _send_restocked_from_low_notification(product):
    """Send notification when product is restocked above low stock threshold"""
    admins_assistants = CustomUser.objects.filter(
        role__in=[CustomUser.ROLE_ADMIN, CustomUser.ROLE_ASSISTANT],
        is_active=True
    )
    
    for user in admins_assistants:
        print(f"📈 Creating NORMAL STOCK notification for {product.name} to {user.username}")
        NotificationService.create_notification(
            recipient=user,
            notification_type=Notification.TYPE_LOW_STOCK_ALERT,  # Use low stock type for positive news
            title=f"📈 Stock Normal: {product.name}",
            message=f"Le produit '{product.name}' est de nouveau en stock normal. Quantité: {product.quantity}",
            priority=Notification.PRIORITY_LOW,
            related_product=product,
            data={
                'product_id': product.id,
                'product_name': product.name,
                'current_quantity': product.quantity,
                'reorder_threshold': product.reorder_threshold,
                'stock_status': 'NORMAL',
                'trigger': 'immediate_stock_change'
            }
        )