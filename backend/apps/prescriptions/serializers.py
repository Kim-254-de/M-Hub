from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.cases.services import farmer_language
from apps.products.models import Product

from .messages import card_instructions
from .models import Prescription


class DraftOptionSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    product_id = serializers.UUIDField()
    name = serializers.CharField()
    pcpb_reg_no = serializers.CharField()
    active_ingredients = serializers.ListField(child=serializers.CharField())
    local_evidence = serializers.BooleanField()
    improved = serializers.IntegerField(allow_null=True)
    reported = serializers.IntegerField(allow_null=True)
    typical_day = serializers.IntegerField(allow_null=True)
    evidence_text = serializers.CharField()
    avg_price_kes = serializers.IntegerField(allow_null=True)
    quantity = serializers.CharField()
    follow_label = serializers.BooleanField()
    phi_days = serializers.IntegerField(allow_null=True)
    ppe_notes = serializers.CharField(allow_blank=True)


class DraftSerializer(serializers.Serializer):
    case_id = serializers.UUIDField()
    disease = serializers.DictField()
    farm_size_acres = serializers.DecimalField(max_digits=7, decimal_places=2, allow_null=True)
    local_data = serializers.BooleanField(help_text='False: show "Not enough local data yet"')
    options = DraftOptionSerializer(many=True)


class ApproveSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(
        help_text="The top option, or another allowed option (e.g. if out of stock)"
    )


class CardProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ("id", "name", "pcpb_reg_no", "active_ingredients", "label_rate", "phi_days", "ppe_notes")
        read_only_fields = fields


class InstructionsSerializer(serializers.Serializer):
    language = serializers.CharField(help_text="The language the text is in (a fallback if not yet reviewed)")
    dose = serializers.CharField()
    harvest = serializers.CharField()
    safety = serializers.ListField(child=serializers.CharField())
    label_notes = serializers.CharField(allow_blank=True)


class PrescriptionCardSerializer(serializers.ModelSerializer):
    """The prescription card (Documentation §6.3)."""

    disease = serializers.CharField(source="disease.name", allow_null=True)
    approved_product = CardProductSerializer()
    options = CardProductSerializer(source="allowed_products", many=True)
    approved_by = serializers.CharField(source="approved_by.name")
    phi_days = serializers.IntegerField(source="approved_product.phi_days", allow_null=True)
    safety_notes = serializers.CharField(source="approved_product.ppe_notes")
    qr_payload = serializers.CharField(source="code", help_text="Encode this in the QR code")
    is_expired = serializers.BooleanField()
    instructions = serializers.SerializerMethodField(
        help_text="Dose, harvest wait and spraying safety in the farmer's language (label notes as printed)"
    )

    class Meta:
        model = Prescription
        fields = (
            "id",
            "case",
            "code",
            "qr_payload",
            "disease",
            "approved_product",
            "options",
            "quantity",
            "safety_notes",
            "phi_days",
            "instructions",
            "approved_by",
            "expires_at",
            "is_expired",
            "created_at",
        )
        read_only_fields = fields

    @extend_schema_field(InstructionsSerializer)
    def get_instructions(self, prescription) -> dict:
        return card_instructions(prescription, farmer_language(prescription.case.farmer))
