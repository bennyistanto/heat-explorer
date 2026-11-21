"""Is the 2008 break around the Tsugaru Strait a step in AgERA5?

01_step_screen.py flagged 104 cells at 41-42 N, 139.7-141.6 E with a break in
2008. If AgERA5 really steps there, the screen was right to flag them and
target T2 (leave northern Japan alone) was the wrong test.

Data: NOAA ISD-Lite stations in 40.3-43.3 N, 139-142.6 E with records from
1990 or earlier to 2024 or later; AgERA5 Tmax and Tmin at each station's cell.
Series: monthly mean of daily (max + min) / 2, AgERA5 minus station, with the
mean annual cycle of the difference removed.

For each station two models are fitted to the monthly difference, 1985-2025:
  step   two means with one break (break month searched, 5 years each side)
  drift  a straight line
and compared by BIC (the step model is charged 3 parameters, the line 2).

Reading rule, written on 2026-11-21 before the run:
  A station shows a STEP when the step model beats the line by 10 BIC units
  or more and the step is 0.5 K or more.
  AGERA5 STEP IN 2008 if at least 2 stations whose cell is flagged show a
  step with the break in 2007 to 2009, AND no more than 1 station whose cell
  is not flagged does, AND the difference between pairs of those in-group
  stations themselves (station minus station) shows no step of 0.5 K in 2007
  to 2009 (which would point at the stations, not AgERA5).
  Otherwise NOT SHOWN.

Limits: ISD-Lite is not quality controlled; station histories (moves,
instrument changes) are not consulted; several stations changing in the same
year would defeat the station-pair check.

Run:  bash tools/py.sh -W ignore validation/step_screen/02_tsugaru_check.py
Output: validation/step_screen/results/tsugaru_check.txt
"""
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool

import netCDF4 as nc
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = "E:/temp/agera5"
ISD = "E:/temp/station-isd"
SCREEN = "E:/temp/agera5/derived-products/heat-explorer/step-screen/step_screen_v0.npz"
VARS = {"t2mmax": "Temperature_Air_2m_Max_24h", "t2mmin": "Temperature_Air_2m_Min_24h"}
YEARS = range(1979, 2026)
BOX = (40.3, 43.3, 139.0, 142.6)
I0, I1 = int(round((90 - BOX[1]) / 0.1)), int(round((90 - BOX[0]) / 0.1)) + 1
J0, J1 = int(round((BOX[2] + 180) / 0.1)), int(round((BOX[3] + 180) / 0.1)) + 1


def job(a):
    v, y = a
    d = nc.Dataset(f"{RAW}/{v}/agera5_{v}_{y}.nc")
    d.set_auto_mask(False)
    x = np.asarray(d.variables[VARS[v]][:, I0:I1, J0:J1])
    t = np.asarray(d.variables["time"][:])
    d.close()
    return v, y, t, x


def fit(s):
    """Step against line on a monthly series. Returns dict."""
    s = s[(s.index.year >= 1985)]
    y = s.values.astype("f8")
    t = (s.index.year + (s.index.month - 0.5) / 12).values
    n = len(y)
    if n < 240:
        return None
    best = (np.inf, None, 0.0)
    for k in range(60, n - 60):
        m1, m2 = y[:k].mean(), y[k:].mean()
        sse = ((y[:k] - m1) ** 2).sum() + ((y[k:] - m2) ** 2).sum()
        if sse < best[0]:
            best = (sse, k, m2 - m1)
    p = np.polyfit(t, y, 1)
    sse_l = ((y - np.polyval(p, t)) ** 2).sum()
    bic_s = n * np.log(best[0] / n) + 3 * np.log(n)
    bic_l = n * np.log(sse_l / n) + 2 * np.log(n)
    return {"n": n, "break": str(s.index[best[1]]), "break_year": s.index[best[1]].year, "step": best[2],
            "line_K_per_decade": p[0] * 10, "bic_gain": bic_l - bic_s}


if __name__ == "__main__":
    spec = importlib.util.spec_from_file_location("pc", os.path.join(HERE, "..", "confidence_map", "02_patch_check.py"))
    pc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pc)
    z = np.load(SCREEN)
    flag, brk = z["suspect"], z["break_year"]
    with Pool(32) as p:
        got = {(v, y): (t, x) for v, y, t, x in p.imap_unordered(job, [(v, y) for y in YEARS for v in VARS])}
    dates = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(np.concatenate([got[("t2mmax", y)][0] for y in YEARS]), unit="D"))
    tx = np.concatenate([got[("t2mmax", y)][1] for y in YEARS]).astype("f4")
    tn = np.concatenate([got[("t2mmin", y)][1] for y in YEARS]).astype("f4")
    land = tx[0] != -9999.0

    h = pd.read_csv(f"{ISD}/isd-history.csv", dtype=str).rename(columns={"STATION NAME": "NAME", "ELEV(M)": "ELEV"})
    for c in ("LAT", "LON"):
        h[c] = pd.to_numeric(h[c], errors="coerce")
    h["b"], h["e"] = h.BEGIN.str[:4].astype(int), h.END.str[:4].astype(int)
    c = h[(h.b <= 1990) & (h.e >= 2024) & h.LAT.between(BOX[0], BOX[1]) & h.LON.between(BOX[2], BOX[3])].copy()
    c = c.sort_values("b").drop_duplicates("USAF")
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(pc.fetch, [(r.USAF, r.WBAN, y) for r in c.itertuples() for y in YEARS]))

    out = ["Tsugaru Strait check. Produced by validation/step_screen/02_tsugaru_check.py",
           "Monthly AgERA5 minus station, annual cycle of the difference removed, 1985-2025. bic_gain > 10 favours a step over a line.", ""]
    rows, stn = [], {}
    for r in c.itertuples():
        ci, cj = int(round((90 - r.LAT) / 0.1)), int(round((r.LON + 180) / 0.1))
        if not (I0 <= ci < I1 and J0 <= cj < J1) or not land[ci - I0, cj - J0]:
            continue
        sd = pc.station_daily(r.USAF, r.WBAN, r.LON)
        if sd is None:
            continue
        ag = pd.Series((tx[:, ci - I0, cj - J0] + tn[:, ci - I0, cj - J0]) / 2 - 273.15, index=dates)
        both = pd.concat([sd.rename("s"), ag.rename("a")], axis=1).dropna()
        ms, ma = pc.monthly(both.s), pc.monthly(both.a)
        d = (ma - ms).dropna()
        d = d - d.groupby(d.index.month).transform("mean")
        f = fit(d)
        if f is None:
            continue
        stn[r.USAF] = (str(r.NAME).strip(), ms, bool(flag[ci, cj]))
        is_step = f["bic_gain"] >= 10 and abs(f["step"]) >= 0.5
        yr = d.groupby(d.index.year).mean()
        rows.append({"usaf": r.USAF, "name": str(r.NAME).strip()[:20], "lat": r.LAT, "lon": r.LON, "cell_flagged": bool(flag[ci, cj]),
                     "cell_break": int(brk[ci, cj]), "break": f["break"], "step_K": round(f["step"], 2),
                     "line_K_dec": round(f["line_K_per_decade"], 2), "bic_gain": round(f["bic_gain"], 1), "STEP": is_step,
                     "in_2007_09": is_step and 2007 <= f["break_year"] <= 2009,
                     "annual_2003_2013": " ".join(f"{v:+.1f}" for v in yr.reindex(range(2003, 2014)).values)})
    t = pd.DataFrame(rows).sort_values(["cell_flagged", "lat"], ascending=[False, True])
    pd.set_option("display.width", 320, "display.max_columns", 30, "display.max_colwidth", 80)
    out.append(t.to_string(index=False))
    out.append("\n(annual_2003_2013: yearly mean of AgERA5 minus station, K, for 2003 to 2013)")

    ing = t[t.cell_flagged].usaf.tolist()
    out.append("\n== Station minus station, pairs of stations whose cells are flagged")
    pair_step = False
    for i in range(len(ing)):
        for j in range(i + 1, len(ing)):
            d = (stn[ing[i]][1] - stn[ing[j]][1]).dropna()
            d = d - d.groupby(d.index.month).transform("mean")
            f = fit(d)
            if f is None:
                continue
            s = f["bic_gain"] >= 10 and abs(f["step"]) >= 0.5 and 2007 <= f["break_year"] <= 2009
            pair_step |= s
            out.append(f"  {stn[ing[i]][0][:16]:16s} minus {stn[ing[j]][0][:16]:16s}: best break {f['break']}, step {f['step']:+.2f} K, bic_gain {f['bic_gain']:.1f}{'  <- step in 2007-09' if s else ''}")
    n_in = int(t[t.cell_flagged].in_2007_09.sum())
    n_out = int(t[~t.cell_flagged].in_2007_09.sum())
    verdict = "AGERA5 STEP IN 2008" if (n_in >= 2 and n_out <= 1 and not pair_step) else "NOT SHOWN"
    out.append(f"\nStations on flagged cells with a step in 2007-09: {n_in} of {int(t.cell_flagged.sum())}; on unflagged cells: {n_out} of {int((~t.cell_flagged).sum())}; station-pair step in 2007-09: {pair_step}")
    out.append(f"VERDICT by the rule written first: {verdict}")
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "tsugaru_check.txt"), "w") as f:
        f.write(txt + "\n")
    print(txt)
