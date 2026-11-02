from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from .services import planner, risk
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


class GeoTests(SimpleTestCase):
    def test_point_at_interpolates_along_line(self):
        line = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
        cumulative = cumulative_miles(line)
        lat, lon = point_at(line, cumulative, cumulative[-1] / 4)
        self.assertAlmostEqual(lon, 0.5, places=3)
        self.assertEqual(point_at(line, cumulative, 0), line[0])
        self.assertEqual(point_at(line, cumulative, 1e9), line[-1])
