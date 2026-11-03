import json
import logging
import re
from functools import cache, lru_cache
from pathlib import Path

import requests
from timezonefinder import TimezoneFinder

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "truck-weather-router/1.0 (assessment project)"}
_LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_PLACE_KEYS = ("city", "town", "village", "hamlet", "county")
# US places with 5,000+ people (GeoNames, CC BY 4.0), used when Nominatim refuses or is down.
# Nominatim rate-limits shared cloud IPs, so the hosted app cannot rely on it alone.
OFFLINE_CITIES = Path(__file__).resolve().parent.parent / "data" / "us_cities.json"
log = logging.getLogger(__name__)


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


@cache
def _offline_places():
    data = json.loads(OFFLINE_CITIES.read_text())
    return data["states"], data["cities"]  # cities: [name, state code, lat, lon, population], largest first


def search_offline(query, limit=5):
    """'Fargo, ND', 'Fargo, North Dakota' or 'Fargo' -> matching cities, most populous first."""
    states, cities = _offline_places()
    name, _, state = (part.strip().lower() for part in query.partition(","))
    codes = {code for code, full in states.items() if state in (code.lower(), full.lower())} if state else None
    if state and not codes:  # a partly typed state name, e.g. 'Fargo, North'
        codes = {code for code, full in states.items() if full.lower().startswith(state)}
    out = []
    for city, code, lat, lon, _pop in cities:
        if city.lower().startswith(name) and (codes is None or code in codes):
            out.append({"lat": lat, "lon": lon, "label": f"{city}, {states[code]}"})
            if len(out) == limit:
                break
    return out


def search(query, limit=5):
    """Nominatim first; the offline city list if Nominatim fails."""
    try:
        resp = requests.get(
            NOMINATIM,
            params={"q": query, "format": "json", "limit": limit, "countrycodes": "us", "addressdetails": 1},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        return [{"lat": float(r["lat"]), "lon": float(r["lon"]), "label": _label(r)} for r in resp.json()]
    except requests.RequestException as exc:
        results = search_offline(query, limit)
        log.warning("Nominatim failed (%s); %d offline matches for %r", exc, len(results), query)
        if not results:
            raise
        return results


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
