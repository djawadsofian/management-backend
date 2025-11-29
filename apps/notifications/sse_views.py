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

logger = logging.getLogger(__name__)

# Dictionary to track active connections
active_connections = {}


@sync_to_async
def get_unread_notifications(user_id):
    """Get ALL unread notifications on initial connect"""
    notifications = Notification.objects.filter(
        recipient_id=user_id,
        is_read=False
    ).select_related('related_project', 'related_maintenance', 'related_product').order_by('created_at')
    
    result = []
    for notification in notifications:
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
        
        result.append(notification_data)
        
        # Mark as sent
        notification.mark_as_sent()
    
    return result


@sync_to_async
def get_new_notifications(user_id, last_check_time):
    """Get notifications created after last check time"""
    notifications = Notification.objects.filter(
        recipient_id=user_id,
        created_at__gt=last_check_time,
        is_read=False
    ).select_related('related_project', 'related_maintenance', 'related_product').order_by('created_at')
    
    result = []
    for notification in notifications:
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
        
        result.append(notification_data)
        
        # Mark as sent
        notification.mark_as_sent()
    
    return result


@require_GET
async def notification_stream(request):
    """SSE endpoint - sends initial notifications then polls for new ones every 30 seconds"""
    user = request.user
    if not user.is_authenticated:
        from django.http import JsonResponse
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    print(f"🔗 NEW SSE CONNECTION: User {user.id} - {user.username}")
    
    async def event_stream():
        connection_id = f"{user.id}_{timezone.now().timestamp()}"
        active_connections[connection_id] = True
        
        try:
            # Send connection event
            yield f"data: {json.dumps({'event': 'connected', 'message': 'Connected to notification stream', 'user_id': user.id})}\n\n"
            print(f"📤 Sent 'connected' event to user {user.id}")
            
            # SEND ALL UNREAD NOTIFICATIONS ON CONNECT
            initial_notifications = await get_unread_notifications(user.id)
            print(f"📬 Sending {len(initial_notifications)} initial unread notifications to user {user.id}")
            
            for notification_data in initial_notifications:
                print(f"📤 Sending initial notification {notification_data['id']} to user {user.id}")
                yield f"data: {json.dumps({'event': 'notification', 'data': notification_data})}\n\n"
            
            # Mark last check time AFTER sending initial notifications
            last_check_time = timezone.now()
            print(f"⏰ Initial check time set to {last_check_time}")
            
            # Poll for NEW notifications every 30 seconds
            while active_connections.get(connection_id, False):
                try:
                    # Check for new notifications created after last check
                    new_notifications = await get_new_notifications(user.id, last_check_time)
                    
                    if new_notifications:
                        print(f"📬 Found {len(new_notifications)} new notifications for user {user.id}")
                    
                    for notification_data in new_notifications:
                        print(f"📤 Sending new notification {notification_data['id']} to user {user.id}")
                        yield f"data: {json.dumps({'event': 'notification', 'data': notification_data})}\n\n"
                    
                    # Update last check time
                    last_check_time = timezone.now()
                    
                    # Send keepalive ping
                    yield f"data: {json.dumps({'event': 'ping', 'timestamp': int(timezone.now().timestamp())})}\n\n"
                    
                    # Wait 30 seconds before next poll
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    print(f"❌ Error in polling: {e}")
                    logger.error(f"Error in polling for user {user.id}: {e}")
                    break
                    
        except GeneratorExit:
            print(f"🔴 Client disconnected: user {user.id}")
        except Exception as e:
            print(f"❌ Fatal error in event stream for user {user.id}: {e}")
            logger.error(f"Fatal error in event stream: {e}")
        finally:
            if connection_id in active_connections:
                del active_connections[connection_id]
            print(f"🧹 Cleaned up connection for user {user.id}")
    
    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache, no-transform'
    response['X-Accel-Buffering'] = 'no'
    response['Connection'] = 'keep-alive'
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Cache-Control, Authorization'
    response['Access-Control-Allow-Credentials'] = 'true'
    
    return response


@require_GET
@login_required
def notification_count(request):
    """Get unread notification count"""
    from django.http import JsonResponse
    count = NotificationService.get_unread_count(request.user)
    
    return JsonResponse({
        'count': count,
        'user_id': request.user.id
    })