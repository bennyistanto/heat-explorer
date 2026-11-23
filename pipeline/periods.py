"""Which days the page can show on the daily map.

Two kinds of period:
    the recent window   the last RECENT days that can be classed, continuous
    past events         each row of config/archive_events.csv (name, start, end),
                        with PAD days added before and after; west, south, east,
                        north give the map extent the page opens the event on, and
                        focus_lat, focus_lon the place whose province it selects

Every pass that makes daily products (pipeline/web_products.py,
run_daynight.py, run_humid.py) takes its list of days from here, so they
agree. To add an event, add a row to the csv and re-run those three.

    periods(days) -> list of {"name", "start", "end", "idx"}, idx = positions on the store's time axis
    all_days(days) -> sorted unique positions over all periods

Run to list them:  bash tools/py.sh pipeline/periods.py
"""
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
EVENTS = os.path.join(HERE, "..", "config", "archive_events.csv")
RECENT, PAD, TAIL, LOOK = 365, 5, 2, 70          # LOOK: days needed before a day to count the day of its spell


def periods(days):
    days = np.asarray(days)
    idx = pd.DatetimeIndex(pd.Timestamp("1900-01-01") + pd.to_timedelta(days, unit="D"))
    last = len(days) - TAIL                                     # one past the last day that can be classed
    out = [{"name": f"Year to {idx[last - 1].day} {idx[last - 1]:%b %Y}", "start": str(idx[last - RECENT].date()), "end": str(idx[last - 1].date()), "idx": np.arange(last - RECENT, last)}]
    ev = pd.read_csv(EVENTS, parse_dates=["start", "end"]).sort_values("start")
    for r in ev.itertuples():
        a = int(np.searchsorted(idx.values, np.datetime64(r.start - pd.Timedelta(days=PAD))))
        b = int(np.searchsorted(idx.values, np.datetime64(r.end + pd.Timedelta(days=PAD)), side="right"))
        a, b = max(a, LOOK), min(b, last)
        if b > a:
            out.append({"name": f"{r.start.year}: {r.name}", "start": str(idx[a].date()), "end": str(idx[b - 1].date()), "idx": np.arange(a, b),
                        "bbox": [float(r.west), float(r.south), float(r.east), float(r.north)] if hasattr(r, "west") and pd.notna(r.west) else None,
                        "focus": [float(r.focus_lat), float(r.focus_lon)] if hasattr(r, "focus_lat") and pd.notna(r.focus_lat) else None})
    return out


def all_days(days):
    return np.unique(np.concatenate([p["idx"] for p in periods(days)]))


if __name__ == "__main__":
    import zarr
    d = zarr.open_group("E:/temp/agera5/derived-products/heat-explorer/v1/heat_state.zarr", mode="r")["time"][:]
    ps = periods(d)
    for p in ps:
        print(f"{p['start']} to {p['end']}  {len(p['idx']):4d} days  {p['name']}")
    n = len(all_days(d))
    print(f"{len(ps)} periods, {n} distinct days ({n - RECENT} outside the recent window)")
