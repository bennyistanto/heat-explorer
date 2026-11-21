"""Variant, tried AFTER 01_test_revision.py failed check R2: class each spell day
by how far above its threshold that day is, not by the spell's running total.

  intensity class = 1 spell, 2 severe, 3 extreme by the 80th and 95th percentile
  of the daily excess on baseline spell days (min_run 3).

It is causal by construction and immediate: no waiting for a total to build.
It does not say how long a spell has lasted; duration and running magnitude
would be shown as separate numbers.

POST HOC: this was thought of after seeing the R2 failure, on the same 9 events.
It is a comparison to inform a design choice, not a test that can pass.

Run:  bash tools/py.sh -W ignore validation/detector_v3/02_intensity_variant.py
Output: validation/detector_v3/results/intensity_variant.txt
"""
import importlib.util
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("det3", os.path.join(HERE, "detector.py"))
d3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d3)
p1 = d3.p1

if __name__ == "__main__":
    z = np.load(p1.CELLS)
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(z["time"], unit="D"))
    y = idx.year.values
    base = (y >= 1991) & (y <= 2020)
    rec = (y >= 2021) & (y <= 2025)
    rows, ev = [], []
    names = {0: "none", 1: "spell", 2: "severe", 3: "extreme"}
    for site in p1.ELEV:
        g = lambda v: np.where(z[f"{v}__{site}"][:, 5, 5] == -9999.0, np.nan, z[f"{v}__{site}"][:, 5, 5].astype("f8") - 273.15)
        tm = (g("t2mmax") + np.append(g("t2mmin")[1:], np.nan)) / 2
        b = d3.detect(tm, idx, min_run=3)
        e80, e95, ci = b["e80"], b["e95"], b["cls_day"]      # now computed in detector.py (adopted 2026-11-21)
        first = []
        for s, e in zip(b["s"], b["e"]):
            k = np.where(ci[s:e + 1] >= 2)[0]
            if len(k) and 1991 <= idx[s].year <= 2020:
                first.append(k[0] + 1)
        rows.append({"site": site, "e80": e80, "e95": e95, "e80_K": e80 * b["iqr"], "e95_K": e95 * b["iqr"],
                     "sev_days_yr_intensity": (ci[base] >= 2).sum() / 30, "sev_days_yr_running": (b["cls_causal"][base] >= 2).sum() / 30,
                     "sev_days_yr_intensity_2125": (ci[rec] >= 2).sum() / 5, "median_day_to_severe": float(np.median(first)) if first else np.nan,
                     "share_spells_ever_severe": float(np.mean([(ci[s:e + 1] >= 2).any() for s, e in zip(b["s"], b["e"]) if 1991 <= idx[s].year <= 2020]))})
        for en, s2, w0, w1 in p1.EVENTS:
            if s2 != site:
                continue
            w = (idx >= pd.Timestamp(w0)) & (idx <= pd.Timestamp(w1))
            k = np.where(w & (ci >= 2))[0]
            k2 = np.where(w & (b["cls_causal"] >= 2))[0]
            ev.append({"event": en, "site": site, "spell_days": int(b["spell"][w].sum()), "intensity_class": names[int(ci[w].max())],
                       "sev_days_intensity": int((ci[w] >= 2).sum()), "first_severe_intensity": str(idx[k[0]].date()) if len(k) else "never",
                       "running_class": names[int(b["cls_causal"][w].max())], "sev_days_running": int((b["cls_causal"][w] >= 2).sum()),
                       "first_severe_running": str(idx[k2[0]].date()) if len(k2) else "never",
                       "peak_excess_K": round(float((b["excess"][w] * b["iqr"]).max()), 1)})
    S, E = pd.DataFrame(rows), pd.DataFrame(ev)
    pd.set_option("display.width", 320, "display.max_columns", 40)
    out = ["Intensity-class variant (post hoc comparison). Produced by validation/detector_v3/02_intensity_variant.py",
           f"Events reaching severe inside the window: by daily intensity {int((E.intensity_class != 'spell').sum())} of {len(E)}; by running magnitude {int((E.running_class != 'spell').sum())} of {len(E)}",
           "\n== Events", E.to_string(index=False), "\n== Sites, 1991-2020 unless marked", S.round(2).to_string(index=False)]
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "intensity_variant.txt"), "w") as f:
        f.write(txt + "\n")
    print(txt)
