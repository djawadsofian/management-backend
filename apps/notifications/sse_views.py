# apps/notifications/sse_views.py
import json
import asyncio
import logging
from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from channels.db import database_sync_to_async
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

# Global dictionary to store user queues
user_queues = {}

def add_user_queue(user_id):
    """Add a queue for a user"""
    if user_id not in user_queues:
        user_queues[user_id] = asyncio.Queue()
    return user_queues[user_id]

def remove_user_queue(user_id):
    """Remove a user's queue"""
    if user_id in user_queues:
        del user_queues[user_id]

def get_user_queue(user_id):
    """Get a user's queue"""
    return user_queues.get(user_id)

# Signal handler
def notification_signal_handler(sender, notification, recipient, **kwargs):
    """
    Handle notification_created signal and push to user's queue
    """
    user_queue = get_user_queue(recipient.id)
    if user_queue:
        try:
            # Serialize notification
            notification_data = {
                'id': notification.id,
                'type': notification.notification_type,
                'title': notification.title,
                'message': notification.message,
                'priority': notification.priority,
                'created_at': notification.created_at.isoformat(),
                'is_read': notification.is_read,
                'is_confirmed': notification.is_confirmed,
                'data': notification.data or {},
            }
            
            # Add related objects
            if notification.related_project:
                notification_data['project'] = {
                    'id': notification.related_project.id,
                    'name': notification.related_project.name,
                }
            
            if notification.related_maintenance:
                notification_data['maintenance'] = {
                    'id': notification.related_maintenance.id,
                    'start_date': notification.related_maintenance.start_date.isoformat(),
                }

            if notification.related_product:
                notification_data['product'] = {
                    'id': notification.related_product.id,
                    'name': notification.related_product.name,
                }
            
            # Push to async queue
            try:
                user_queue.put_nowait(notification_data)
                logger.info(f"Notification {notification.id} pushed to queue for user {recipient.id}")
            except asyncio.QueueFull:
                logger.warning(f"Queue full for user {recipient.id}, dropping notification")
            
        except Exception as e:
            logger.error(f"Error pushing notification to queue: {e}")

# Connect signal (make sure this is called when module loads)
from apps.notifications.signals import notification_created
notification_created.connect(notification_signal_handler)

@database_sync_to_async
def mark_notification_sent(notification_id):
    """Mark notification as sent (async)"""
    try:
        notification = Notification.objects.get(id=notification_id)
        notification.mark_as_sent()
        return True
    except Notification.DoesNotExist:
        return False

async def event_stream_generator(user):
    """
    Async generator function that yields SSE events
    """
    user_queue = add_user_queue(user.id)
    
    try:
        # Send initial connection success event
        yield f"data: {json.dumps({'event': 'connected', 'message': 'Connected to notification stream', 'user_id': user.id})}\n\n"
        
        # Send keepalive every 30 seconds
        keepalive_interval = 30
        last_keepalive = asyncio.get_event_loop().time()
        
        while True:
            try:
                # Check for new notifications (with timeout)
                try:
                    notification_data = await asyncio.wait_for(
                        user_queue.get(), 
                        timeout=1.0
                    )
                    
                    # Send notification event
                    yield f"data: {json.dumps({'event': 'notification', 'data': notification_data})}\n\n"
                    
                    # Mark as sent
                    await mark_notification_sent(notification_data['id'])
                    
                except asyncio.TimeoutError:
                    # No notification available, check for keepalive
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_keepalive >= keepalive_interval:
                        # Send keepalive ping
                        yield f"data: {json.dumps({'event': 'ping', 'timestamp': int(current_time)})}\n\n"
                        last_keepalive = current_time
                
            except Exception as e:
                logger.error(f"Error in event stream: {e}")
                break
                
    except GeneratorExit:
        logger.info(f"Client disconnected: user {user.id}")
    finally:
        # Clean up queue when connection closes
        remove_user_queue(user.id)

# WSGI-compatible view
@require_GET
@login_required
async def notification_stream(request):
    """
    SSE endpoint for real-time notifications (ASGI version)
    """
    # Your existing authentication logic...
    
    async def event_stream():
        # Your existing event stream logic, but make it truly async
        user_queue = add_user_queue(request.user.id)
        
        try:
            yield f"data: {json.dumps({'event': 'connected', 'message': 'Connected to notification stream', 'user_id': request.user.id})}\n\n"
            
            keepalive_interval = 30
            last_keepalive = asyncio.get_event_loop().time()
            
            while True:
                try:
                    # Use async queue get
                    notification_data = await asyncio.wait_for(
                        user_queue.get(), 
                        timeout=1.0
                    )
                    
                    yield f"data: {json.dumps({'event': 'notification', 'data': notification_data})}\n\n"
                    
                    # Mark as sent async
                    await mark_notification_sent(notification_data['id'])
                    
                except asyncio.TimeoutError:
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_keepalive >= keepalive_interval:
                        yield f"data: {json.dumps({'event': 'ping', 'timestamp': int(current_time)})}\n\n"
                        last_keepalive = current_time
                
        except Exception as e:
            logger.error(f"Error in event stream: {e}")
        finally:
            remove_user_queue(request.user.id)
    
    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Cache-Control'
    
    return response

@require_GET
@login_required
def notification_count(request):
    """
    Get unread notification count
    """
    count = NotificationService.get_unread_count(request.user)
    
    return JsonResponse({
        'count': count,
        'user_id': request.user.id
    })