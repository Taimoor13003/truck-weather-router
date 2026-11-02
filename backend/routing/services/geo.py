"""Small geometry helpers for polylines expressed as (lat, lon) pairs."""
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_MI = 3958.8


def haversine_mi(a, b):
    lat1, lon1, lat2, lon2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * asin(sqrt(h))


def cumulative_miles(points):
    """Distance from the first point to each point, measured along the line."""
    out = [0.0]
    for prev, cur in zip(points, points[1:]):
        out.append(out[-1] + haversine_mi(prev, cur))
    return out


def point_at(points, cumulative, mile):
    """Interpolated (lat, lon) at `mile` along the polyline."""
    if mile <= 0:
        return points[0]
    if mile >= cumulative[-1]:
        return points[-1]
    lo, hi = 0, len(cumulative) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if cumulative[mid] <= mile:
            lo = mid
        else:
            hi = mid
    span = cumulative[hi] - cumulative[lo] or 1e-9
    t = (mile - cumulative[lo]) / span
    return (
        points[lo][0] + (points[hi][0] - points[lo][0]) * t,
        points[lo][1] + (points[hi][1] - points[lo][1]) * t,
    )


def downsample(points, max_points):
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    picked = [points[int(i * step)] for i in range(max_points)]
    picked.append(points[-1])
    return picked


def mean_distance_to_line(sample, line):
    """Average distance in miles from each sample point to its nearest point on `line`."""
    total = sum(min(haversine_mi(p, q) for q in line) for p in sample)
    return total / len(sample)
