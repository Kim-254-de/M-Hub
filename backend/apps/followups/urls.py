from django.urls import path

from .views import CheckInView, FollowUpView, SprayView

urlpatterns = [
    path("cases/<uuid:case_id>/follow-up/", FollowUpView.as_view(), name="case-follow-up"),
    path("cases/<uuid:case_id>/follow-up/spray/", SprayView.as_view(), name="case-follow-up-spray"),
    path("cases/<uuid:case_id>/follow-up/check-ins/", CheckInView.as_view(), name="case-follow-up-check-ins"),
]
