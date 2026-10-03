"""Nearby confirmed cases: the outbreak alert on Check Crop and "similar cases nearby" on a diagnosis.

Only agrovet-confirmed diagnoses count, never AI suggestions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.geo import haversine_km
from apps.products.models import Disease

from .models import FinalDiagnosis

# About 0.009 degrees of latitude per km; a box first, then the exact distance.
_DEGREES_PER_KM = 1 / 111.0


@dataclass(frozen=True)
class Outbreak:
    disease: Disease
    count: int
    ward: str  # where most of the cases are, for "near Chuka"


def _nearby(latitude, longitude, *, days: int, radius_km: float):
    since = timezone.now() - timedelta(days=days)
    box = radius_km * _DEGREES_PER_KM * 1.5  # generous for longitude away from the equator
    lat, lng = float(latitude), float(longitude)
    candidates = FinalDiagnosis.objects.filter(
        created_at__gte=since,
        latitude__range=(lat - box, lat + box),
        longitude__range=(lng - box, lng + box),
    ).select_related("disease")
    return [f for f in candidates if haversine_km(lat, lng, f.latitude, f.longitude) <= radius_km]


def nearby_outbreaks(latitude, longitude) -> list[Outbreak]:
    config = settings.OUTBREAK
    by_disease: dict = {}
    for final in _nearby(latitude, longitude, days=config["DAYS"], radius_km=config["RADIUS_KM"]):
        by_disease.setdefault(final.disease_id, []).append(final)
    outbreaks = [
        Outbreak(
            disease=finals[0].disease,
            count=len(finals),
            ward=Counter(f.ward for f in finals if f.ward).most_common(1)[0][0]
            if any(f.ward for f in finals)
            else "",
        )
        for finals in by_disease.values()
        if len(finals) >= config["MIN_CASES"]
    ]
    return sorted(outbreaks, key=lambda o: -o.count)


def similar_nearby(final: FinalDiagnosis, *, days: int = 30) -> int:
    """Other confirmed cases of the same disease near this one, recently."""
    if final.latitude is None or final.longitude is None:
        return 0
    return sum(
        1
        for f in _nearby(final.latitude, final.longitude, days=days, radius_km=settings.OUTBREAK["RADIUS_KM"])
        if f.disease_id == final.disease_id and f.pk != final.pk
    )
