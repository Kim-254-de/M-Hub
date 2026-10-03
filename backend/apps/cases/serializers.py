from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import Farm

from . import services
from .messages import retake_message
from .models import Case, CasePhoto


class SymptomAnswersSerializer(serializers.Serializer):
    """The quick questions asked after the photos (Documentation §6.1, step 4).

    Fixed choices so the same questions work as WhatsApp buttons later.
    """

    started = serializers.ChoiceField(
        choices=["less_than_3_days", "3_to_7_days", "1_to_2_weeks", "over_2_weeks"],
        help_text="When the symptoms were first noticed.",
    )
    share_affected = serializers.ChoiceField(
        choices=["few", "some", "most"],
        help_text="few: under 10% of plants; some: 10-50%; most: over 50%.",
    )
    recent_weather = serializers.MultipleChoiceField(
        choices=["rainy", "humid", "hot_dry", "cold", "normal"],
        help_text="Weather over the past week; choose all that apply.",
    )
    already_sprayed = serializers.BooleanField()
    sprayed_product = serializers.CharField(max_length=200, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_recent_weather(self, value):
        if not value:
            raise serializers.ValidationError("Choose at least one option.")
        return sorted(value)


class CasePhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CasePhoto
        fields = ("id", "type", "image", "width", "height", "created_at")
        read_only_fields = ("id", "width", "height", "created_at")

    def validate_image(self, image):
        max_bytes = settings.DETECT["MAX_PHOTO_BYTES"]
        if image.size > max_bytes:
            raise serializers.ValidationError(f"Photo is larger than {max_bytes // (1024 * 1024)} MB.")
        return image


class CaseCreateSerializer(serializers.ModelSerializer):
    farm = serializers.PrimaryKeyRelatedField(queryset=Farm.objects.none(), required=False, allow_null=True)

    class Meta:
        model = Case
        fields = ("farm", "latitude", "longitude")

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            fields["farm"].queryset = Farm.objects.filter(farmer=request.user)
        return fields

    def validate(self, attrs):
        if (attrs.get("latitude") is None) != (attrs.get("longitude") is None):
            raise serializers.ValidationError("Send both latitude and longitude, or neither.")
        return attrs


class DetectionStatusSerializer(serializers.Serializer):
    """Where the report is in the photo check, for the app to poll after submitting."""

    ai_status = serializers.CharField(allow_null=True)
    needs_retake = serializers.BooleanField()
    retake_reason = serializers.CharField(allow_null=True)
    retake_message = serializers.CharField(allow_null=True)


VOICE_NOTE_TYPES = {"m4a", "aac", "mp3", "3gp", "ogg", "webm", "wav", "mp4"}
VOICE_NOTE_MAX_BYTES = 2 * 1024 * 1024  # about a minute of speech


class VoiceNoteSerializer(serializers.Serializer):
    audio = serializers.FileField()

    def validate_audio(self, audio):
        extension = audio.name.rsplit(".", 1)[-1].lower() if "." in audio.name else ""
        if extension not in VOICE_NOTE_TYPES:
            raise serializers.ValidationError("Send the voice note as an audio file (m4a, aac, mp3, ogg).")
        if audio.size > VOICE_NOTE_MAX_BYTES:
            raise serializers.ValidationError("The voice note is too long. Keep it under one minute.")
        return audio


class CaseSerializer(serializers.ModelSerializer):
    photos = CasePhotoSerializer(many=True, read_only=True)
    missing_photos = serializers.SerializerMethodField()
    detection = serializers.SerializerMethodField()
    disease = serializers.SerializerMethodField(
        help_text="Confirmed disease in the farmer's language, else null"
    )

    class Meta:
        model = Case
        fields = (
            "id",
            "status",
            "channel",
            "farm",
            "latitude",
            "longitude",
            "symptom_answers",
            "photos",
            "missing_photos",
            "detection",
            "disease",
            "voice_note",
            "created_at",
            "submitted_at",
        )
        read_only_fields = fields

    def get_disease(self, case) -> str | None:
        final = getattr(case, "final_diagnosis", None)
        if final is None:
            return None
        profile = getattr(case.farmer, "farmer_profile", None)
        return final.disease.display_name(profile.language if profile else "en")

    def get_missing_photos(self, case) -> list[str]:
        present = {photo.type for photo in case.photos.all()}
        return [t for t in CasePhoto.REQUIRED_TYPES if t not in present]

    @extend_schema_field(DetectionStatusSerializer)
    def get_detection(self, case) -> dict:
        ai_diagnosis = services.latest_ai_diagnosis(case)
        reason = services.retake_reason(ai_diagnosis)
        message = retake_message(reason, services.farmer_language(case.farmer)) if reason else None
        return {
            "ai_status": ai_diagnosis.status if ai_diagnosis else None,
            "needs_retake": reason is not None,
            "retake_reason": reason,
            "retake_message": message,
        }
