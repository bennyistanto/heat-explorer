"""Where the raw AgERA5 days are, in time order.

Two kinds of file, both read-only for every pass:
    yearly files    E:/temp/agera5/<var>/agera5_<var>_<year>.nc
    supplements     E:/temp/agera5/derived-products/heat-explorer/raw_update/<var>/agera5_<var>_<first>_<last>.nc
                    days after the last yearly file, written by pipeline/fetch_agera5.py

    files(v)            every file of variable v, in time order
    files(v, years)     only the files holding those years; supplements are filed under the year of their first day
    time_axis(v)        days since 1900-01-01 over all files; raises if a day is missing or repeated

Run to list them:  bash tools/py.sh pipeline/rawfiles.py
"""
import glob
import os
import re

import netCDF4 as nc
import numpy as np

RAW = "E:/temp/agera5"
UPD = "E:/temp/agera5/derived-products/heat-explorer/raw_update"
VARS = {"t2mmax": "Temperature_Air_2m_Max_24h", "t2mmin": "Temperature_Air_2m_Min_24h", "t2mdp": "Dew_Point_Temperature_2m_Mean_24h"}


def yearly(v):
    return sorted(p.replace("\\", "/") for p in glob.glob(f"{RAW}/{v}/agera5_{v}_[0-9][0-9][0-9][0-9].nc"))


def supplements(v):
    return sorted(p.replace("\\", "/") for p in glob.glob(f"{UPD}/{v}/agera5_{v}_[0-9]*_[0-9]*.nc"))


def year_of(p):
    return int(re.search(r"_(\d{4})", os.path.basename(p)).group(1))


def files(v, years=None):
    out = yearly(v) + supplements(v)
    return out if years is None else [p for p in out if year_of(p) in set(years)]


def last_year(v="t2mmax"):
    return max(year_of(p) for p in files(v))


def time_axis(v="t2mmax"):
    out = []
    for p in files(v):
        d = nc.Dataset(p)
        out.append(np.asarray(d.variables["time"][:]).astype("i8"))
        d.close()
    t = np.concatenate(out)
    if not (np.diff(t) == 1).all():
        raise SystemExit(f"{v}: the days are not one unbroken run; first break after day {int(t[np.argmax(np.diff(t) != 1)])} (days since 1900-01-01)")
    return t


if __name__ == "__main__":
    import pandas as pd
    for v in VARS:
        t = time_axis(v)
        f = files(v)
        print(f"{v}: {len(f)} files ({len(supplements(v))} supplements), {len(t)} days, {(pd.Timestamp('1900-01-01') + pd.Timedelta(days=int(t[0]))).date()} to {(pd.Timestamp('1900-01-01') + pd.Timedelta(days=int(t[-1]))).date()}")
