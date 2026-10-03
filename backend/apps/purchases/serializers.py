from rest_framework import serializers

from apps.agrovets.models import StoreItem
from apps.products.models import Product

from .models import Order, Payment, Verification


class ProductSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ("id", "name", "pcpb_reg_no", "active_ingredients", "phi_days")
        read_only_fields = fields


class StoreOfferSerializer(serializers.Serializer):
    store_item_id = serializers.UUIDField(source="store_item.id")
    agrovet_id = serializers.UUIDField(source="store_item.agrovet.id")
    agrovet_name = serializers.CharField(source="store_item.agrovet.name")
    agrovet_phone = serializers.CharField(source="store_item.agrovet.phone")
    latitude = serializers.DecimalField(source="store_item.agrovet.latitude", max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(
        source="store_item.agrovet.longitude", max_digits=9, decimal_places=6
    )
    distance_km = serializers.FloatField(allow_null=True)
    price_kes = serializers.IntegerField(source="store_item.price_kes")
    product = ProductSummarySerializer(source="store_item.product")


class StoreQuerySerializer(serializers.Serializer):
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-90, max_value=90, required=False
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-180, max_value=180, required=False
    )
    radius_km = serializers.FloatField(min_value=1, max_value=200, required=False)

    def validate(self, attrs):
        if ("latitude" in attrs) != ("longitude" in attrs):
            raise serializers.ValidationError("Send both latitude and longitude, or neither.")
        return attrs


class OrderCreateSerializer(serializers.Serializer):
    prescription_code = serializers.CharField(max_length=16)
    store_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=50, default=1)
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices)


class PayOrderSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20, required=False, help_text="Defaults to the account phone")


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id",
            "status",
            "amount_kes",
            "phone",
            "mpesa_receipt",
            "result_desc",
            "created_at",
            "completed_at",
        )
        read_only_fields = fields


class VerificationSerializer(serializers.ModelSerializer):
    product = ProductSummarySerializer(read_only=True)
    message = serializers.SerializerMethodField()

    MESSAGES = {
        Verification.Result.VERIFIED: "Verified: genuine registered product, as prescribed.",
        Verification.Result.MISMATCH: "This is not the product on the order.",
        Verification.Result.NOT_REGISTERED: "Not a registered product. Do not use.",
        Verification.Result.NOT_PRESCRIBED: "Registered, but not what was prescribed for this disease.",
        Verification.Result.UNREADABLE: (
            "We could not read the PCPB number. Retake the photo closer to the label."
        ),
    }

    class Meta:
        model = Verification
        fields = ("id", "type", "result", "message", "product", "detected_reg_no", "created_at")
        read_only_fields = fields

    def get_message(self, obj) -> str:
        return self.MESSAGES.get(obj.result, "")


class OrderSerializer(serializers.ModelSerializer):
    prescription_code = serializers.CharField(source="prescription.code", read_only=True)
    agrovet_name = serializers.CharField(source="agrovet.name", read_only=True)
    product = ProductSummarySerializer(read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    verifications = VerificationSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "prescription_code",
            "agrovet",
            "agrovet_name",
            "product",
            "unit_price_kes",
            "quantity",
            "total_kes",
            "payment_method",
            "status",
            "paid_at",
            "collected_at",
            "cancelled_at",
            "payments",
            "verifications",
            "created_at",
        )
        read_only_fields = fields


class LabelCheckSerializer(serializers.Serializer):
    photo = serializers.ImageField()


class SaleMatchSerializer(serializers.Serializer):
    prescription_code = serializers.CharField(max_length=16)
    product_id = serializers.UUIDField(help_text="Product handed to the farmer")


class StoreItemSerializer(serializers.ModelSerializer):
    product = ProductSummarySerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True), source="product", write_only=True
    )

    class Meta:
        model = StoreItem
        fields = ("id", "product", "product_id", "price_kes", "in_stock", "updated_at")
        read_only_fields = ("id", "product", "updated_at")

    def validate(self, attrs):
        # Store rule: catalogue items must be registered products, one listing per product.
        agrovet = self.context["agrovet"]
        product = attrs.get("product")
        if (
            product
            and self.instance is None
            and StoreItem.objects.filter(agrovet=agrovet, product=product).exists()
        ):
            raise serializers.ValidationError({"product_id": "This product is already in your store."})
        if self.instance is not None and product and product != self.instance.product:
            raise serializers.ValidationError({"product_id": "The product of a listing cannot be changed."})
        return attrs
