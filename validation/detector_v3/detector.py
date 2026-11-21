"""Heat spell detector, revision 3 (single-cell reference implementation).

Changes from the tuned detector of validation/heat_spell_prototype/03_tune_detector.py
("ctr_p90_fixed"), made after the second method critique (2026-11-21, items A1 and A2):

  1. MINIMUM LENGTH. A heat spell is a run of at least MIN_RUN flagged days
     (default 3). Shorter runs are not spells and carry no class. Before, a
     single flagged day was an event, and 15 to 33 percent of events were.
  2. DAILY INTENSITY CLASS (user decision, 2026-11-21). Each spell day is
     classed by that day's own excess over its threshold: spell, severe or
     extreme by the 80th and 95th percentile of the daily excess on baseline
     spell days. It uses no later day, so a live monitor can show it. This is
     the class the map draws (field cls_day). Duration and the spell's
     magnitude so far (field running) are separate numbers and drive event
     ranking. Two other classes are kept for comparison only: cls_causal (by
     the running total, tested first and found slow: median 6 days to reach
     severe) and cls_final (the finished spell, hindsight, archive use).
  3. ONE SPREAD MEASURE. Excess is divided by the inter-quartile range of the
     baseline anomalies of the 3-day mean, the same quantity the excess is
     measured on. The code always did this; the specification said "Tm
     anomalies" and is corrected to match.

Unchanged: Tm = (Tmax(d) + Tmin(d+1)) / 2; t3 = 3-day mean centred on the day;
a day is flagged when t3 is above its calendar-day 90th percentile (15-day
window, seasonal cycle removed, 1991-2020) and above the all-year median, OR
above the all-year 95th percentile; excess is the larger of the two
exceedances; class cuts are the 80th and 95th percentile of the magnitudes of
finished baseline spells; fixed 1991-2020 thresholds.

Latency: t3 on day d needs Tm(d+1), which needs Tmin(d+2). The latest day
that can be classed is two days behind the newest data.
"""
import importlib.util
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_P = os.path.join(HERE, "..", "heat_spell_prototype")


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_P, fn))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


p1 = _load("p01", "01_prototype.py")
t3mod = _load("t03", "03_tune_detector.py")
MIN_RUN, CAL_Q, CUTS = 3, 90, (80, 95)


def detect(tm, idx, min_run=MIN_RUN):
    """tm: daily Tm for one cell (deg C, NaN where missing); idx: DatetimeIndex.

    Returns a dict with per-day arrays (flag, spell, excess, running, cls_day,
    cls_causal, cls_final) and per-spell arrays (s, e, mag, cls), plus the cuts.
    """
    import pandas as pd
    n = len(tm)
    t3 = pd.Series(tm).rolling(3, center=True).mean().values
    thr, clim, iqr, base = t3mod.cal_threshold(t3, idx, CAL_Q)
    ok = np.isfinite(t3)
    p50, p95 = np.percentile(t3[base & ok], [50, 95])
    cal = ok & (t3 > thr) & (t3 > p50)
    allyr = ok & (t3 > p95)
    flag = cal | allyr
    exc = np.nan_to_num(np.where(flag, np.fmax((t3 - thr) / iqr, (t3 - p95) / iqr), 0.0))
    s, e = p1.runs(flag, min_len=min_run)
    s, e = np.asarray(s, int), np.asarray(e, int)
    mag = np.array([exc[a:b + 1].sum() for a, b in zip(s, e)])
    inb = (idx.year[s] >= 1991) & (idx.year[s] <= 2020)
    q80, q95 = np.percentile(mag[inb], CUTS)
    cls = 1 + (mag >= q80).astype(int) + (mag >= q95).astype(int)
    spell = np.zeros(n, bool)
    running = np.zeros(n)
    cls_final = np.zeros(n, int)
    for a, b, c in zip(s, e, cls):
        spell[a:b + 1] = True
        running[a:b + 1] = np.cumsum(exc[a:b + 1])
        cls_final[a:b + 1] = c
    cls_causal = np.where(spell, 1 + (running >= q80).astype(int) + (running >= q95).astype(int), 0)
    e80, e95 = np.percentile(exc[spell & np.asarray(base)], CUTS)
    cls_day = np.where(spell, 1 + (exc >= e80).astype(int) + (exc >= e95).astype(int), 0)
    return {"flag": flag, "spell": spell, "excess": exc, "running": running, "cls_day": cls_day, "cls_causal": cls_causal, "cls_final": cls_final,
            "e80": float(e80), "e95": float(e95),
            "s": s, "e": e, "mag": mag, "cls": cls, "q80": float(q80), "q95": float(q95), "iqr": float(iqr),
            "which": np.where(cal & allyr, 3, np.where(cal, 1, np.where(allyr, 2, 0)))}
