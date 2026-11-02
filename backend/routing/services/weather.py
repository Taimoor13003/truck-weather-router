"""Hourly forecasts. Wind in mph, rain and snowfall in inches per hour.

Primary source: Open-Meteo (free, no key, many locations per request).
Fallback: MET Norway (free, no key, one location per request), used for any locations Open-Meteo
cannot serve, so the app keeps working when the primary service is overloaded.
"""

import time
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from .geo import interpolate

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
MET_NORWAY = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
MET_HEADERS = {"User-Agent": "truck-weather-router/1.0 (assessment project)"}  # MET requires an identifying UA
BATCH = 40  # Open-Meteo locations per request
PAST_DAYS = 1
FORECAST_DAYS = 10
CACHE_TTL_S = 30 * 60
MPS_TO_MPH = 2.23694
MM_TO_IN = 1 / 25.4
SNOW_TO_LIQUID = 10  # common 10:1 ratio, used only when the source gives no separate snowfall
_RETRYABLE = (429, 500, 502, 503, 504)
_cache = {}


class WeatherError(RuntimeError):
    pass


def key_for(lat, lon):
    """Forecast grid cell. Model resolution is ~10 km, so 2 decimals loses nothing."""
    return (round(lat, 2), round(lon, 2))


class Forecast:
    """Hourly series starting at `start` (UTC)."""

    def __init__(self, start, wind, rain, snow, source="Open-Meteo"):
        self.start, self.wind, self.rain, self.snow, self.source = start, wind, rain, snow, source

    def at(self, when):
        """(wind mph, rain in/hr, snow in/hr) at `when`, linearly interpolated between forecast hours."""
        pos = (when - self.start).total_seconds() / 3600
        pos = min(max(pos, 0.0), len(self.wind) - 1.0)
        lo = int(pos)
        hi = min(lo + 1, len(self.wind) - 1)
        t = pos - lo
        return tuple(series[lo] + (series[hi] - series[lo]) * t for series in (self.wind, self.rain, self.snow))


def _get(url, params, headers=None, attempts=2):
    """GET with a short retry on rate limits / server errors. Returns the JSON body or None."""
    for attempt in range(attempts):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
        except requests.RequestException:
            resp = None
        if resp is not None and resp.status_code == 200:
            return resp.json()
        if resp is not None and resp.status_code not in _RETRYABLE:
            return None
        if attempt + 1 < attempts:
            time.sleep(1 + attempt)
    return None


# --- Open-Meteo -----------------------------------------------------------------------------


def _clean(values):
    """Open-Meteo uses null for missing hours; treat them as calm/dry."""
    return [v or 0.0 for v in values]


def _parse_open_meteo(entry):
    h = entry["hourly"]
    start = datetime.fromisoformat(h["time"][0]).replace(tzinfo=timezone.utc)
    # Liquid precipitation is rain plus showers; snowfall is reported separately.
    rain = [r + s for r, s in zip(_clean(h["rain"]), _clean(h["showers"]))]
    return Forecast(start, _clean(h["wind_speed_10m"]), rain, _clean(h["snowfall"]))


def _fetch_open_meteo(keys):
    params = {
        "latitude": ",".join(str(k[0]) for k in keys),
        "longitude": ",".join(str(k[1]) for k in keys),
        "hourly": "wind_speed_10m,rain,showers,snowfall",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "UTC",
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
    }
    data = _get(OPEN_METEO, params)
    if data is None:
        return {}
    entries = data if isinstance(data, list) else [data]
    return dict(zip(keys, (_parse_open_meteo(e) for e in entries)))


# --- MET Norway (fallback) ------------------------------------------------------------------


def parse_met(body):
    """MET's series is hourly for ~2.5 days, then 6-hourly; resample it to a regular hourly series."""
    series = body["properties"]["timeseries"]
    times = [datetime.fromisoformat(s["time"].replace("Z", "+00:00")) for s in series]
    start = times[0]
    xs = [(t - start).total_seconds() / 3600 for t in times]
    wind = [s["data"]["instant"]["details"].get("wind_speed", 0.0) * MPS_TO_MPH for s in series]
    temp = [s["data"]["instant"]["details"].get("air_temperature", 10.0) for s in series]
    rate_mm = []  # precipitation rate (mm/hr) valid from each timestamp until the next one
    for s in series:
        if "next_1_hours" in s["data"]:
            rate_mm.append(s["data"]["next_1_hours"]["details"].get("precipitation_amount", 0.0))
        elif "next_6_hours" in s["data"]:
            rate_mm.append(s["data"]["next_6_hours"]["details"].get("precipitation_amount", 0.0) / 6)
        else:
            rate_mm.append(0.0)

    hourly_wind, rain, snow = [], [], []
    for h in range(int(xs[-1]) + 1):
        hourly_wind.append(interpolate(xs, wind, h))
        i = bisect_right(xs, h) - 1
        liquid_in = rate_mm[i] * MM_TO_IN
        # MET gives no snowfall field: at or below freezing, precipitation falls as snow.
        if temp[i] <= 0:
            rain.append(0.0)
            snow.append(liquid_in * SNOW_TO_LIQUID)
        else:
            rain.append(liquid_in)
            snow.append(0.0)
    return Forecast(start, hourly_wind, rain, snow, source="MET Norway")


def _fetch_met(key):
    body = _get(MET_NORWAY, {"lat": key[0], "lon": key[1]}, headers=MET_HEADERS)
    return parse_met(body) if body else None


# --- public ---------------------------------------------------------------------------------


def fetch_forecasts(keys):
    """Forecast for every (lat, lon) grid key: cached, then Open-Meteo in batches, then MET Norway."""
    now = time.time()
    result = {k: _cache[k][1] for k in keys if k in _cache and now - _cache[k][0] < CACHE_TTL_S}
    missing = [k for k in dict.fromkeys(keys) if k not in result]

    batches = [missing[i : i + BATCH] for i in range(0, len(missing), BATCH)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for fetched in pool.map(_fetch_open_meteo, batches):
            result.update(fetched)

    still_missing = [k for k in missing if k not in result]
    if still_missing:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for k, forecast in zip(still_missing, pool.map(_fetch_met, still_missing)):
                if forecast:
                    result[k] = forecast
    if any(k not in result for k in missing):
        raise WeatherError("The weather services are unavailable right now. Please try again in a minute.")

    for k in missing:
        _cache[k] = (now, result[k])
    return result
