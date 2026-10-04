"""Load the diseases the service covers: tomato late blight and early blight.

Idempotent: an existing row (matched by name, any case) keeps admin edits and only gets
missing values filled in. Run once per environment: ``python manage.py seed_diseases``.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.products.models import Disease

DISEASES = [
    {
        "name": "Late blight",
        "scientific_name": "Phytophthora infestans",
        # Kindwise crop.health suggestion id.
        "provider_ids": ["b9ec757fefb92520"],
        "local_names": {"sw": "Baa chelewa"},
        "safe_actions": {
            "en": [
                "Remove and bury every leaf with dark, water-soaked patches today.",
                "Water at the base of the plant in the morning, not over the leaves.",
                "Keep away from the plot when leaves are wet so you do not spread it.",
            ],
            "sw": [
                "Ondoa na ufukie kila jani lenye madoa meusi yenye maji leo.",
                "Mwagilia kwenye shina asubuhi, si juu ya majani.",
                "Usiingie shambani majani yakiwa na maji ili usieneze ugonjwa.",
            ],
        },
    },
    {
        "name": "Early blight",
        "scientific_name": "Alternaria solani",
        "provider_ids": [],
        "local_names": {"sw": "Baa mapema"},
        "safe_actions": {
            "en": [
                "Pick off the lower leaves with brown rings and bury them away from the farm.",
                "Mulch around the plants so soil does not splash onto the leaves.",
                "Give the plants space and stake them so air can move through.",
            ],
            "sw": [
                "Ondoa majani ya chini yenye duara za kahawia na uyafukie mbali na shamba.",
                "Weka matandazo kuzunguka mimea ili udongo usirukie majani.",
                "Acha nafasi kati ya mimea na uifunge kwenye miti ili hewa ipite.",
            ],
        },
    },
]


class Command(BaseCommand):
    help = "Load tomato late blight and early blight into the disease catalogue."

    @transaction.atomic
    def handle(self, *args, **options):
        for spec in DISEASES:
            disease = Disease.objects.filter(name__iexact=spec["name"]).first()
            if disease is None:
                Disease.objects.create(**spec)
                self.stdout.write(f"Added {spec['name']}")
                continue
            changed = []
            for field, value in spec.items():
                if field != "name" and not getattr(disease, field):
                    setattr(disease, field, value)
                    changed.append(field)
            if changed:
                disease.save(update_fields=[*changed, "updated_at"])
            self.stdout.write(f"{spec['name']}: {'filled ' + ', '.join(changed) if changed else 'unchanged'}")
