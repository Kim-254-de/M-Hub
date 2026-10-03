from django.urls import path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import FarmerRegisterView, FarmViewSet, MeView, OtpRequestView, OtpVerifyView, PhoneTokenView

router = SimpleRouter()
router.register("farms", FarmViewSet, basename="farm")

urlpatterns = [
    path("auth/otp/", OtpRequestView.as_view(), name="auth-otp"),
    path("auth/otp/verify/", OtpVerifyView.as_view(), name="auth-otp-verify"),
    path("auth/register/", FarmerRegisterView.as_view(), name="auth-register"),
    path("me/", MeView.as_view(), name="me"),
    path("auth/token/", PhoneTokenView.as_view(), name="auth-token"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),
    *router.urls,
]
