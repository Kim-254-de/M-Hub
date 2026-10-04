from django.urls import path

from . import views

urlpatterns = [
    path("mpesa/callback/<str:token>/", views.mpesa_callback, name="mpesa-callback"),
]
