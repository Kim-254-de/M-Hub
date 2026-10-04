# ruff: noqa: E501  (demo data rows read better on one line)
"""Demo data for trying the farmer app: one farmer with cases in every state, two verified agrovets,
two registered blight products, nearby confirmed cases (outbreak alert) and local results.

    python manage.py seed_demo            # only with DEBUG=True
    Log in on the app with 0700 000 001 and PIN 1234.

Everything here is made up. Never run it against production data.
"""

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.accounts.models import Farm, FarmerProfile, User
from apps.agrovets.models import Agrovet, StoreItem
from apps.cases.models import Case, CasePhoto
from apps.diagnosis.models import AgrovetReview, AIDiagnosis, AISuggestion, FinalDiagnosis
from apps.followups import services as followups
from apps.prescriptions.models import Prescription, TreatmentOutcome
from apps.prescriptions.services import calculate_dose
from apps.products.models import Disease, Product, TreatmentRule
from apps.purchases.models import Order, Verification
from apps.rewards.models import RewardEntry

CHUKA = (Decimal("-0.333000"), Decimal("37.650000"))
PHONE, PIN = "+254700000001", "1234"


def _photo(kind: str) -> ContentFile:
    """A simple drawn picture so the case cards have thumbnails (no real crop photos in the repo)."""
    image = Image.new("RGB", (800, 600), (233, 240, 226))
    draw = ImageDraw.Draw(image)
    if kind == "leaf":
        draw.ellipse((150, 100, 650, 500), fill=(78, 140, 70), outline=(40, 80, 40), width=8)
        for box in ((300, 220, 380, 290), (450, 320, 520, 380), (360, 380, 410, 420)):
            draw.ellipse(box, fill=(90, 70, 50))
    elif kind == "plant":
        draw.line((400, 560, 400, 60), fill=(50, 110, 50), width=14)
        for y in (150, 260, 370):
            draw.ellipse((220, y, 400, y + 70), fill=(78, 140, 70))
            draw.ellipse((400, y + 40, 580, y + 110), fill=(78, 140, 70))
        draw.ellipse((300, 420, 360, 480), fill=(210, 70, 46))
    else:
        draw.line((300, 580, 300, 20), fill=(50, 110, 50), width=40)
        draw.rectangle((282, 220, 318, 300), fill=(90, 70, 50))
        draw.ellipse((420, 300, 600, 480), fill=(210, 70, 46))
        draw.ellipse((470, 340, 530, 390), fill=(90, 70, 50))
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=80)
    return ContentFile(buffer.getvalue(), name=f"{kind}.jpg")


class Command(BaseCommand):
    help = "Create demo data for the farmer app (DEBUG only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true", help="Run even when DEBUG is off (test deployments only)"
        )
        parser.add_argument(
            "--skip-existing", action="store_true", help="Do nothing if the demo farmer exists"
        )

    @transaction.atomic
    def handle(self, *args, force=False, skip_existing=False, **options):
        if not settings.DEBUG and not force:
            raise CommandError("seed_demo only runs with DEBUG=True.")
        if skip_existing and User.objects.filter(phone=PHONE).exists():
            self.stdout.write("Demo data already exists; nothing to do.")
            return
        if User.objects.filter(phone=PHONE).exists():
            raise CommandError(f"Demo data already exists (farmer {PHONE}).")
        now = timezone.now()
        lat, lng = CHUKA

        # Agrovets and products --------------------------------------------------------------
        def agrovet(name, phone, dlat, dlng):
            user = User.objects.create_user(
                username=f"agrovet-{phone}", password=None, phone=phone, role=User.Role.AGROVET
            )
            return Agrovet.objects.create(
                user=user, name=name, pcpb_licence_no=f"DEMO-{phone[-4:]}", phone=phone,
                latitude=lat + Decimal(dlat), longitude=lng + Decimal(dlng), status=Agrovet.Status.VERIFIED,
            )  # fmt: skip

        mwangi = agrovet("Mwangi Agrovet, Chuka", "+254711000001", "0.004", "0.006")
        kirimara = agrovet("Kirimara Farm Supplies", "+254711000002", "-0.012", "0.018")

        late = Disease.objects.create(
            name="Late blight",
            scientific_name="Phytophthora infestans",
            local_names={"sw": "Baa chelewa"},
            explanations={
                "en": "A fast-spreading disease that makes dark, wet patches on leaves, stems and fruit. "
                "It spreads quickly in cool, wet weather.",
                "sw": "Ugonjwa unaoenea haraka unaoleta mabaka meusi yenye unyevu kwenye majani, mashina na "
                "matunda. Huenea haraka wakati wa baridi na mvua.",
            },
        )
        early = Disease.objects.create(
            name="Early blight", scientific_name="Alternaria solani", local_names={"sw": "Baa ya mapema"}
        )
        for disease, ingredient in ((late, "Mancozeb"), (late, "Metalaxyl-M"), (early, "Mancozeb")):
            TreatmentRule.objects.create(disease=disease, active_ingredient=ingredient)

        ridomil = Product.objects.create(
            pcpb_reg_no="PCPB (CR) 0856", name="Ridomil Gold MZ 68 WG", active_ingredients=["Metalaxyl-M", "Mancozeb"],
            approved_crops=["tomato"], label_rate="50 g per 20 L", rate_per_acre=Decimal("250"), rate_unit="g",
            pack_size=Decimal("250"), phi_days=7, ppe_notes="Harmful if swallowed. Wear gloves and a mask.",
        )  # fmt: skip
        dithane = Product.objects.create(
            pcpb_reg_no="PCPB (CR) 0154", name="Dithane M-45", active_ingredients=["Mancozeb"],
            approved_crops=["tomato"], label_rate="40 g per 20 L", phi_days=7,
        )  # fmt: skip
        for store, product, price in (
            (mwangi, ridomil, 1300),
            (kirimara, ridomil, 1250),
            (mwangi, dithane, 450),
        ):
            StoreItem.objects.create(agrovet=store, product=product, price_kes=price)

        # The demo farmer --------------------------------------------------------------------------
        farmer = User.objects.create_user(
            username=PHONE, password=PIN, phone=PHONE, first_name="Wanjiru Mwenda"
        )
        FarmerProfile.objects.create(
            user=farmer, language="sw", county="Tharaka Nithi", ward="Chuka", consent_at=now
        )
        farm = Farm.objects.create(farmer=farmer, latitude=lat, longitude=lng, size_acres=Decimal("0.50"))

        def case(status, days_ago, **extra):
            c = Case.objects.create(
                farmer=farmer, farm=farm, status=status, ward="Chuka", county="Tharaka Nithi",
                latitude=lat, longitude=lng, submitted_at=now - timedelta(days=days_ago),
                symptom_answers={"started": "3_to_7_days", "share_affected": "some", "recent_weather": ["rainy"],
                                 "already_sprayed": False},
                **extra,
            )  # fmt: skip
            for kind in ("leaf", "plant", "stem_fruit"):
                photo = CasePhoto(case=c, type=kind, width=800, height=600)
                photo.image.save(f"{kind}.jpg", _photo(kind), save=True)
            ai = AIDiagnosis.objects.create(
                case=c, provider="kindwise", status=AIDiagnosis.Status.COMPLETED, is_plant=True, is_tomato=True,
                completed_at=c.submitted_at,
            )  # fmt: skip
            AISuggestion.objects.create(
                ai_diagnosis=ai,
                rank=1,
                external_id="demo-late-blight",
                name="late blight",
                probability=Decimal("0.8700"),
            )
            return c

        def confirm(c, disease=late):
            FinalDiagnosis.objects.create(
                case=c,
                disease=disease,
                confidence="high",
                confirmed_by=mwangi,
                ward="Chuka",
                latitude=lat,
                longitude=lng,
            )

        def prescribe(c):
            dose = calculate_dose(ridomil, farm.size_acres)
            p = Prescription.objects.create(
                case=c, approved_product=ridomil, approved_by=mwangi, disease=late, quantity=dose.quantity,
                dose_amount=dose.amount, dose_unit=dose.unit, dose_packs=dose.packs, dose_pack_size=dose.pack_size,
                expires_at=now + timedelta(days=14),
            )  # fmt: skip
            p.allowed_products.set([ridomil, dithane])
            return p

        # 1. Waiting for the agrovet, with the AI's provisional suggestion.
        waiting = case(Case.Status.DIAGNOSING, 0)
        AgrovetReview.objects.create(case=waiting, agrovet=mwangi, round=1)
        # 2. Second opinion requested.
        case(Case.Status.SECOND_OPINION, 1)
        # 3. Treatment ready: confirmed and prescribed.
        ready = case(Case.Status.PRESCRIBED, 2)
        confirm(ready)
        prescribe(ready)
        # 4. Bought, label verified, sprayed two days ago: the day 2 check-in is due.
        done = case(Case.Status.VERIFIED, 6)
        confirm(done)
        order = Order.objects.create(
            prescription=prescribe(done), farmer=farmer, agrovet=mwangi, product=ridomil, unit_price_kes=1300,
            quantity=1, total_kes=1300, payment_method="pay_at_shop", status=Order.Status.COLLECTED,
            collected_at=now - timedelta(days=3),
        )  # fmt: skip
        Verification.objects.create(
            order=order, type="label_check", result="verified", actor=farmer, product=ridomil
        )
        RewardEntry.objects.create(
            farmer=farmer,
            reason=RewardEntry.Reason.VERIFIED_PURCHASE,
            points=10,
            source_ref=f"order:{order.id}",
        )
        followups.record_spray(farmer=farmer, case=done, sprayed_at=now - timedelta(days=2, hours=1))

        # Neighbours: 6 confirmed late blight cases this week (outbreak alert) and 23 reported outcomes
        # with Ridomil, 18 improved (local results on the prescription card).
        for i in range(23):
            neighbour = User.objects.create_user(username=f"demo-neighbour-{i}", password=None)
            c = Case.objects.create(
                farmer=neighbour, status=Case.Status.VERIFIED, ward="Chuka", latitude=lat, longitude=lng
            )
            FinalDiagnosis.objects.create(
                case=c,
                disease=late,
                confidence="high",
                confirmed_by=mwangi,
                ward="Chuka",
                latitude=lat,
                longitude=lng,
            )
            if i >= 6:
                FinalDiagnosis.objects.filter(case=c).update(created_at=now - timedelta(days=20))
            TreatmentOutcome.objects.create(
                case=c, farmer=neighbour, disease=late, product=ridomil, improved=i < 18, days_after_spraying=4 if i < 18 else None,
                ward="Chuka", latitude=lat, longitude=lng,
            )  # fmt: skip

        self.stdout.write(self.style.SUCCESS(f"Demo data created. Log in with {PHONE} and PIN {PIN}."))
