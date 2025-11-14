# apps/core/exceptions.py
from rest_framework.views import exception_handler
from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import APIException


class InsufficientStockError(APIException):
    """Raised when there's not enough stock for an operation"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = {'message': 'Stock insuffisant'}
    default_code = 'insufficient_stock'


class InvalidStatusTransitionError(APIException):
    """Raised when an invalid status transition is attempted"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = {'message': 'Transition de statut invalide'}
    default_code = 'invalid_status_transition'


class BusinessRuleViolationError(APIException):
    """Raised when a business rule is violated"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = {'message': 'Règle métier violée'}
    default_code = 'business_rule_violation'


class ResourceNotVerifiedError(APIException):
    """Raised when attempting to use an unverified resource"""
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = {'message': 'Ressource non vérifiée'}
    default_code = 'resource_not_verified'


def custom_exception_handler(exc, context):
    """Custom exception handler to return all errors in {message: ""} format"""
    response = exception_handler(exc, context)
    
    if response is not None:
        # For custom exceptions that already have {message: ""} format
        if hasattr(exc, 'default_detail') and isinstance(exc.default_detail, dict) and 'message' in exc.default_detail:
            response.data = exc.default_detail
        else:
            # Convert other errors to simple message format
            if response.status_code == status.HTTP_400_BAD_REQUEST:
                message = "Données invalides"
                
                if isinstance(response.data, dict):
                    # Handle field-level validation errors - translate common ones
                    if 'message' in response.data:
                        message = str(response.data['message'])
                    else:
                        # Get first error from any field and translate it
                        first_error = list(response.data.values())[0]
                        if isinstance(first_error, list):
                            error_text = str(first_error[0])
                        else:
                            error_text = str(first_error)
                        
                        # Translate common validation errors to French
                        if 'required' in error_text.lower():
                            message = "Champ obligatoire manquant"
                        elif 'invalid' in error_text.lower():
                            message = "Donnée invalide"
                        elif 'unique' in error_text.lower():
                            message = "Doublon non autorisé"
                        elif 'blank' in error_text.lower():
                            message = "Champ ne peut pas être vide"
                        else:
                            message = error_text
                
                response.data = {"message": message}
                
            elif response.status_code == status.HTTP_401_UNAUTHORIZED:
                response.data = {"message": "Non authentifié"}
            elif response.status_code == status.HTTP_403_FORBIDDEN:
                response.data = {"message": "Accès refusé"}
            elif response.status_code == status.HTTP_404_NOT_FOUND:
                response.data = {"message": "Non trouvé"}
            elif response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR:
                response.data = {"message": "Erreur serveur"}
    
    return response