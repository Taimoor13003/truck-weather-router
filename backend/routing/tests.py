from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import requests
from django.test import SimpleTestCase

from .services import geocode, hos, osrm, planner, risk, weather
from .services.geo import cumulative_miles, haversine_mi, point_at


class ClassifyTests(SimpleTestCase):
    def test_wind_bands(self):
        cases = {10: 0, 24.9: 0, 25: 1, 34: 1, 35: 2, 44: 2, 45: 3, 54: 3, 55: 4, 80: 4}
        for mph, level in cases.items():
            self.assertEqual(risk.classify("wind", mph), level, f"wind {mph}")

    def test_rain_bands(self):
        cases = {0.05: 0, 0.10: 1, 0.20: 1, 0.25: 2, 0.49: 2, 0.50: 3, 1.00: 3, 1.01: 4}
        for rate, level in cases.items():
            self.assertEqual(risk.classify("rain", rate), level, f"rain {rate}")

    def test_snow_bands(self):
        cases = {0.2: 0, 0.5: 1, 1.0: 2, 2.0: 3, 3.0: 3, 3.1: 4}
        for rate, level in cases.items():
            self.assertEqual(risk.classify("snow", rate), level, f"snow {rate}")


class LoadRuleTests(SimpleTestCase):
    def test_worst_condition_wins(self):
        self.assertEqual(risk.assess(10, 0.3, 0.6, 10_000).level, risk.HIGH)

    def test_very_high_wind_is_no_travel_for_any_load(self):
        self.assertEqual(risk.assess(55, 0, 0, 1_000).level, risk.NO_TRAVEL)

    def test_heavy_load_in_45_to_54_wind_is_no_travel(self):
        self.assertEqual(risk.assess(50, 0, 0, 30_001).level, risk.NO_TRAVEL)
        self.assertEqual(risk.assess(50, 0, 0, 30_000).level, risk.SEVERE)

    def test_very_heavy_load_in_35_to_44_wind_is_severe(self):
        self.assertEqual(risk.assess(40, 0, 0, 40_001).level, risk.SEVERE)
        self.assertEqual(risk.assess(40, 0, 0, 40_000).level, risk.HIGH)

    def test_calm_weather_is_low(self):
        result = risk.assess(5, 0, 0, 80_000)
        self.assertEqual((result.level, result.reasons), (risk.LOW, []))


class PlannerTests(SimpleTestCase):
    def test_checkpoint_spacing_includes_start_and_end(self):
        self.assertEqual(planner.checkpoint_miles(60, 25), [0.0, 25.0, 50.0, 60])
        self.assertEqual(planner.checkpoint_miles(50, 25), [0.0, 25.0, 50])

    def test_validation(self):
        now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
        planner.validate_inputs(40_000, 25)
        planner.validate_departure(now + timedelta(hours=2), now)
        for weight, interval in ((0, 25), (40_000, 7)):
            with self.assertRaises(planner.PlanError):
                planner.validate_inputs(weight, interval)
        for departure in (now + timedelta(days=9), now - timedelta(days=1)):
            with self.assertRaises(planner.PlanError):
                planner.validate_departure(departure, now)

    def _route(self, name, duration_s, severe, high, avg, blocked=False):
        summary = {"severe_miles": severe, "high_miles": high, "avg_risk": avg}
        return {"name": name, "duration_s": duration_s, "summary": summary, "blocked": blocked}

    def test_ranking_prefers_fewer_severe_miles_over_speed(self):
        fast = self._route("A", 3600, severe=40, high=0, avg=1.0)
        safe = self._route("B", 5400, severe=0, high=30, avg=0.8)
        best = min([fast, safe], key=planner._rank_key)
        self.assertEqual(best["name"], "B")
        self.assertIn("avoids 40 miles of Severe", planner._recommendation([fast, safe], best))

    def test_blocked_route_loses_even_if_otherwise_better(self):
        blocked = self._route("A", 3600, severe=0, high=0, avg=0.0, blocked=True)
        open_ = self._route("B", 7200, severe=10, high=10, avg=1.5)
        self.assertEqual(min([blocked, open_], key=planner._rank_key)["name"], "B")

    def test_ties_fall_back_to_travel_time(self):
        a = self._route("A", 5000, 0, 0, 0.5)
        b = self._route("B", 4000, 0, 0, 0.5)
        self.assertEqual(min([a, b], key=planner._rank_key)["name"], "B")


class HoursOfServiceTests(SimpleTestCase):
    H = 3600

    def test_short_trip_has_no_stops(self):
        self.assertEqual(hos.elapsed_s(5 * self.H), 5 * self.H)
        self.assertEqual(hos.stops(5 * self.H), [])

    def test_break_after_eight_hours_of_driving(self):
        self.assertEqual(hos.elapsed_s(8 * self.H), 8 * self.H)
        self.assertEqual(hos.elapsed_s(9 * self.H), 9.5 * self.H)

    def test_rest_after_eleven_hours_of_driving(self):
        self.assertEqual(hos.elapsed_s(11 * self.H), 11.5 * self.H)
        # 11 h + 30 min break + 10 h rest, then 1 h more driving.
        self.assertEqual(hos.elapsed_s(12 * self.H), 22.5 * self.H)

    def test_stop_list_for_two_day_trip(self):
        kinds = [(drive / self.H, kind) for drive, kind, _ in hos.stops(20 * self.H)]
        self.assertEqual(kinds, [(8, "30-min break"), (11, "10-h rest"), (19, "30-min break")])


class TruckSpeedTests(SimpleTestCase):
    def test_segments_are_capped_at_truck_speed(self):
        # Two 1 km segments: one at 120 km/h (too fast for a truck), one at 36 km/h.
        route = {
            "geometry": {"coordinates": [[0, 0], [0.009, 0], [0.018, 0]]},
            "legs": [{"annotation": {"distance": [1000, 1000], "duration": [30, 100]}}],
            "duration": 130,
        }
        parsed = osrm.parse_route(route)
        capped = 1000 / osrm.TRUCK_MAX_MPS
        self.assertAlmostEqual(parsed["drive_s"], capped + 100, places=3)
        self.assertAlmostEqual(parsed["distance_mi"], 2000 / osrm.METERS_PER_MILE, places=6)


class ForecastTests(SimpleTestCase):
    def test_values_are_interpolated_between_hours(self):
        start = datetime(2026, 11, 2, tzinfo=timezone.utc)
        forecast = weather.Forecast(start, [10, 30], [0.0, 0.2], [0.0, 1.0])
        wind, rain, snow = forecast.at(start + timedelta(minutes=30))
        self.assertAlmostEqual(wind, 20)
        self.assertAlmostEqual(rain, 0.1)
        self.assertAlmostEqual(snow, 0.5)
        self.assertEqual(forecast.at(start + timedelta(days=3)), (30, 0.2, 1.0))

    def test_met_norway_series_is_resampled_hourly(self):
        def step(time, wind_ms, temp_c, data):
            return {
                "time": time,
                "data": {"instant": {"details": {"wind_speed": wind_ms, "air_temperature": temp_c}}, **data},
            }

        body = {
            "properties": {
                "timeseries": [
                    step("2026-11-02T00:00:00Z", 10, 5, {"next_1_hours": {"details": {"precipitation_amount": 2.54}}}),
                    step(
                        "2026-11-02T01:00:00Z", 20, -2, {"next_6_hours": {"details": {"precipitation_amount": 15.24}}}
                    ),
                    step("2026-11-02T07:00:00Z", 20, -2, {}),
                ]
            }
        }
        forecast = weather.parse_met(body)
        self.assertEqual(len(forecast.wind), 8)
        self.assertAlmostEqual(forecast.wind[0], 10 * weather.MPS_TO_MPH, places=3)
        self.assertAlmostEqual(forecast.rain[0], 0.1)  # 2.54 mm in 1 h, above freezing
        self.assertEqual(forecast.snow[0], 0.0)
        self.assertAlmostEqual(forecast.snow[3], 0.1 * weather.SNOW_TO_LIQUID)  # 15.24 mm over 6 h, frozen
        self.assertEqual(forecast.source, "MET Norway")

    def test_fallback_source_used_when_primary_fails(self):
        start = datetime(2026, 11, 2, tzinfo=timezone.utc)
        backup = weather.Forecast(start, [5.0], [0.0], [0.0], source="MET Norway")
        with (
            patch.dict(weather._cache, clear=True),
            patch.object(weather, "_fetch_open_meteo", return_value={}),
            patch.object(weather, "_fetch_met", return_value=backup),
        ):
            result = weather.fetch_forecasts([(40.0, -90.0), (41.0, -91.0)])
        self.assertEqual({f.source for f in result.values()}, {"MET Norway"})

    def test_error_when_every_source_fails(self):
        with (
            patch.dict(weather._cache, clear=True),
            patch.object(weather, "_fetch_open_meteo", return_value={}),
            patch.object(weather, "_fetch_met", return_value=None),
            self.assertRaises(weather.WeatherError),
        ):
            weather.fetch_forecasts([(40.0, -90.0)])


def fake_osrm_route(lat, mph):
    """An OSRM-style response for a straight east-west road at `lat`, driven at `mph`."""
    coords = [[-100 + i * 0.02, lat] for i in range(101)]
    seg_m = [haversine_mi((a[1], a[0]), (b[1], b[0])) * osrm.METERS_PER_MILE for a, b in zip(coords, coords[1:])]
    speed = mph * osrm.METERS_PER_MILE / 3600
    seg_s = [m / speed for m in seg_m]
    raw = {
        "geometry": {"coordinates": coords},
        "legs": [{"annotation": {"distance": seg_m, "duration": seg_s}}],
        "duration": sum(seg_s),
    }
    return osrm.parse_route(raw)


class PlanPipelineTests(SimpleTestCase):
    """plan_trip end to end, with every external service replaced by a deterministic fake."""

    NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)

    def fake_forecasts(self, keys):
        start = self.NOW - timedelta(days=1)
        hours = 24 * 10
        # Gale on the northern road (lat 36), calm on the southern one (lat 34).
        dry = [0.0] * hours
        return {k: weather.Forecast(start, [50.0 if k[0] > 35 else 8.0] * hours, dry, dry) for k in keys}

    def plan(self, weight_lb):
        place = {"lat": 35.0, "lon": -100.0, "label": "Somewhere, Texas"}
        routes = [fake_osrm_route(36.0, 60), fake_osrm_route(34.0, 50)]  # north is faster
        with (
            patch.object(geocode, "geocode", return_value=place),
            patch.object(osrm, "fetch_routes", return_value=routes),
            patch.object(geocode, "timezone_at", return_value="America/Chicago"),
            patch.object(weather, "fetch_forecasts", side_effect=self.fake_forecasts),
        ):
            return planner.plan_trip("A", "B", datetime(2026, 11, 2, 8, 0), weight_lb, 25, now=self.NOW)

    def test_heavy_truck_is_sent_around_the_gale(self):
        result = self.plan(45_000)
        north, south = result["routes"]
        self.assertTrue(north["blocked"])  # 50 mph wind with > 30,000 lb is No Travel
        self.assertEqual(north["summary"]["max_level"], risk.NO_TRAVEL)
        self.assertEqual(result["recommended_id"], south["id"])
        self.assertIn("Route B", result["recommendation"])

    def test_light_truck_still_avoids_severe_wind(self):
        result = self.plan(10_000)
        north = result["routes"][0]
        self.assertFalse(north["blocked"])
        self.assertEqual(north["summary"]["max_level"], risk.SEVERE)
        self.assertEqual(result["recommended_id"], result["routes"][1]["id"])

    def test_naive_departure_is_local_time_at_origin(self):
        result = self.plan(10_000)
        self.assertEqual(result["timezone"], "America/Chicago")
        self.assertEqual(result["departure"], "2026-11-02T08:00:00-06:00")
        first = result["routes"][0]["checkpoints"][0]
        self.assertEqual(first["eta"], result["departure"])

    def test_checkpoints_and_heat_series_are_complete(self):
        route = self.plan(10_000)["routes"][0]
        miles = [c["mile"] for c in route["checkpoints"]]
        self.assertEqual(miles[:3], [0.0, 25.0, 50.0])
        self.assertAlmostEqual(miles[-1], route["distance_mi"], places=0)
        self.assertTrue(all(len(c["heat"]) == planner.HEAT_HOURS + 1 for c in route["checkpoints"]))
        self.assertAlmostEqual(sum(route["summary"]["miles_by_level"]), route["distance_mi"], delta=0.5)


class ApiTests(SimpleTestCase):
    def test_plan_rejects_missing_fields(self):
        resp = self.client.post("/api/plan", data={"origin": "Dallas"}, content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_plan_passes_local_departure_through(self):
        with patch.object(planner, "plan_trip", return_value={"ok": True}) as plan_trip:
            resp = self.client.post(
                "/api/plan",
                data={
                    "origin": "Dallas, TX",
                    "destination": "Chicago, IL",
                    "departure": "2026-11-03T08:00",
                    "weight_lb": 40000,
                },
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        args = plan_trip.call_args.args
        self.assertEqual(args[:2], ("Dallas, TX", "Chicago, IL"))
        self.assertEqual(args[2], datetime(2026, 11, 3, 8, 0))  # naive: local at origin
        self.assertEqual(args[3:], (40000.0, 25))

    def test_plan_reports_validation_errors_as_400(self):
        with patch.object(planner, "plan_trip", side_effect=planner.PlanError("bad departure")):
            resp = self.client.post(
                "/api/plan",
                data={"origin": "a", "destination": "b", "departure": "2026-11-03T08:00", "weight_lb": 1},
                content_type="application/json",
            )
        self.assertEqual((resp.status_code, resp.json()["error"]), (400, "bad departure"))

    def test_places_needs_three_characters(self):
        self.assertEqual(self.client.get("/api/places?q=da").json(), {"results": []})


class GeocodeTests(SimpleTestCase):
    def test_label_uses_city_and_state(self):
        item = {
            "display_name": "Dallas, Dallas County, Texas, United States",
            "address": {"city": "Dallas", "state": "Texas"},
        }
        self.assertEqual(geocode._label(item), "Dallas, Texas")

    def test_offline_search_matches_city_and_state(self):
        self.assertEqual(geocode.search_offline("Fargo, ND", 1)[0]["label"], "Fargo, North Dakota")
        self.assertEqual(geocode.search_offline("des moines, iowa", 1)[0]["label"], "Des Moines, Iowa")
        self.assertEqual(geocode.search_offline("Des Moines", 1)[0]["label"], "Des Moines, Iowa")  # largest first
        self.assertEqual(geocode.search_offline("Nowhereville, ND"), [])

    def test_search_falls_back_offline_when_nominatim_fails(self):
        with patch.object(geocode.requests, "get", side_effect=requests.ConnectionError("blocked")):
            result = geocode.search("Fargo, ND", 1)
        self.assertEqual(result[0]["label"], "Fargo, North Dakota")
        self.assertAlmostEqual(result[0]["lat"], 46.877, places=2)

    def test_timezone_is_resolved_offline(self):
        self.assertEqual(geocode.timezone_at(44.98, -93.27), "America/Chicago")
        self.assertEqual(geocode.timezone_at(34.05, -118.24), "America/Los_Angeles")


class GeoTests(SimpleTestCase):
    def test_point_at_interpolates_along_line(self):
        line = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
        cumulative = cumulative_miles(line)
        lat, lon = point_at(line, cumulative, cumulative[-1] / 4)
        self.assertAlmostEqual(lon, 0.5, places=3)
        self.assertEqual(point_at(line, cumulative, 0), line[0])
        self.assertEqual(point_at(line, cumulative, 1e9), line[-1])
