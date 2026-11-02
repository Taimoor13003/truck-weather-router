import re
from functools import lru_cache

import requests

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "truck-weather-router/1.0 (assessment project)"}
_LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class GeocodeError(ValueError):
    pass


def _label(item):
    parts = item.get("display_name", "").split(", ")
    # "Dallas, Dallas County, Texas, United States" -> "Dallas, Texas"
    return f"{parts[0]}, {parts[-3]}" if len(parts) >= 4 else item.get("display_name", "")


def search(query, limit=5):
    resp = requests.get(
        NOMINATIM,
        params={"q": query, "format": "json", "limit": limit, "countrycodes": "us"},
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return [
        {"lat": float(r["lat"]), "lon": float(r["lon"]), "label": _label(r)}
        for r in resp.json()
    ]


@lru_cache(maxsize=256)
def geocode(query):
    """Resolve free text (or a literal 'lat, lon') to one location."""
    match = _LATLON.match(query)
    if match:
        lat, lon = float(match.group(1)), float(match.group(2))
        return {"lat": lat, "lon": lon, "label": f"{lat:.4f}, {lon:.4f}"}
    results = search(query, limit=1)
    if not results:
        raise GeocodeError(f"Could not find a US location for '{query}'.")
    return results[0]
