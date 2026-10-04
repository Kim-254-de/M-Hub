from django.urls import path

from . import views

urlpatterns = [
    path("webhook/", views.webhook, name="whatsapp-webhook"),
    path("simulator/", views.simulator_page, name="whatsapp-simulator"),
    path("simulator/api/send/", views.simulator_send, name="whatsapp-simulator-send"),
    path("simulator/api/inbox/", views.simulator_inbox, name="whatsapp-simulator-inbox"),
    path("simulator/api/reset/", views.simulator_reset, name="whatsapp-simulator-reset"),
]
