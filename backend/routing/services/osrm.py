"""Route alternatives from the public OSRM server (no API key, no routing engine of our own)."""
import time
from concurrent.futures import ThreadPoolExecutor
from itertools import accumulate

import requests

from .geo import downsample, haversine_mi, mean_distance_to_line

OSRM = "https://router.project-osrm.org/route/v1/driving"
WANT_ROUTES = 3
SAME_ROUTE_MILES = 2.0  # routes closer than this on average are the same road
MAX_SLOWDOWN = 1.6  # discard detours more than 60% slower than the fastest route
METERS_PER_MILE = 1609.344
# OSRM's public server only has a car profile. Heavy trucks are limited to 65 mph in most US
# states (and by fleet governors), so every road segment is slowed to at most this speed.
TRUCK_MAX_MPH = 65
TRUCK_MAX_MPS = TRUCK_MAX_MPH * METERS_PER_MILE / 3600


class RoutingError(RuntimeError):
    pass


def parse_route(r):
    """One OSRM route -> points plus cumulative miles and truck driving seconds at every point."""
    points = [(lat, lon) for lon, lat in r["geometry"]["coordinates"]]
    seg_m, seg_s = [], []
    for leg in r["legs"]:
        annotation = leg.get("annotation", {})
        seg_m += annotation.get("distance", [])
        seg_s += annotation.get("duration", [])
    if len(seg_m) != len(points) - 1 or len(seg_s) != len(seg_m):
        # No usable per-segment data: spread the total duration evenly over the distance.
        seg_m = [haversine_mi(a, b) * METERS_PER_MILE for a, b in zip(points, points[1:])]
        total_m = sum(seg_m) or 1.0
        seg_s = [r["duration"] * m / total_m for m in seg_m]
    truck_s = [max(s, m / TRUCK_MAX_MPS) for m, s in zip(seg_m, seg_s)]
    cum_mi = [0.0, *accumulate(m / METERS_PER_MILE for m in seg_m)]
    cum_s = [0.0, *accumulate(truck_s)]
    return {"points": points, "cum_mi": cum_mi, "cum_s": cum_s, "distance_mi": cum_mi[-1], "drive_s": cum_s[-1]}


def _request(coords, alternatives=False):
    path = ";".join(f"{lon},{lat}" for lat, lon in coords)
    params = {
        "overview": "full",
        "geometries": "geojson",
        "annotations": "distance,duration",
        "alternatives": "3" if alternatives else "false",
    }
    for attempt in range(3):
        try:
            resp = requests.get(f"{OSRM}/{path}", params=params, timeout=40)
            if resp.status_code == 200 and resp.json().get("code") == "Ok":
                return [parse_route(r) for r in resp.json()["routes"]]
            # Only rate limits and server errors are worth retrying; NoRoute etc. are final.
            if resp.status_code != 429 and resp.status_code < 500:
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
    """Up to three distinct driving routes, fastest (for a truck) first."""
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
        fastest = kept[0]["drive_s"]
        attempts = [[origin_pt, via, dest_pt] for via in _detour_waypoints(origin_pt, dest_pt)]
        # Ask for every candidate at once, then take them in preference order (smallest detour first).
        with ThreadPoolExecutor(max_workers=len(attempts)) as pool:
            candidates = list(pool.map(lambda coords: _request(coords)[:1], attempts))
        for cand in (c for found_one in candidates for c in found_one):
            if len(kept) < WANT_ROUTES and cand["drive_s"] <= fastest * MAX_SLOWDOWN and _is_new(cand, kept):
                kept.append(cand)

    kept.sort(key=lambda r: r["drive_s"])
    return kept
