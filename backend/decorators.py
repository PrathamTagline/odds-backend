from functools import wraps
from django.conf import settings
from rest_framework.response import Response
from rest_framework import status


def require_tagline_secret(view_class):
    """
    Decorator to mark ViewSets that require x-tagline-secret-key validation.
    Apply this decorator to your ViewSet class.
    
    Usage:
        @require_tagline_secret
        class MyViewSet(viewsets.ModelViewSet):
            queryset = MyModel.objects.all()
            serializer_class = MySerializer
    """
    view_class.require_tagline_secret = True
    return view_class