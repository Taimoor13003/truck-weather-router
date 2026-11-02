import re
from functools import cache, lru_cache

import requests
from timezonefinder import TimezoneFinder

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "truck-weather-router/1.0 (assessment project)"}
_LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_PLACE_KEYS = ("city", "town", "village", "hamlet", "county")


class GeocodeError(ValueError):
    pass


def _label(item):
    """'Dallas, Texas' from Nominatim's address parts, falling back to the full display name."""
    address = item.get("address", {})
    place = next((address[k] for k in _PLACE_KEYS if k in address), None)
    state = address.get("state")
    if place and state:
        return f"{place}, {state}"
    return item.get("display_name", "")


def search(query, limit=5):
    resp = requests.get(
        NOMINATIM,
        params={"q": query, "format": "json", "limit": limit, "countrycodes": "us", "addressdetails": 1},
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return [{"lat": float(r["lat"]), "lon": float(r["lon"]), "label": _label(r)} for r in resp.json()]


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


@cache
def _tz_finder():
    return TimezoneFinder()  # offline polygon data, loaded once per process


def timezone_at(lat, lon):
    """IANA time zone (e.g. 'America/Chicago') for a point, resolved offline."""
    return _tz_finder().timezone_at(lat=lat, lng=lon) or "UTC"
