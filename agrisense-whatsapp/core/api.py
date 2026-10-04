"""Read-only REST API so the AgriSense mobile app shares the same data as the WhatsApp bot."""
from rest_framework import routers, serializers, viewsets

from .models import Agrovet, Diagnosis, Product
from .utils import normalize_phone


class AgrovetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agrovet
        fields = ["id", "name", "county", "town", "location_hint", "phone", "is_verified"]


class ProductSerializer(serializers.ModelSerializer):
    agrovet = AgrovetSerializer(read_only=True)
    farmer_price = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = ["id", "name", "active_ingredient", "pack_size", "price", "farmer_discount_pct", "farmer_price",
                  "target_keywords", "crops", "usage_note", "in_stock", "agrovet"]


class DiagnosisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Diagnosis
        fields = ["id", "crop", "disease", "confidence", "description", "treatment", "status", "agrovet_note",
                  "outcome", "image", "created_at"]


class AgrovetViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AgrovetSerializer

    def get_queryset(self):
        qs = Agrovet.objects.filter(is_verified=True)
        county = self.request.query_params.get("county")
        return qs.filter(county__iexact=county) if county else qs


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer

    def get_queryset(self):
        qs = Product.objects.filter(in_stock=True, agrovet__is_verified=True).select_related("agrovet")
        disease = self.request.query_params.get("disease")
        if disease:
            ids = [p.pk for p in qs if p.matches(disease, self.request.query_params.get("crop", ""))]
            qs = qs.filter(pk__in=ids)
        return qs


class DiagnosisViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/diagnoses/?phone=0712345678 — a farmer's diagnoses (add auth before production)."""
    serializer_class = DiagnosisSerializer

    def get_queryset(self):
        phone = normalize_phone(self.request.query_params.get("phone", ""))
        return Diagnosis.objects.filter(farmer__phone=phone) if phone else Diagnosis.objects.none()


router = routers.DefaultRouter()
router.register("agrovets", AgrovetViewSet, basename="agrovet")
router.register("products", ProductViewSet, basename="product")
router.register("diagnoses", DiagnosisViewSet, basename="diagnosis")
