# config/asgi.py
import os
from django.core.asgi import get_asgi_application
from django.urls import resolve
from channels.routing import ProtocolTypeRouter
from apps.notifications.sse_views import notification_stream

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_app = get_asgi_application()

async def http_router(scope, receive, send):
    """
    Custom router:
    - If the path is SSE endpoint -> use SSE view
    - Else -> forward to Django ASGI app
    """
    path = scope.get("path", "")

    if path == "/api/notifications/stream/":
        return await notification_stream(scope, receive, send)

    return await django_app(scope, receive, send)


application = ProtocolTypeRouter({
    "http": http_router,
})
