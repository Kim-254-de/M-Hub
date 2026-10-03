from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.agrovets.models import Agrovet
from apps.cases.models import Case
from apps.cases.serializers import CasePhotoSerializer
from apps.core.geo import haversine_km
from apps.products.models import Disease

from . import review as review_services
from .models import AgrovetReview, AIDiagnosis, AISuggestion, PeerComment

# Provider details that are safe to show. Provider treatment advice names
# chemicals that may not be PCPB-registered for tomato in Kenya, so only the
# "prevention" part of "treatment" is exposed (Documentation §11: registered
# products only; products come from Prescribe, never from the AI).
SAFE_DETAIL_KEYS = ("common_names", "type", "description", "symptoms", "severity", "spreading", "wiki_url")


class AISuggestionSerializer(serializers.ModelSerializer):
    details = serializers.SerializerMethodField()

    class Meta:
        model = AISuggestion
        fields = (
            "rank",
            "external_id",
            "name",
            "scientific_name",
            "probability",
            "is_healthy",
            "details",
            "similar_images",
        )
        read_only_fields = fields

    def get_details(self, obj) -> dict:
        details = obj.details or {}
        safe = {key: details[key] for key in SAFE_DETAIL_KEYS if details.get(key) is not None}
        treatment = details.get("treatment")
        if isinstance(treatment, dict) and treatment.get("prevention"):
            safe["prevention"] = treatment["prevention"]
        return safe


class AIDiagnosisSerializer(serializers.ModelSerializer):
    suggestions = AISuggestionSerializer(many=True, read_only=True)
    needs_retake = serializers.BooleanField(read_only=True)

    class Meta:
        model = AIDiagnosis
        fields = (
            "id",
            "case",
            "provider",
            "status",
            "is_plant",
            "is_tomato",
            "needs_retake",
            "crop_name",
            "crop_probability",
            "model_version",
            "error_code",
            "suggestions",
            "created_at",
            "completed_at",
        )
        read_only_fields = fields


# --- Processes 3.2-3.6 ------------------------------------------------------------


class DiseaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Disease
        fields = ("id", "name", "scientific_name", "type")
        read_only_fields = fields


class AgrovetSummarySerializer(serializers.ModelSerializer):
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Agrovet
        fields = ("id", "name", "phone", "latitude", "longitude", "distance_km")
        read_only_fields = fields

    def get_distance_km(self, agrovet) -> float | None:
        case = self.context.get("case")
        if case is None or case.latitude is None or case.longitude is None:
            return None
        return round(haversine_km(case.latitude, case.longitude, agrovet.latitude, agrovet.longitude), 2)


class ChooseAgrovetSerializer(serializers.Serializer):
    agrovet_id = serializers.UUIDField()


class ReviewCaseSerializer(serializers.ModelSerializer):
    """What a reviewer sees of a case: photos, answers and area, never the farmer's identity."""

    photos = CasePhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Case
        fields = (
            "id",
            "status",
            "county",
            "ward",
            "latitude",
            "longitude",
            "symptom_answers",
            "photos",
            "submitted_at",
        )
        read_only_fields = fields


class AgrovetReviewListSerializer(serializers.ModelSerializer):
    case_id = serializers.UUIDField(source="case.id", read_only=True)
    ward = serializers.CharField(source="case.ward", read_only=True)
    submitted_at = serializers.DateTimeField(source="case.submitted_at", read_only=True)

    class Meta:
        model = AgrovetReview
        fields = (
            "id",
            "case_id",
            "round",
            "status",
            "chosen_by_farmer",
            "ward",
            "submitted_at",
            "created_at",
        )
        read_only_fields = fields


class AgrovetReviewSerializer(serializers.ModelSerializer):
    case = ReviewCaseSerializer(read_only=True)
    ai_diagnosis = serializers.SerializerMethodField()
    evidence = serializers.SerializerMethodField()
    disease = DiseaseSerializer(read_only=True)
    first_opinion = serializers.SerializerMethodField()

    class Meta:
        model = AgrovetReview
        fields = (
            "id",
            "round",
            "status",
            "chosen_by_farmer",
            "case",
            "ai_diagnosis",
            "evidence",
            "first_opinion",
            "decision",
            "disease",
            "notes",
            "created_at",
            "decided_at",
        )
        read_only_fields = fields

    @extend_schema_field(AIDiagnosisSerializer(allow_null=True))
    def get_ai_diagnosis(self, review):
        ai = (
            AIDiagnosis.objects.filter(case=review.case)
            .prefetch_related("suggestions")
            .order_by("-created_at")
            .first()
        )
        return AIDiagnosisSerializer(ai).data if ai else None

    @extend_schema_field(serializers.DictField())
    def get_evidence(self, review) -> dict:
        # Live while pending; the snapshot the agrovet decided on afterwards.
        if review.status == AgrovetReview.Status.PENDING:
            return review_services.collect_evidence(review.case)
        return review.evidence

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_first_opinion(self, review) -> dict | None:
        """For a second opinion: what the first agrovet decided. Their identity is not shown."""
        if review.round != AgrovetReview.Round.SECOND_OPINION:
            return None
        first = (
            AgrovetReview.objects.filter(
                case=review.case, round=AgrovetReview.Round.FIRST, status=AgrovetReview.Status.DECIDED
            )
            .select_related("disease")
            .first()
        )
        if first is None:
            return None
        return {
            "decision": first.decision,
            "disease": DiseaseSerializer(first.disease).data if first.disease else None,
            "notes": first.notes,
        }


class DecisionSerializer(serializers.Serializer):
    disease_id = serializers.UUIDField(required=False, allow_null=True)
    unsure = serializers.BooleanField(default=False)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if bool(attrs.get("disease_id")) == attrs["unsure"]:
            raise serializers.ValidationError("Send a disease_id, or unsure=true.")
        return attrs


class PeerCaseSerializer(serializers.ModelSerializer):
    photos = CasePhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Case
        fields = ("id", "ward", "symptom_answers", "photos", "submitted_at")
        read_only_fields = fields


class PeerCommentSerializer(serializers.ModelSerializer):
    disease_id = serializers.UUIDField(required=False, allow_null=True)
    disease = DiseaseSerializer(read_only=True)

    class Meta:
        model = PeerComment
        fields = ("id", "disease_id", "disease", "comment", "created_at")
        read_only_fields = ("id", "disease", "created_at")
        extra_kwargs = {"comment": {"required": False, "allow_blank": True}}


class ProvisionalResultSerializer(serializers.Serializer):
    """The AI suggestion shown while an agrovet confirms. Not a diagnosis; never names products."""

    kind = serializers.ChoiceField(choices=["likely", "healthy", "unsure"])
    disease = DiseaseSerializer(allow_null=True, help_text="Catalogue disease, when the AI name matches one")
    name = serializers.CharField(allow_null=True, help_text="Disease name shown to the farmer")
    probability = serializers.FloatField(allow_null=True)
    message = serializers.CharField()


class AIEvidenceSerializer(serializers.Serializer):
    name = serializers.CharField()
    percent = serializers.IntegerField()


class CaseDiagnosisSerializer(serializers.Serializer):
    """The farmer's view of where their diagnosis stands."""

    case_id = serializers.UUIDField()
    status = serializers.CharField()
    message = serializers.CharField(allow_null=True)
    provisional = ProvisionalResultSerializer(
        allow_null=True, help_text="AI suggestion while waiting for the agrovet; null once confirmed"
    )
    safe_actions = serializers.ListField(
        child=serializers.CharField(), help_text="Product-free steps the farmer can take now"
    )
    disease = DiseaseSerializer(allow_null=True)
    confidence = serializers.CharField(allow_null=True)
    confirmed_by = serializers.CharField(allow_null=True, help_text="Agrovet name")
    ai_corrected = serializers.BooleanField(
        allow_null=True, help_text="True if the agrovet's diagnosis differs from the AI suggestion"
    )
    ai_corrected_message = serializers.CharField(allow_null=True)
    reviewer = AgrovetSummarySerializer(allow_null=True, help_text="Agrovet currently reviewing the case")
    disease_name = serializers.CharField(
        allow_null=True, help_text="Confirmed disease in the farmer's language"
    )
    similar_nearby = serializers.IntegerField(
        allow_null=True, help_text="Other confirmed cases of this disease nearby in the last 30 days"
    )


class OutbreakSerializer(serializers.Serializer):
    disease = DiseaseSerializer()
    name = serializers.CharField(help_text="Disease name in the farmer's language")
    count = serializers.IntegerField()
    ward = serializers.CharField(allow_blank=True)
    message = serializers.CharField(help_text="Alert text in the farmer's language")
