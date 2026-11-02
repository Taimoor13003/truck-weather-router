"""US Hours-of-Service rules for property-carrying drivers (FMCSA 49 CFR 395.3), simplified.

- At most 11 hours of driving, then a 10-hour off-duty rest.
- A 30-minute break once 8 hours of driving have accumulated since the last rest.

The 14-hour on-duty window and the 60/70-hour weekly limits are not modelled: a single trip
planned from a fresh start is governed by the two rules above.
"""

import math

DRIVE_LIMIT_S = 11 * 3600
BREAK_AFTER_S = 8 * 3600
BREAK_S = 30 * 60
REST_S = 10 * 3600


def elapsed_s(drive_s):
    """Wall-clock seconds from departure until `drive_s` seconds of driving have been done."""
    if drive_s <= 0:
        return 0.0
    rests = math.ceil(drive_s / DRIVE_LIMIT_S) - 1  # rests taken before the current shift
    in_shift = drive_s - rests * DRIVE_LIMIT_S
    breaks = rests + (1 if in_shift > BREAK_AFTER_S else 0)  # every completed shift had its break
    return drive_s + rests * REST_S + breaks * BREAK_S


def stops(total_drive_s):
    """(drive seconds at which the stop starts, kind, length in seconds) for the whole trip."""
    out = []
    shift_start = 0.0
    while True:
        if shift_start + BREAK_AFTER_S < total_drive_s:
            out.append((shift_start + BREAK_AFTER_S, "30-min break", BREAK_S))
        if shift_start + DRIVE_LIMIT_S < total_drive_s:
            out.append((shift_start + DRIVE_LIMIT_S, "10-h rest", REST_S))
            shift_start += DRIVE_LIMIT_S
        else:
            return out
