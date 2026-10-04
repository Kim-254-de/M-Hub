from django.urls import path

from . import views

urlpatterns = [
    path("whatsapp/", views.webhook, name="whatsapp-webhook"),
]
