from rest_framework import serializers

from .models import AIDiagnosis, AISuggestion

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
