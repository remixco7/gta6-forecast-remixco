# GTA VI launch-day Twitch forecast

Entry for make.fun `gta6-twitch-ccu-forecast-01`: forecast the concurrent
Twitch viewers in the Grand Theft Auto VI category for each hour 2 to 24
of release day (2026-11-19 UTC), as five quantiles per hour, from the
case's hour-1 print and its comparables.

## Method

`main.py` (Python 3.13, standard library only) re-derives the day's shape
from the case file's own comparables at run time. Each past launch's
release-day curve is written as log-ratios to its own hour-1 print. How
steep a launch day is depends almost entirely on how big hour 1 already
was (corr(log hour1, log peak/hour1) = -0.94 across the kit's 38
comparables): an already-unlocked launch stays near flat, a
not-yet-unlocked one climbs 10-100x. So each comparable is weighted by
how close its log hour-1 print is to the target's (Gaussian kernel,
bandwidth 1.0 in log units); the weighted median log-ratio per hour is
the forecast centre and the weighted spread per hour is its width,
`q_tau(h) = p1 * exp(median_h + z_tau * sigma_h)`, smoothed across hours.

Validation on the four practice cases, scored against SullyGnome's
published hourly averages (which match each case's known hour-1 print
exactly): pinball loss **0.234**, typical miss 51%, 90% coverage 0.98.
The house baseline on the same four cases scores 0.387 / 83% / 0.78.

## Run

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `<id>.in` in the input directory, writes `<id>.out` per case:
`{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, ...]}` for
hours 2 to 24. Deterministic: two runs write identical bytes, about
0.1 s per case, no network, no randomness.
