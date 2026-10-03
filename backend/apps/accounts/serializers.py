from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from apps.rewards.services import balance

from . import otp
from .models import Farm, FarmerProfile, User
from .phone import normalize_kenyan_phone


class PhoneField(serializers.CharField):
    default_error_messages = {"invalid_phone": "Enter a Kenyan mobile number, e.g. 0712345678."}

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 20)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        phone = normalize_kenyan_phone(super().to_internal_value(data))
        if phone is None:
            self.fail("invalid_phone")
        return phone


class PinField(serializers.RegexField):
    def __init__(self, **kwargs):
        super().__init__(
            r"^\d{4,6}$",
            write_only=True,
            error_messages={"invalid": "PIN must be 4 to 6 digits."},
            style={"input_type": "password"},
            **kwargs,
        )


def tokens_for(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class OtpRequestSerializer(serializers.Serializer):
    phone = PhoneField()
    language = serializers.ChoiceField(choices=FarmerProfile.Language.choices, default="sw")

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("An account with this phone number already exists.")
        return value


class OtpVerifySerializer(serializers.Serializer):
    phone = PhoneField()
    code = serializers.RegexField(r"^\s*\d{6}\s*$", error_messages={"invalid": "Enter the 6-digit code."})


class PhoneTokenResponseSerializer(serializers.Serializer):
    phone_token = serializers.CharField(
        help_text="Send with the registration to prove the phone was verified"
    )


class FarmerRegistrationSerializer(serializers.Serializer):
    phone = PhoneField()
    phone_token = serializers.CharField(required=False, write_only=True, help_text="From auth/otp/verify/")
    pin = PinField()
    name = serializers.CharField(max_length=150)
    language = serializers.ChoiceField(
        choices=FarmerProfile.Language.choices, default=FarmerProfile.Language.SWAHILI
    )
    county = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    ward = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    consent = serializers.BooleanField(write_only=True, help_text="Farmer agrees to the data-use terms.")

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("An account with this phone number already exists.")
        return value

    def validate(self, attrs):
        if settings.ACCOUNTS["REQUIRE_OTP"]:
            verified = otp.phone_from_token(attrs.get("phone_token", ""))
            if verified != attrs["phone"]:
                raise serializers.ValidationError(
                    {"phone_token": "Verify the phone number with the SMS code first."}
                )
        return attrs

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError("Consent to data use is required to register.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        # PINs are numeric and short by design (feature phones, low literacy), so Django's
        # password validators are not applied; brute force is limited by the auth throttle.
        user = User(username=validated_data["phone"], phone=validated_data["phone"], role=User.Role.FARMER)
        user.first_name = validated_data["name"]
        user.set_password(validated_data["pin"])
        user.save()
        FarmerProfile.objects.create(
            user=user,
            language=validated_data["language"],
            county=validated_data["county"],
            ward=validated_data["ward"],
            consent_at=timezone.now(),
        )
        return user


class PhoneTokenSerializer(serializers.Serializer):
    phone = PhoneField()
    pin = PinField()

    def validate(self, attrs):
        user = User.objects.filter(phone=attrs["phone"], is_active=True).first()
        if user is None or not user.check_password(attrs["pin"]):
            raise AuthenticationFailed("Invalid phone number or PIN.")
        return tokens_for(user)


class TokenPairSerializer(serializers.Serializer):
    refresh = serializers.CharField(read_only=True)
    access = serializers.CharField(read_only=True)


class FarmSerializer(serializers.ModelSerializer):
    crops = serializers.ListField(child=serializers.CharField(max_length=32), required=False)

    class Meta:
        model = Farm
        fields = ("id", "name", "latitude", "longitude", "size_acres", "crops", "created_at")
        read_only_fields = ("id", "created_at")


class MeSerializer(serializers.Serializer):
    """The signed-in farmer's profile (Profile tab)."""

    name = serializers.CharField(source="first_name", max_length=150)
    phone = serializers.CharField(read_only=True)
    language = serializers.ChoiceField(
        source="farmer_profile.language", choices=FarmerProfile.Language.choices
    )
    county = serializers.CharField(source="farmer_profile.county", max_length=64, allow_blank=True)
    ward = serializers.CharField(source="farmer_profile.ward", max_length=64, allow_blank=True)
    notifications_enabled = serializers.BooleanField(source="farmer_profile.notifications_enabled")
    points = serializers.SerializerMethodField()
    support_whatsapp = serializers.SerializerMethodField(
        help_text="Empty when WhatsApp support is not offered"
    )
    farms = FarmSerializer(many=True, read_only=True)

    def get_points(self, user) -> int:
        return balance(user)

    def get_support_whatsapp(self, user) -> str:
        return settings.ACCOUNTS["SUPPORT_WHATSAPP"]

    def update(self, user, validated_data):
        profile_data = validated_data.pop("farmer_profile", {})
        if "first_name" in validated_data:
            user.first_name = validated_data["first_name"]
            user.save(update_fields=["first_name"])
        profile = user.farmer_profile
        for field, value in profile_data.items():
            setattr(profile, field, value)
        if profile_data:
            profile.save(update_fields=[*profile_data, "updated_at"])
        return user
