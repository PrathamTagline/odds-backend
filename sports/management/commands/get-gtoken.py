from django.core.management.base import BaseCommand
from backend.services.gtoken_service import get_cookie_token


class Command(BaseCommand):
    help = "Fetches g_token cookie from d247.com"

    def handle(self, *args, **options):
        self.stdout.write("Starting g_token retrieval...")

        try:
            g_token = get_cookie_token()
            if g_token:
                self.stdout.write(self.style.SUCCESS(f"g_token: {g_token}"))
            else:
                self.stdout.write(self.style.WARNING("g_token not found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fetching g_token: {e}"))
