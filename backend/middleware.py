from django.http import JsonResponse
from django.conf import settings
from rest_framework import status


class SecretKeyMiddleware:
    """
    Middleware to check x-tagline-secret-key header for specific paths.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that require secret key check (e.g., sports app under /api/)
        self.protected_paths = [
            '/api/',
        ]

    def __call__(self, request):
        # Check if the path starts with any protected path
        for path in self.protected_paths:
            if request.path.startswith(path):
                header_key = request.headers.get("x-tagline-secret-key")
                expected_key = getattr(settings, "TAGLINE_SECRET_KEY", None)
                if not (header_key and expected_key and header_key == expected_key):
                    return JsonResponse({
                        "status": False,
                        "message": "Invalid secret key"
                    }, status=status.HTTP_403_FORBIDDEN)
                break  # If matched, check done

        response = self.get_response(request)
        return response
