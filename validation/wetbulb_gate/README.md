# Wet-bulb gate

Tests whether AgERA5 can support an absolute humid-heat layer, by comparing its
afternoon wet-bulb (`Tw_day`, from daily maximum temperature and daily mean
dewpoint) with station observations. Run on 2026-11-21. **Result: the gate fails.**

## Run

```
bash tools/py.sh validation/wetbulb_gate/01_download_isd.py
bash tools/py.sh validation/wetbulb_gate/02_extract_agera5_points.py
bash tools/py.sh validation/wetbulb_gate/03_compare.py
```

Step 2 reads 192 raw AgERA5 files and took 400 s. Outputs: `results/summary.txt`,
`results/isd_comparison.csv`, `results/wxgrid_comparison.csv`.

## Data

| Source | What | Where |
|---|---|---|
| NOAA ISD-Lite | hourly temperature and dewpoint, 29 stations, 1979 to 2025, 1,341 station-years, 73 MB | `E:\temp\station-isd\raw`, list in `E:\temp\station-isd\stations.csv` |
| wxgrid compiled dataset | Indonesian daily TX, TG, HU, HU13; 185 sites selected | `F:\temp\station\compiled` (read-only, owned by the wxgrid repo) |
| AgERA5 | `t2mmax, t2mmin, t2mmean, t2mdp` at 214 points | `E:\temp\agera5\derived-products\heat-explorer\wetbulb-gate` |
| ETOPO1 | cell elevation for pressure | `E:\temp\dem\etopo180_4558_b013_12d8.nc` |

ISD-Lite download pattern: `https://noaa-isd-pds.s3.amazonaws.com/isd-lite/data/<year>/<usaf>-<wban>-<year>.gz`
(the old `ncei.noaa.gov/pub/data/noaa/isd-lite` path now redirects there).
"Jacobabad" is ISD station 417150 Shahbaz AB, 3 km from the town coordinates.

## Result

Gate, written before the run: fail if the 99th percentile gap exceeds 1 K, or
days per year above a band edge differ by more than 2 times.

ISD, 29 stations, AgERA5 minus station (medians across stations):

| Comparison | Gap at p50 | p95 | p99 | Stations with p99 gap over 1 K |
|---|---|---|---|---|
| Station daily maximum wet-bulb vs `Tw_day` | -0.94 | -1.31 | -1.60 | 20 of 29 |
| Station wet-bulb at the hour of Tmax vs `Tw_day` | -0.24 | -0.43 | -0.72 | 13 of 29 |
| Station maximum of hourly temperature vs AgERA5 Tmax | -1.15 | -1.49 | -1.80 | 21 of 29 |
| Station daily mean dewpoint vs AgERA5 dewpoint | -0.37 | -0.66 | -0.70 | 13 of 29 |

Days per year with wet-bulb at or above 28 C: AgERA5 gives a median of 0.05
times the station count, and is outside the 0.5 to 2 range at 19 of the 20
stations where the level occurs. At 26 C: median ratio 0.47, outside the range
at 13 of 23.

Where the gap comes from, by region:

- **Gulf coast** (Bahrain, Doha, Dhahran, Abu Dhabi, Kuwait): wet-bulb at the hour of Tmax agrees (gap -0.7 to +0.7 K), but the daily maximum is 1.5 to 4.3 K higher at the station. The humid peak is not at the hour of maximum temperature there, so a Tmax-plus-mean-dewpoint estimate misses it by construction.
- **Inland South Asia** (Shahbaz AB, Nawabshah, Ahmedabad, Hyderabad, Delhi): AgERA5 dewpoint is 2.0 to 3.2 K too low on average.
- **Coastal equatorial stations** (Singapore, Jakarta, Manaus): AgERA5 Tmax is 1.6 to 2.4 K lower than the station, and day-to-day correlation of wet-bulb is only 0.44 to 0.74, against 0.92 to 0.99 at most other stations.
- **Mid-latitudes** (Paris, Moscow, Portland, Phoenix, Houston): gaps within 1 K.

wxgrid, Indonesia: AgERA5 Tmax is lower than station TX by a median of 2.45 K
(183 sites, daily correlation median 0.66); daily mean wet-bulb is lower by a
median of 0.69 K (182 sites, correlation 0.71); wet-bulb from TX with 13:00
humidity is lower by 2.22 K (20 sites, correlation 0.33).

## Anomaly skill (04_anomaly_skill.py)

```
bash tools/py.sh -W ignore validation/wetbulb_gate/04_anomaly_skill.py
```

Removes each series' own smoothed seasonal cycle, then measures anomaly
correlation and the hit rate of monthly 90th percentile exceedance. Outputs
`results/anomaly_skill.txt` and `results/anomaly_skill.csv`. Headline: skill
rises steadily with the spread of AgERA5's own anomalies (rank correlation
+0.94 for Tmax across the 29 ISD stations), from a hit rate of 0.34 where that
spread is below 0.75 K to 0.79 where it exceeds 2.5 K. This is the basis of the
confidence mask in `references/indicators.md`.

## HadISD repeat (05_download_hadisd.py, 06_compare_hadisd.py)

Same comparison with quality-controlled HadISD 3.4.3.2025f, 26 of the 29
stations, 150 MB in `E:\temp\station-hadisd\nc`. Per-station files:
`https://www.metoffice.gov.uk/hadobs/hadisd/v343_2025f/data/hadisd.3.4.3.2025f_19310101-20250829_<usaf>-<wban>.nc.gz`.
Non-Commercial Government Licence; validation use only, not redistributed.

Result: unchanged. Daily maximum wet-bulb gap at the 99th percentile -1.69 K
(ISD-Lite, same stations: -1.75 K); days at or above 28 C 0.05 times observed
in both; anomaly correlation and hit rates equal to two decimals. Quality
control lowered record maxima at some stations (Manaus 34.3 to 30.8 C) but kept
the Gulf extremes (Dhahran 36.1, Bahrain 35.3, Doha 35.0 C). See
`results/hadisd_summary.txt`.

## Limits of this test

- ISD-Lite is not quality controlled. Station maxima such as 37.7 C wet-bulb at Shahbaz AB are probably bad dewpoints, which is why the gate uses the 99th percentile, not the maximum. A HadISD repeat would be cleaner.
- Stations with 8 observations a day miss the true daily maximum, which makes the station figures conservative.
- A station is a point, often an airport or a coast; an AgERA5 cell is about 120 km2 of smoothed model. Part of every gap is representativeness, not error.
- wxgrid temperature and humidity are not yet quality controlled in that project, day labels can be off by one, and many sites lack elevation. Treat the Indonesian numbers as indicative.
- Correlations are on raw daily values, so outside the tropics they are inflated by the seasonal cycle. An anomaly correlation is the fair test for the relative indicators and has not been run.
