"""Trend in yearly counts: Theil-Sen slope, Mann-Kendall test, a pre-whitened repeat, and false discovery rate.

Used for "trend in heat spell days" (references/indicators.md, "Is it
emerging", product 1). All functions take an array of shape (series, years)
with equally spaced years and work on every series at once.

    theil_sen(x)        median of the slopes between all pairs of years, per year
    mann_kendall(x)     S, its variance with the correction for tied values, the
                        continuity-corrected z, and the two-sided p-value
    prewhitened(x)      the series with its lag-1 autocorrelation removed:
                        x(t) - r1 x(t-1), with r1 measured on the series itself.
                        Measured here on 20,000 trend-free series with lag-1
                        autocorrelation 0.4: plain Mann-Kendall gives p below
                        0.05 at 16.5 percent of them, this version at 4.7
                        percent. "Trend-free" pre-whitening (detrend first, put
                        the trend back) was tried and rejected: 21.3 percent.
                        The cost is power: with a real trend and no
                        autocorrelation, fewer series pass (85 against 95
                        percent at a trend of 0.04 standard deviations a year)
    fdr_threshold(p,q)  the largest p-value that passes the Benjamini-Hochberg
                        step-up rule at rate q (0 if none passes)

A trend is called significant here only when BOTH the plain and the
pre-whitened Mann-Kendall p-values pass the same false discovery threshold.
That is a project choice, made to be on the cautious side.

Self-test:  bash tools/py.sh pipeline/trend.py
"""
import numpy as np
from scipy import stats


def _pairs(n):
    i, j = np.triu_indices(n, 1)
    return i, j


def theil_sen(x, chunk=20000):
    x = np.asarray(x, "f8")
    i, j = _pairs(x.shape[1])
    out = np.empty(x.shape[0])
    for a in range(0, x.shape[0], chunk):
        b = x[a:a + chunk]
        out[a:a + chunk] = np.median((b[:, j] - b[:, i]) / (j - i), axis=1)
    return out


def mann_kendall(x, chunk=20000):
    x = np.asarray(x, "f8")
    m, n = x.shape
    i, j = _pairs(n)
    s = np.empty(m)
    for a in range(0, m, chunk):
        b = x[a:a + chunk]
        s[a:a + chunk] = np.sign(b[:, j] - b[:, i]).sum(axis=1)
    srt = np.sort(x, axis=1)                                   # tie groups: runs of equal values in the sorted series
    run = np.ones(m)
    tie = np.zeros(m)
    for k in range(1, n):
        same = srt[:, k] == srt[:, k - 1]
        tie += np.where(~same, run * (run - 1) * (2 * run + 5), 0.0)
        run = np.where(same, run + 1, 1.0)
    tie += run * (run - 1) * (2 * run + 5)
    var = (n * (n - 1) * (2 * n + 5) - tie) / 18.0
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(var > 0, (s - np.sign(s)) / np.sqrt(var), 0.0)
    return s, var, z, 2 * stats.norm.sf(np.abs(z))


def prewhitened(x):
    x = np.asarray(x, "f8")
    x0 = x - x.mean(axis=1, keepdims=True)
    den = (x0 ** 2).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        r1 = np.where(den > 0, (x0[:, 1:] * x0[:, :-1]).sum(axis=1) / den, 0.0)
    return x[:, 1:] - r1[:, None] * x[:, :-1], r1


def fdr_threshold(p, q):
    p = np.sort(np.asarray(p, "f8")[np.isfinite(p)])
    if p.size == 0:
        return 0.0
    ok = p <= q * np.arange(1, p.size + 1) / p.size
    return float(p[np.nonzero(ok)[0].max()]) if ok.any() else 0.0


def trend_table(x, q=0.10, where=None):
    """Slope per year, plain and pre-whitened p, and the significance flag at false discovery rate q over the series in `where`."""
    slope = theil_sen(x)
    p1 = mann_kendall(x)[3]
    xw, r1 = prewhitened(x)
    p2 = mann_kendall(xw)[3]
    p = np.maximum(p1, p2)
    thr = fdr_threshold(p if where is None else p[where], q)
    return {"slope": slope, "p": p1, "p_pw": p2, "r1": r1, "sig": p <= thr, "threshold": thr}


if __name__ == "__main__":
    rng = np.random.default_rng(1)
    x = np.round(rng.normal(30, 8, (300, 47)) + 0.3 * np.arange(47)[None, :] * rng.uniform(-1, 1, (300, 1)))
    ref = np.array([stats.theilslopes(r, np.arange(47))[0] for r in x])
    print(f"Theil-Sen against scipy.stats.theilslopes, 300 series: largest difference {np.abs(theil_sen(x) - ref).max():.2e}")
    s, var, z, p = mann_kendall(x)
    s2 = np.array([sum(np.sign(r[j] - r[i]) for i in range(47) for j in range(i + 1, 47)) for r in x[:40]])
    tau_p = np.array([stats.kendalltau(np.arange(47), r, method="asymptotic").pvalue for r in x])
    zc = np.where(var > 0, s / np.sqrt(var), 0.0)              # scipy's asymptotic test has no continuity correction
    print(f"Mann-Kendall S against a plain double loop, 40 series: differing {int((s[:40] != s2).sum())}")
    print(f"p-value without the continuity correction against scipy.stats.kendalltau (asymptotic, tie-corrected): largest difference {np.abs(2 * stats.norm.sf(np.abs(zc)) - tau_p).max():.2e}")
    null = rng.normal(0, 1, (20000, 47))
    t = trend_table(null, 0.10)
    print(f"20,000 series of pure noise: plain p below 0.05 at {(t['p'] < 0.05).mean():.3f} (expected 0.05); called significant at false discovery rate 0.10: {int(t['sig'].sum())}")
    ar = np.zeros((20000, 47))
    e = rng.normal(0, 1, (20000, 47))
    for k in range(1, 47):
        ar[:, k] = 0.4 * ar[:, k - 1] + e[:, k]
    t = trend_table(ar, 0.10)
    print(f"20,000 series with lag-1 autocorrelation 0.4 and no trend: plain p below 0.05 at {(t['p'] < 0.05).mean():.3f}, pre-whitened {(t['p_pw'] < 0.05).mean():.3f}; called significant: {int(t['sig'].sum())}")
