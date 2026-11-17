#!/usr/bin/env python3
"""Forecast GTA VI launch-day Twitch viewers, hour by hour (quantiles).

Method (tuned offline on the kit's practice cases, never on the final):
  Every past big launch in the case file's `comparables` has a release-day
  hourly curve.  Write each launch's curve as log-ratios to its own hour-1
  print, r_h = ln(viewers_h / viewers_1).  Across 38 launches those ratios
  are not one shape: how steep the day is depends almost entirely on how
  big hour 1 already was (corr(log hour1, log peak/hour1) = -0.94).  A
  launch whose hour 1 is already huge (a global unlock at 00:00 UTC, or
  days of early access) stays near flat; a launch whose hour 1 is a
  trickle (its main unlock still hours away) climbs 10-100x by evening.
  So this program, at run time, re-derives the shape from the case's own
  comparables, weighting each launch by how close its log hour-1 print is
  to the target's (Gaussian kernel, bandwidth 1.0 in log units), and takes
  the weighted median log-ratio per hour as the forecast's centre and the
  weighted spread of log-ratios per hour as its width:

    median_h  = weighted median of r_h over comparables
    sigma_h   = weighted sd of r_h, floored at 0.15
    q_tau(h)  = p1 * exp(median_h + z_tau * sigma_h)

  with z = (-1.645, -0.674, 0, 0.674, 1.645) for the levels
  (0.05, 0.25, 0.5, 0.75, 0.95).  Each level's log-quantile series is
  smoothed with a 3-hour moving average, then enforced non-decreasing
  across levels.  A comparable only counts if its release-day curve is
  complete (all 24 hours present, hour 1 above 0); the GTA VI category's
  own pre-release comparable has no release day yet, so it drops out on
  its own.  With no usable comparable the program falls back to the
  house baseline's persistence spread (sigma 0.15 per sqrt hour).

  Validation (leave-one-out over the 38 comparables in the kit, and the
  four practice cases scored against SullyGnome's published hourly
  averages, which match each practice case's known hour-1 print exactly):
    practice pinball loss 0.234, typical miss 51%, 90% coverage 0.98
    house baseline on the same four cases: loss 0.387, miss 83%, cov 0.78

  The program is deterministic: comparables are sorted by name, input
  files are read in name order, there is no randomness, no clock, no
  network and no state between runs, so two runs write identical bytes.
  Standard library only.  It reads $MAKEFUN_INPUT_DIR (else /input) and
  writes $MAKEFUN_OUTPUT_DIR (else /output), one <id>.out per <id>.in.
"""

import json
import math
import os
from datetime import datetime, timezone

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
BANDWIDTH = 1.0          # kernel bandwidth, log units of hour-1 viewers
SIGMA_FLOOR = 0.15       # minimum log-spread of any hour
BASELINE_SIGMA = 0.15    # fallback persistence spread per sqrt hour
MAX_VIEWERS = 1_000_000_000


def parse_time(text):
    """Parse an ISO 8601 UTC timestamp into an aware datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def release_day_curve(comparable):
    """Hourly viewers for hours 1..24 of a comparable's release day.

    Returns a list of 24 numbers, or None when any release-day hour is
    missing or hour 1 is not above zero.
    """
    day_start = parse_time(comparable["day_start"])
    curve = [None] * 24
    for point in comparable.get("hourly", []):
        offset = int((parse_time(point["from"]) - day_start).total_seconds() // 3600)
        if 0 <= offset < 24:
            curve[offset] = point["viewers"]
    if curve[0] is None or curve[0] <= 0:
        return None
    if any(v is None or v <= 0 for v in curve):
        return None
    return curve


def weighted_quantile(pairs, tau):
    """Smallest value whose cumulative weight reaches tau of the total."""
    ordered = sorted(pairs)
    total = sum(w for _, w in ordered)
    cut = tau * total
    acc = 0.0
    for value, weight in ordered:
        acc += weight
        if acc >= cut:
            return value
    return ordered[-1][0]


def smooth3(values):
    """Three-point moving average, ends averaged over the two they have."""
    out = []
    for i in range(len(values)):
        window = values[max(0, i - 1):min(len(values), i + 2)]
        out.append(sum(window) / len(window))
    return out


def kernel_forecast(p1, curves):
    """Quantile rows for hours 2..24 from comparable log-ratio curves.

    `curves` is a list of (hour1_viewers, [log-ratio per hour 1..24]).
    """
    log_p1 = math.log(p1)
    log_rows = []
    for h in range(2, 25):
        pairs = []
        for hour1, ratios in curves:
            weight = math.exp(-0.5 * ((math.log(hour1) - log_p1) / BANDWIDTH) ** 2)
            pairs.append((ratios[h - 1], weight))
        median = weighted_quantile(pairs, 0.5)
        total = sum(w for _, w in pairs)
        mean = sum(v * w for v, w in pairs) / total
        variance = sum(w * (v - mean) ** 2 for v, w in pairs) / total
        sigma = max(SIGMA_FLOOR, math.sqrt(variance))
        log_rows.append([median + z * sigma for z in Z])
    # Smooth each level's log series across hours, then exponentiate.
    for j in range(len(Z)):
        column = smooth3([row[j] for row in log_rows])
        for i in range(len(log_rows)):
            log_rows[i][j] = column[i]
    rows = []
    for h, log_row in zip(range(2, 25), log_rows):
        quantiles = [max(1.0, p1 * math.exp(x)) for x in log_row]
        for j in range(1, len(quantiles)):
            quantiles[j] = max(quantiles[j], quantiles[j - 1])
        quantiles = [min(MAX_VIEWERS, round(q, 2)) for q in quantiles]
        rows.append({"hour": h, "q": quantiles})
    return rows


def baseline_forecast(p1):
    """Persistence fallback: every hour stays at hour 1's print."""
    rows = []
    for h in range(2, 25):
        spread = BASELINE_SIGMA * math.sqrt(h - 1)
        quantiles = [max(1.0, p1 * math.exp(z * spread)) for z in Z]
        for j in range(1, len(quantiles)):
            quantiles[j] = max(quantiles[j], quantiles[j - 1])
        quantiles = [min(MAX_VIEWERS, round(q, 2)) for q in quantiles]
        rows.append({"hour": h, "q": quantiles})
    return rows


def forecast_case(case):
    """Forecast one case dict, returning the {"hours": [...]} object."""
    known = case["known"]
    first = next(k for k in known if k["hour"] == 1)
    p1 = max(1.0, float(first["viewers"]))
    curves = []
    for comparable in sorted(
        case.get("comparables", []),
        key=lambda c: (c["name"], c.get("day_start", "")),
    ):
        curve = release_day_curve(comparable)
        if curve is None:
            continue
        ratios = [math.log(v / curve[0]) for v in curve]
        curves.append((curve[0], ratios))
    if curves:
        hours = kernel_forecast(p1, curves)
    else:
        hours = baseline_forecast(p1)
    return {"hours": hours}


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    inputs = sorted(f for f in os.listdir(INPUT_DIR) if f.endswith(".in"))
    for filename in inputs:
        case_id = filename[: -len(".in")]
        with open(os.path.join(INPUT_DIR, filename), encoding="utf-8") as fh:
            case = json.load(fh)
        if list(case["levels"]) != LEVELS:
            raise ValueError(f"{filename} asks for levels {case['levels']}")
        result = forecast_case(case)
        with open(os.path.join(OUTPUT_DIR, f"{case_id}.out"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
