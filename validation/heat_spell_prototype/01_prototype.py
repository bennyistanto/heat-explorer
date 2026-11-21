"""Prototype of the design v2 heat spell on 17 single AgERA5 cells.

Tests the rule in references/indicators.md (signal 1) and chooses the
warm-season floor by running several variants against documented events.

Rule under test
  Tm(d)   = (Tmax(d) + Tmin(d+1)) / 2
  hot day = Tm above its calendar-day 90th percentile (15-day window, 1991-2020,
            seasonal cycle removed before the percentile) AND the floor
  spell   = run of at least 3 hot days
  magnitude per day = (Tm - threshold) / IQR of baseline anomalies; summed per spell
  severity = spell, severe, extreme by the 80th and 95th percentile of baseline
             spell magnitudes at the cell (project choice)

Floor variants
  none     no floor
  p50/p75/p90   centred 3-day mean of Tm above that all-year percentile of baseline Tm
  season   day-of-year climatological mean of Tm above the cell's annual median

The same rule is run on afternoon wet-bulb (Tmax with daily mean dewpoint,
pressure from an assumed site elevation) as the humid heat spell.

Input: hx_cells.npz (11 x 11 windows at 17 sites; the centre cell is used).
Single cells only: this shows how the rule behaves, it is not the adm1 event suite.

Run:  bash tools/py.sh -W ignore validation/heat_spell_prototype/01_prototype.py
Output: validation/heat_spell_prototype/results/
"""
import importlib.util
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CELLS = "E:/temp/agera5/derived-products/heat-explorer/critique-2026-11-20/hx_cells.npz"
spec = importlib.util.spec_from_file_location("cmp03", os.path.join(HERE, "..", "wetbulb_gate", "03_compare.py"))
c3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c3)

ELEV = {"Singapore": 15, "Jakarta": 10, "Lagos": 20, "Manaus": 60, "Delhi": 215, "Jacobabad": 55,
        "Hyderabad_IN": 540, "Dhahran": 20, "Phoenix": 340, "Paris": 60, "Moscow": 150,
        "Portland_OR": 30, "Sydney_W": 40, "Nairobi": 1700, "LaPaz": 3800, "Verkhoyansk": 140, "DomeC": 3230}
# same windows as the 2026-11-20 critique, so results are comparable with EHF
EVENTS = [("Europe Aug 2003", "Paris", "2003-08-01", "2003-08-15"),
          ("Russia 2010", "Moscow", "2010-07-10", "2010-08-20"),
          ("India May 2015", "Hyderabad_IN", "2015-05-18", "2015-06-03"),
          ("India May 2015", "Delhi", "2015-05-18", "2015-06-03"),
          ("India-Pakistan 2022", "Delhi", "2022-03-10", "2022-05-20"),
          ("India-Pakistan 2022", "Jacobabad", "2022-03-10", "2022-05-20"),
          ("Pacific NW Jun 2021", "Portland_OR", "2021-06-25", "2021-06-30"),
          ("SE Australia 2019-20", "Sydney_W", "2019-12-15", "2020-02-05"),
          ("Siberia Jun 2020", "Verkhoyansk", "2020-06-15", "2020-06-30")]
FLOORS = ["none", "p50", "p75", "p90", "season"]
BASE = (1991, 2020)


def doy365(idx):
    """Day of year on a 365-day calendar; 29 Feb shares 28 Feb."""
    d = idx.dayofyear.values.copy()
    leap = idx.is_leap_year
    d[leap & (d >= 60)] -= 1
    return d


def smooth_clim(x, doy, base, win=31):
    c = pd.Series(x[base]).groupby(doy[base]).mean().reindex(range(1, 366)).interpolate(limit_direction="both")
    h = win // 2
    w = pd.concat([c.iloc[-h:], c, c.iloc[:h]]).rolling(win, center=True).mean().iloc[h:-h]
    return w.values  # index 0 is day 1


def thresholds(x, idx):
    """Calendar-day p90 with the seasonal cycle removed first. Returns threshold, clim, IQR."""
    doy = doy365(idx)
    base = (idx.year >= BASE[0]) & (idx.year <= BASE[1]) & np.isfinite(x)
    clim = smooth_clim(x, doy, base)
    anom = x - clim[doy - 1]
    p90 = np.empty(365)
    ab, db = anom[base], doy[base]
    for d in range(1, 366):
        dist = np.abs(db - d)
        p90[d - 1] = np.percentile(ab[np.minimum(dist, 365 - dist) <= 7], 90)
    q25, q75 = np.percentile(ab, [25, 75])
    return clim[doy - 1] + p90[doy - 1], clim, q75 - q25, base


def runs(flag, min_len=3):
    """Start and end (inclusive) indices of runs of True at least min_len long."""
    f = np.concatenate([[0], flag.astype(int), [0]])
    d = np.diff(f)
    s, e = np.where(d == 1)[0], np.where(d == -1)[0] - 1
    k = (e - s + 1) >= min_len
    return s[k], e[k]


def spells(x, idx, floor):
    thr, clim, iqr, base = thresholds(x, idx)
    doy = doy365(idx)
    hot = x > thr
    if floor in ("p50", "p75", "p90"):
        lvl = np.percentile(x[base], int(floor[1:]))
        m3 = pd.Series(x).rolling(3, center=True, min_periods=2).mean().values
        hot &= m3 > lvl
    elif floor == "season":
        hot &= (clim > np.median(clim))[doy - 1]
    hot &= np.isfinite(x)
    s, e = runs(hot)
    mag_day = np.where(hot, (x - thr) / iqr, 0.0)
    mag = np.array([mag_day[a:b + 1].sum() for a, b in zip(s, e)])
    inbase = (idx.year[s] >= BASE[0]) & (idx.year[s] <= BASE[1])
    q80, q95 = (np.percentile(mag[inbase], [80, 95]) if inbase.sum() >= 5 else (np.inf, np.inf))
    cls = 1 + (mag >= q80).astype(int) + (mag >= q95).astype(int)
    day_cls = np.zeros(len(x), int)
    for a, b, c in zip(s, e, cls):
        day_cls[a:b + 1] = c
    return {"day_cls": day_cls, "s": s, "e": e, "mag": mag, "cls": cls, "clim": clim, "doy": doy}


def site_summary(sp, idx):
    y = idx.year.values
    in_spell = sp["day_cls"] > 0
    per = lambda a, b: in_spell[(y >= a) & (y <= b)].sum() / (b - a + 1)
    cold = np.argsort(sp["clim"])[:91] + 1            # coldest quarter by climatology
    return {"days_yr_7990": per(1979, 1990), "days_yr_9120": per(1991, 2020), "days_yr_2125": per(2021, 2025),
            "spells_yr_9120": ((idx.year[sp["s"]] >= 1991) & (idx.year[sp["s"]] <= 2020)).sum() / 30,
            "cold_quarter_share": float(np.isin(sp["doy"][in_spell], cold).mean()) if in_spell.any() else 0.0,
            "zero_years": int(sum(in_spell[y == yr].sum() == 0 for yr in range(1979, 2026)))}


def event_row(sp, idx, a, b):
    w = (idx >= a) & (idx <= b)
    yr_of = idx.year[sp["s"]].values
    ann = pd.Series(sp["mag"]).groupby(yr_of).sum().reindex(range(1979, 2027), fill_value=0.0)
    ey = pd.Timestamp(a).year
    hit = [k for k, (s, e) in enumerate(zip(sp["s"], sp["e"])) if (idx[e] >= pd.Timestamp(a)) and (idx[s] <= pd.Timestamp(b))]
    names = {0: "none", 1: "spell", 2: "severe", 3: "extreme"}
    return {"spell_days": int((sp["day_cls"][w] > 0).sum()), "window_days": int(w.sum()),
            "class": names[int(sp["day_cls"][w].max())],
            "event_mag": float(sum(sp["mag"][k] for k in hit)),
            "year_rank_by_cum_mag": int((ann > ann[ey]).sum() + 1) if ann[ey] > 0 else 48}


if __name__ == "__main__":
    res = os.path.join(HERE, "results")
    os.makedirs(res, exist_ok=True)
    z = np.load(CELLS)
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(z["time"], unit="D"))

    def series(site):
        g = lambda v: np.where(z[f"{v}__{site}"][:, 5, 5] == -9999.0, np.nan, z[f"{v}__{site}"][:, 5, 5].astype("f8") - 273.15)
        tx, tn, td = g("t2mmax"), g("t2mmin"), g("t2mdp")
        tm = (tx + np.append(tn[1:], np.nan)) / 2
        tw = c3.wetbulb(tx, c3.esat(td), c3.pressure(ELEV[site]))
        return tm, tw

    data = {s: series(s) for s in ELEV}
    summ, ev, hum = [], [], []
    for floor in FLOORS:
        for site, (tm, tw) in data.items():
            sp = spells(tm, idx, floor)
            summ.append({"floor": floor, "site": site, **site_summary(sp, idx)})
            for name, s2, a, b in EVENTS:
                if s2 == site:
                    ev.append({"floor": floor, "event": name, "site": site, **event_row(sp, idx, a, b)})
    for site, (tm, tw) in data.items():       # humid spell with the season floor
        st, sw = spells(tm, idx, "season"), spells(tw, idx, "season")
        a, b = st["day_cls"] > 0, sw["day_cls"] > 0
        mon = pd.Series(idx.month[b]).value_counts().head(2).index.tolist() if b.any() else []
        hum.append({"site": site, **{f"tw_{k}": v for k, v in site_summary(sw, idx).items()},
                    "share_also_temp_spell": float((a & b).sum() / max(b.sum(), 1)), "peak_months": mon})
    summ, ev, hum = pd.DataFrame(summ), pd.DataFrame(ev), pd.DataFrame(hum)
    summ.round(3).to_csv(f"{res}/site_summary.csv", index=False)
    ev.round(3).to_csv(f"{res}/events.csv", index=False)
    hum.round(3).to_csv(f"{res}/humid_spell.csv", index=False)

    pd.set_option("display.width", 250)
    out = ["Heat spell prototype, 17 single cells. Produced by validation/heat_spell_prototype/01_prototype.py",
           "\n== Events by floor variant: spell days in window / class / rank of the year by cumulative magnitude (of 48)"]
    e2 = ev.assign(cell=ev.spell_days.astype(str) + "/" + ev.window_days.astype(str) + " " + ev["class"] + " #" + ev.year_rank_by_cum_mag.astype(str))
    out.append(e2.pivot(index=["event", "site"], columns="floor", values="cell")[FLOORS].to_string())
    out.append("\n== Events passed (class severe or extreme AND year in top 3), of 9")
    ok = ev.assign(ok=ev["class"].isin(["severe", "extreme"]) & (ev.year_rank_by_cum_mag <= 3))
    out.append(ok.groupby("floor").ok.sum().reindex(FLOORS).to_string())
    for col, title in (("days_yr_9120", "Spell days per year, 1991-2020"), ("cold_quarter_share", "Share of spell days in the coldest quarter"),
                       ("zero_years", "Years with no spell day, of 47")):
        out.append(f"\n== {title}")
        out.append(summ.pivot(index="site", columns="floor", values=col)[FLOORS].round(2).to_string())
    out.append("\n== Trend check, floor = season: spell days per year")
    out.append(summ[summ.floor == "season"].set_index("site")[["days_yr_7990", "days_yr_9120", "days_yr_2125", "spells_yr_9120"]].round(1).to_string())
    out.append("\n== Humid heat spell (wet-bulb, floor = season)")
    out.append(hum.set_index("site")[["tw_days_yr_7990", "tw_days_yr_9120", "tw_days_yr_2125", "tw_cold_quarter_share", "share_also_temp_spell", "peak_months"]].round(2).to_string())
    txt = "\n".join(out)
    with open(f"{res}/summary.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
