"""Tune detector D (unusual for the date OR hot for the place).

02 showed D detects all nine test events but flags 43 to 71 days per year and
saturates in the tropics. Three knobs are tested here:

  flag    all3   = a 3-day window over threshold flags all 3 days (as in 02)
          centre = a day is flagged when the 3-day mean centred on it is over threshold
  cal     calendar-day percentile for the "unusual for the date" test: 90 or 95
  trend   fixed  = thresholds from 1991-2020 applied to the raw series
          moving = the cell's linear warming trend (annual mean Tm, 1979-2025) is
                   removed first, so the test is against the current climate

The "hot for the place" test stays at the all-year 95th percentile, and the
floor at the all-year median, both of the 3-day mean.

Pass criterion for an event, written before this run: flagged, and classed
severe or extreme (top 20 percent of baseline events by magnitude). The rank of
the event among all events at the cell is reported, not used as a criterion.

Run:  bash tools/py.sh -W ignore validation/heat_spell_prototype/03_tune_detector.py
Output: validation/heat_spell_prototype/results/tune_*.csv, tune_summary.txt
"""
import importlib.util
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("p01", os.path.join(HERE, "01_prototype.py"))
p1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p1)

CONFIGS = {  # name: (flag, cal percentile, trend)
    "all3_p90_fixed": ("all3", 90, "fixed"),      # detector D from 02, for reference
    "ctr_p90_fixed": ("centre", 90, "fixed"),
    "ctr_p95_fixed": ("centre", 95, "fixed"),
    "ctr_p90_moving": ("centre", 90, "moving"),
    "ctr_p95_moving": ("centre", 95, "moving"),
}


def cal_threshold(x, idx, q):
    """Calendar-day percentile q with the seasonal cycle removed first (15-day window)."""
    doy = p1.doy365(idx)
    base = (idx.year >= 1991) & (idx.year <= 2020) & np.isfinite(x)
    clim = p1.smooth_clim(x, doy, base)
    ab, db = (x - clim[doy - 1])[base], doy[base]
    pq = np.empty(365)
    for d in range(1, 366):
        dist = np.abs(db - d)
        pq[d - 1] = np.percentile(ab[np.minimum(dist, 365 - dist) <= 7], q)
    q25, q75 = np.percentile(ab, [25, 75])
    return clim[doy - 1] + pq[doy - 1], clim, q75 - q25, base


def detrend(tm, idx):
    """Remove the linear trend of annual mean Tm, centred on the baseline midpoint."""
    yr = idx.year.values
    ann = pd.Series(tm).groupby(yr).mean().loc[1979:2025]
    slope = np.polyfit(ann.index.values.astype(float), ann.values, 1)[0]
    t = yr + (idx.dayofyear.values - 0.5) / 365.25
    return tm - slope * (t - 2006.0), slope * 10


def detect(tm, idx, flag, cal_q, trend):
    slope10 = 0.0
    if trend == "moving":
        tm, slope10 = detrend(tm, idx)
    n = len(tm)
    if flag == "centre":
        t3 = pd.Series(tm).rolling(3, center=True).mean().values
    else:
        t3 = (tm + np.append(tm[1:], np.nan) + np.append(tm[2:], [np.nan, np.nan])) / 3
    thr, clim, iqr, base = cal_threshold(t3, idx, cal_q)
    ok = np.isfinite(t3)
    p50, p95 = np.percentile(t3[base & ok], [50, 95])
    cal = ok & (t3 > thr) & (t3 > p50)
    allyr = ok & (t3 > p95)
    start = cal | allyr
    exc_start = np.where(start, np.fmax((t3 - thr) / iqr, (t3 - p95) / iqr), 0.0)
    exc_start = np.nan_to_num(exc_start)
    if flag == "centre":
        flagged, exc = start, exc_start
    else:
        flagged = np.zeros(n, bool)
        exc = np.zeros(n)
        for k in (0, 1, 2):
            flagged[k:] |= start[:n - k]
            exc[k:] = np.maximum(exc[k:], exc_start[:n - k])
    s, e = p1.runs(flagged, min_len=1)
    mag = np.array([exc[a:b + 1].sum() for a, b in zip(s, e)])
    inb = (idx.year[s] >= 1991) & (idx.year[s] <= 2020)
    q80, q95 = np.percentile(mag[inb], [80, 95])
    cls = 1 + (mag >= q80).astype(int) + (mag >= q95).astype(int)
    day_cls = np.zeros(n, int)
    for a, b, c in zip(s, e, cls):
        day_cls[a:b + 1] = c
    doy = p1.doy365(idx)
    return {"day_cls": day_cls, "s": s, "e": e, "mag": mag, "cls": cls, "clim": clim, "doy": doy,
            "only_cal": int((cal & ~allyr).sum()), "only_all": int((allyr & ~cal).sum()), "both": int((cal & allyr).sum()),
            "slope10": slope10}


def event_row(sp, idx, a, b):
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    w = (idx >= a) & (idx <= b)
    hit = [k for k, (s, e) in enumerate(zip(sp["s"], sp["e"])) if idx[e] >= a and idx[s] <= b]
    names = {0: "none", 1: "spell", 2: "severe", 3: "extreme"}
    big = max((sp["mag"][k] for k in hit), default=0.0)
    return {"flag_days": int((sp["day_cls"][w] > 0).sum()), "window_days": int(w.sum()),
            "class": names[int(sp["day_cls"][w].max())],
            "event_rank": int((sp["mag"] > big).sum() + 1) if hit else None, "n_events": len(sp["mag"])}


if __name__ == "__main__":
    res = os.path.join(HERE, "results")
    z = np.load(p1.CELLS)
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(z["time"], unit="D"))
    summ, ev = [], []
    for site in p1.ELEV:
        g = lambda v: np.where(z[f"{v}__{site}"][:, 5, 5] == -9999.0, np.nan, z[f"{v}__{site}"][:, 5, 5].astype("f8") - 273.15)
        tm = (g("t2mmax") + np.append(g("t2mmin")[1:], np.nan)) / 2
        for name, (flag, q, trend) in CONFIGS.items():
            sp = detect(tm, idx, flag, q, trend)
            y = idx.year.values
            sev = sp["day_cls"] >= 2
            per = lambda m, a, b: m[(y >= a) & (y <= b)].sum() / (b - a + 1)
            tot = max(sp["only_cal"] + sp["only_all"] + sp["both"], 1)
            summ.append({"cfg": name, "site": site, **p1.site_summary(sp, idx),
                         "sev_days_yr_9120": per(sev, 1991, 2020), "sev_days_yr_2125": per(sev, 2021, 2025),
                         "events_yr_9120": ((idx.year[sp["s"]] >= 1991) & (idx.year[sp["s"]] <= 2020)).sum() / 30,
                         "share_date_only": sp["only_cal"] / tot, "share_place_only": sp["only_all"] / tot,
                         "trend_K_per_decade": sp["slope10"]})
            for en, s2, a, b in p1.EVENTS:
                if s2 == site:
                    ev.append({"cfg": name, "event": en, "site": site, **event_row(sp, idx, a, b)})
    summ, ev = pd.DataFrame(summ), pd.DataFrame(ev)
    summ.round(3).to_csv(f"{res}/tune_site_summary.csv", index=False)
    ev.to_csv(f"{res}/tune_events.csv", index=False)

    C = list(CONFIGS)
    pd.set_option("display.width", 260)
    out = ["Detector D tuning, 17 single cells. Produced by validation/heat_spell_prototype/03_tune_detector.py",
           "\n== Events: flagged days in window / class / rank of the event among all events at the cell"]
    e2 = ev.assign(cell=ev.flag_days.astype(str) + "/" + ev.window_days.astype(str) + " " + ev["class"] + " #"
                   + ev.event_rank.fillna(0).astype(int).astype(str) + " of " + ev.n_events.astype(str))
    out.append(e2.pivot(index=["event", "site"], columns="cfg", values="cell")[C].to_string())
    ok = ev.assign(any=ev.flag_days > 0, sev=ev["class"].isin(["severe", "extreme"]), top5=ev.event_rank <= 5)
    out.append("\n== Of 9 events: flagged at all / severe or extreme (the pass criterion) / event in the top 5 at its cell")
    out.append(ok.groupby("cfg")[["any", "sev", "top5"]].sum().reindex(C).to_string())
    rng = lambda col: summ.groupby("cfg")[col].agg(["min", "median", "max"]).reindex(C).round(1)
    for col, title in (("days_yr_9120", "Flagged days per year 1991-2020, across the 17 cells"),
                       ("sev_days_yr_9120", "Days per year in severe or extreme events, 1991-2020"),
                       ("events_yr_9120", "Events per year, 1991-2020")):
        out.append(f"\n== {title}")
        out.append(rng(col).to_string())
    for col, title in (("days_yr_7990", "Flagged days per year, 1979-1990"), ("days_yr_9120", "Flagged days per year, 1991-2020"),
                       ("days_yr_2125", "Flagged days per year, 2021-2025"), ("sev_days_yr_2125", "Severe or extreme days per year, 2021-2025"),
                       ("cold_quarter_share", "Share of flagged days in the coldest quarter")):
        out.append(f"\n== {title}")
        out.append(summ.pivot(index="site", columns="cfg", values=col)[C].round(2).to_string())
    out.append("\n== Which test fired (ctr_p90_moving): share of flagged days from the date test only / place test only; trend removed")
    out.append(summ[summ.cfg == "ctr_p90_moving"].set_index("site")[["share_date_only", "share_place_only", "trend_K_per_decade"]].round(2).to_string())
    txt = "\n".join(out)
    with open(f"{res}/tune_summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
