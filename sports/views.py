import json
import os
from dotenv import load_dotenv
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from dotenv import load_dotenv

from backend.services import redis_service
from backend.services.scaper_service import get_highlight_home_private, get_odds, get_tree_record

from rest_framework.generics import ListAPIView
from .models import Sport, Competition, Event
from .serializers import EventOnlySerializer, SportSerializer,CompetitionOnlySerializer
from rest_framework.response import Response
from backend.permissions import HasTaglineSecretKey
from typing import List, Dict, Any, Optional
from backend.services.redis_service import redis_service
load_dotenv()



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

        # run_scraper(target_url=TARGET_URL, password_for_decrypt=PASSWORD_FOR_DECRYPT)
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


class SportListView(ListAPIView):
    queryset = Sport.objects.all()
    serializer_class = SportSerializer
    permission_classes = [HasTaglineSecretKey]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "status": True,
            "message": "Sports fetched successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class CompetitionListAPIView(APIView):
    permission_classes = [HasTaglineSecretKey]

    def get(self, request, event_type_id=None):
        try:
            # filter Sport by event_type_id instead of id
            sport = Sport.objects.get(event_type_id=event_type_id)
            competitions = Competition.objects.filter(sport=sport)

            data = {
                "sport": SportSerializer(sport).data,
                "competitions": CompetitionOnlySerializer(competitions, many=True).data
            }

            return Response({
                "status": True,
                "message": "Competition data fetched successfully",
                **data
            }, status=status.HTTP_200_OK)
        except Sport.DoesNotExist:
            return Response({
                "status": False,
                "message": "Sport not found"
            }, status=status.HTTP_404_NOT_FOUND)


class EventListAPIView(APIView):
    permission_classes = [HasTaglineSecretKey]
    def get(self, request, event_type_id=None, competition_id=None):
        try:
            # Find sport by event_type_id
            sport = Sport.objects.get(event_type_id=event_type_id)

            # Find competition by competition_id + sport
            competition = Competition.objects.get(competition_id=competition_id, sport=sport)

            # Fetch events
            events = Event.objects.filter(sport=sport, competition=competition)

            if not events.exists():
                return Response({
                    "status": False,
                    "message": "No events found"
                }, status=status.HTTP_404_NOT_FOUND)

            return Response({
                "status": True,
                "message": "Events fetched successfully",
                "sport": SportSerializer(sport).data,
                "competition": CompetitionOnlySerializer(competition).data,
                "events": EventOnlySerializer(events, many=True).data
            }, status=status.HTTP_200_OK)

        except Sport.DoesNotExist:
            return Response({
                "status": False,
                "message": "Sport not found"
            }, status=status.HTTP_404_NOT_FOUND)
        except Competition.DoesNotExist:
            return Response({
                "status": False,
                "message": "Competition not found"
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                "status": False,
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EventDataFromRedisView(APIView):
    permission_classes = [HasTaglineSecretKey]

    def post(self, request, *args, **kwargs):
        try:
            event_ids = request.data.get('event_ids', [])
            if not event_ids or not isinstance(event_ids, list):
                return Response({
                    "status": False,
                    "message": "event_ids must be a non-empty list"
                }, status=status.HTTP_400_BAD_REQUEST)

            data = {}
            for event_id in event_ids:
                key_decrypted = f"sport/{event_id}/4/decrypted_data"
                value = redis_service.get_data(key_decrypted)
                if value:
                    data[str(event_id)] = value
                else:
                    # Try plain data if decrypted not available
                    key_plain = f"sport/{event_id}/4/plain_data"
                    value = redis_service.get_data(key_plain)
                    data[str(event_id)] = value

            return Response({
                "status": True,
                "message": "Event data fetched successfully",
                "data": data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "status": False,
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
