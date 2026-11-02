# Truck Weather Router

A React + Django app that helps a truck driver pick the safest route. Enter an origin, destination, departure time and load weight. The app returns three route options, samples the forecast along each one at the time the truck will actually be there, scores the risk, and recommends a route. A heatmap with a 0 to 48 hour slider shows how conditions along the corridor evolve.

## How it works

1. **Geocoding**: Nominatim (OpenStreetMap) turns place names into coordinates.
2. **Routing**: the public OSRM server returns driving alternatives. If it returns fewer than three distinct roads, the backend asks for more by excluding motorways and by routing through sideways via-points, then drops anything that is the same road (average distance under 2 miles) or more than 70% slower than the fastest route.
3. **Truck timing**: OSRM returns travel time for every road segment. Each segment is slowed to at most 65 mph (the usual US truck limit), so ETAs follow the real road: slow through cities, fast on interstates. On top of that the driver's US Hours-of-Service rules are applied: a 30-minute break after 8 hours of driving and a 10-hour rest after 11 hours. Those stops push every later ETA back and are shown on the map and in the route details.
4. **Checkpoints**: points are placed every 10, 25 or 50 miles (user's choice) along each route, plus start and end. Each gets the ETA from step 3.
5. **Weather**: Open-Meteo hourly forecasts (wind in mph, rain and snowfall in inches per hour) are fetched for all checkpoints in parallel batches and cached for 30 minutes. Values are interpolated between forecast hours to the exact ETA.
6. **Risk**: the thresholds from the brief are applied to wind, rain and snow separately (the worst wins), then the load rules:
   - wind >= 55 mph: No Travel for any load
   - wind 45 to 54 mph with a load over 30,000 lb: No Travel
   - wind 35 to 44 mph with a load over 40,000 lb: Severe
7. **Recommendation**: routes are ranked by, in order: no No Travel checkpoint, fewest Severe miles, fewest High miles, lowest distance-weighted average risk, shortest door-to-door time. The UI explains the trade-off in one sentence (for example "Route C costs 2 h 55 min more than Route A but avoids 40 miles of Severe weather").
8. **Heatmap**: for each checkpoint the backend also scores the weather at departure + 0, 1, ... 48 hours. The slider recolours a canvas heat layer from that data instantly, with no further requests. Colour means risk level (green, yellow, orange, red, purple), not point density.

## Run locally

Backend (Python 3.11+):

```bash
cd backend
pip install -r requirements.txt
DJANGO_DEBUG=1 python manage.py runserver 127.0.0.1:8000
```

Frontend (Node 20+), in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173. The Vite dev server proxies `/api` to Django. No API keys are needed.

Tests (risk thresholds, load rules, ranking, truck speed, Hours of Service, forecast interpolation, geometry, validation):

```bash
cd backend
python manage.py test
```

## API

| Endpoint | Description |
|---|---|
| `POST /api/plan` | body: `origin`, `destination`, `departure` (ISO time), `weight_lb`, `interval_mi` (10, 25 or 50). Returns three routes with checkpoints, risk summaries, per-hour heat data and the recommendation. |
| `GET /api/places?q=` | place-name suggestions for the form |
| `GET /api/health` | liveness check |

## Deploy

`render.yaml` is a Render blueprint. It builds the React app, installs the Django app and serves both from one gunicorn service (WhiteNoise serves `frontend/dist`).

## Assumptions and limits

- **Routing uses a car road network.** The free public OSRM server has no truck profile, so low bridges, weight-restricted roads and hazmat rules are not considered, and live traffic is not included. Truck speed (65 mph cap) and driver breaks are modelled on top. A production version would swap in a commercial truck router; only `osrm.py` would change.
- **Hours of Service is simplified** to the 11-hour driving limit, 10-hour rest and 30-minute break, starting from a fresh driver. The 14-hour on-duty window and weekly limits are not modelled. While the truck is parked for a rest, the weather at the parking spot is not scored (the truck is not driving).
- **Forecast horizon.** Open-Meteo forecasts reach about 10 days, so departures are limited to the next 5 days (so the 48 h slider stays inside the forecast).
- **Wind is sustained 10 m wind, not gusts.** The brief's table speaks of wind speed, so gusts are not used.
- **Snow is snowfall in inches per hour** (not liquid equivalent), matching the brief's units.
- **Boundaries.** Where the brief's ranges touch (for example rain exactly 0.25), the higher level applies. No Travel for rain and snow is strictly greater than 1.00 and 3.0.
- **A stretch takes the worse of its two end checkpoints** when miles per risk level are counted, which is conservative.
- **Public free services.** OSRM and Nominatim are shared demo servers with usage limits. A plan takes about 10 seconds, mostly waiting on them; all calls that can run in parallel do.
- US locations only (geocoding is restricted to the US).
