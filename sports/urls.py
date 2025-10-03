from django.urls import path
from .views import TreeRecordView,OddsView,HighlightHomePrivateView

urlpatterns = [
    path('tree-record/', TreeRecordView.as_view(), name='tree_record_api'),
    path("odds/", OddsView.as_view(), name="odds"),
    path("highlight-home/", HighlightHomePrivateView.as_view(), name="highlight-home"),
]