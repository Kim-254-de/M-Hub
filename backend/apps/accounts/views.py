from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .models import Farm
from .permissions import IsFarmer
from .serializers import (
    FarmerRegistrationSerializer,
    FarmSerializer,
    PhoneTokenSerializer,
    TokenPairSerializer,
    tokens_for,
)


class AuthThrottleMixin:
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def get_authenticate_header(self, request):
        # Makes failed logins 401 rather than 403, as simplejwt's own token views do.
        return 'Bearer realm="api"'


class FarmerRegisterView(AuthThrottleMixin, generics.GenericAPIView):
    """Create a farmer account and return login tokens."""

    serializer_class = FarmerRegistrationSerializer

    @extend_schema(responses={201: TokenPairSerializer})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(tokens_for(user), status=status.HTTP_201_CREATED)


class PhoneTokenView(AuthThrottleMixin, generics.GenericAPIView):
    """Log in with phone number and PIN."""

    serializer_class = PhoneTokenSerializer

    @extend_schema(responses={200: TokenPairSerializer})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class FarmViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = FarmSerializer
    permission_classes = [IsAuthenticated, IsFarmer]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation
            return Farm.objects.none()
        return self.request.user.farms.all()

    def perform_create(self, serializer):
        serializer.save(farmer=self.request.user)
