from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.static import serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.rewards.views import MyRewardsView

api_v1 = [
    path("", include("apps.accounts.urls")),
    path("", include("apps.cases.urls")),
    path("", include("apps.diagnosis.urls")),
    path("", include("apps.prescriptions.urls")),
    path("", include("apps.purchases.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.followups.urls")),
    path("", include("apps.advisory.urls")),
    path("rewards/", MyRewardsView.as_view(), name="my-rewards"),
]

urlpatterns = [
    path("health/", lambda request: JsonResponse({"status": "ok"}), name="health"),
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "api"), namespace="v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

if settings.DEBUG:
    # Local development: uploaded photos and voice notes.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, "SERVE_MEDIA", False):
    # Small hosted pilot (Railway volume): Django serves media itself. See config/settings/prod.py.
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]
