import math


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in km. Used until PostGIS is set up (Documentation §9.2)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (float(lat1), float(lon1), float(lat2), float(lon2)))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))
