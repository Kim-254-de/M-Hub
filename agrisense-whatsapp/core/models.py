import secrets

from django.db import models


class Farmer(models.Model):
    LANG_EN = "en"
    LANG_SW = "sw"
    LANGUAGES = [(LANG_EN, "English"), (LANG_SW, "Kiswahili")]

    phone = models.CharField(max_length=15, unique=True, help_text="2547XXXXXXXX")
    whatsapp_name = models.CharField(max_length=100, blank=True)
    full_name = models.CharField(max_length=100, blank=True)
    county = models.CharField(max_length=50, blank=True)
    ward = models.CharField(max_length=80, blank=True, help_text="Ward / village")
    main_crops = models.CharField(max_length=200, blank=True)
    language = models.CharField(max_length=2, choices=LANGUAGES, default=LANG_EN)
    is_registered = models.BooleanField(default=False)
    # Data-use consent (Kenya Data Protection Act, 2019), given when confirming registration.
    consent_at = models.DateTimeField(null=True, blank=True)
    points = models.PositiveIntegerField(default=0, help_text="Rewards for verified purchases")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name or self.whatsapp_name or 'Farmer'} ({self.phone})"


class Agrovet(models.Model):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15, help_text="WhatsApp number, 2547XXXXXXXX")
    county = models.CharField(max_length=50)
    town = models.CharField(max_length=80, blank=True)
    location_hint = models.CharField(max_length=200, blank=True, help_text="e.g. Opposite Chuka market")
    is_verified = models.BooleanField(default=False, help_text="Sells genuine, certified products")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} — {self.town or self.county}"


class Product(models.Model):
    agrovet = models.ForeignKey(Agrovet, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=120)
    pcpb_reg_no = models.CharField(
        max_length=32, blank=True, help_text='PCPB registration number printed on the label, e.g. "PCPB (CR) 0856"'
    )
    active_ingredient = models.CharField(max_length=120, blank=True)
    pack_size = models.CharField(max_length=40, blank=True)
    price = models.PositiveIntegerField(help_text="KES")
    farmer_discount_pct = models.PositiveSmallIntegerField(default=0)
    target_keywords = models.CharField(
        max_length=300,
        help_text="Comma-separated disease/pest keywords this treats, e.g. 'late blight, early blight'",
    )
    crops = models.CharField(max_length=200, blank=True, help_text="Comma-separated, blank = any crop")
    usage_note = models.CharField(max_length=300, blank=True)
    in_stock = models.BooleanField(default=True)

    @property
    def farmer_price(self):
        return round(self.price * (100 - self.farmer_discount_pct) / 100)

    def matches(self, disease_name, crop=""):
        name = (disease_name or "").lower()
        keywords = [k.strip().lower() for k in self.target_keywords.split(",") if k.strip()]
        if not any(k in name or name in k for k in keywords):
            return False
        if self.crops and crop:
            crops = [c.strip().lower() for c in self.crops.split(",") if c.strip()]
            return crop.lower() in crops
        return True

    def __str__(self):
        return f"{self.name} {self.pack_size} @ {self.agrovet.name}"


class Diagnosis(models.Model):
    STATUS_AUTO = "auto"
    STATUS_REVIEW = "needs_review"
    STATUS_CONFIRMED = "confirmed"
    STATUS_REJECTED = "rejected"
    STATUSES = [
        (STATUS_AUTO, "AI result sent"),
        (STATUS_REVIEW, "Waiting for agrovet"),
        (STATUS_CONFIRMED, "Confirmed by agrovet"),
        (STATUS_REJECTED, "Corrected by agrovet"),
    ]
    OUTCOMES = [("worked", "Worked"), ("partly", "Partly worked"), ("no_change", "No change")]

    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name="diagnoses")
    crop = models.CharField(max_length=50)
    image = models.FileField(upload_to="diagnoses/%Y/%m/", blank=True)
    wa_media_id = models.CharField(max_length=100, blank=True)
    disease = models.CharField(max_length=150, blank=True)
    confidence = models.FloatField(default=0)
    description = models.TextField(blank=True)
    treatment = models.TextField(blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_AUTO)
    reviewed_by = models.ForeignKey(Agrovet, null=True, blank=True, on_delete=models.SET_NULL)
    agrovet_note = models.TextField(blank=True, help_text="Sent to the farmer when you confirm/correct")
    outcome = models.CharField(max_length=20, choices=OUTCOMES, blank=True)
    outcome_verified = models.BooleanField(default=False, help_text="Agrovet checked the outcome")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "diagnoses"

    def __str__(self):
        return f"{self.crop}: {self.disease or 'pending'} ({self.farmer.phone})"


def _pickup_code():
    return secrets.token_hex(3).upper()


class Order(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_COLLECTED = "collected"
    STATUSES = [
        (STATUS_PENDING, "Awaiting payment"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Payment failed"),
        (STATUS_COLLECTED, "Collected"),
    ]

    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name="orders")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    diagnosis = models.ForeignKey(Diagnosis, null=True, blank=True, on_delete=models.SET_NULL)
    quantity = models.PositiveSmallIntegerField(default=1)
    amount = models.PositiveIntegerField(help_text="KES")
    pay_phone = models.CharField(max_length=15)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_PENDING)
    checkout_request_id = models.CharField(max_length=100, blank=True, db_index=True)
    mpesa_receipt = models.CharField(max_length=30, blank=True)
    LABEL_VERIFIED = "verified"
    LABEL_NOT_REGISTERED = "not_registered"
    LABEL_NOT_PRESCRIBED = "not_prescribed"
    LABEL_RESULTS = [
        (LABEL_VERIFIED, "Verified genuine"),
        (LABEL_NOT_REGISTERED, "Not a registered product"),
        (LABEL_NOT_PRESCRIBED, "Registered, but not the prescribed product"),
    ]

    pickup_code = models.CharField(max_length=10, default=_pickup_code)
    followup_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    label_result = models.CharField(max_length=20, choices=LABEL_RESULTS, blank=True)
    label_reg_no = models.CharField(max_length=40, blank=True, help_text="PCPB number read from the label")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.pk} {self.product.name} x{self.quantity} — {self.get_status_display()}"
