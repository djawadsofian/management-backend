# apps/core/middleware.py
"""
Middleware to track current user for signal handlers
"""
import threading

_thread_locals = threading.local()


def get_current_user():
    """Get current user from thread local storage"""
    return getattr(_thread_locals, 'user', None)


def set_current_user(user):
    """Set current user in thread local storage"""
    _thread_locals.user = user


class CurrentUserMiddleware:
    """
    Middleware to store current user in thread local storage
    This allows signal handlers to access the current user
    """
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Store current user
        if hasattr(request, 'user') and request.user.is_authenticated:
            set_current_user(request.user)
        else:
            set_current_user(None)
        
        response = self.get_response(request)
        
        # Clean up
        set_current_user(None)
        
        return response