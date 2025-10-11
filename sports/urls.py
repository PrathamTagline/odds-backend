from django.urls import path
from .views import TreeRecordView, OddsView, HighlightHomePrivateView, SportListView, CompetitionListAPIView, EventListAPIView, EventDataFromRedisView

urlpatterns = [
    path('tree-record/', TreeRecordView.as_view(), name='tree_record_api'),
    path("odds/", OddsView.as_view(), name="odds"),
    path("highlight-home/", HighlightHomePrivateView.as_view(), name="highlight-home"),
    path("sports-data/", SportListView.as_view(), name="sport-list"),
    path("<int:event_type_id>/competitions/", CompetitionListAPIView.as_view(), name="competition-list"),
    path("<int:event_type_id>/<int:competition_id>/events/", EventListAPIView.as_view(), name="event-list-by-sport-competition"),
    path("event-data/", EventDataFromRedisView.as_view(), name="event-data-from-redis"),
]
