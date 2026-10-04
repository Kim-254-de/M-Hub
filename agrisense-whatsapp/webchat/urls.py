from django.urls import path

from . import views

urlpatterns = [
    path("", views.page, name="webchat"),
    path("api/inbox/", views.inbox),
    path("api/send/", views.send),
    path("api/stk/", views.stk),
    path("api/reset/", views.reset),
]
