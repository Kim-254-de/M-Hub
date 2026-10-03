import hmac
import json
import logging

from django.conf import settings
from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agrovets.models import StoreItem

from . import services
from .models import Order, Payment, Verification
from .serializers import (
    LabelCheckSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    PaymentSerializer,
    PayOrderSerializer,
    SaleMatchSerializer,
    StoreItemSerializer,
    StoreOfferSerializer,
    StoreQuerySerializer,
    VerificationSerializer,
)

logger = logging.getLogger(__name__)


class PurchaseAPIError(APIException):
    def __init__(self, error: services.PurchaseError):
        self.status_code = error.status
        super().__init__(detail={"detail": str(error), "code": error.code})


def run(fn, *args, **kwargs):
    """Call a service and translate rule violations into API errors."""
    try:
        return fn(*args, **kwargs)
    except services.PurchaseError as exc:
        raise PurchaseAPIError(exc) from exc


# --- Farmer: 5.1 stores for a prescription -----------------------------------


class PrescriptionStoresView(APIView):
    @extend_schema(parameters=[StoreQuerySerializer], responses=StoreOfferSerializer(many=True))
    def get(self, request, code):
        query = StoreQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        prescription = run(services.get_prescription_for_farmer, request.user, code)
        offers = run(services.find_stores, prescription, **query.validated_data)
        return Response(StoreOfferSerializer(offers, many=True).data)


# --- Farmer and agrovet: orders ----------------------------------------------


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Farmers see their own orders; agrovets see orders placed at their store."""

    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        user = self.request.user
        qs = Order.objects.select_related("prescription", "agrovet", "product").prefetch_related(
            Prefetch("payments", queryset=Payment.objects.order_by("-created_at")),
            Prefetch("verifications", queryset=Verification.objects.select_related("product")),
        )
        agrovet = getattr(user, "agrovet", None)
        if agrovet is not None:
            return qs.filter(agrovet=agrovet)
        return qs.filter(farmer=user)

    def get_farmer_order(self):
        order = self.get_object()
        if order.farmer_id != self.request.user.pk:
            raise PermissionDenied("Only the farmer who placed the order can do this.")
        return order

    @extend_schema(request=OrderCreateSerializer, responses={201: OrderSerializer})
    def create(self, request):
        data = OrderCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        prescription = run(
            services.get_prescription_for_farmer, request.user, data.validated_data["prescription_code"]
        )
        order = run(
            services.create_order,
            farmer=request.user,
            prescription=prescription,
            store_item_id=data.validated_data["store_item_id"],
            quantity=data.validated_data["quantity"],
            payment_method=data.validated_data["payment_method"],
        )
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=PayOrderSerializer, responses={202: PaymentSerializer})
    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        order = self.get_farmer_order()
        data = PayOrderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        phone = data.validated_data.get("phone") or request.user.phone or ""
        payment = run(services.initiate_payment, farmer=request.user, order=order, phone=phone)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=None, responses=OrderSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = run(services.cancel_order, farmer=request.user, order=self.get_farmer_order())
        return Response(OrderSerializer(order).data)

    @extend_schema(request=LabelCheckSerializer, responses={201: VerificationSerializer})
    @action(
        detail=True, methods=["post"], url_path="label-check", parser_classes=[MultiPartParser, FormParser]
    )
    def label_check(self, request, pk=None):
        order = self.get_farmer_order()
        data = LabelCheckSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        photo = data.validated_data["photo"]
        if photo.size > settings.PURCHASES["MAX_LABEL_PHOTO_BYTES"]:
            raise PurchaseAPIError(services.PurchaseError("The photo is too large.", code="photo_too_large"))
        verification = run(services.label_check, farmer=request.user, order=order, photo=photo.read())
        return Response(VerificationSerializer(verification).data, status=status.HTTP_201_CREATED)


# --- Agrovet: 5.3 sale match and store catalogue ------------------------------


class SaleMatchView(APIView):
    @extend_schema(request=SaleMatchSerializer, responses={201: VerificationSerializer})
    def post(self, request):
        data = SaleMatchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        verification = run(
            services.match_sale,
            agrovet_user=request.user,
            code=data.validated_data["prescription_code"],
            product_id=data.validated_data["product_id"],
        )
        return Response(VerificationSerializer(verification).data, status=status.HTTP_201_CREATED)


class StoreItemViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """A verified agrovet's in-app store. Only registered (active) products can be listed."""

    serializer_class = StoreItemSerializer
    permission_classes = [IsAuthenticated]

    def get_agrovet(self):
        return run(services.get_verified_agrovet, self.request.user)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StoreItem.objects.none()
        return StoreItem.objects.filter(agrovet=self.get_agrovet()).select_related("product")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if getattr(self, "swagger_fake_view", False):
            return context
        context["agrovet"] = self.get_agrovet()
        return context

    def perform_create(self, serializer):
        serializer.save(agrovet=self.get_agrovet())

    def perform_destroy(self, instance):
        # Listings referenced by orders are kept for history; take them out of stock instead.
        if instance.orders.exists():
            instance.in_stock = False
            instance.save(update_fields=["in_stock", "updated_at"])
        else:
            instance.delete()


# --- M-Pesa callback ------------------------------------------------------------


class MpesaCallbackView(APIView):
    """Daraja STK callback. Authenticated by the secret token in the URL (Daraja does not sign callbacks)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]
    throttle_classes = []

    @extend_schema(exclude=True)
    def post(self, request, token):
        expected = settings.MPESA["CALLBACK_TOKEN"]
        if not expected or not hmac.compare_digest(str(token), expected):
            logger.warning(
                "Rejected M-Pesa callback with invalid token from %s", request.META.get("REMOTE_ADDR")
            )
            raise NotFound()
        try:
            services.handle_stk_callback(request.data)
        except ValueError:
            logger.warning("Malformed M-Pesa callback: %s", json.dumps(request.data)[:500])
            return Response(
                {"ResultCode": 1, "ResultDesc": "Malformed callback"}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})
