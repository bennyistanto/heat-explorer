"""Test revision 3 of the heat spell detector on the 17 single cells and 9 events.

Checks, written on 2026-11-21 BEFORE the first run:
  R0  Regression. With min_run = 1 and the archive (final) class, the per-day
      class equals 03_tune_detector's "ctr_p90_fixed" on every day at all 17
      cells. This proves the revision changes only what it says it changes.
  R1  With min_run = 3, each of the 9 events still has spell days in its window.
  R2  With min_run = 3 and CAUSAL classes, at least 8 of the 9 events reach
      severe on some day inside their window (8 of 9 were severe or extreme
      under the old hindsight class).
  The revision is accepted if R0, R1 and R2 all hold.

Reported, not criteria: how many flagged days and events the 3-day minimum
removes; the class cuts before and after; on which day of a spell the causal
class reaches severe and extreme; the share of archive-severe days that are
already severe on the day; days per year by period.

Single cells and the same 9 events used to tune the detector, so this is a
check of the revision, not new evidence that the detector is right.

Run:  bash tools/py.sh -W ignore validation/detector_v3/01_test_revision.py
Output: validation/detector_v3/results/revision_summary.txt, revision_sites.csv, revision_events.csv
"""
import importlib.util
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("det3", os.path.join(HERE, "detector.py"))
d3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d3)
p1, old = d3.p1, d3.t3mod

if __name__ == "__main__":
    res = os.path.join(HERE, "results")
    os.makedirs(res, exist_ok=True)
    z = np.load(p1.CELLS)
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(z["time"], unit="D"))
    y = idx.year.values
    per = lambda m, a, b: float(m[(y >= a) & (y <= b)].sum() / (b - a + 1))
    sites, events, r0 = [], [], []
    for site in p1.ELEV:
        g = lambda v: np.where(z[f"{v}__{site}"][:, 5, 5] == -9999.0, np.nan, z[f"{v}__{site}"][:, 5, 5].astype("f8") - 273.15)
        tm = (g("t2mmax") + np.append(g("t2mmin")[1:], np.nan)) / 2
        o = old.detect(tm, idx, "centre", 90, "fixed")
        a = d3.detect(tm, idx, min_run=1)
        b = d3.detect(tm, idx, min_run=3)
        r0.append(bool(np.array_equal(a["cls_final"], o["day_cls"])))
        inb = lambda r: (idx.year[r["s"]] >= 1991) & (idx.year[r["s"]] <= 2020)
        sev_f, sev_c = b["cls_final"] >= 2, b["cls_causal"] >= 2
        # day of the spell on which the causal class first reaches severe / extreme, baseline spells that get there
        d_sev, d_ext = [], []
        for s, e, c in zip(b["s"][inb(b)], b["e"][inb(b)], b["cls"][inb(b)]):
            run = b["running"][s:e + 1]
            if c >= 2:
                d_sev.append(int(np.argmax(run >= b["q80"])) + 1)
            if c >= 3:
                d_ext.append(int(np.argmax(run >= b["q95"])) + 1)
        sites.append({"site": site, "R0": r0[-1],
                      "flag_days_yr": per(a["flag"], 1991, 2020), "spell_days_yr": per(b["spell"], 1991, 2020),
                      "share_flag_days_dropped": 1 - b["spell"].sum() / max(a["flag"].sum(), 1),
                      "events_yr_min1": float(inb(a).sum() / 30), "events_yr_min3": float(inb(b).sum() / 30),
                      "q80_min1": a["q80"], "q80_min3": b["q80"], "q95_min1": a["q95"], "q95_min3": b["q95"],
                      "sev_days_yr_archive": per(sev_f, 1991, 2020), "sev_days_yr_causal": per(sev_c, 1991, 2020),
                      "causal_share_of_archive_sev": float(sev_c[(y >= 1991) & (y <= 2020)].sum() / max(sev_f[(y >= 1991) & (y <= 2020)].sum(), 1)),
                      "median_day_to_severe": float(np.median(d_sev)) if d_sev else np.nan,
                      "median_day_to_extreme": float(np.median(d_ext)) if d_ext else np.nan,
                      "spell_days_yr_2125": per(b["spell"], 2021, 2025), "sev_days_yr_causal_2125": per(sev_c, 2021, 2025)})
        for en, s2, w0, w1 in p1.EVENTS:
            if s2 != site:
                continue
            w = (idx >= pd.Timestamp(w0)) & (idx <= pd.Timestamp(w1))
            hit = [k for k in range(len(b["s"])) if idx[b["e"][k]] >= pd.Timestamp(w0) and idx[b["s"][k]] <= pd.Timestamp(w1)]
            first = np.where(w & (b["cls_causal"] >= 2))[0]
            big = max((b["mag"][k] for k in hit), default=0.0)
            names = {0: "none", 1: "spell", 2: "severe", 3: "extreme"}
            events.append({"event": en, "site": site, "window_days": int(w.sum()),
                           "flag_days_min1": int(a["flag"][w].sum()), "spell_days_min3": int(b["spell"][w].sum()),
                           "archive_class": names[int(b["cls_final"][w].max())], "causal_class": names[int(b["cls_causal"][w].max())],
                           "sev_days_archive": int((b["cls_final"][w] >= 2).sum()), "sev_days_causal": int((b["cls_causal"][w] >= 2).sum()),
                           "first_causal_severe": str(idx[first[0]].date()) if len(first) else "never",
                           "event_rank": int((b["mag"] > big).sum() + 1) if hit else None, "n_spells": len(b["mag"]),
                           "R1": bool(b["spell"][w].any()), "R2": bool((b["cls_causal"][w] >= 2).any())})
    S, E = pd.DataFrame(sites), pd.DataFrame(events)
    S.round(3).to_csv(f"{res}/revision_sites.csv", index=False)
    E.to_csv(f"{res}/revision_events.csv", index=False)
    pd.set_option("display.width", 320, "display.max_columns", 40)
    R0, R1, R2 = all(r0), bool(E.R1.all()), int(E.R2.sum())
    out = ["Detector revision 3. Produced by validation/detector_v3/01_test_revision.py",
           f"R0 regression against 03_tune_detector (min_run 1, archive class): {'HOLDS at all 17 cells' if R0 else 'FAILS at ' + str([s for s, k in zip(p1.ELEV, r0) if not k])}",
           f"R1 every event keeps spell days with the 3-day minimum: {'HOLDS' if R1 else 'FAILS'} ({int(E.R1.sum())} of {len(E)})",
           f"R2 events reaching severe on the day (causal class): {R2} of {len(E)} -> {'HOLDS' if R2 >= 8 else 'FAILS'}",
           f"REVISION {'ACCEPTED' if (R0 and R1 and R2 >= 8) else 'NOT ACCEPTED'} by the rule written first",
           "\n== Events (min_run 3)",
           E.drop(columns=["R1", "R2"]).to_string(index=False),
           "\n== Effect of the 3-day minimum, 1991-2020",
           S[["site", "flag_days_yr", "spell_days_yr", "share_flag_days_dropped", "events_yr_min1", "events_yr_min3", "q80_min1", "q80_min3", "q95_min1", "q95_min3"]].round(2).to_string(index=False),
           "\n== Causal against archive class, 1991-2020, and recent years",
           S[["site", "sev_days_yr_archive", "sev_days_yr_causal", "causal_share_of_archive_sev", "median_day_to_severe", "median_day_to_extreme", "spell_days_yr_2125", "sev_days_yr_causal_2125"]].round(2).to_string(index=False),
           "\n== Ranges across the 17 cells (min, median, max)"]
    for c in ("share_flag_days_dropped", "spell_days_yr", "events_yr_min3", "sev_days_yr_causal", "causal_share_of_archive_sev", "median_day_to_severe"):
        out.append(f"  {c}: {S[c].min():.2f}, {S[c].median():.2f}, {S[c].max():.2f}")
    txt = "\n".join(out)
    with open(f"{res}/revision_summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
