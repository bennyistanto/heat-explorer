"""Are the high-exceedance patches in normal-confidence cells real warming?

01_confidence_map.py found cells with a normal anomaly spread where a third or
more of 2021-2025 days exceed an approximate 90th percentile of 1991-2020. The
three largest groups are in northern Japan, on the Bhutan-Sikkim Himalaya and
on the eastern Tibetan Plateau. Their mean shift for 2021-2025 is 1.8 to 2.6 K.

This script asks whether that shift is in the stations too.

  1. AgERA5: full-record Tmax and Tmin for a box around each patch. Annual
     anomaly of (Tmax + Tmin) / 2 for the patch cells and for the rest of the
     box; shift by month; Tmax and Tmin separately.
  2. Stations: NOAA ISD-Lite stations inside each box with a record from 1990
     or earlier to 2024 or later (up to 6 per box, those with most years).
     Daily (max + min) / 2 of hourly temperature on days with 6 or more
     observations. Monthly means need 20 such days.
  3. Same months only: station shift and AgERA5 shift (nearest land cell), and
     the mean difference AgERA5 minus station by period, to show a step.

Reading rule, written on 2026-11-21 before the run:
  REAL        the stations show at least two thirds of the AgERA5 shift, and
              AgERA5 minus station changes by less than 0.5 K between
              1991-2020 and 2021-2025
  ARTEFACT    the stations show less than one third of the shift, or the
              difference changes by 1 K or more
  MIXED       anything between
  NO EVIDENCE fewer than 2 usable stations in the box

ISD-Lite is not quality controlled, a station is a point, and station moves
are not checked. This is a first look, not a homogeneity analysis.

Run:  bash tools/py.sh -W ignore validation/confidence_map/02_patch_check.py
Output: validation/confidence_map/results/patch_check.txt, patch_stations.csv
"""
import glob
import gzip
import io
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool

import netCDF4 as nc
import numpy as np
import pandas as pd

RAW = "E:/temp/agera5"
ISD = "E:/temp/station-isd"
CONF = "E:/temp/agera5/derived-products/heat-explorer/confidence/confidence_v0.npz"
BASE = "https://noaa-isd-pds.s3.amazonaws.com/isd-lite/data"
HERE = os.path.dirname(os.path.abspath(__file__))
VARS = {"t2mmax": "Temperature_Air_2m_Max_24h", "t2mmin": "Temperature_Air_2m_Min_24h"}
YEARS = range(1979, 2026)
BOXES = {  # name: (lat_min, lat_max, lon_min, lon_max), each patch plus about 1.5 degrees
    "Northern Japan": (36.5, 45.6, 138.0, 146.0),
    "Bhutan-Sikkim Himalaya": (26.0, 30.0, 86.5, 91.5),
    "Eastern Tibetan Plateau": (31.0, 37.0, 94.0, 102.0),
}


def idx(b):
    a0, a1, o0, o1 = b
    return (int(round((90 - a1) / 0.1)), int(round((90 - a0) / 0.1)) + 1,
            int(round((o0 + 180) / 0.1)), int(round((o1 + 180) / 0.1)) + 1)


def job(a):
    v, y = a
    d = nc.Dataset(f"{RAW}/{v}/agera5_{v}_{y}.nc")
    d.set_auto_mask(False)
    x = d.variables[VARS[v]]
    t = np.asarray(d.variables["time"][:])
    out = {}
    for k, b in BOXES.items():
        i0, i1, j0, j1 = idx(b)
        out[k] = np.asarray(x[:, i0:i1, j0:j1])
    d.close()
    return v, y, t, out


def fetch(j):
    usaf, wban, y = j
    dst = f"{ISD}/raw/{usaf}-{wban}-{y}.gz"
    if os.path.exists(dst):
        return
    try:
        with urllib.request.urlopen(f"{BASE}/{y}/{usaf}-{wban}-{y}.gz", timeout=60) as r:
            data = r.read()
        with open(dst + ".part", "wb") as f:
            f.write(data)
        os.replace(dst + ".part", dst)
    except Exception:
        pass


def station_daily(usaf, wban, lon):
    parts = []
    for fn in sorted(glob.glob(f"{ISD}/raw/{usaf}-{wban}-*.gz")):
        with gzip.open(fn, "rt") as f:
            txt = f.read()
        if txt.strip():
            parts.append(pd.read_csv(io.StringIO(txt), sep=r"\s+", header=None, usecols=range(5), names=["y", "m", "d", "h", "t"]))
    if not parts:
        return None
    d = pd.concat(parts, ignore_index=True)
    d = d[(d.t != -9999)]
    t = pd.Series(d.t.values / 10.0, index=pd.to_datetime(dict(year=d.y, month=d.m, day=d.d, hour=d.h)) + pd.Timedelta(hours=int(round(lon / 15.0))))
    t = t[t.between(-70, 58)]
    g = t.groupby(t.index.floor("D"))
    ok = g.size() >= 6
    return ((g.max() + g.min()) / 2)[ok]


def monthly(s, need=20):
    g = s.groupby([s.index.year, s.index.month])
    m = g.mean()[g.count() >= need]
    m.index = pd.PeriodIndex([pd.Period(year=y, month=mo, freq="M") for y, mo in m.index], freq="M")
    return m


def anom(m):
    b = m[(m.index.year >= 1991) & (m.index.year <= 2020)]
    clim = b.groupby(b.index.month).mean()
    n = b.groupby(b.index.month).count()
    clim = clim[n >= 15]
    return (m - clim.reindex(m.index.month).values).dropna()


def per(a, y0, y1):
    x = a[(a.index.year >= y0) & (a.index.year <= y1)]
    return float(x.mean()) if len(x) >= 12 else np.nan


if __name__ == "__main__":
    t0 = time.time()
    res = os.path.join(HERE, "results")
    z = np.load(CONF)
    sdg, excg = z["sd"], z["exc_recent"]
    with Pool(32) as p:
        got = {(v, y): (t, o) for v, y, t, o in p.imap_unordered(job, [(v, y) for y in YEARS for v in VARS])}
    tt = np.concatenate([got[("t2mmax", y)][0] for y in YEARS])
    dates = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(tt, unit="D"))
    print(f"read {time.time() - t0:.0f} s", flush=True)

    h = pd.read_csv(f"{ISD}/isd-history.csv", dtype=str)
    for c in ("LAT", "LON", "ELEV(M)"):
        h[c] = pd.to_numeric(h[c], errors="coerce")
    h = h.rename(columns={"STATION NAME": "NAME", "ELEV(M)": "ELEV"})
    h["b"], h["e"] = h.BEGIN.str[:4].astype(int), h.END.str[:4].astype(int)
    out = ["Patch check. Produced by validation/confidence_map/02_patch_check.py",
           "Anomalies are monthly, relative to 1991-2020, of daily (Tmax + Tmin) / 2. Shift = mean anomaly 2021-2025.", ""]
    strows = []
    for name, b in BOXES.items():
        a0, a1, o0, o1 = b
        i0, i1, j0, j1 = idx(b)
        cat = lambda v: np.concatenate([got[(v, y)][1][name] for y in YEARS]).astype("f4")
        tx, tn = cat("t2mmax"), cat("t2mmin")
        land = tx[0] != -9999.0
        tx, tn = np.where(tx < 100, np.nan, tx - 273.15), np.where(tn < 100, np.nan, tn - 273.15)
        sat = land & (sdg[i0:i1, j0:j1] >= 1.5) & (excg[i0:i1, j0:j1] >= 0.33)
        rest = land & ~sat & (excg[i0:i1, j0:j1] < 0.25)
        out.append(f"== {name}: box {a0}-{a1} N, {o0}-{o1} E; land cells {int(land.sum())}, patch cells {int(sat.sum())}, comparison cells (exc < 0.25) {int(rest.sum())}")
        for lab, x in (("mean", (tx + tn) / 2), ("Tmax", tx), ("Tmin", tn)):
            ps, rs = (anom(monthly(pd.Series(np.nanmean(x[:, m], axis=1), index=dates))) for m in (sat, rest))
            line = f"  AgERA5 {lab:4s} patch / rest of box, K:"
            for y0, y1 in ((1979, 1990), (1991, 2000), (2001, 2010), (2011, 2020), (2021, 2025)):
                line += f"  {y0}-{str(y1)[2:]} {per(ps, y0, y1):+.2f} / {per(rs, y0, y1):+.2f}"
            out.append(line)
            if lab == "mean":
                yr = ps.groupby(ps.index.year).mean()
                out.append("  patch annual anomaly 2012-2025: " + " ".join(f"{y}:{v:+.1f}" for y, v in yr.loc[2012:2025].items()))
                rec = ps[ps.index.year >= 2021]
                out.append("  patch shift by month 2021-2025: " + " ".join(f"{m}:{v:+.1f}" for m, v in rec.groupby(rec.index.month).mean().items()))
        # stations
        c = h[(h.b <= 1990) & (h.e >= 2024) & h.LAT.between(a0, a1) & h.LON.between(o0, o1)].copy()
        c["span"] = c.e - c.b
        c = c.sort_values("span", ascending=False).drop_duplicates("USAF")
        # prefer stations near patch cells
        ii, jj = np.nonzero(sat)
        plat, plon = 90 - 0.1 * (ii + i0), -180 + 0.1 * (jj + j0)
        c["dist"] = [float(np.min(np.hypot(plat - la, (plon - lo) * np.cos(np.deg2rad(la)))) * 111) for la, lo in zip(c.LAT, c.LON)]
        c = c.sort_values("dist").head(6)
        with ThreadPoolExecutor(16) as ex:
            list(ex.map(fetch, [(r.USAF, r.WBAN, y) for r in c.itertuples() for y in YEARS]))
        used, ratios, dsteps = 0, [], []
        for r in c.itertuples():
            sd_ = station_daily(r.USAF, r.WBAN, r.LON)
            if sd_ is None:
                continue
            ci, cj = int(round((90 - r.LAT) / 0.1)) - i0, int(round((r.LON + 180) / 0.1)) - j0
            if not (0 <= ci < land.shape[0] and 0 <= cj < land.shape[1]) or not land[ci, cj]:
                continue
            ag = pd.Series((tx[:, ci, cj] + tn[:, ci, cj]) / 2, index=dates)
            both = pd.concat([sd_.rename("s"), ag.rename("a")], axis=1).dropna()
            ms, ma = monthly(both.s), monthly(both.a)
            common = ms.index.intersection(ma.index)
            as_, aa = anom(ms[common]), anom(ma[common])
            common = as_.index.intersection(aa.index)
            as_, aa = as_[common], aa[common]
            ss, sa = per(as_, 2021, 2025), per(aa, 2021, 2025)
            if np.isnan(ss) or np.isnan(sa):
                continue
            dd = aa - as_
            dstep = per(dd, 2021, 2025) - per(dd, 1991, 2020)
            used += 1
            ratios.append(ss / sa if sa > 0.3 else np.nan)
            dsteps.append(dstep)
            n21 = int((common.year >= 2021).sum())
            out.append(f"  station {r.USAF} {str(r.NAME).strip()[:22]:22s} {r.LAT:.2f}N {r.LON:.2f}E {r.ELEV:.0f} m, {r.dist:.0f} km from patch, cell exc {excg[ci + i0, cj + j0]:.2f}: "
                       f"shift station {ss:+.2f} K, AgERA5 {sa:+.2f} K ({n21} months); AgERA5 minus station by period "
                       + " ".join(f"{y0}-{str(y1)[2:]} {per(dd, y0, y1):+.2f}" for y0, y1 in ((1991, 2000), (2001, 2010), (2011, 2020), (2021, 2025))))
            strows.append({"patch": name, "usaf": r.USAF, "wban": r.WBAN, "name": str(r.NAME).strip(), "lat": r.LAT, "lon": r.LON,
                           "elev_m": r.ELEV, "km_from_patch": round(r.dist), "shift_station": round(ss, 2), "shift_agera5": round(sa, 2),
                           "diff_step": round(dstep, 2), "months_2021_25": n21})
        if used < 2:
            verdict = "NO EVIDENCE"
        else:
            rr, ds = np.nanmedian(ratios), np.nanmedian(np.abs(dsteps))
            verdict = "REAL" if (rr >= 2 / 3 and ds < 0.5) else ("ARTEFACT" if (rr < 1 / 3 or ds >= 1.0) else "MIXED")
            out.append(f"  stations used {used}; median station/AgERA5 shift ratio {rr:.2f}; median absolute change in the difference {ds:.2f} K")
        out.append(f"  VERDICT by the rule written first: {verdict}")
        out.append("")
    pd.DataFrame(strows).to_csv(f"{res}/patch_stations.csv", index=False)
    out.append(f"total {time.time() - t0:.0f} s")
    txt = "\n".join(out)
    with open(f"{res}/patch_check.txt", "w") as f:
        f.write(txt + "\n")
    print(txt)
