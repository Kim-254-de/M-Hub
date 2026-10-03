from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
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
    path("rewards/", MyRewardsView.as_view(), name="my-rewards"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "api"), namespace="v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("whatsapp/", include("apps.whatsapp.urls")),
]

if settings.DEBUG:
    # Uploaded photos in development (the simulator shows the farmer's own photos).
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
