from django.http import HttpResponse

from .services.gtoken_service import get_cookie_token


def home_view(request):
    print((get_cookie_token()))
    return HttpResponse("Welcome to D247 APIs.")