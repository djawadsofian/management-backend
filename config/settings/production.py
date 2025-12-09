# config/settings/production.py
"""
Production-specific settings.
"""
from config.settings.base import BASE_DIR, REST_FRAMEWORK
from .base import *


# Security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# HSTS settings
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Only JSON renderer in production
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
]

# LOGGING = {
#     'version': 1,
#     'disable_existing_loggers': False,
#     'formatters': {
#         'verbose': {
#             'format': '{levelname} {asctime} {module} {message}',
#             'style': '{',
#         },
#     },
#     'handlers': {
#         'file': {
#             'level': 'ERROR',
#             'class': 'logging.FileHandler',
#             'filename': BASE_DIR / 'logs' / 'django.log',
#             'formatter': 'verbose',
#         },
#         'console': {
#             'class': 'logging.StreamHandler',
#             'formatter': 'verbose',
#         },
#     },
#     'root': {
#         'handlers': ['console', 'file'],
#         'level': 'INFO',
#     },
#     'loggers': {
#         'django': {
#             'handlers': ['console', 'file'],
#             'level': 'INFO',
#             'propagate': False,
#         },
#     },
# }

# CORS_ALLOWED_ORIGINS = [
#     "http://5.135.241.51",
# ]
# CSRF_TRUSTED_ORIGINS = [
#     "http://5.135.241.51",
# ]
ALLOWED_HOSTS = ['backend','management_backend']

# Use BrowsableAPI renderer in development
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
    'rest_framework.renderers.BrowsableAPIRenderer',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'elevator_db',
        'USER': 'elevator_user',
        'PASSWORD': 'elevator_pass',
        'HOST': 'postgres',
        'PORT': '5432',
    }
}