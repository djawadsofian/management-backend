# # config/asgi.py
# import os
# from django.core.asgi import get_asgi_application
# from django.urls import resolve
# from channels.routing import ProtocolTypeRouter
# from apps.notifications.sse_views import notification_stream

# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# django_app = get_asgi_application()

# async def http_router(scope, receive, send):
#     """
#     Custom router:
#     - If the path is SSE endpoint -> use SSE view
#     - Else -> forward to Django ASGI app
#     """
#     path = scope.get("path", "")

#     if path == "/api/notifications/stream/":
#         return await notification_stream(scope, receive, send)

#     return await django_app(scope, receive, send)


# application = ProtocolTypeRouter({
#     "http": http_router,
# })




# config/asgi.py
# import os
# from django.core.asgi import get_asgi_application

# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# # Initialize Django ASGI application early to ensure the AppRegistry
# # is populated before importing code that may import ORM models.
# django_asgi_app = get_asgi_application()

# # NOW import your SSE view after Django is initialized
# from apps.notifications.sse_views import notification_stream

# async def application(scope, receive, send):
#     """
#     Main ASGI application that routes requests
#     """
#     if scope['type'] == 'http':
#         path = scope.get('path', '')
        
#         # Route SSE endpoint to async view
#         if path == '/api/notifications/stream/':
#             # Convert ASGI scope to Django request-like object
#             from django.http import HttpRequest
#             from channels.db import database_sync_to_async
            
#             # Create a Django request object from ASGI scope
#             request = HttpRequest()
#             request.method = scope['method']
#             request.path = path
#             request.META = {}
            
#             # Copy headers
#             for header_name, header_value in scope.get('headers', []):
#                 header_name = header_name.decode('latin1')
#                 header_value = header_value.decode('latin1')
                
#                 # Convert to Django META format
#                 if header_name.lower() == 'authorization':
#                     request.META['HTTP_AUTHORIZATION'] = header_value
#                 else:
#                     meta_key = f"HTTP_{header_name.upper().replace('-', '_')}"
#                     request.META[meta_key] = header_value
            
#             # Get user from session/auth
#             @database_sync_to_async
#             def get_user():
#                 from django.contrib.auth.models import AnonymousUser
#                 from rest_framework_simplejwt.authentication import JWTAuthentication
                
#                 # Try JWT authentication
#                 auth_header = request.META.get('HTTP_AUTHORIZATION', '')
#                 if auth_header.startswith('Bearer '):
#                     try:
#                         jwt_auth = JWTAuthentication()
#                         validated_token = jwt_auth.get_validated_token(auth_header.split(' ')[1])
#                         user = jwt_auth.get_user(validated_token)
#                         return user
#                     except Exception:
#                         pass
                
#                 return AnonymousUser()
            
#             request.user = await get_user()
            
#             # Call the SSE view
#             response = await notification_stream(request)
            
#             # Convert Django response to ASGI
#             await send({
#                 'type': 'http.response.start',
#                 'status': response.status_code,
#                 'headers': [
#                     [key.encode(), value.encode()] 
#                     for key, value in response.items()
#                 ],
#             })
            
#             # Stream the response
#             async for chunk in response.streaming_content:
#                 await send({
#                     'type': 'http.response.body',
#                     'body': chunk.encode() if isinstance(chunk, str) else chunk,
#                     'more_body': True,
#                 })
            
#             # End response
#             await send({
#                 'type': 'http.response.body',
#                 'body': b'',
#                 'more_body': False,
#             })
            
#             return
    
#     # For all other requests, use Django ASGI app
#     await django_asgi_app(scope, receive, send)





# config/asgi.py
import os
from django.core.asgi import get_asgi_application
from .settings.base import DEBUG

if DEBUG:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

async def application(scope, receive, send):
    """
    Main ASGI application that routes requests
    """
    if scope['type'] == 'http':
        path = scope.get('path', '')
        
        # Route SSE endpoint to async view
        if path == '/api/notifications/stream/':
            try:
                # Import here to avoid circular imports
                from django.http import HttpRequest
                from channels.db import database_sync_to_async
                from rest_framework_simplejwt.authentication import JWTAuthentication
                from django.contrib.auth.models import AnonymousUser
                
                # Create a Django request object from ASGI scope
                request = HttpRequest()
                request.method = scope['method']
                request.path = path
                request.META = {}
                
                # Copy headers
                for header_name, header_value in scope.get('headers', []):
                    header_name = header_name.decode('latin1')
                    header_value = header_value.decode('latin1')
                    
                    # Convert to Django META format
                    if header_name.lower() == 'authorization':
                        request.META['HTTP_AUTHORIZATION'] = header_value
                    else:
                        meta_key = f"HTTP_{header_name.upper().replace('-', '_')}"
                        request.META[meta_key] = header_value
                
                # Get query string for token
                query_string = scope.get('query_string', b'').decode('latin1')
                if 'token=' in query_string:
                    import urllib.parse
                    params = urllib.parse.parse_qs(query_string)
                    token = params.get('token', [''])[0]
                    if token and not request.META.get('HTTP_AUTHORIZATION'):
                        request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'
                
                # Get user from authentication
                @database_sync_to_async
                def get_user():
                    # Try JWT authentication
                    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
                    if auth_header.startswith('Bearer '):
                        try:
                            jwt_auth = JWTAuthentication()
                            validated_token = jwt_auth.get_validated_token(auth_header.split(' ')[1])
                            user = jwt_auth.get_user(validated_token)
                            return user
                        except Exception:
                            pass
                    
                    return AnonymousUser()
                
                request.user = await get_user()
                
                # Check if user is authenticated
                if not request.user.is_authenticated:
                    # Return proper error response for unauthenticated users
                    await send({
                        'type': 'http.response.start',
                        'status': 401,
                        'headers': [
                            [b'content-type', b'application/json'],
                            [b'cache-control', b'no-cache'],
                        ],
                    })
                    await send({
                        'type': 'http.response.body',
                        'body': b'{"error": "Authentication required"}',
                        'more_body': False,
                    })
                    return
                
                # Import and call the SSE view
                from apps.notifications.sse_views import notification_stream
                response = await notification_stream(request)
                
                # Handle different response types
                if hasattr(response, 'streaming_content'):
                    # Streaming response (SSE)
                    await send({
                        'type': 'http.response.start',
                        'status': response.status_code,
                        'headers': [
                            [key.encode(), value.encode()] 
                            for key, value in response.items()
                        ],
                    })
                    
                    # Stream the response
                    async for chunk in response.streaming_content:
                        await send({
                            'type': 'http.response.body',
                            'body': chunk.encode() if isinstance(chunk, str) else chunk,
                            'more_body': True,
                        })
                    
                    # End response
                    await send({
                        'type': 'http.response.body',
                        'body': b'',
                        'more_body': False,
                    })
                else:
                    # Regular response
                    await send({
                        'type': 'http.response.start',
                        'status': response.status_code,
                        'headers': [
                            [key.encode(), value.encode()] 
                            for key, value in response.items()
                        ],
                    })
                    await send({
                        'type': 'http.response.body',
                        'body': response.content,
                        'more_body': False,
                    })
                
            except Exception as e:
                # Handle any errors in SSE processing
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error in SSE handling: {e}")
                
                await send({
                    'type': 'http.response.start',
                    'status': 500,
                    'headers': [
                        [b'content-type', b'application/json'],
                    ],
                })
                await send({
                    'type': 'http.response.body',
                    'body': b'{"error": "Internal server error"}',
                    'more_body': False,
                })
            
            return
    
    # For all other requests, use Django ASGI app
    await django_asgi_app(scope, receive, send)