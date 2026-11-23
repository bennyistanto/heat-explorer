"""Checks on site/data written by pipeline/web_products.py.

1. Every file in the manifest exists with the stated size; nothing unlisted.
2. Size budget (references/dashboard.md): whole set under 500 MB; first load
   under 3 MB; any single fetch under 2 MB. Offenders are listed.
3. The latest daily layer decodes to codes 0 to 4 and equals the live class
   computed here from the store.
4. The district id raster decodes back to the lookup, every cell.
5. One country file read back the way the page would (Canada): British
   Columbia's daily share equals the admin series, rounded down to a percent; its
   2021 event has the size and dates found in validation/event_size.
6. Annual layers: the mean of severe_2021 to severe_2025 equals the run
   summary of the global run (cells clipped at 254 left out).
7. The last two days of the record are not shown anywhere.

Run:  bash tools/py.sh -W ignore pipeline/check_web.py
Output: pipeline/results/check_web.txt
"""
import gzip
import json
import os
import struct

import numpy as np
import pandas as pd
import zarr
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DST = os.path.join(HERE, "..", "site", "data")
V1 = "E:/temp/agera5/derived-products/heat-explorer/v1"


def read_bin(path):
    with open(path, "rb") as f:
        n = struct.unpack("<I", f.read(4))[0]
        head = json.loads(f.read(n).decode("utf-8"))
        out = {}
        for a in head["arrays"]:
            dt = np.dtype(a["dtype"])
            out[a["name"]] = np.frombuffer(f.read(int(np.prod(a["shape"])) * dt.itemsize), dt).reshape(a["shape"])
        assert f.read(1) == b"", "bytes left over"
    return head, out


if __name__ == "__main__":
    man = json.load(open(f"{DST}/manifest.json", encoding="utf-8"))
    out, fails = [f"Checks on site/data. Produced by pipeline/check_web.py", f"built {man['built']}; last date {man['last_date']}; last input day {man['last_input_date']}"], []

    listed = {f["path"]: f["bytes"] for f in man["files"]}
    on_disk = {os.path.relpath(os.path.join(dp, fn), DST).replace("\\", "/"): os.path.getsize(os.path.join(dp, fn)) for dp, _, fs in os.walk(DST) for fn in fs}
    on_disk.pop("manifest.json", None)
    on_disk.pop("files.js", None)
    bad = [k for k, v in listed.items() if on_disk.get(k) != v] + [k for k in on_disk if k not in listed]
    out.append(f"\n1. Files listed {len(listed):,}; missing, changed or unlisted: {len(bad)}")
    if bad:
        fails.append("file list")

    total = sum(on_disk.values()) + os.path.getsize(f"{DST}/manifest.json")
    # what the opening view fetches: the fixed files, the latest day and the day before it (warmed for the slider),
    # the lines drawn on the map, and the numbers of the country the page opens on
    adm, lat = json.load(open(f"{DST}/admins.json", encoding="utf-8")), json.load(open(f"{DST}/latest.json", encoding="utf-8"))
    score = [(lat["adm1"]["severe"][i] * u["area_km2"] if lat["adm1"]["tier"][i] == 2 else 0) for i, u in enumerate(adm["adm1"])]
    open_id = adm["adm0"][adm["adm1"][int(np.argmax(score))]["adm0"]]["id"]
    day_before = str((pd.Timestamp(man["last_date"]) - pd.Timedelta(days=1)).date())
    first = ["files.js", "manifest.json", "admins.json", "latest.json", "static/mask.png", "static/adm2.png", "static/adm2_parent.dat", "static/countries.json", "static/coast.json",
             f"daily/{man['last_date']}.png", f"daily/{day_before}.png", f"admin/{open_id}.dat", f"events/{open_id}.json"]
    first = [(q, f"{DST}/{q}") for q in first if os.path.exists(f"{DST}/{q}")]
    DIST = os.path.join(DST, "..", "..", "dist")                                  # the page and its libraries, when the static site has been built
    built = os.path.exists(f"{DIST}/index.html")
    if built:
        first = [r for r in first if r[0] != "files.js"]                          # the built copy of the file list is counted instead
        first.append(("(built) index.html", f"{DIST}/index.html"))
        for sub in ("_import", "_npm", "_observablehq"):
            for root, _, fs in os.walk(f"{DIST}/{sub}"):
                first += [(f"(built) {sub}/{f}", os.path.join(root, f)) for f in fs if f.endswith((".js", ".css"))]

    def served(path):                                                             # bytes if text is gzipped by the host; images are already compressed
        raw = open(path, "rb").read()
        return len(raw) if path.endswith(".png") else len(gzip.compress(raw, 6))
    gz = {f["path"]: f["gzip_bytes"] for f in man["files"]}
    fl = sum(os.path.getsize(q) for _, q in first)
    flz = sum(served(q) for _, q in first)
    big = sorted(((v, k) for k, v in on_disk.items() if v > 2e6), reverse=True)
    out.append(f"\n2. Total {total / 1e6:.1f} MB (target under 500). First load, {len(first)} files{'' if built else ' (static site not built: page and libraries NOT counted)'}: {fl / 1e6:.2f} MB as stored, {flz / 1e6:.2f} MB if text is served gzipped (target under 3). Province lines (fetched on zooming in) and the small maps (fetched on scrolling to them) are not in it. Largest:")
    for q, path in sorted(first, key=lambda r: -os.path.getsize(r[1]))[:12]:
        out.append(f"      {q[:60]:60s} {os.path.getsize(path) / 1e6:6.2f} MB  served {served(path) / 1e6:5.2f}")
    out.append(f"   files over 2 MB: {len(big)}" + "".join(f"\n      {k} {v / 1e6:.2f} MB (gzip {gz.get(k, v) / 1e6:.2f})" for v, k in big[:12]))
    out.append("   by group: " + "; ".join(f"{k} {b['bytes'] / 1e6:.1f} MB in {b['files']} files" for k, b in sorted(man["size_by_group"].items(), key=lambda kv: -kv[1]["bytes"])))
    if total > 500e6:
        fails.append("total size")
    if flz > 3e6:
        fails.append("first load")
    if big:
        fails.append(f"{len(big)} files over 2 MB")

    g = zarr.open_group(f"{V1}/heat_state.zarr", mode="r")
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(g["time"][:], unit="D"))
    k = int(np.where(idx == pd.Timestamp(man["last_date"]))[0][0])
    c = g["cls_day"][k - 2:k + 1]
    sp = (c >= 1) & (c <= 3)
    want = np.where(c[2] == 255, 4, np.where(sp.all(axis=0), c[2], 0)).astype("u1")
    raw = np.asarray(Image.open(f"{DST}/daily/{man['last_date']}.png"))
    got = np.where(raw == 255, 4, raw & 3).astype("u1")            # bits 0-1 class, bits 2-7 day of the spell, 255 sea
    run = raw >> 2
    d = int((got != want).sum()) + int((((run >= 3) != ((got >= 1) & (got <= 3))) & (raw != 255)).sum())
    out.append(f"\n3. Latest daily layer: codes {sorted(np.unique(got).tolist())}; cells where the class or the day count disagrees with the store: {d}; longest day count {int(run[raw != 255].max())}; in a heat spell {int((got == 1).sum()):,}, severe {int((got == 2).sum()):,}, extreme {int((got == 3).sum()):,}")
    if d:
        fails.append("daily layer")

    lk = np.load(f"{V1}/admin/lookup.npz")["adm2"]
    rgb = np.asarray(Image.open(f"{DST}/static/adm2.png")).astype("i8")
    dec = (rgb[..., 0] << 16 | rgb[..., 1] << 8 | rgb[..., 2]) - 1
    d = int((dec != lk).sum())
    out.append(f"\n4. District id raster: cells differing from the lookup: {d}")
    if d:
        fails.append("id raster")

    adm = json.load(open(f"{DST}/admins.json", encoding="utf-8"))
    j = next(i for i, u in enumerate(adm["adm1"]) if u["name"] == "British Columbia")
    a0 = adm["adm0"][adm["adm1"][j]["adm0"]]["id"]
    head, arr = read_bin(f"{DST}/admin/{a0}.dat")
    r = next(i for i, u in enumerate(head["units"]) if u["level"] == "adm1" and u["row"] == j)
    A = zarr.open_group(f"{V1}/admin/series.zarr", mode="r")
    ref = (A["adm1_spell"][:head["days"], j] // 100).astype("u1")
    d = int((arr["spell"][r] != ref).sum())
    ev = next(u for u in json.load(open(f"{DST}/events/{a0}.json"))["units"] if u["level"] == "adm1" and u["row"] == j)
    st = pd.Timestamp("1979-01-01") + pd.to_timedelta(ev["start"], unit="D")
    q = int(np.where(st == pd.Timestamp("2021-06-22"))[0][0]) if (st == pd.Timestamp("2021-06-22")).any() else -1
    okev = q >= 0 and ev["days"][q] == 24 and abs(ev["size"][q] - 56.5) < 0.11
    out.append(f"\n5. {a0}: {len(head['units'])} units in the file; British Columbia daily share differs from the admin series on {d} days; events {len(ev['start'])}; "
               f"2021 event: {'start 2021-06-22, ' + str(ev['days'][q]) + ' days, size ' + str(ev['size'][q]) if q >= 0 else 'NOT FOUND'} (expected 24 days, 56.5)")
    # daily degree-days: summed over the last finished event inside the 365-day window they must give that event's size
    off = head["days"] - head["trailing"]
    inwin = [i for i in range(len(ev["start"])) if ev["start"][i] >= off and ev["start"][i] + ev["days"][i] - 1 < head["days"] - 3]
    if inwin:
        i = inwin[-1]
        sz = arr["degdays"][r][ev["start"][i] - off:ev["start"][i] - off + ev["days"][i]].sum() / 1000
        okdd = abs(sz - ev["size"][i]) < 0.011
        out.append(f"   daily degree-days summed over the event of {st[i].date()} ({ev['days'][i]} days): {sz:.2f}; size in the events file {ev['size'][i]:.2f}  {'same' if okdd else 'DIFFERENT'}")
    else:
        okdd = True
        out.append("   no finished event inside the 365-day window to test the daily degree-days on")
    if d or not okev or not okdd:
        fails.append("country file")

    S = np.load(f"{V1}/run_summary_global.npz")["days_per_year"][3]
    yrs = [np.asarray(Image.open(f"{DST}/annual/severe_{y}.png")).astype("f4") for y in range(2021, 2026)]
    clip = np.any([y >= 254 for y in yrs], axis=0)
    m = np.isfinite(S) & ~clip
    d = float(np.abs(np.mean(yrs, axis=0)[m] - S[m]).max())
    out.append(f"\n6. Annual severe days, mean of 2021 to 2025 against the global run summary: largest difference {d:.3f} days over {int(m.sum()):,} cells")
    if d > 0.01:
        fails.append("annual layers")

    last_in = pd.Timestamp(man["last_input_date"])
    late = [p for p in on_disk if p.startswith("daily/") and pd.Timestamp(p[6:16]) > last_in - pd.Timedelta(days=2)]
    okd = (last_in - pd.Timestamp(man["last_date"])).days == 2 and not late and head["days"] == k + 1
    out.append(f"\n7. Last date shown is {(last_in - pd.Timestamp(man['last_date'])).days} days behind the last input day; daily layers after it: {len(late)}; series length {head['days']} days (expected {k + 1})")
    if not okd:
        fails.append("latency")

    # 8. periods: a daily layer for every day of every period, and the past-event numbers against the admin series
    want = set()
    for q in man.get("periods", []):
        want |= {str(d.date()) for d in pd.date_range(q["start"], q["end"])}
    have = {q[6:16] for q in on_disk if q.startswith("daily/")}
    okp = want == have
    out.append(f"\n8. Periods: {len(man.get('periods', []))}; days they cover {len(want):,}; daily layers on disk {len(have):,}; sets equal: {okp}")
    ap = f"{DST}/admin_arch/{a0}.dat"
    if os.path.exists(ap):
        ah, aa = read_bin(ap)
        ra = next(i for i, u in enumerate(ah["units"]) if u["level"] == "adm1" and u["row"] == j)
        col = A["adm1_severe"][:, j]
        da = int((aa["severe"][ra] != (col[np.array(ah["days"])] // 100).astype("u1")).sum())
        out.append(f"   past-event file of {a0}: {len(ah['days'])} days; British Columbia severe share differs from the admin series on {da} days; arrays {sorted(aa)}")
        okp = okp and da == 0
    if not okp:
        fails.append("periods")
    mm = man.get("monthly")
    if mm:
        nmon = len([q for q in on_disk if q.startswith("monthly/")])
        m1 = np.asarray(Image.open(f"{DST}/monthly/severe_2021-06.png")).astype("i4")
        k0, k1 = int(np.where(idx == pd.Timestamp("2021-06-01"))[0][0]), int(np.where(idx == pd.Timestamp("2021-06-30"))[0][0])
        cc = g["cls_day"][k0:k1 + 1, 300:500, 500:700]
        ref = np.where(cc[0] == 255, 255, ((cc >= 2) & (cc <= 3)).sum(axis=0))
        dm = int((m1[300:500, 500:700] != ref).sum())
        out.append(f"\n9. Monthly layers: {mm['first']} to {mm['last']}, {mm['months']} months, {nmon} files; severe days in June 2021 over western Canada differ from the store at {dm} cells")
        if nmon != 2 * mm["months"] or dm:
            fails.append("monthly layers")

    out.append(f"\nSuppressed below the cell floor of {man['settings']['cell_floor']}: {man['counts']['suppressed_below_floor']}")
    out.append(f"Boundary licence: {man['boundaries']['licence_decision']}; countries with an 'Other' licence: {', '.join(man['boundaries']['countries_with_other_licence'])}")
    out.append(f"\nRESULT: {'ALL CHECKS PASS' if not fails else 'FAILED: ' + '; '.join(fails)}")
    txt = "\n".join(out)
    with open(os.path.join(HERE, "results", "check_web.txt"), "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)
