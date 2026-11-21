"""Compare detector forms after 01_prototype.py passed only 4 of 9 events.

01 showed two failure modes of "3 consecutive days above the calendar-day p90":
  - peak-season events (India May 2015) are hot for the place but not unusual
    for the date, so the calendar threshold is not crossed;
  - spiky climates (Sydney) rarely give 3 consecutive hot days.

Detectors compared (all on Tm = (Tmax(d) + Tmin(d+1)) / 2, baseline 1991-2020):
  A  3 consecutive days above calendar-day p90, floor p50          (01, for reference)
  B  3-day mean above the calendar-day p90 of 3-day means, floor p50; all 3 days flagged
  C  3-day mean above the all-year p95 (the EHF significance test); all 3 days flagged
  D  B or C: unusual for the date, or hot for the place

Magnitude per flagged day = largest positive excess over the thresholds in use,
divided by the IQR of baseline anomalies. Events are merged runs of flagged days.
Severity by the 80th and 95th percentile of baseline event magnitudes.

Run:  bash tools/py.sh -W ignore validation/heat_spell_prototype/02_detector_variants.py
Output: validation/heat_spell_prototype/results/variants_*.csv, variants_summary.txt
"""
import importlib.util
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("p01", os.path.join(HERE, "01_prototype.py"))
p1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p1)

DET = ["A", "B", "C", "D"]


def detect(tm, idx, det):
    thr, clim, iqr, base = p1.thresholds(tm, idx)
    doy = p1.doy365(idx)
    n = len(tm)
    p50, p95 = np.percentile(tm[base], [50, 95])
    t3 = (tm + np.append(tm[1:], np.nan) + np.append(tm[2:], [np.nan, np.nan])) / 3   # d, d+1, d+2
    exc = np.zeros(n)
    flag = np.zeros(n, bool)
    if det == "A":
        m3 = pd.Series(tm).rolling(3, center=True, min_periods=2).mean().values
        hot = (tm > thr) & (m3 > p50) & np.isfinite(tm)
        s, e = p1.runs(hot)
        for a, b in zip(s, e):
            flag[a:b + 1] = True
        exc = np.where(flag, (tm - thr) / iqr, 0.0)
    else:
        thr3, _, _, _ = p1.thresholds(np.where(np.isfinite(t3), t3, np.nan), idx)
        cal = (t3 > thr3) & (t3 > p50)
        allyr = t3 > p95
        start = {"B": cal, "C": allyr, "D": cal | allyr}[det] & np.isfinite(t3)
        for k in (0, 1, 2):
            flag[k:] |= start[:n - k] if k else start
        e_cal = (tm - thr) / iqr if det in ("B", "D") else np.full(n, -np.inf)
        e_all = (tm - p95) / iqr if det in ("C", "D") else np.full(n, -np.inf)
        exc = np.where(flag, np.clip(np.fmax(e_cal, e_all), 0, None), 0.0)
        exc = np.nan_to_num(exc)
    s, e = p1.runs(flag, min_len=1)
    mag = np.array([exc[a:b + 1].sum() for a, b in zip(s, e)])
    inb = (idx.year[s] >= 1991) & (idx.year[s] <= 2020)
    q80, q95 = np.percentile(mag[inb], [80, 95])
    cls = 1 + (mag >= q80).astype(int) + (mag >= q95).astype(int)
    day_cls = np.zeros(n, int)
    for a, b, c in zip(s, e, cls):
        day_cls[a:b + 1] = c
    return {"day_cls": day_cls, "s": s, "e": e, "mag": mag, "cls": cls, "clim": clim, "doy": doy}


if __name__ == "__main__":
    res = os.path.join(HERE, "results")
    z = np.load(p1.CELLS)
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(z["time"], unit="D"))
    summ, ev = [], []
    for site in p1.ELEV:
        g = lambda v: np.where(z[f"{v}__{site}"][:, 5, 5] == -9999.0, np.nan, z[f"{v}__{site}"][:, 5, 5].astype("f8") - 273.15)
        tm = (g("t2mmax") + np.append(g("t2mmin")[1:], np.nan)) / 2
        for det in DET:
            sp = detect(tm, idx, det)
            summ.append({"det": det, "site": site, **p1.site_summary(sp, idx)})
            for name, s2, a, b in p1.EVENTS:
                if s2 == site:
                    ev.append({"det": det, "event": name, "site": site, **p1.event_row(sp, idx, a, b)})
    summ, ev = pd.DataFrame(summ), pd.DataFrame(ev)
    summ.round(3).to_csv(f"{res}/variants_site_summary.csv", index=False)
    ev.round(3).to_csv(f"{res}/variants_events.csv", index=False)

    pd.set_option("display.width", 250)
    out = ["Detector variants, 17 single cells. Produced by validation/heat_spell_prototype/02_detector_variants.py",
           "A consecutive days, calendar p90 | B 3-day mean, calendar p90 | C 3-day mean, all-year p95 | D B or C",
           "\n== Events: flagged days in window / class / rank of the year by cumulative magnitude (of 48)"]
    e2 = ev.assign(cell=ev.spell_days.astype(str) + "/" + ev.window_days.astype(str) + " " + ev["class"] + " #" + ev.year_rank_by_cum_mag.astype(str))
    out.append(e2.pivot(index=["event", "site"], columns="det", values="cell")[DET].to_string())
    ok = ev.assign(sev=ev["class"].isin(["severe", "extreme"]), top3=ev.year_rank_by_cum_mag <= 3, any=ev.spell_days > 0)
    out.append("\n== Of 9 events: detected at all / severe or extreme / severe-or-extreme and year in top 3")
    out.append(ok.groupby("det")[["any", "sev"]].sum().assign(both=ok.assign(b=ok.sev & ok.top3).groupby("det").b.sum()).reindex(DET).to_string())
    for col, title in (("days_yr_9120", "Flagged days per year, 1991-2020"), ("cold_quarter_share", "Share of flagged days in the coldest quarter"),
                       ("zero_years", "Years with no flagged day, of 47"), ("days_yr_7990", "Flagged days per year, 1979-1990"),
                       ("days_yr_2125", "Flagged days per year, 2021-2025")):
        out.append(f"\n== {title}")
        out.append(summ.pivot(index="site", columns="det", values=col)[DET].round(2).to_string())
    txt = "\n".join(out)
    with open(f"{res}/variants_summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
