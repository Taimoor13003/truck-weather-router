from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from .services import hos, osrm, planner, risk, weather
from .services.geo import cumulative_miles, point_at


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
        planner.validate(now + timedelta(hours=2), 40_000, 25, now)
        for bad in (
            (now + timedelta(days=9), 40_000, 25),
            (now, 0, 25),
            (now, 40_000, 7),
        ):
            with self.assertRaises(planner.PlanError):
                planner.validate(*bad, now)

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


class GeoTests(SimpleTestCase):
    def test_point_at_interpolates_along_line(self):
        line = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
        cumulative = cumulative_miles(line)
        lat, lon = point_at(line, cumulative, cumulative[-1] / 4)
        self.assertAlmostEqual(lon, 0.5, places=3)
        self.assertEqual(point_at(line, cumulative, 0), line[0])
        self.assertEqual(point_at(line, cumulative, 1e9), line[-1])
