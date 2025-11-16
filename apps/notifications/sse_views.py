# apps/notifications/sse_views.py
"""
Server-Sent Events (SSE) views for real-time notifications
"""
import json
import time
import queue
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from apps.notifications.models import Notification
from apps.notifications.signals import notification_created
import logging

logger = logging.getLogger(__name__)

# Global dictionary to store user queues
# Format: {user_id: queue.Queue}
user_queues = {}


def add_user_queue(user_id):
    """Add a queue for a user"""
    if user_id not in user_queues:
        user_queues[user_id] = queue.Queue()
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
                'data': notification.data or {},
            }
            
            # Add related objects
            if notification.related_project:
                notification_data['project'] = {
                    'id': notification.related_project.id,
                    'name': notification.related_project.name,
                    'client_name': notification.related_project.client.name,
                }
            
            if notification.related_maintenance:
                notification_data['maintenance'] = {
                    'id': notification.related_maintenance.id,
                    'start_date': notification.related_maintenance.start_date.isoformat(),
                    'end_date': notification.related_maintenance.end_date.isoformat(),
                }
            
            # Push to queue
            user_queue.put(notification_data)
            logger.info(f"Notification {notification.id} pushed to queue for user {recipient.id}")
            
        except Exception as e:
            logger.error(f"Error pushing notification to queue: {e}")


# Connect signal
notification_created.connect(notification_signal_handler)


def event_stream(user):
    """
    Generator function that yields SSE events
    """
    user_queue = add_user_queue(user.id)
    
    try:
        # Send initial connection success event
        yield f"event: connected\ndata: {json.dumps({'message': 'Connected to notification stream', 'user_id': user.id})}\n\n"
        
        # Send keepalive every 30 seconds to prevent timeout
        keepalive_interval = 30
        last_keepalive = time.time()
        
        while True:
            try:
                # Check for new notifications (non-blocking with timeout)
                try:
                    notification_data = user_queue.get(timeout=1)
                    
                    # Send notification event
                    yield f"event: notification\ndata: {json.dumps(notification_data)}\n\n"
                    
                    # Mark as sent
                    try:
                        notification = Notification.objects.get(id=notification_data['id'])
                        notification.mark_as_sent()
                    except Notification.DoesNotExist:
                        pass
                    
                except queue.Empty:
                    # No notification available, check for keepalive
                    current_time = time.time()
                    if current_time - last_keepalive >= keepalive_interval:
                        # Send keepalive ping
                        yield f"event: ping\ndata: {json.dumps({'timestamp': int(current_time)})}\n\n"
                        last_keepalive = current_time
                
            except Exception as e:
                logger.error(f"Error in event stream: {e}")
                break
                
    except GeneratorExit:
        logger.info(f"Client disconnected: user {user.id}")
    finally:
        # Clean up queue when connection closes
        remove_user_queue(user.id)


@require_GET
@login_required
def notification_stream(request):
    """
    SSE endpoint for real-time notifications
    
    Usage:
        const eventSource = new EventSource('/api/notifications/stream/');
        
        eventSource.addEventListener('connected', (e) => {
            console.log('Connected:', JSON.parse(e.data));
        });
        
        eventSource.addEventListener('notification', (e) => {
            const notification = JSON.parse(e.data);
            console.log('New notification:', notification);
        });
        
        eventSource.addEventListener('ping', (e) => {
            console.log('Keepalive ping');
        });
    """
    response = StreamingHttpResponse(
        event_stream(request.user),
        content_type='text/event-stream'
    )
    
    # SSE headers
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
    
    return response


@require_GET
@login_required
def notification_count(request):
    """
    Get unread notification count
    
    Returns:
        JSON with unread count
    """
    from django.http import JsonResponse
    from apps.notifications.services import NotificationService
    
    count = NotificationService.get_unread_count(request.user)
    
    return JsonResponse({
        'count': count,
        'user_id': request.user.id
    })