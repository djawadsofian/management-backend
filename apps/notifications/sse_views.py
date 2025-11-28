# apps/notifications/sse_views.py
import json
import asyncio
import logging
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from asgiref.sync import sync_to_async
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from multiprocessing import Manager

logger = logging.getLogger(__name__)

manager = Manager()
user_queues = manager.dict() 

def add_user_queue(user_id):
    """Add a queue for a user"""
    if user_id not in user_queues:
        user_queues[user_id] = asyncio.Queue(maxsize=100)
        print(f"📝 Created new queue for user {user_id}")
    else:
        print(f"📝 Using existing queue for user {user_id}")
    return user_queues[user_id]

def remove_user_queue(user_id):
    """Remove a user's queue"""
    if user_id in user_queues:
        del user_queues[user_id]
        print(f"🗑️ Removed queue for user {user_id}")

def get_user_queue(user_id):
    """Get a user's queue"""
    queue = user_queues.get(user_id)
    if queue:
        print(f"📦 Found queue for user {user_id}")
    else:
        print(f"❌ No queue found for user {user_id}")
    return queue

# Signal handler

def notification_signal_handler(sender, notification, recipient, **kwargs):
    """
    Handle notification_created signal and push to user's queue
    """
    print(f"🚨 SIGNAL HANDLER CALLED: Notification {notification.id} for user {recipient.id}")
    
    user_queue = get_user_queue(recipient.id)
    if user_queue:
        print(f"📦 User queue found, pushing notification {notification.id} to queue...")
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
                print(f"✅ SUCCESS: Notification {notification.id} pushed to queue for user {recipient.id}")
            except asyncio.QueueFull:
                print(f"❌ QUEUE FULL: Queue full for user {recipient.id}, dropping notification")
            
        except Exception as e:
            print(f"❌ ERROR pushing notification to queue: {e}")
    else:
        print(f"⚠️  No user queue found for user {recipient.id} (user not connected via SSE)")

# Connect signal
from apps.notifications.signals import notification_created
notification_created.connect(notification_signal_handler)
print("✅ Signal handler connected!")


@sync_to_async
def mark_notification_sent(notification_id):
    """Mark notification as sent (async)"""
    try:
        notification = Notification.objects.get(id=notification_id)
        notification.mark_as_sent()
        return True
    except Notification.DoesNotExist:
        return False


# CRITICAL FIX: Make this a proper async view for ASGI
@require_GET
async def notification_stream(request):
    """
    SSE endpoint for real-time notifications (ASGI version)
    """
    # Check authentication
    user = request.user
    if not user.is_authenticated:
        from django.http import JsonResponse
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    print(f"🔗 NEW SSE CONNECTION: User {user.id} - {user.username}")
    print(f"📊 Current active queues: {list(user_queues.keys())}")
    
    async def event_stream():
        user_queue = add_user_queue(user.id)
        print(f"📝 User {user.id} queue ready - total queues: {len(user_queues)}")
        
        try:
            # Send initial connection success event
            yield f"data: {json.dumps({'event': 'connected', 'message': 'Connected to notification stream', 'user_id': user.id})}\n\n"
            print(f"📤 Sent 'connected' event to user {user.id}")
            
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
                        
                        print(f"📤 Sending notification {notification_data['id']} to user {user.id}")
                        # Send notification event
                        yield f"data: {json.dumps({'event': 'notification', 'data': notification_data})}\n\n"
                        print(f"✅ Notification {notification_data['id']} sent to user {user.id}")
                        
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
                    print(f"❌ Error in event stream for user {user.id}: {e}")
                    break
                    
        except GeneratorExit:
            print(f"🔴 Client disconnected: user {user.id}")
        finally:
            # Clean up queue when connection closes
            remove_user_queue(user.id)
            print(f"🧹 Cleaned up queue for user {user.id}")
    
    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    # CRITICAL: Set proper headers for SSE
    response['Cache-Control'] = 'no-cache, no-transform'
    response['X-Accel-Buffering'] = 'no'
    response['Connection'] = 'keep-alive'
    
    # CORS headers (adjust as needed for your frontend)
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Cache-Control, Authorization'
    response['Access-Control-Allow-Credentials'] = 'true'
    
    return response


@require_GET
@login_required
def notification_count(request):
    """
    Get unread notification count
    """
    from django.http import JsonResponse
    count = NotificationService.get_unread_count(request.user)
    
    return JsonResponse({
        'count': count,
        'user_id': request.user.id
    })