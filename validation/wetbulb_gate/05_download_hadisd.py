"""Download HadISD (quality-controlled sub-daily station data) for the gate stations.

Source: Met Office Hadley Centre, HadISD version 3.4.3.2025f
  https://www.metoffice.gov.uk/hadobs/hadisd/v343_2025f/download.html
  per-station files: .../v343_2025f/data/hadisd.3.4.3.2025f_19310101-20250829_<usaf>-<wban>.nc.gz

Licence: Non-Commercial Government Licence; Crown copyright, Met Office.
Non-commercial use with attribution. The provider asks users to cite Dunn et al.
(2012, 2014, 2016), Dunn (2019) and Smith et al. (2011), and to state the
version and download date. Redistribution must carry the same usage statement.
The files are kept outside the repository and are not republished.

Stations are the ones chosen in 01_download_isd.py. Three of the 29 are not in
HadISD (Tejgaon, Jakarta Observatory, Lagos Murtala Muhammed).

Run:  bash tools/py.sh validation/wetbulb_gate/05_download_hadisd.py
Output: E:/temp/station-hadisd/nc/*.nc
"""
import gzip
import os
import shutil
import urllib.request

import pandas as pd

OUT = "E:/temp/station-hadisd"
BASE = "https://www.metoffice.gov.uk/hadobs/hadisd/v343_2025f/data"
STEM = "hadisd.3.4.3.2025f_19310101-20250829_"

if __name__ == "__main__":
    os.makedirs(f"{OUT}/nc", exist_ok=True)
    listed = {ln.split()[0] for ln in open(f"{OUT}/stations_fullinfo.txt", encoding="latin-1") if ln.strip()}
    st = pd.read_csv("E:/temp/station-isd/stations.csv", dtype={"usaf": str, "wban": str})
    for s in st.itertuples():
        sid = f"{s.usaf}-{s.wban}"
        dst = f"{OUT}/nc/{STEM}{sid}.nc"
        if sid not in listed:
            print(sid, s.name.strip(), "not in HadISD")
            continue
        if os.path.exists(dst):
            print(sid, "have")
            continue
        req = urllib.request.Request(f"{BASE}/{STEM}{sid}.nc.gz", headers={"User-Agent": "Mozilla/5.0 research-client"})
        with urllib.request.urlopen(req, timeout=180) as r, open(dst + ".gz", "wb") as f:
            shutil.copyfileobj(r, f)
        with gzip.open(dst + ".gz", "rb") as g, open(dst + ".part", "wb") as f:
            shutil.copyfileobj(g, f)
        os.replace(dst + ".part", dst)
        os.remove(dst + ".gz")
        print(sid, s.name.strip(), f"{os.path.getsize(dst) / 1e6:.0f} MB")
