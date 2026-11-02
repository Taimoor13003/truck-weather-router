"""Hourly forecasts from Open-Meteo (free, no API key). Wind in mph, precipitation in inches."""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

API = "https://api.open-meteo.com/v1/forecast"
BATCH = 40  # locations per request
PAST_DAYS = 1
FORECAST_DAYS = 10
CACHE_TTL_S = 30 * 60
_cache = {}


class WeatherError(RuntimeError):
    pass


def key_for(lat, lon):
    """Forecast grid cell. Open-Meteo resolution is ~10 km, so 2 decimals loses nothing."""
    return (round(lat, 2), round(lon, 2))


class Forecast:
    def __init__(self, start, wind, rain, snow):
        self.start, self.wind, self.rain, self.snow = start, wind, rain, snow

    def at(self, when):
        """(wind mph, rain in/hr, snow in/hr) for the hour nearest `when`."""
        idx = round((when - self.start).total_seconds() / 3600)
        idx = min(max(idx, 0), len(self.wind) - 1)
        return self.wind[idx], self.rain[idx], self.snow[idx]


def _parse(entry):
    h = entry["hourly"]
    start = datetime.fromisoformat(h["time"][0]).replace(tzinfo=timezone.utc)
    clean = lambda values: [v or 0.0 for v in values]
    # Liquid precipitation is rain plus showers; snowfall is reported separately.
    rain = [r + s for r, s in zip(clean(h["rain"]), clean(h["showers"]))]
    return Forecast(start, clean(h["wind_speed_10m"]), rain, clean(h["snowfall"]))


def _fetch_batch(keys):
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
    for attempt in range(4):
        resp = requests.get(API, params=params, timeout=40)
        if resp.status_code == 200:
            data = resp.json()
            entries = data if isinstance(data, list) else [data]
            return dict(zip(keys, (_parse(e) for e in entries)))
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(1.5 * (attempt + 1))
    raise WeatherError("The weather service is unavailable right now. Please try again.")


def fetch_forecasts(keys):
    """Forecast for every (lat, lon) grid key, fetched in parallel batches and cached briefly."""
    now = time.time()
    result = {k: _cache[k][1] for k in keys if k in _cache and now - _cache[k][0] < CACHE_TTL_S}
    missing = [k for k in dict.fromkeys(keys) if k not in result]
    batches = [missing[i : i + BATCH] for i in range(0, len(missing), BATCH)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for fetched in pool.map(_fetch_batch, batches):
            for k, forecast in fetched.items():
                _cache[k] = (now, forecast)
                result[k] = forecast
    return result
