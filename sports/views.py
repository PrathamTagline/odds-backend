import os
from dotenv import load_dotenv
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from backend.services.odds_data_gather_service import run_scraper
from backend.services.scaper_service import (
    get_tree_record,
    get_odds,
    get_highlight_home_private,
)

load_dotenv()


def get_decryption_key():
    """Fetch and validate DECRYPTION_KEY from environment."""
    key = os.getenv("DECRYPTION_KEY")
    if not key:
        raise ValueError("DECRYPTION_KEY not configured in environment")
    return key


class BaseAPIView(APIView):
    """Base APIView with common methods."""

    def handle_exception(self, exc):
        return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TreeRecordView(BaseAPIView):
    """API endpoint to fetch and return tree records."""

    def get(self, request, *args, **kwargs):
        TARGET_URL = "https://d247.com/game-details/4/559593926"
        PASSWORD_FOR_DECRYPT = os.getenv("DECRYPTION_KEY", "cae7b808-8b1e-4f47-87a5-1a4b6a08030e")

        run_scraper(target_url=TARGET_URL, password_for_decrypt=PASSWORD_FOR_DECRYPT)
        try:
            key = get_decryption_key()
            data = get_tree_record(key)
            if "error" in data:
                return Response(data, status=status.HTTP_401_UNAUTHORIZED)
            return Response({"message": "Tree data fetched successfully", "data": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return self.handle_exception(e)


class OddsView(BaseAPIView):
    """API endpoint to fetch odds using sport_id and event_id."""

    def get(self, request, *args, **kwargs):
        try:
            sport_id = request.query_params.get("sport_id")
            event_id = request.query_params.get("event_id")

            if not sport_id or not event_id:
                return Response(
                    {"error": "sport_id and event_id are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            key = get_decryption_key()
            data = get_odds(int(sport_id), int(event_id), key)
            return Response({"odds": data}, status=status.HTTP_200_OK)

        except Exception as e:
            return self.handle_exception(e)


class HighlightHomePrivateView(BaseAPIView):
    """API endpoint to fetch highlight home private data using etid."""

    def get(self, request, *args, **kwargs):
        try:
            etid = request.query_params.get("etid")
            if not etid:
                return Response({"error": "etid is required"}, status=status.HTTP_400_BAD_REQUEST)

            key = get_decryption_key()
            data = get_highlight_home_private(int(etid), key)
            return Response({"highlight": data}, status=status.HTTP_200_OK)

        except Exception as e:
            return self.handle_exception(e)
