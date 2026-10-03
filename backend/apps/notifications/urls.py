from django.urls import path

from .views import SmsDeliveryReportView

urlpatterns = [
    path(
        "notifications/sms/delivery/<str:token>/", SmsDeliveryReportView.as_view(), name="sms-delivery-report"
    ),
]
