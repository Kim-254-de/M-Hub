from django.urls import path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import FarmerRegisterView, FarmViewSet, PhoneTokenView

router = SimpleRouter()
router.register("farms", FarmViewSet, basename="farm")

urlpatterns = [
    path("auth/register/", FarmerRegisterView.as_view(), name="auth-register"),
    path("auth/token/", PhoneTokenView.as_view(), name="auth-token"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),
    *router.urls,
]
