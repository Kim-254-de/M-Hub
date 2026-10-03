from django.conf import settings
from rest_framework import serializers

from .models import CheckIn, ShareAffected


class SpraySerializer(serializers.Serializer):
    sprayed_at = serializers.DateTimeField(required=False, help_text="Defaults to now")
    amount_used = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class CheckInCreateSerializer(serializers.Serializer):
    day = serializers.IntegerField(help_text="2, 4 or 7 days after spraying")
    new_spots = serializers.ChoiceField(
        choices=CheckIn.NewSpots.choices, help_text="Are new spots still appearing on the plants?"
    )
    share_affected = serializers.ChoiceField(
        choices=ShareAffected.choices, help_text="few: under 10% of plants; some: 10-50%; most: over 50%."
    )
    photo = serializers.ImageField(required=False)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate_photo(self, photo):
        max_bytes = settings.DETECT["MAX_PHOTO_BYTES"]
        if photo.size > max_bytes:
            raise serializers.ValidationError(f"Photo is larger than {max_bytes // (1024 * 1024)} MB.")
        return photo


class CheckInSerializer(serializers.ModelSerializer):
    advice = serializers.CharField(read_only=True)

    class Meta:
        model = CheckIn
        fields = ("day", "new_spots", "share_affected", "photo", "notes", "advice", "created_at")
        read_only_fields = fields


class ScheduleItemSerializer(serializers.Serializer):
    day = serializers.IntegerField()
    due_at = serializers.DateTimeField()
    status = serializers.ChoiceField(choices=["done", "due", "upcoming", "missed"])
    check_in = CheckInSerializer(allow_null=True)


class SprayRecordSerializer(serializers.Serializer):
    sprayed_at = serializers.DateTimeField()
    product_id = serializers.UUIDField()
    product = serializers.CharField()
    amount_used = serializers.CharField()
    harvest_safe_from = serializers.DateTimeField(allow_null=True, help_text="Do not harvest before this")


class ExpectedResultsSerializer(serializers.Serializer):
    product = serializers.CharField()
    enough_data = serializers.BooleanField()
    improved = serializers.IntegerField(allow_null=True)
    reported = serializers.IntegerField(allow_null=True)
    typical_day = serializers.IntegerField(allow_null=True)
    response_rate = serializers.FloatField(
        allow_null=True, help_text="Share of nearby farmers who finished their follow-up"
    )
    text = serializers.CharField()


class FollowUpSerializer(serializers.Serializer):
    case_id = serializers.UUIDField()
    can_record_spray = serializers.BooleanField()
    spray = SprayRecordSerializer(allow_null=True)
    schedule = ScheduleItemSerializer(many=True)
    next_due_day = serializers.IntegerField(allow_null=True)
    complete = serializers.BooleanField()
    expected = ExpectedResultsSerializer(allow_null=True, help_text="Results of verified farmers nearby")
