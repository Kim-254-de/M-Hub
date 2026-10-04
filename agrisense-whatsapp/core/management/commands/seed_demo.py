"""python manage.py seed_demo --agrovet-phone 2547XXXXXXXX

Creates verified demo agrovets and products so the buy flow has something to show.
Product names are generic (active ingredient) — real agrovets should replace them.
"""
from django.core.management.base import BaseCommand

from core.models import Agrovet, Product

AGROVETS = [
    ("Chuka Farmers Agrovet", "Tharaka-Nithi", "Chuka", "Next to Chuka main market"),
    ("Gatunga Agro Supplies", "Tharaka-Nithi", "Gatunga", "Gatunga shopping centre"),
    ("Nakuru Green Agrovet", "Nakuru", "Nakuru Town", "Kenyatta Avenue, near the bus stage"),
    ("Kiambu Shamba Supplies", "Kiambu", "Kiambu Town", "Opposite Kiambu county offices"),
]

# PCPB numbers below are DEMO values for the simulator, not real registrations.
# Replace with real register entries before showing real farmers.
PCPB = {
    "Metalaxyl + Mancozeb fungicide": "PCPB (CR) 0856",
    "Mancozeb fungicide": "PCPB (CR) 1201",
    "Copper fungicide": "PCPB (CR) 0734",
    "Emamectin benzoate insecticide": "PCPB (CR) 1489",
    "Sulphur fungicide": "PCPB (CR) 0612",
    "Imidacloprid insecticide": "PCPB (CR) 1133",
}

PRODUCTS = [
    # name, ingredient, pack, price, discount, keywords, crops, usage
    ("Metalaxyl + Mancozeb fungicide", "Metalaxyl 4% + Mancozeb 64% WP", "50 g", 380, 10,
     "late blight, blight, downy mildew", "tomato, potato, kale, cabbage",
     "Mix 50 g in 20 L of water. Spray every 7–10 days. Wear gloves and a mask."),
    ("Mancozeb fungicide", "Mancozeb 80% WP", "100 g", 250, 5,
     "early blight, leaf spot, blight, anthracnose", "",
     "Mix 40–50 g in 20 L of water. Spray every 7 days in wet weather."),
    ("Copper fungicide", "Copper oxychloride 50% WP", "100 g", 300, 10,
     "rust, bean rust, coffee leaf rust, coffee berry disease, bacterial", "beans, coffee, tomato, avocado",
     "Mix 50 g in 20 L of water. Do not spray in strong sun."),
    ("Emamectin benzoate insecticide", "Emamectin benzoate 5% WG", "25 g", 450, 10,
     "fall armyworm, armyworm, stem borer, caterpillar", "maize, cabbage, kale, tomato",
     "Mix 5 g in 20 L of water. Spray into the maize funnel early morning or evening."),
    ("Sulphur fungicide", "Sulphur 80% WG", "100 g", 220, 0,
     "powdery mildew, mildew", "",
     "Mix 40 g in 20 L of water. Avoid spraying above 30°C."),
    ("Imidacloprid insecticide", "Imidacloprid 200 SL", "50 ml", 350, 5,
     "aphid, whitefly, thrips, mosaic", "",
     "Mix 10 ml in 20 L of water. Controls the insects that spread viruses."),
]


class Command(BaseCommand):
    help = "Seed verified demo agrovets and products."

    def add_arguments(self, parser):
        parser.add_argument("--agrovet-phone", default="254700000000",
                            help="Your own WhatsApp number (2547...) so you receive agrovet review requests.")
        parser.add_argument("--county", default="", help="Put the first demo agrovet in this county.")

    def handle(self, *args, **opts):
        for i, (name, county, town, hint) in enumerate(AGROVETS):
            if i == 0 and opts["county"]:
                county = opts["county"]
            agrovet, _ = Agrovet.objects.update_or_create(
                name=name,
                defaults={"county": county, "town": town, "location_hint": hint, "is_verified": True,
                          "phone": opts["agrovet_phone"] if i == 0 else f"25470000000{i}"},
            )
            for j, (pname, ing, pack, price, disc, kw, crops, usage) in enumerate(PRODUCTS):
                Product.objects.update_or_create(
                    agrovet=agrovet, name=pname,
                    defaults={"pcpb_reg_no": PCPB[pname], "active_ingredient": ing, "pack_size": pack,
                              "price": price + i * 10,
                              "farmer_discount_pct": disc, "target_keywords": kw, "crops": crops,
                              "usage_note": usage, "in_stock": True},
                )
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(AGROVETS)} agrovets and {len(PRODUCTS)} products each. "
            f"First agrovet phone: {opts['agrovet_phone']}"
        ))
