import json
from datetime import datetime, timezone

import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .services import geocode, osrm, planner, weather


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def places(request):
    query = request.GET.get("q", "").strip()
    if len(query) < 3:
        return JsonResponse({"results": []})
    try:
        return JsonResponse({"results": geocode.search(query)})
    except requests.RequestException:
        return _error("Place search is unavailable right now.", 502)


@csrf_exempt
@require_POST
def plan(request):
    try:
        body = json.loads(request.body)
        origin, dest = str(body["origin"]).strip(), str(body["destination"]).strip()
        weight_lb = float(body["weight_lb"])
        interval_mi = int(body.get("interval_mi", 25))
        departure = datetime.fromisoformat(str(body["departure"]).replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError):
        return _error("Send origin, destination, departure (ISO time), weight_lb and optionally interval_mi.")
    if not origin or not dest:
        return _error("Origin and destination are required.")
    if departure.tzinfo is None:
        departure = departure.replace(tzinfo=timezone.utc)

    try:
        result = planner.plan_trip(origin, dest, departure.astimezone(timezone.utc), weight_lb, interval_mi)
    except (planner.PlanError, geocode.GeocodeError) as exc:
        return _error(str(exc))
    except (osrm.RoutingError, weather.WeatherError) as exc:
        return _error(str(exc), 502)
    except requests.RequestException:
        return _error("A map or weather service could not be reached. Please try again.", 502)
    return JsonResponse(result)
