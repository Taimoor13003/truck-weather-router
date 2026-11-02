"""Route alternatives from the public OSRM server (no API key, no routing engine of our own)."""
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from .geo import downsample, haversine_mi, mean_distance_to_line

OSRM = "https://router.project-osrm.org/route/v1/driving"
WANT_ROUTES = 3
SAME_ROUTE_MILES = 2.0  # routes closer than this on average are the same road
MAX_SLOWDOWN = 1.7  # discard detours more than 70% slower than the fastest route


class RoutingError(RuntimeError):
    pass


def _request(coords, alternatives=False, exclude=None):
    path = ";".join(f"{lon},{lat}" for lat, lon in coords)
    params = {"overview": "full", "geometries": "geojson", "alternatives": "3" if alternatives else "false"}
    if exclude:
        params["exclude"] = exclude
    for attempt in range(3):
        try:
            resp = requests.get(f"{OSRM}/{path}", params=params, timeout=40)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "Ok":
                    return [
                        {
                            "distance_mi": r["distance"] / 1609.344,
                            "duration_s": r["duration"],
                            "points": [(lat, lon) for lon, lat in r["geometry"]["coordinates"]],
                        }
                        for r in data["routes"]
                    ]
                if data.get("code") == "NoRoute":
                    return []
        except requests.RequestException:
            pass
        time.sleep(1 + attempt)
    return []


def _is_new(candidate, kept):
    sample = downsample(candidate["points"], 25)
    return all(mean_distance_to_line(sample, downsample(k["points"], 300)) > SAME_ROUTE_MILES for k in kept)


def _detour_waypoints(origin, dest):
    """Via-points offset sideways from the midpoint, used to force genuinely different roads."""
    mid_lat, mid_lon = (origin[0] + dest[0]) / 2, (origin[1] + dest[1]) / 2
    d_lat, d_lon = dest[0] - origin[0], dest[1] - origin[1]
    for scale in (0.08, 0.16, 0.26):
        for sign in (1, -1):
            yield (mid_lat - sign * d_lon * scale, mid_lon + sign * d_lat * scale)


def fetch_routes(origin, dest):
    """Up to three distinct driving routes, fastest first."""
    origin_pt, dest_pt = (origin["lat"], origin["lon"]), (dest["lat"], dest["lon"])
    if haversine_mi(origin_pt, dest_pt) < 1:
        raise RoutingError("Origin and destination are the same place.")

    found = _request([origin_pt, dest_pt], alternatives=True)
    if not found:
        raise RoutingError("No drivable route between those locations.")
    kept = [found[0]]
    for cand in found[1:]:
        if len(kept) < WANT_ROUTES and _is_new(cand, kept):
            kept.append(cand)

    if len(kept) < WANT_ROUTES:
        fastest = kept[0]["duration_s"]
        attempts = [([origin_pt, dest_pt], "motorway")]
        attempts += [([origin_pt, via, dest_pt], None) for via in _detour_waypoints(origin_pt, dest_pt)]
        # Ask for every candidate at once, then take them in preference order.
        with ThreadPoolExecutor(max_workers=4) as pool:
            candidates = list(pool.map(lambda a: _request(a[0], exclude=a[1])[:1], attempts))
        for cand in (c for found_one in candidates for c in found_one):
            if len(kept) < WANT_ROUTES and cand["duration_s"] <= fastest * MAX_SLOWDOWN and _is_new(cand, kept):
                kept.append(cand)

    kept.sort(key=lambda r: r["duration_s"])
    return kept
