from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import MpesaCallbackView, OrderViewSet, PrescriptionStoresView, SaleMatchView, StoreItemViewSet

router = SimpleRouter()
router.register("orders", OrderViewSet, basename="order")
router.register("agrovet/store-items", StoreItemViewSet, basename="store-item")

urlpatterns = [
    path("prescriptions/<str:code>/stores/", PrescriptionStoresView.as_view(), name="prescription-stores"),
    path("agrovet/sales/match/", SaleMatchView.as_view(), name="sale-match"),
    path("payments/mpesa/callback/<str:token>/", MpesaCallbackView.as_view(), name="mpesa-callback"),
    *router.urls,
]
