"""Turn routes + forecasts into checkpoints, risk summaries and a recommendation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import geocode, hos, osrm, risk, weather
from .geo import downsample, interpolate, point_at

INTERVALS = (10, 25, 50)
HEAT_HOURS = 48
MAX_DEPARTURE_AHEAD = timedelta(days=5)
MAX_DEPARTURE_BEHIND = timedelta(hours=12)
MAP_POINTS = 700  # route line resolution sent to the browser
ROUTE_NAMES = ["Route A", "Route B", "Route C"]


class PlanError(ValueError):
    pass


def validate_inputs(weight_lb, interval_mi):
    if interval_mi not in INTERVALS:
        raise PlanError(f"Checkpoint interval must be one of {', '.join(map(str, INTERVALS))} miles.")
    if not 0 < weight_lb <= 200_000:
        raise PlanError("Load weight must be between 1 and 200,000 lb.")


def validate_departure(departure, now):
    if departure < now - MAX_DEPARTURE_BEHIND:
        raise PlanError("Departure is in the past. Pick a time from now up to 5 days ahead.")
    if departure > now + MAX_DEPARTURE_AHEAD:
        raise PlanError("Departure must be within the next 5 days (weather forecasts do not reach further).")


def checkpoint_miles(total_mi, interval_mi):
    miles = [float(m) for m in range(0, int(total_mi), interval_mi)]
    if total_mi - miles[-1] >= 1:
        miles.append(total_mi)
    else:
        miles[-1] = total_mi
    return miles


def build_checkpoints(route, interval_mi, departure):
    """Evenly spaced points along the route, each with the truck's estimated arrival time.

    The ETA comes from the routing API's per-segment travel times (slowed to truck speed, see
    osrm.py), so slow city stretches and fast interstates are timed correctly, plus the driver's
    required breaks and rests (hos.py). That is what lets us ask "what will the weather be when
    the truck actually gets here?".
    """
    points, cum_mi, cum_s = route["points"], route["cum_mi"], route["cum_s"]
    out = []
    for mile in checkpoint_miles(cum_mi[-1], interval_mi):
        lat, lon = point_at(points, cum_mi, mile)
        drive = interpolate(cum_mi, cum_s, mile)
        eta = departure + timedelta(seconds=hos.elapsed_s(drive))
        out.append({"mile": round(mile, 1), "lat": lat, "lon": lon, "eta": eta})
    return out


def build_stops(route, departure):
    """Where and when the driver must take a break or a rest on this route."""
    out = []
    for drive, kind, length in hos.stops(route["drive_s"]):
        mile = interpolate(route["cum_s"], route["cum_mi"], drive)
        lat, lon = point_at(route["points"], route["cum_mi"], mile)
        # Arrival at the stop: everything before it, but not the stop itself.
        start = departure + timedelta(seconds=hos.elapsed_s(drive))
        out.append(
            {
                "kind": kind,
                "mile": round(mile, 1),
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "start": start.isoformat(),
                "end": (start + timedelta(seconds=length)).isoformat(),
            }
        )
    return out


def _summarize(checkpoints):
    miles_by_level = [0.0] * len(risk.LEVELS)
    for a, b in zip(checkpoints, checkpoints[1:]):
        # A stretch takes the worse of its two end checkpoints (conservative).
        miles_by_level[max(a["level"], b["level"])] += b["mile"] - a["mile"]
    total = sum(miles_by_level) or 1.0
    avg = sum(level * miles for level, miles in enumerate(miles_by_level)) / total
    return {
        "miles_by_level": [round(m, 1) for m in miles_by_level],
        "severe_miles": round(sum(miles_by_level[risk.SEVERE :]), 1),
        "high_miles": round(miles_by_level[risk.HIGH], 1),
        "avg_risk": round(avg, 2),
        "max_level": max(c["level"] for c in checkpoints),
    }


def _rank_key(route):
    s = route["summary"]
    # Brief: fewest Severe miles, then fewest High miles, then lowest average risk, then shortest time.
    # A route containing a No Travel checkpoint is only chosen if every route has one.
    return (route["blocked"], s["severe_miles"], s["high_miles"], s["avg_risk"], route["duration_s"])


def _recommendation(routes, best):
    fastest = min(routes, key=lambda r: r["duration_s"])
    if all(r["blocked"] for r in routes):
        return (
            f"Every route crosses a No Travel zone at the forecast time. "
            f"{best['name']} is the least bad; consider delaying departure."
        )
    if best is fastest:
        if best["summary"]["severe_miles"] == 0 and best["summary"]["high_miles"] == 0:
            return f"{best['name']} is both the fastest and the calmest route: no High or Severe weather expected."
        return f"{best['name']} is the fastest route and also has the least dangerous weather of the three."
    extra_min = round((best["duration_s"] - fastest["duration_s"]) / 60)
    saved = fastest["summary"]["severe_miles"] - best["summary"]["severe_miles"]
    h, m = divmod(extra_min, 60)
    cost = f"{h} h {m} min" if h else f"{m} min"
    if saved > 0:
        return (
            f"{best['name']} costs {cost} more than {fastest['name']} but avoids {saved:.0f} miles of Severe weather."  # noqa: E501
        )
    if best["summary"]["high_miles"] < fastest["summary"]["high_miles"]:
        return f"{best['name']} costs {cost} more than {fastest['name']} but has fewer High-risk miles."
    return f"{best['name']} costs {cost} more than {fastest['name']} but has lower overall weather risk."


def plan_trip(origin_text, dest_text, departure, weight_lb, interval_mi, now=None):
    """Plan a trip. A naive `departure` means local clock time at the origin (what a driver types)."""
    now = now or datetime.now(timezone.utc)
    validate_inputs(weight_lb, interval_mi)

    with ThreadPoolExecutor(max_workers=2) as pool:
        origin, dest = pool.map(geocode.geocode, (origin_text, dest_text))
    with ThreadPoolExecutor(max_workers=2) as pool:
        routes_job = pool.submit(osrm.fetch_routes, origin, dest)
        tz_name = geocode.timezone_at(origin["lat"], origin["lon"])
        origin_tz = ZoneInfo(tz_name)
        departure = departure.replace(tzinfo=origin_tz) if departure.tzinfo is None else departure.astimezone(origin_tz)
        validate_departure(departure, now)
        raw_routes = routes_job.result()

    for route in raw_routes:
        route["checkpoints"] = build_checkpoints(route, interval_mi, departure)
    keys = [weather.key_for(c["lat"], c["lon"]) for r in raw_routes for c in r["checkpoints"]]
    forecasts = weather.fetch_forecasts(keys)

    routes = []
    for i, route in enumerate(raw_routes):
        checkpoints = []
        for c in route["checkpoints"]:
            forecast = forecasts[weather.key_for(c["lat"], c["lon"])]
            wind, rain, snow = forecast.at(c["eta"])
            assessed = risk.assess(wind, rain, snow, weight_lb)
            # Same place, but at departure + h hours: powers the 0-48 h heatmap slider.
            heat = [
                risk.assess(*forecast.at(departure + timedelta(hours=h)), weight_lb).level
                for h in range(HEAT_HOURS + 1)
            ]
            checkpoints.append(
                {
                    "mile": c["mile"],
                    "lat": round(c["lat"], 5),
                    "lon": round(c["lon"], 5),
                    "eta": c["eta"].isoformat(),
                    "wind_mph": round(wind, 1),
                    "rain_in_hr": round(rain, 3),
                    "snow_in_hr": round(snow, 3),
                    "level": assessed.level,
                    "risk": assessed.label,
                    "reasons": assessed.reasons,
                    "heat": heat,
                }
            )
        total_s = hos.elapsed_s(route["drive_s"])
        routes.append(
            {
                "id": f"route-{i + 1}",
                "name": ROUTE_NAMES[i],
                "distance_mi": round(route["distance_mi"], 1),
                "drive_s": round(route["drive_s"]),
                "duration_s": round(total_s),
                "arrival": (departure + timedelta(seconds=total_s)).isoformat(),
                "stops": build_stops(route, departure),
                "geometry": [[round(lat, 5), round(lon, 5)] for lat, lon in downsample(route["points"], MAP_POINTS)],
                "checkpoints": checkpoints,
                "summary": _summarize(checkpoints),
                "blocked": any(c["level"] == risk.NO_TRAVEL for c in checkpoints),
            }
        )

    best = min(routes, key=_rank_key)
    for rank, route in enumerate(sorted(routes, key=_rank_key), start=1):
        route["rank"] = rank
    return {
        "origin": origin,
        "destination": dest,
        "departure": departure.isoformat(),
        "timezone": tz_name,
        "weight_lb": weight_lb,
        "interval_mi": interval_mi,
        "levels": risk.LEVELS,
        "routes": routes,
        "weather_sources": sorted({f.source for f in forecasts.values()}),
        "recommended_id": best["id"],
        "recommendation": _recommendation(routes, best),
    }
