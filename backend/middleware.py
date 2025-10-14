from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin


class SecretKeyMiddleware(MiddlewareMixin):
    """
    UPDATED: Now skips validation if request will be handled by TaglineSecretKeyMiddleware
    """
    def process_request(self, request):
        # Skip this middleware for requests that will use Tagline secret
        # Let TaglineSecretKeyMiddleware handle those
        return None
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        # Check if the view requires tagline secret validation
        requires_tagline = False
        
        if hasattr(view_func, 'cls'):
            requires_tagline = getattr(view_func.cls, 'require_tagline_secret', False)
        else:
            requires_tagline = getattr(view_func, 'require_tagline_secret', False)
        
        # If view uses Tagline secret, skip this middleware
        if requires_tagline:
            return None
        
        # Otherwise, check for regular secret-key
        secret_key = request.headers.get("secret-key")
        if not secret_key:
            return JsonResponse({"error": "Secret key is required"}, status=403)
        if secret_key != settings.SECRET_KEY:
            return JsonResponse({"error": "Invalid secret key"}, status=403)
        
        return None

class TaglineSecretKeyMiddleware(MiddlewareMixin):
    """
    NEW middleware - validates x-tagline-secret-key for decorated views
    """
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        # Check if the view requires tagline secret validation
        requires_tagline = False
        
        # For DRF ViewSets (class-based views)
        if hasattr(view_func, 'cls'):
            requires_tagline = getattr(view_func.cls, 'require_tagline_secret', False)
        
        # For regular function-based views
        else:
            requires_tagline = getattr(view_func, 'require_tagline_secret', False)
        
        # If not required, skip validation
        if not requires_tagline:
            return None
        
        # Validate secret key
        header_key = request.headers.get("x-tagline-secret-key")
        expected_key = getattr(settings, "TAGLINE_SECRET_KEY", None)
        
        if not expected_key:
            return JsonResponse(
                {"detail": "Server configuration error: TAGLINE_SECRET_KEY not set"},
                status=500
            )
        
        if not header_key:
            return JsonResponse(
                {"detail": "Missing x-tagline-secret-key header"},
                status=403
            )
        
        if header_key != expected_key:
            return JsonResponse(
                {"detail": "Invalid x-tagline-secret-key"},
                status=403
            )
        
        # Validation passed, continue processing
        return None