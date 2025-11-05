# apps/core/exceptions.py
"""
Custom exception classes for better error handling.
Provides domain-specific exceptions with clear messages.
"""
from rest_framework.exceptions import APIException
from rest_framework import status


class InsufficientStockError(APIException):
    """Raised when there's not enough stock for an operation"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Insufficient stock available for this operation.'
    default_code = 'insufficient_stock'


class InvalidStatusTransitionError(APIException):
    """Raised when an invalid status transition is attempted"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Invalid status transition.'
    default_code = 'invalid_status_transition'


class BusinessRuleViolationError(APIException):
    """Raised when a business rule is violated"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Business rule violation.'
    default_code = 'business_rule_violation'


class ResourceNotVerifiedError(APIException):
    """Raised when attempting to use an unverified resource"""
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'Resource must be verified before use.'
    default_code = 'resource_not_verified'