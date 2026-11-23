"""Web data products: what the static page fetches.

Reads the heat-state store and the admin series (both outside the repository)
and writes site/data/ (gitignored), the data folder of the Observable Framework
site, with files.js, the list of files Framework is to publish. Nothing here is
published by this script.

Latest date: the centred 3-day mean of day d needs the minimum of day d+2, so
the last two days of the record cannot be classed. The store holds 0 for them.
Every product here stops two days before the end of the record.

    manifest.json                 dates, parameters, counts, file list with sizes
    latest.json                   shares and status tier of every country and province on the latest date
    admins.json                   countries and provinces: ids, names, parent, cells, area, licence
    static/mask.png               palette PNG, 3600 x 1801: bit 0 low confidence, bit 1 reduced
                                  confidence, bit 2 data suspect; 255 sea
    static/adm2.png               RGB PNG: district row index + 1 packed in 24 bits, 0 none
    static/adm2_parent.dat        uint16 per district row: row index of its province
    static/countries.json         country lines and name points, for drawing only (pipeline/web_outlines.py)
    static/coast.json,            coastline and borders between provinces of one country, for drawing only
    static/provinces.json         (pipeline/web_lines.py)
    daily/YYYY-MM-DD.png          8-bit PNG, one per day of the recent window (365 days) and of each past event. Bits 0-1: class shown
                                  under live labelling (0 none, 1 heat spell, 2 severe, 3 extreme).
                                  Bits 2-7: day of the spell, capped at 62 (shown from day 3). 255 sea
    annual/spell_YYYY.png,        8-bit PNG: days in the year in a heat spell / severe or extreme
    annual/severe_YYYY.png        (class of the day, not live labelling); 254 = 254 or more, 255 sea
    admin/<adm0_id>.dat           country and its provinces: daily share in a heat spell since 1979
                                  (uint8 percent), severe and extreme for the last 365 days,
                                  heat spell area-days per year (uint16, x 10), hot day and hot night
                                  shares for the last 180 days when run_daynight.py has been run, and daily
                                  degree-days for the last 365 days (uint16, x 1000)
    admin2/<adm0_id>.dat          its districts: three shares for the last 90 days, and per year the
                                  spell and severe area-days (uint16, x 10)
    static/trend.png              trend in heat spell days per year, 3 by 3 blocks: 0 no significant trend,
                                  1 to 254 slope as (v - 128) / 2 days per decade, 255 sea (pipeline/trend.py)
    static/season.png             season status on the last date: 0 none, 1 new this week, 2 again after a break,
                                  5 no longer in a spell, 10 + N still in one for N weeks, 255 sea
    humid/YYYY-MM-DD.png          EXPERIMENTAL. 8-bit PNG: 1 in a humid heat spell (live labelling), 0 not, 255 sea;
                                  static/mask_humid.png is this layer's own confidence mask (bit 0 low, bit 1 reduced)
    monthly/spell_YYYY-MM.png,    8-bit PNG: days in the month in a heat spell / severe or extreme (class of the
    monthly/severe_YYYY-MM.png    day, not live labelling), every complete month since 1979-01; 255 sea
    admin_arch/<adm0_id>.dat      the day-keyed numbers of admin/<id>.dat (severe, extreme, degree-days, hot day and
                                  night, humid) for the days of the past events listed in config/archive_events.csv
    weekly/wNN.png                8-bit PNG: highest class shown on any day of the week (0 to 3), 255 sea;
                                  w00 is the week ending on the last day. Dates are in the manifest
    events/<adm0_id>.json         events of the country and its provinces: start, days, peak share,
                                  size in degree-days
    (.dat and not .bin: download managers take .bin files away from the browser)
    .dat layout: uint32 little-endian header length, UTF-8 JSON header, then the arrays the
    header lists, in order, with no padding.

Not built here, and why: trend and season layers (classes not defined), hot
spot layer (gate not run), humid layer (not built), the space-time cube files,
district events, unit outlines (the page can outline a unit from the id
raster), the largest-patch number.

Shares are whole percents rounded down. Antarctica gets no series.
Units below the cell-count floor get no series or events; the page shows the
clicked cell and the parent instead. The count is in the manifest.

Run:  bash tools/py.sh -W ignore pipeline/web_products.py
"""
import gzip
import json
import os
import shutil
import struct
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
import zarr
from PIL import Image

import periods as PER          # pipeline/periods.py: which days the daily map can show
import trend as TRD            # pipeline/trend.py, beside this script

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DP = "E:/temp/agera5/derived-products/heat-explorer"
V1 = f"{DP}/v1"
DST = os.path.join(ROOT, "site", "data")
NLAT, NLON, TR, TC = 1801, 3600, 200, 400
WINDOW, TRAIL1, TRAIL2 = PER.RECENT, 365, 90   # daily layers of the recent window; province trailing days; district trailing days
FLOOR = 9                                   # land cells below which a unit gets no area shares (set by the author, 2026-11-22)
SHARE_DAY, GAP, MIN_DAYS = 0.25, 2, 3       # event rule (not frozen)
TIER = (0.25, 0.50)                         # severe share: part of the area (setting), most of the area (frozen)
PAL = [231, 230, 225, 240, 190, 140, 217, 120, 60, 116, 41, 12, 251, 250, 247]
_G = {}


def init(T, starts, m_end, mstarts):
    _G["c"] = zarr.open_group(f"{V1}/heat_state.zarr", mode="r")["cls_day"]
    _G["T"], _G["starts"], _G["m_end"], _G["mstarts"] = T, starts, m_end, mstarts


def tile_annual(a):
    r0, c0 = a
    r1, c1 = min(r0 + TR, NLAT), min(c0 + TC, NLON)
    c = _G["c"][:max(_G["T"], _G["m_end"]), r0:r1, c0:c1]
    if (c[0] == 255).all():
        return r0, c0, None, None, None, None
    s1, s2 = (c >= 1) & (c <= 3), (c >= 2) & (c <= 3)
    sp = np.add.reduceat(s1[:_G["T"]].astype("u2"), _G["starts"], axis=0)                 # days per year
    sv = np.add.reduceat(s2[:_G["T"]].astype("u2"), _G["starts"], axis=0)
    msp = np.add.reduceat(s1[:_G["m_end"]].astype("u1"), _G["mstarts"], axis=0)           # days per month, at most 31
    msv = np.add.reduceat(s2[:_G["m_end"]].astype("u1"), _G["mstarts"], axis=0)
    return r0, c0, sp, sv, msp, msv


def events(on):
    idx = np.flatnonzero(on)
    if idx.size == 0:
        return []
    brk = np.flatnonzero(np.diff(idx) > GAP + 1)
    lo, hi = np.r_[idx[0], idx[brk + 1]], np.r_[idx[brk], idx[-1]]
    return [(int(s), int(e)) for s, e in zip(lo, hi) if on[s:e + 1].sum() >= MIN_DAYS]


def pct(x):
    # rounded DOWN to a whole percent, so that 50 and 25 on the page mean the share really reached 0.50 and 0.25
    return np.where(x == 65535, 255, np.minimum(x, 10000) // 100).astype("u1")


def write_bin(path, header, arrays):
    h = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(path, "wb") as f:
        f.write(struct.pack("<I", len(h)))
        f.write(h)
        for a in arrays:
            f.write(np.ascontiguousarray(a).tobytes())


def save_p(arr, path):
    im = Image.fromarray(arr, "P")
    im.putpalette(PAL + [0] * (768 - len(PAL)))
    im.save(path, optimize=True)


if __name__ == "__main__":
    t0 = time.time()
    # site/data is inside OneDrive, which can hold a lock on a folder while it syncs: remove the old
    # files one by one and keep the folders, so a locked folder cannot stop the build
    for dp, _, fs in os.walk(DST):
        for fn in fs:
            os.remove(os.path.join(dp, fn))
    for d in ("static", "daily", "weekly", "humid", "annual", "monthly", "admin", "admin_arch", "admin2", "events"):
        os.makedirs(os.path.join(DST, d), exist_ok=True)
    g = zarr.open_group(f"{V1}/heat_state.zarr", mode="r")
    C = g["cls_day"]
    days = g["time"][:]
    idx_all = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))
    T = len(days) - max(2, int(dict(g.attrs).get("unclassed_tail_days", 2)))   # the last days cannot be classed
    idx = idx_all[:T]
    last = idx[-1]
    A = zarr.open_group(f"{V1}/admin/series.zarr", mode="r")
    LK = np.load(f"{V1}/admin/lookup.npz")
    U0, U1, U2 = (pd.read_csv(f"{V1}/admin/units_adm{k}.csv") for k in (0, 1, 2))
    land = C[0] != 255

    # ---- static layers
    sd = np.load(f"{DP}/confidence/confidence_v0.npz")["sd"]
    mask = np.zeros((NLAT, NLON), "u1")
    mask[np.isfinite(sd) & (sd < 1.0)] |= 1
    mask[np.isfinite(sd) & (sd >= 1.0) & (sd < 1.5)] |= 2
    cs = pd.read_csv(os.path.join(ROOT, "config", "data_suspect", "cells_v1.csv"))
    mask[cs.row.values, cs.col.values] |= 4
    mask[~land] = 255
    Image.fromarray(mask, "L").save(f"{DST}/static/mask.png", optimize=True)
    for k in ("adm2",):                                        # the page finds the province through adm2_parent.dat
        v = (LK[k].astype("i8") + 1).astype("u4")
        rgb = np.stack([(v >> 16) & 255, (v >> 8) & 255, v & 255], axis=-1).astype("u1")
        Image.fromarray(rgb, "RGB").save(f"{DST}/static/{k}.png", optimize=True)
    a1_of_a2 = pd.Series(np.arange(len(U1)), index=U1.adm1_id).reindex(U2.adm1_id).fillna(65535).values.astype("u2")
    a1_of_a2.tofile(f"{DST}/static/adm2_parent.dat")
    for nm in ("countries", "coast", "provinces"):             # lines and names for orientation, from pipeline/web_outlines.py and web_lines.py
        if os.path.exists(f"{V1}/web/{nm}.json"):
            shutil.copyfile(f"{V1}/web/{nm}.json", f"{DST}/static/{nm}.json")

    # ---- daily layers: class under live labelling, and the day of the spell
    # One byte per cell: bits 0-1 the class shown (0 none, 1 heat spell, 2 severe, 3 extreme), bits 2-7 the
    # number of consecutive spell days up to this day, capped at 62; 255 is sea. A cell is shown (live) from day 3.
    LOOK = 70                                                  # days read before the window so the day count can start
    c = C[T - WINDOW - LOOK:T]
    run = np.zeros(c.shape[1:], "u1")
    NW = 12                                                    # whole weeks, counted back from the last day
    weekly = np.zeros((NW,) + c.shape[1:], "u1")
    for j in range(c.shape[0]):
        sp = (c[j] >= 1) & (c[j] <= 3)
        run = np.where(sp, np.minimum(run + 1, 62), 0).astype("u1")
        k = j - LOOK
        if k >= 0:
            v = np.where(c[j] == 255, 255, np.where(run >= 3, c[j], 0) | (run << 2)).astype("u1")
            Image.fromarray(v, "L").save(f"{DST}/daily/{idx[T - WINDOW + k].date()}.png", optimize=True)
            wk = (WINDOW - 1 - k) // 7
            if wk < NW:
                weekly[wk] = np.maximum(weekly[wk], np.where(run >= 3, c[j], 0).astype("u1"))
    # past events (config/archive_events.csv through pipeline/periods.py): the same daily layer for each of their days
    PS = PER.periods(days)
    shown = PER.all_days(days)                                 # every day the daily map can show, positions on the time axis
    arch = shown[shown < T - WINDOW]
    done = set()
    for P in PS[1:]:
        a, b = int(P["idx"][0]), int(P["idx"][-1]) + 1
        cc = C[a - LOOK:b]
        rn = np.zeros(cc.shape[1:], "u1")
        for j in range(cc.shape[0]):
            spj = (cc[j] >= 1) & (cc[j] <= 3)
            rn = np.where(spj, np.minimum(rn + 1, 62), 0).astype("u1")
            tday = a - LOOK + j
            if tday >= a and tday < T - WINDOW and tday not in done:
                done.add(tday)
                Image.fromarray(np.where(cc[j] == 255, 255, np.where(rn >= 3, cc[j], 0) | (rn << 2)).astype("u1"), "L").save(f"{DST}/daily/{idx[tday].date()}.png", optimize=True)
        del cc, rn
    assert len(done) == len(arch), (len(done), len(arch))
    # weekly layers: the highest class shown on any day of the week (0 to 3), 255 sea; w00 is the week ending on the last day
    weeks = []
    for wk in range(NW):
        Image.fromarray(np.where(land, weekly[wk], 255).astype("u1"), "L").save(f"{DST}/weekly/w{wk:02d}.png", optimize=True)
        weeks.append({"file": f"weekly/w{wk:02d}.png", "start": str(idx[T - 1 - 7 * wk - 6].date()), "end": str(idx[T - 1 - 7 * wk].date())})
    # ---- season status on the last date, from the weekly layers (a project definition, not tested on events)
    # 0 none; 1 new this week (no spell in the 11 weeks before); 2 again this week after a break; 5 no longer in a spell (was last week);
    # 10 + N still in a spell, N weeks running (2 to 12); 255 sea
    inw = weekly >= 1
    alive, wrun = np.ones(inw.shape[1:], bool), np.zeros(inw.shape[1:], "u1")
    for wk in range(NW):
        alive &= inw[wk]
        wrun += alive
    season = np.zeros(inw.shape[1:], "u1")
    season[inw[0] & ~inw[1] & ~inw[2:].any(axis=0)] = 1
    season[inw[0] & ~inw[1] & inw[2:].any(axis=0)] = 2
    season[inw[0] & inw[1]] = (10 + wrun)[inw[0] & inw[1]]
    season[~inw[0] & inw[1]] = 5
    season[~land] = 255
    Image.fromarray(season, "L").save(f"{DST}/static/season.png", optimize=True)
    wl = np.repeat(np.cos(np.deg2rad(90 - 0.1 * np.arange(NLAT)))[:, None], NLON, axis=1)
    SEAS = {}
    for lv in ("adm0", "adm1"):                                 # share of each unit's land area: new, again, still, no longer
        ii = LK[lv]
        okc = (ii >= 0) & land
        nun = len(U0) if lv == "adm0" else len(U1)
        den = np.bincount(ii[okc], weights=wl[okc], minlength=nun)
        cats = (season == 1, season == 2, season >= 10, season == 5)
        with np.errstate(invalid="ignore", divide="ignore"):
            SEAS[lv] = np.stack([np.where(den > 0, np.floor(100 * np.bincount(ii[okc & (cq & (season != 255))], weights=wl[okc & (cq & (season != 255))], minlength=nun) / den), 255) for cq in cats]).astype("u1")
    season_counts = {k: int(((season == v) if v < 10 else (season >= 10) & (season != 255)).sum()) for k, v in (("none", 0), ("new", 1), ("again", 2), ("no_longer", 5), ("still", 10))}
    del c, run, weekly, inw, season

    # ---- humid heat spell, EXPERIMENTAL, yes or no only (pipeline/run_humid.py), if it has been run for these dates
    HU = None
    if os.path.exists(f"{V1}/humid/humid_recent.npz"):
        z = np.load(f"{V1}/humid/humid_recent.npz")
        hpos = np.searchsorted(z["days"], np.asarray(days)[shown])
        if hpos.max() < len(z["days"]) and np.array_equal(z["days"][hpos], np.asarray(days)[shown]):      # the pass covers every shown day
            lvh = z["live"]
            for q, tday in zip(hpos, shown):                     # 0 no, 1 in a humid heat spell (live labelling), 255 sea
                Image.fromarray(np.where(lvh[q] == 255, 255, lvh[q] == 1).astype("u1"), "L").save(f"{DST}/humid/{idx[tday].date()}.png", optimize=True)
            sdh = np.load(f"{V1}/humid/humid_cells.npz")["sd"]
            mh = np.zeros((NLAT, NLON), "u1")                    # this layer's own confidence, from the spread of its own input
            mh[np.isfinite(sdh) & (sdh < 1.0)] |= 1
            mh[np.isfinite(sdh) & (sdh >= 1.0) & (sdh < 1.5)] |= 2
            mh[~land] = 255
            Image.fromarray(mh, "L").save(f"{DST}/static/mask_humid.png", optimize=True)
            za = np.load(f"{V1}/humid/humid_admin.npz")
            hrec, harc = hpos[shown >= T - TRAIL1], hpos[shown < T - WINDOW]
            HU = {"adm0": za["adm0"][hrec], "adm1": za["adm1"][hrec], "dpy": {"adm0": za["adm0_days_per_year"], "adm1": za["adm1_days_per_year"]}, "n": int(len(hrec)),
                  "arch": {"adm0": za["adm0"][harc], "adm1": za["adm1"][harc]}}
            del lvh
    print(f"static and daily {time.time() - t0:.0f} s", flush=True)

    # ---- annual layers, complete years
    years = list(range(1979, last.year if (last.month, last.day) != (12, 31) else last.year + 1))
    starts = np.array([int(np.where(idx == pd.Timestamp(y, 1, 1))[0][0]) for y in years])
    t_end = int(np.where(idx == pd.Timestamp(years[-1], 12, 31))[0][0]) + 1
    asp = np.zeros((len(years), NLAT, NLON), "u2")
    asv = np.zeros((len(years), NLAT, NLON), "u2")
    tiles = [(r, cc) for r in range(0, NLAT, TR) for cc in range(0, NLON, TC)]
    months = [m for m in pd.period_range("1979-01", last.strftime("%Y-%m"), freq="M") if m.end_time.normalize() <= last]      # complete months only
    mstarts = np.array([int(np.where(idx == m.start_time)[0][0]) for m in months])
    m_end = int(np.where(idx == months[-1].end_time.normalize())[0][0]) + 1
    msp = np.full((len(months), NLAT, NLON), 255, "u1")
    msv = np.full((len(months), NLAT, NLON), 255, "u1")
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 10, initializer=init, initargs=(t_end, starts, m_end, mstarts)) as p:
        for r0, c0, a, b, ma, mb in p.imap_unordered(tile_annual, tiles):
            if a is not None:
                asp[:, r0:r0 + a.shape[1], c0:c0 + a.shape[2]], asv[:, r0:r0 + a.shape[1], c0:c0 + a.shape[2]] = a, b
                msp[:, r0:r0 + a.shape[1], c0:c0 + a.shape[2]], msv[:, r0:r0 + a.shape[1], c0:c0 + a.shape[2]] = ma, mb
    for k, m in enumerate(months):                              # days in the month in a heat spell / severe or extreme, 255 sea
        for nm, arr in (("spell", msp), ("severe", msv)):
            Image.fromarray(np.where(land, arr[k], 255).astype("u1"), "L").save(f"{DST}/monthly/{nm}_{m}.png", optimize=True)
    del msp, msv
    clipped = {"spell": int(((asp > 254) & land).sum()), "severe": int(((asv > 254) & land).sum())}
    for k, y in enumerate(years):
        for nm, arr in (("spell", asp), ("severe", asv)):
            Image.fromarray(np.where(land, np.minimum(arr[k], 254), 255).astype("u1"), "L").save(f"{DST}/annual/{nm}_{y}.png", optimize=True)
    # ---- trend in heat spell days, 1979 to the last complete year, on 3 by 3 blocks of cells (about the reanalysis footprint)
    nbr, nbc = (NLAT - 1) // 3, NLON // 3
    lm = land[:nbr * 3]
    cnt = lm.reshape(nbr, 3, nbc, 3).sum(axis=(1, 3))
    bm = np.where(lm[None], asp[:, :nbr * 3], 0).astype("f4").reshape(len(years), nbr, 3, nbc, 3).sum(axis=(2, 4)) / np.maximum(cnt, 1)
    okb = cnt > 0
    northb = np.repeat((90 - 0.1 * (3 * np.arange(nbr) + 1) > -60)[:, None], nbc, axis=1)[okb]
    tt = TRD.trend_table(bm[:, okb].T, q=0.10, where=northb)
    dec = tt["slope"] * 10                                      # days per decade
    codeb = np.full((nbr, nbc), 255, "u1")                      # 0 no significant trend; 1..254 slope, (v - 128) / 2 days per decade; 255 no land
    codeb[okb] = np.where(tt["sig"], np.clip(np.rint(dec * 2) + 128, 1, 254), 0).astype("u1")
    tgrid = np.full((NLAT, NLON), 255, "u1")
    tgrid[:nbr * 3] = np.repeat(np.repeat(codeb, 3, axis=0), 3, axis=1)
    tgrid[~land] = 255
    Image.fromarray(tgrid, "L").save(f"{DST}/static/trend.png", optimize=True)
    trend_info = {"years": [years[0], years[-1]], "blocks": int(northb.sum()), "false_discovery_rate": 0.10, "p_threshold": round(float(tt["threshold"]), 5),
                  "significant_up": int((tt["sig"] & (dec > 0) & northb).sum()), "significant_down": int((tt["sig"] & (dec < 0) & northb).sum()),
                  "plain_p_below_0.05": int(((tt["p"] < 0.05) & northb).sum()), "median_slope_days_per_decade": round(float(np.median(dec[northb])), 2),
                  "median_lag1": round(float(np.median(tt["r1"][northb])), 3),
                  "rule": "Theil-Sen slope; Mann-Kendall p, plain and after removing lag-1 autocorrelation, both must pass the Benjamini-Hochberg threshold; blocks north of 60 S",
                  "caveat": "The source is a reanalysis whose inputs change over the years, which can add or hide a trend, and the yardstick is fixed on 1991 to 2020 and not adjusted for warming."}
    del asp, asv, bm
    print(f"annual {time.time() - t0:.0f} s", flush=True)

    # ---- admin tables
    yr = idx.year.values
    ysl = [(int(a), int(b)) for a, b in zip(starts, list(starts[1:]) + [t_end])]
    # hot days and hot nights, if pipeline/run_daynight.py has been run for these dates
    DN = None
    if os.path.exists(f"{V1}/admin/daynight.npz"):
        z = np.load(f"{V1}/admin/daynight.npz")
        dpos = np.searchsorted(z["days"], np.asarray(days)[shown])
        if dpos.max() < len(z["days"]) and np.array_equal(z["days"][dpos], np.asarray(days)[shown]):      # the pass covers every shown day
            drec, darc = dpos[shown >= T - TRAIL1], dpos[shown < T - WINDOW]
            DN = {"adm0": z["adm0"][:, drec], "adm1": z["adm1"][:, drec], "n": int(len(drec)), "base_rate": [float(v) for v in z["base_rate"]],
                  "arch": {"adm0": z["adm0"][:, darc], "adm1": z["adm1"][:, darc]}}
    S1 = {m: A[f"adm1_{m}"][:T] for m in ("spell", "severe", "extreme", "degdays")}
    S0 = {m: A[f"adm0_{m}"][:T] for m in ("spell", "severe", "extreme", "degdays")}
    S2 = {m: A[f"adm2_{m}"][:T] for m in ("spell", "severe", "extreme")}
    ok0, ok1, ok2 = U0.land_cells.values >= FLOOR, U1.land_cells.values >= FLOOR, U2.land_cells.values >= FLOOR
    # Antarctica is outside the product (nothing south of 60 S is drawn or classed for the page)
    ok0 &= U0.iso_3.astype(str).values != "ATA"
    ok1 &= U1.iso_3.astype(str).values != "ATA"
    ok2 &= U2.iso_3.astype(str).values != "ATA"
    a0_of_a1 = pd.Series(np.arange(len(U0)), index=U0.adm0_id).reindex(U1.adm0_id).values
    a0_of_a2 = pd.Series(np.arange(len(U0)), index=U0.adm0_id).reindex(U2.adm0_id).values
    s = lambda v: "" if pd.isna(v) else str(v)
    admins = {"adm0": [{"id": r.adm0_id, "name": s(r.adm0_name), "iso3": s(r.iso_3), "cells": int(r.land_cells), "area_km2": int(r.area_km2), "series": bool(ok0[i])} for i, r in enumerate(U0.itertuples())],
              "adm1": [{"id": r.adm1_id, "name": s(r.adm1_name), "adm0": int(a0_of_a1[i]), "cells": int(r.land_cells), "area_km2": int(r.area_km2), "licence": s(r.src_lic), "series": bool(ok1[i])} for i, r in enumerate(U1.itertuples())]}
    with open(f"{DST}/admins.json", "w", encoding="utf-8") as f:
        json.dump(admins, f, ensure_ascii=False, separators=(",", ":"))

    def tier(v):
        return np.where(v == 65535, -1, np.where(v >= TIER[1] * 1e4, 2, np.where(v >= TIER[0] * 1e4, 1, 0))).astype("i1")
    latest = {"date": str(last.date()), "tiers": "0 no widespread severe heat, 1 part of the area (severe share 0.25), 2 most of the area (0.50), -1 no value",
              "adm0": {"spell": pct(S0["spell"][-1]).tolist(), "severe": pct(S0["severe"][-1]).tolist(), "tier": np.where(ok0, tier(S0["severe"][-1]), -1).tolist()},
              "adm1": {"spell": pct(S1["spell"][-1]).tolist(), "severe": pct(S1["severe"][-1]).tolist(), "tier": np.where(ok1, tier(S1["severe"][-1]), -1).tolist()}}
    with open(f"{DST}/latest.json", "w") as f:
        json.dump(latest, f, separators=(",", ":"))

    n_ev = 0
    for i0, r0 in enumerate(U0.itertuples()):
        kids = np.where((a0_of_a1 == i0) & ok1)[0]
        units = ([("adm0", i0, S0)] if ok0[i0] else []) + [("adm1", int(k), S1) for k in kids]
        if units:
            head = {"start": "1979-01-01", "days": T, "trailing": TRAIL1, "units": [{"level": lv, "row": k} for lv, k, _ in units],
                    "arrays": [{"name": "spell", "dtype": "uint8", "shape": [len(units), T], "unit": "percent of land area, 255 no value"},
                               {"name": "severe", "dtype": "uint8", "shape": [len(units), TRAIL1]}, {"name": "extreme", "dtype": "uint8", "shape": [len(units), TRAIL1]},
                               {"name": "annual_spell", "dtype": "uint16", "shape": [len(units), len(years)], "unit": "area-days in a heat spell per year x 10, from the exact shares", "first_year": years[0]},
                               {"name": "degdays", "dtype": "uint16", "shape": [len(units), TRAIL1], "unit": "daily degree-days x 1000 for the last 365 days; summed over an event's days they give its size up to a date"}]}
            ann1 = np.array([[int(round(float(np.minimum(S["spell"][a:b, k], 10000).sum(dtype="f8")) / 1e3)) for a, b in ysl] for _, k, S in units], "u2")
            tu = TRD.trend_table(ann1 / 10.0)                    # per unit: days per decade, plain p, pre-whitened p (no allowance for many units)
            for q_, uu in enumerate(head["units"]):
                uu["trend"] = [round(float(tu["slope"][q_] * 10), 2), round(float(tu["p"][q_]), 4), round(float(tu["p_pw"][q_]), 4)]
            head["arrays"].append({"name": "season", "dtype": "uint8", "shape": [len(units), 4], "unit": "percent of land area on the last date: new this week, again after a break, still in a spell, no longer in one"})
            extra = []
            if DN is not None:                                 # four shares per day: day only, night only, both, outside the warm season
                head["arrays"].append({"name": "daynight", "dtype": "uint8", "shape": [len(units), 4, DN["n"]], "unit": "percent of land area, rounded down",
                                       "classes": ["hot by day only", "hot by night only", "hot by day and night", "hot by day or night outside the warm season"]})
                extra = [np.stack([pct(DN[lv][:, :, k]) for lv, k, _ in units])]
            if HU is not None:                                 # experimental: share in a humid heat spell, and days a year in two periods
                head["arrays"].append({"name": "humid", "dtype": "uint8", "shape": [len(units), HU["n"]], "unit": "percent of land area in a humid heat spell, rounded down; EXPERIMENTAL"})
                head["arrays"].append({"name": "humid_days", "dtype": "uint16", "shape": [len(units), 2], "unit": "area-mean humid heat spell days a year x 10: 1991-2020, 2021-2025"})
                extra += [np.stack([pct(HU[lv][:, k]) for lv, k, _ in units]),
                          np.array([[int(round(float(np.nan_to_num(v)) * 10)) for v in HU["dpy"][lv][:, k]] for lv, k, _ in units], "u2")]
            write_bin(f"{DST}/admin/{r0.adm0_id}.dat", head, [np.stack([pct(S[m][-n:, k]) for _, k, S in units]) for m, n in (("spell", T), ("severe", TRAIL1), ("extreme", TRAIL1))] + [ann1, np.stack([np.minimum(S["degdays"][-TRAIL1:, k], 65534).astype("u2") for _, k, S in units]), np.stack([SEAS[lv][:, k] for lv, k, _ in units])] + extra)
            if len(arch):                                      # the same day-keyed numbers for the days of the past events
                ah = {"start": "1979-01-01", "days": [int(v) for v in arch], "units": [{"level": lv, "row": k} for lv, k, _ in units],
                      "arrays": [{"name": "severe", "dtype": "uint8", "shape": [len(units), len(arch)]}, {"name": "extreme", "dtype": "uint8", "shape": [len(units), len(arch)]},
                                 {"name": "degdays", "dtype": "uint16", "shape": [len(units), len(arch)]}]}
                aarr = [np.stack([pct(S[m][arch, k]) for _, k, S in units]) for m in ("severe", "extreme")] + [np.stack([np.minimum(S["degdays"][arch, k], 65534).astype("u2") for _, k, S in units])]
                if DN is not None:
                    ah["arrays"].append({"name": "daynight", "dtype": "uint8", "shape": [len(units), 4, len(arch)]})
                    aarr.append(np.stack([pct(DN["arch"][lv][:, :, k]) for lv, k, _ in units]))
                if HU is not None:
                    ah["arrays"].append({"name": "humid", "dtype": "uint8", "shape": [len(units), len(arch)]})
                    aarr.append(np.stack([pct(HU["arch"][lv][:, k]) for lv, k, _ in units]))
                write_bin(f"{DST}/admin_arch/{r0.adm0_id}.dat", ah, aarr)
            evj = []
            for lv, k, S in units:
                shr = S["spell"][:, k] / 1e4
                dd = S["degdays"][:, k] / 1e3
                ev = events(shr >= SHARE_DAY)
                n_ev += len(ev)
                evj.append({"level": lv, "row": k, "start": [a for a, _ in ev], "days": [b - a + 1 for a, b in ev],
                            "peak": [int(round(float(shr[a:b + 1].max()) * 100)) for a, b in ev], "size": [round(float(dd[a:b + 1].sum()), 2) for a, b in ev],
                            "open": bool(ev and ev[-1][1] >= T - 1 - GAP)})
            with open(f"{DST}/events/{r0.adm0_id}.json", "w") as f:
                json.dump({"start": "1979-01-01", "rule": f"share in a heat spell >= {SHARE_DAY}, gaps of {GAP} days joined, at least {MIN_DAYS} such days", "size": "degree-days",
                           "start_unit": "days since start", "units": evj}, f, separators=(",", ":"))
        k2 = np.where((a0_of_a2 == i0) & ok2)[0]
        if len(k2):
            ann = [np.stack([np.rint(np.minimum(S2[m][a:b, k2], 10000).sum(axis=0, dtype="f8") / 1e3).astype("u2") for a, b in ysl]).T for m in ("spell", "severe")]
            head = {"last_date": str(last.date()), "trailing": TRAIL2, "years": [years[0], years[-1]],
                    "units": [{"row": int(k), "id": U2.adm2_id[k], "name": s(U2.adm2_name[k]), "adm1": int(a1_of_a2[k]), "cells": int(U2.land_cells[k]), "area_km2": int(U2.area_km2[k])} for k in k2],
                    "arrays": [{"name": m, "dtype": "uint8", "shape": [len(k2), TRAIL2], "unit": "percent of land area"} for m in ("spell", "severe", "extreme")]
                    + [{"name": f"annual_{m}", "dtype": "uint16", "shape": [len(k2), len(years)], "unit": "area-days x 10"} for m in ("spell", "severe")]}
            write_bin(f"{DST}/admin2/{r0.adm0_id}.dat", head, [pct(S2[m][-TRAIL2:, k2]).T for m in ("spell", "severe", "extreme")] + ann)
    print(f"admin {time.time() - t0:.0f} s", flush=True)

    # ---- manifest
    files, by = [], {}
    for dp, _, fs in os.walk(DST):
        for fn in fs:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, DST).replace("\\", "/")
            if rel in ("files.js", "manifest.json"):
                continue
            sz = os.path.getsize(p)
            with open(p, "rb") as f:
                gz = len(gzip.compress(f.read(), 6)) if not fn.endswith(".png") else sz
            files.append({"path": rel, "bytes": sz, "gzip_bytes": gz})
            grp = rel.split("/")[0] if "/" in rel else rel
            b = by.setdefault(grp, {"files": 0, "bytes": 0, "gzip_bytes": 0, "largest": 0})
            b["files"] += 1
            b["bytes"] += sz
            b["gzip_bytes"] += gz
            b["largest"] = max(b["largest"], sz)
    hold = sorted(set(U1.adm0_name[U1.src_lic.astype(str).str.startswith("Other")].astype(str)))
    man = {"built": time.strftime("%Y-%m-%d %H:%M:%S"), "detector_version": dict(g.attrs).get("detector_version"), "definition": "docs/detector-v1-frozen.md",
           "source": "AgERA5 daily maximum and minimum 2 m temperature", "baseline": "1991-2020, fixed",
           "record_start": str(idx[0].date()), "last_input_date": str(idx_all[-1].date()), "last_date": str(last.date()),
           "latency_note": "the newest day shown is two days behind the newest input day",
           "grid": {"rows": NLAT, "cols": NLON, "north": 90.0, "west": -180.0, "step": 0.1, "cell_centres": True},
           "daily_window": [str(idx[T - WINDOW].date()), str(last.date())], "weekly": weeks,
           "periods": [{"name": P["name"], "start": P["start"], "end": P["end"], "bbox": P.get("bbox"), "focus": P.get("focus")} for P in PS], "archive_days": int(len(arch)),
           "monthly": {"first": str(months[0]), "last": str(months[-1]), "months": len(months)},
           "trend": trend_info,
           "season": {"cells": season_counts, "note": "project definition from the last 12 weekly layers; not part of frozen version 1.0, not tested on events"},
           "humid": None if HU is None else {"status": "EXPERIMENTAL", "days": HU["n"], "caution": "Humid heat here is judged against 1991 to 2020. The humidity record in the source data drifts, so recent years are flagged far more often than the past for reasons that are partly not climate.",
                                              "note": "yes or no only; never part of a headline number, rank, trend or status; own confidence mask in static/mask_humid.png; see pipeline/run_humid.py"},
           "daynight": None if DN is None else {"days": DN["n"], "baseline_rate_hot_day_hot_night": DN["base_rate"], "note": "project definition, not part of frozen version 1.0, not tested on events; see pipeline/run_daynight.py"}, "annual_years": [years[0], years[-1]],
           "settings": {"status_tiers_severe_share": list(TIER), "status_tier_note": "0.50 is frozen, 0.25 is a setting", "event_rule": {"share_in_spell": SHARE_DAY, "gap_days": GAP, "min_days": MIN_DAYS, "frozen": False},
                        "event_size": "degree-days above the heat threshold, area mean, summed over the event (setting, not frozen)",
                        "cell_floor": FLOOR, "cell_floor_note": "set 2026-11-22; units below it have no area shares; at 9 cells a share moves in steps of about 11 percent",
                        "confidence_limits_K": [1.0, 1.5], "confidence_note": "provisional limits on the sd of AgERA5 daily mean temperature anomalies"},
           "counts": {"land_cells": int(land.sum()), "land_cells_in_no_unit": int((land & (LK["adm1"] < 0)).sum()),
                      "adm0": int(len(U0)), "adm1": int(len(U1)), "adm2": int(len(U2)),
                      "suppressed_below_floor": {"adm0": int((~ok0).sum()), "adm1": int((~ok1).sum()), "adm2": int((~ok2).sum())},
                      "events_written": n_ev, "data_suspect_cells": int(len(cs)), "annual_cells_clipped_at_254": clipped},
           "not_built": ["hot spot layer", "space-time cube files", "district events", "largest severe patch"],
           "boundaries": {"licence": "Open Database License (ODbL) 1.0", "licence_url": "https://opendatacommons.org/licenses/odbl/1-0/",
                          "credit": "Boundaries: FieldMaps Global Edge-matched Subnational Boundaries (adm1, adm2) and OpenStreetMap contributors (adm0), under the Open Database License 1.0.",
                          "source": "FieldMaps edge-matched subnational boundaries, release 2025-07-29", "licence_decision": "Checked by the author, 2026-11-22: clear. adm0 from OpenStreetMap, adm1 and adm2 from the HDX edge-matched set, credited under ODbL 1.0. Rows whose source licence reads 'Other' were checked on the source pages on 2026-11-22: Honduras, Lebanon, Niger and Türkiye are CC BY-IGO on HDX; Tuvalu is CC BY 4.0 on geoBoundaries",
                          "source_licences_checked": {"Honduras": "CC BY-IGO", "Lebanon": "CC BY-IGO", "Niger": "CC BY-IGO", "Türkiye": "CC BY-IGO", "Tuvalu": "CC BY 4.0"},
                          "units_with_other_licence_adm1": int(U1.src_lic.astype(str).str.startswith("Other").sum()), "countries_with_other_licence": hold},
           "size_by_group": by, "total_bytes": int(sum(f["bytes"] for f in files)), "files": files}
    with open(f"{DST}/manifest.json", "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    # Framework publishes only files named by a string literal in a FileAttachment call
    with open(f"{DST}/files.js", "w", encoding="utf-8") as f:
        f.write("// GENERATED by pipeline/web_products.py. Do not edit: rerun the build.\n"
                'import {FileAttachment} from "observablehq:stdlib";\n\nexport const files = {\n')
        for q in ["manifest.json"] + sorted(x["path"] for x in files):
            f.write(f'  "{q}": FileAttachment("{q}"),\n')
        f.write("};\n")
    print(f"DONE {time.time() - t0:.0f} s; last date {last.date()}; total {man['total_bytes'] / 1e6:.1f} MB in {len(files)} files")
    for k, b in sorted(by.items(), key=lambda kv: -kv[1]["bytes"]):
        print(f"  {k:14s} files {b['files']:5d}  {b['bytes'] / 1e6:8.2f} MB  gzip {b['gzip_bytes'] / 1e6:8.2f} MB  largest {b['largest'] / 1e6:6.2f} MB")
    print("  suppressed below the floor:", man["counts"]["suppressed_below_floor"], "| other-licence countries:", hold, "| clipped:", clipped)
