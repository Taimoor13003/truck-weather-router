# Truck Weather Router

A React + Django app that helps a truck driver pick the safest route. Enter an origin, destination, departure time and load weight. The app returns three route options, samples the forecast along each one at the time the truck will actually be there, scores the risk, and recommends a route. A heatmap with a 0 to 48 hour slider shows how conditions along the corridor evolve.

## How it works

1. **Geocoding**: Nominatim (OpenStreetMap) turns place names into coordinates.
2. **Routing**: the public OSRM server returns driving alternatives. If it returns fewer than three distinct roads, the backend asks for more by excluding motorways and by routing through sideways via-points, then drops anything that is the same road (average distance under 2 miles) or more than 70% slower than the fastest route.
3. **Checkpoints**: points are placed every 10, 25 or 50 miles (user's choice) along each route, plus start and end. Each gets an ETA.
4. **Weather**: Open-Meteo hourly forecasts (wind in mph, rain and snowfall in inches per hour) are fetched for all checkpoints in parallel batches and cached for 30 minutes. The reading used is the forecast hour nearest the truck's ETA.
5. **Risk**: the thresholds from the brief are applied to wind, rain and snow separately (the worst wins), then the load rules:
   - wind >= 55 mph: No Travel for any load
   - wind 45 to 54 mph with a load over 30,000 lb: No Travel
   - wind 35 to 44 mph with a load over 40,000 lb: Severe
6. **Recommendation**: routes are ranked by, in order: no No Travel checkpoint, fewest Severe miles, fewest High miles, lowest distance-weighted average risk, shortest travel time. The UI explains the trade-off in one sentence (for example "Route C costs 2 h 55 min more than Route A but avoids 40 miles of Severe weather").
7. **Heatmap**: for each checkpoint the backend also scores the weather at departure + 0, 1, ... 48 hours. The slider recolours a canvas heat layer from that data instantly, with no further requests. Colour means risk level (green, yellow, orange, red, purple), not point density.

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

Tests (risk thresholds, load rules, ranking, geometry, validation):

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

- **Arrival times assume constant average speed.** ETA at a checkpoint is the routing API's total duration scaled by distance. OSRM durations are for cars and ignore traffic, rest stops and truck speed limits, so real arrivals will be later. A real product would use a truck-specific router.
- **Forecast horizon.** Open-Meteo forecasts reach about 10 days, so departures are limited to the next 5 days (so the 48 h slider stays inside the forecast).
- **Wind is sustained 10 m wind, not gusts.** The brief's table speaks of wind speed, so gusts are not used.
- **Snow is snowfall in inches per hour** (not liquid equivalent), matching the brief's units.
- **Boundaries.** Where the brief's ranges touch (for example rain exactly 0.25), the higher level applies. No Travel for rain and snow is strictly greater than 1.00 and 3.0.
- **A stretch takes the worse of its two end checkpoints** when miles per risk level are counted, which is conservative.
- **Public free services.** OSRM and Nominatim are shared demo servers with usage limits. A plan takes roughly 10 to 25 seconds, mostly waiting on them.
- US locations only (geocoding is restricted to the US).
