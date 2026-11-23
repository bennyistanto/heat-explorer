# Heat spell detector, version 1.0 (frozen)

Frozen on 2026-11-21 by the author, after the third held-out event
suite. "Frozen" means the definitions below do not change without a new
version number and a new test on events not used before.

Reference code: `validation/detector_v3/detector.py`, fields `flag`, `spell`
and `cls_day`. Where this text and that code disagree, the code as it stood on
2026-11-21 is the definition and this text is wrong.

## What is frozen

### 1. Input

- Data: AgERA5 daily maximum and minimum 2 m temperature, 0.1 degree, land cells.
- Daily mean: `Tm(d) = (Tmax(d) + Tmin(d+1)) / 2`. The minimum is the one that follows the maximum.
- Smoothed value: `t3(d)`, the mean of `Tm` over days d-1, d, d+1.
- Baseline: 1991 to 2020, fixed. No adjustment for warming since.

### 2. Thresholds, per cell

- Seasonal cycle: the mean of `t3` for each calendar day over the baseline, smoothed with a centred 31-day running mean. 29 February uses 28 February's values.
- Calendar-day percentiles: of `t3` minus the seasonal cycle, pooling the baseline days within 7 days of the calendar day (a 15-day window, about 450 values), added back to the seasonal cycle. Three are used: the 90th, 95th and 99th.
- All-year values: the median and the 95th percentile of `t3` over all baseline days.

### 3. Flagged day

A day is flagged when either holds:

- `t3` is above its calendar-day 90th percentile **and** above the all-year median; or
- `t3` is above the all-year 95th percentile.

### 4. Heat spell

A run of at least 3 consecutive flagged days. Shorter runs are not spells.

### 5. Class of a spell day

- **heat spell:** a spell day not above its calendar-day 95th percentile
- **severe:** above its calendar-day 95th percentile
- **extreme:** above its calendar-day 99th percentile

The class describes that day only. It uses no later day and does not change
after it is written.

### 6. What a live monitor shows ("live labelling")

A day is shown as in a spell when it and the two days before it are all
flagged. So a new spell first appears on its third day. Because `t3(d)` needs
`Tmin(d+2)`, the latest day that can be shown is two days behind the newest
data.

### 7. Admin unit

- A cell belongs to the unit that contains its centre. Cells are weighted by the cosine of latitude.
- "Severe heat over most of the area": the share of the unit's area that is severe or extreme, by the live labelling, is 0.50 or more.

### 8. Location readout

For a place, the 3 by 3 block of cells around the cell that contains it
(about 33 km across). The place is severe when more than half of the block's
land cells are severe or extreme, by the live labelling.

## Evidence

One registered test on events not used to build any of this:
`validation/heldout_suite_3/` (protocol and events written before the run;
run once; no deviations).

| Test | Result | Bar | Median base rate |
|---|---|---|---|
| Admin unit severe on a documented day | 9 of 10 | 8 | 0.06 |
| Location readout severe on a documented day | 8 of 10 | 8 | 0.07 |

Base rate: how often the same condition is met on the same dates in the other
46 years.

Supporting, not confirmatory for this version: two earlier registered suites
(`validation/heldout_suite/`, `validation/heldout_suite_2/`) tested the same
flag and spell rules with a different class and an extra ranking condition.
They came out at 6 of 9 and 7 of 10 and were recorded as not accepted. Without
the ranking condition they read 8 of 9 and 9 of 10.

## Implementations

- Reference, one cell at a time: `validation/detector_v3/detector.py`.
- Production, many cells at once: `pipeline/detector.py`, function `detect_block`. Checked identical to the reference on `flag`, `spell` and `cls_day` on every day at 2,039 cells in 17 climates, 35.5 million cell-days, on 2026-11-21 (`validation/detector_v3/03_fast_equals_reference.py`, result in `validation/detector_v3/results/fast_equals_reference.txt`). That check must be re-run after any change to the production module.

## Known limits of version 1.0

- **Small sample.** Nine of ten is compatible with a true success rate from about 55 to 100 percent. The test shows the detector is not broken on new events. It does not show it is reliable.
- **No false-alarm test** beyond the base rates.
- **Low-confidence climates.** Where day-to-day temperature varies little (17 percent of land, mostly within 10 degrees of the equator), three such units have been tested and one failed (Central Equatoria, February 2025).
- **Not adjusted for warming.** In recent years far more days are flagged than in the baseline. That is a true statement about the climate and a weak one about events.
- **The spell flag is uneven through the year.** Spell days are 6 to 8 percent of days in some warm months and 20 to 44 percent in the hottest month, because the all-year test admits ordinary midsummer days. The class in section 5 is even through the year; the flag is not.
- **Thresholds are taken from all 30 baseline years**, which makes baseline years flag slightly less than later years. Taking them with each year left out in turn would be a new version.
- **Known breaks in the source data** at 1,301 cells (`config/data_suspect/`). Those cells are marked on the page and kept in every number, by the author's decision.
- **The readout test was registered with a rule that sent one readout (Jaipur) away from its event.** It is counted as a failure.

## Not frozen

- The size of a spell or event, and any ranking built on it. Set on 2026-11-22 by the author for admin units: **degree-days**. For each day, the number of degrees (K) by which a cell in a heat spell (live labelling) is above its heat threshold, averaged over the unit's whole area with cells not in a spell counting as zero; summed over the days of the event. The heat threshold is whichever of the two flag thresholds (calendar-day 90th percentile, all-year 95th percentile) the day exceeds by more. Stored as `adm*_degdays` by `pipeline/admin_series.py`. How it was chosen, in order: severe area-days (the severe share summed over the event) was adopted first, after a comparison on the 29 registered unit-windows; a second comparison added degree-days (`validation/event_size/02_revisit.py`), and by the rule written before that run severe area-days was to stay (top 3 of 47 years at 26 of 29 windows for both; landmark events in the top 3 at 6 of 13 for both, in the top 10 at 7 against 9). The author then chose degree-days, preferring a measure of how much heat there was over one of how unusual it was for the time of year. Known cost, measured in the same run: 73 percent of a unit's ten largest events begin in the three summer months, against 52 percent for severe area-days. Both comparisons were post hoc, so this is a setting, not part of version 1.0. The rule that decides which days form one event (a quarter of the area in a heat spell, gaps of up to 2 days joined, at least 3 such days) is unchanged and also not frozen; it joins whole seasons into one event in many low-confidence units.
- The humid heat layer (kept, marked experimental).
- The confidence classes and their limits.
- The middle tier of the admin status line ("part of the area"). Set on 2026-11-22 by the author at a severe share of 0.25 or more (and below 0.50), by the live labelling. It was chosen from how often it is met (a median of about 11 days a year in 1991-2020 at country, province and district level; `pipeline/results/check_admin.txt`), not tested on events, so it is a setting and not part of version 1.0.
- The trend map, the season status and any hot spot analysis.
- How fast the detector is computed. A faster implementation must reproduce the reference code's `flag`, `spell` and `cls_day` exactly.
