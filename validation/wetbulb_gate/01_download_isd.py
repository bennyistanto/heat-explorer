"""Download NOAA ISD-Lite hourly files for the wet-bulb gate stations.

Source: NOAA Integrated Surface Database, public bucket noaa-isd-pds
  https://noaa-isd-pds.s3.amazonaws.com/isd-lite/data/<year>/<usaf>-<wban>-<year>.gz
Station list: https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv
Format: isd-lite-format.txt in the same bucket (fixed width; T and Td in 0.1 C).

ISD-Lite is not quality controlled the way HadISD is. 03_compare.py applies
its own range and completeness checks.

Run:  bash tools/py.sh validation/wetbulb_gate/01_download_isd.py
Output: E:/temp/station-isd/raw/*.gz and E:/temp/station-isd/stations.csv
"""
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

OUT = "E:/temp/station-isd"
BASE = "https://noaa-isd-pds.s3.amazonaws.com/isd-lite/data"
YEARS = range(1979, 2026)

# USAF ids chosen for humid-heat relevance and climate spread; see README.md
USAF = [
    "411500", "404160", "412170", "411700", "405820",            # Gulf
    "428090", "419230", "432790", "421820", "431280", "426470",  # India, Bangladesh
    "417490",                                                    # Sindh (Nawabshah)
    "486980", "484560", "967490", "967450", "941200",            # SE Asia, N Australia
    "652010", "610520", "637400",                                # Africa
    "821110", "722430", "722780", "722020", "726980",            # Americas
    "071490", "275185", "947670",                                # Europe, Russia, Sydney
]
# Jacobabad is not listed by name: take the nearest long-record station
NEAR = {"Jacobabad": (28.30, 68.47)}


def pick_stations():
    h = pd.read_csv(f"{OUT}/isd-history.csv", dtype=str)
    for c in ("LAT", "LON", "ELEV(M)"):
        h[c] = pd.to_numeric(h[c], errors="coerce")
    h["b"] = h.BEGIN.str[:4].astype(int)
    h["e"] = h.END.str[:4].astype(int)
    sel = h[h.USAF.isin(USAF)].copy()
    # one row per USAF: the longest record
    sel["span"] = sel.e - sel.b
    sel = sel.sort_values("span").groupby("USAF").tail(1)
    sel["why"] = "listed"
    for name, (la, lo) in NEAR.items():
        c = h[(h.b <= 1990) & (h.e >= 2020)].dropna(subset=["LAT", "LON"]).copy()
        c["d"] = np.hypot(c.LAT - la, (c.LON - lo) * np.cos(np.deg2rad(la)))
        row = c.sort_values("d").head(1).copy()
        row["why"] = f"nearest to {name} ({row.d.iloc[0] * 111:.0f} km)"
        sel = pd.concat([sel, row])
    sel = sel[["USAF", "WBAN", "STATION NAME", "CTRY", "LAT", "LON", "ELEV(M)", "BEGIN", "END", "why"]]
    sel.columns = ["usaf", "wban", "name", "ctry", "lat", "lon", "elev_m", "begin", "end", "why"]
    sel.to_csv(f"{OUT}/stations.csv", index=False)
    return sel


def fetch(job):
    usaf, wban, y = job
    fn = f"{usaf}-{wban}-{y}.gz"
    dst = f"{OUT}/raw/{fn}"
    if os.path.exists(dst):
        return "have"
    try:
        with urllib.request.urlopen(f"{BASE}/{y}/{fn}", timeout=60) as r:
            data = r.read()
        with open(dst + ".part", "wb") as f:
            f.write(data)
        os.replace(dst + ".part", dst)
        return "ok"
    except urllib.error.HTTPError as e:
        return f"http{e.code}"
    except Exception as e:  # network trouble: report, do not hide
        return f"err:{type(e).__name__}"


if __name__ == "__main__":
    os.makedirs(f"{OUT}/raw", exist_ok=True)
    st = pick_stations()
    print(st.to_string(index=False))
    jobs = [(r.usaf, r.wban, y) for r in st.itertuples() for y in YEARS]
    with ThreadPoolExecutor(16) as ex:
        res = list(ex.map(fetch, jobs))
    print(pd.Series(res).value_counts().to_dict())
    got = pd.DataFrame(jobs, columns=["usaf", "wban", "year"]).assign(res=res)
    print("years present per station:")
    print(got[got.res.isin(["ok", "have"])].groupby("usaf").size().to_string())
