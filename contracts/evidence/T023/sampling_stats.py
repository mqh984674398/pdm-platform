"""Reproduce sampling_stats.txt: samples, signals, median sampling interval and span per SIMULATED scenario.

    backend/.venv/bin/python contracts/evidence/T023/sampling_stats.py
"""

import collections
import csv
import glob
import gzip
import os
import statistics as st
from datetime import datetime

tot = 0
for d in sorted(glob.glob("Data/scenarios/S*")):
    sig = collections.defaultdict(list)
    with gzip.open(d + "/raw_telemetry.csv.gz", "rt") as fh:
        for row in csv.DictReader(fh):
            sig[row["keyname"]].append(row["ts"])
    n = sum(len(v) for v in sig.values())
    tot += n
    ivs, spans = [], []
    for v in sig.values():
        ts = sorted(datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp() for x in v)
        ivs.append(st.median(b - a for a, b in zip(ts, ts[1:])))
        spans.append((ts[-1] - ts[0]) / 86400)
    print(os.path.basename(d)[:3], "samples", n, "signals", len(sig),
          "median_interval_s", sorted({round(i, 1) for i in ivs}), "days", round(max(spans), 1),
          "samples/signal/day", round(n / len(sig) / max(spans)))  # fmt: skip
print("total", tot)
