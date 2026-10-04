from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.static import serve

from core.api import router


def health(request):
    return JsonResponse({"status": "ok", "service": "agrisense-whatsapp"})


urlpatterns = [
    path("", health),
    path("admin/", admin.site.urls),
    path("webhook/", include("whatsapp.urls")),
    path("payments/", include("payments.urls")),
    path("api/", include(router.urls)),
    path("chat/", include("webchat.urls")),
    # Crop photos must be reachable by WhatsApp so agrovets can see them.
    # Fine for a hackathon; use S3/Cloudinary in production.
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
