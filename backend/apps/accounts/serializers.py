from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

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


class FarmerRegistrationSerializer(serializers.Serializer):
    phone = PhoneField()
    pin = PinField()
    name = serializers.CharField(max_length=150)
    language = serializers.ChoiceField(
        choices=FarmerProfile.Language.choices, default=FarmerProfile.Language.SWAHILI
    )
    county = serializers.CharField(max_length=64)
    ward = serializers.CharField(max_length=64)
    consent = serializers.BooleanField(write_only=True, help_text="Farmer agrees to the data-use terms.")

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("An account with this phone number already exists.")
        return value

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
