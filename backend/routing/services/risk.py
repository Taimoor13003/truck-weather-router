"""Weather risk rules from the assessment brief.

Levels, lowest to highest: Low, Moderate, High, Severe, No Travel.
"""
from dataclasses import dataclass, field

LEVELS = ["Low", "Moderate", "High", "Severe", "No Travel"]
LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = range(5)

# Lower bound of Moderate, High, Severe, No Travel for each condition. For rain and snow the
# brief gives No Travel as a strict ">" (rain > 1.00 in/hr, snow > 3.0 in/hr); wind uses ">= 55".
_BOUNDS = {
    "wind": ((25, 35, 45, 55), False),  # mph
    "rain": ((0.10, 0.25, 0.50, 1.00), True),  # in/hr
    "snow": ((0.5, 1.0, 2.0, 3.0), True),  # in/hr
}
_LABELS = {"wind": ("Wind", "mph"), "rain": ("Rain", "in/hr"), "snow": ("Snow", "in/hr")}

HEAVY_LOAD_LB = 30_000
VERY_HEAVY_LOAD_LB = 40_000


def classify(kind, value):
    """Risk level of a single reading (wind in mph, rain/snow in inches per hour)."""
    bounds, strict_top = _BOUNDS[kind]
    level = LOW
    for i, bound in enumerate(bounds):
        top = i == len(bounds) - 1
        if value > bound if (top and strict_top) else value >= bound:
            level = i + 1
    return level


@dataclass
class Risk:
    level: int
    reasons: list = field(default_factory=list)

    @property
    def label(self):
        return LEVELS[self.level]


def assess(wind_mph, rain_in_hr, snow_in_hr, weight_lb):
    """Combine the three conditions (worst wins), then apply the load-weight rules."""
    readings = {"wind": wind_mph, "rain": rain_in_hr, "snow": snow_in_hr}
    level = LOW
    reasons = []
    for kind, value in readings.items():
        lvl = classify(kind, value)
        if lvl > LOW:
            name, unit = _LABELS[kind]
            reasons.append(f"{name} {value:.2f} {unit}: {LEVELS[lvl]}" if kind != "wind" else f"{name} {value:.0f} {unit}: {LEVELS[lvl]}")
        level = max(level, lvl)

    if 45 <= wind_mph < 55 and weight_lb > HEAVY_LOAD_LB:
        level = NO_TRAVEL
        reasons.append(f"Load over {HEAVY_LOAD_LB:,} lb in {wind_mph:.0f} mph wind: No Travel")
    elif 35 <= wind_mph < 45 and weight_lb > VERY_HEAVY_LOAD_LB:
        level = max(level, SEVERE)
        reasons.append(f"Load over {VERY_HEAVY_LOAD_LB:,} lb in {wind_mph:.0f} mph wind: Severe")
    return Risk(level, reasons)
