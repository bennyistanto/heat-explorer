# AgERA5 against weather stations: what agrees, what does not, and what it means for a heat monitor

> Written 2026-11-21. Every number below was computed by a script in this
> repository from data on disk; the script is named beside each result. Where
> something is an interpretation and not a measurement, the text says so.

## 1. Why this comparison was made

heat-explorer is meant to monitor heat around the world from AgERA5, a daily
0.1 degree weather dataset for agriculture derived from the ERA5 reanalysis.
The plan was to show two things: heat that is unusual for a place, and heat
that is dangerous for a human body anywhere, measured by wet-bulb temperature.

The second idea carries a hidden assumption. A map that says "wet-bulb reached
30 C here" only holds if the dataset reproduces the real value at the real
peak. A map that says "unusually hot for this place" needs less: the dataset
only has to rise and fall on the right days. So the question splits in two:

1. **Does AgERA5 get the level right**, especially at the hot and humid extreme?
2. **Does AgERA5 get the timing right**, day to day, well enough to flag the right days?

Stations answer both. This document tells what they said.

## 2. What was compared

| Side | Data | Coverage |
|---|---|---|
| Stations, global | NOAA ISD-Lite: hourly air temperature and dewpoint | 29 stations, 1979 to 2025, 1,341 station-years |
| Stations, Indonesia | wxgrid compiled dataset: daily maximum, minimum and mean temperature, humidity | 185 sites selected, of which 183 gave usable temperature comparisons |
| AgERA5 | daily maximum, minimum, mean temperature and mean dewpoint at the grid cell containing each station | 214 points, 1979-01-01 to 2026-09-15 |

The 29 global stations were chosen for a spread of climates with weight on
humid heat: the Gulf coast, the Indus plain, India and Bangladesh, South-East
Asia, West and East Africa, the Amazon, the southern United States, and four
mid-latitude cities as a reference. The Indonesian sites come from the wxgrid
project, which consolidates BMKG and related station records.

Method in brief:

- **Wet-bulb temperature** is computed the same way on both sides, by an iterative solve of the psychrometric balance, with pressure estimated from elevation (station elevation for stations, mean ETOPO1 elevation of the cell for AgERA5).
- **Station daily maximum wet-bulb** is the highest hourly value in the local day. AgERA5 has no hourly data, so its afternoon wet-bulb is built from daily maximum temperature and daily mean dewpoint. This is the quantity the monitor would have used.
- **Level** is compared by quantiles on days both sides have, mainly the 99th percentile (about the four hottest days a year).
- **Timing** is compared on anomalies: each series has its own seasonal cycle removed, then the correlation and a hit rate are computed. The hit rate is the share of station hot days (above the station's own 90th percentile for that month) that AgERA5 also flags above its own. Chance gives 0.10.

Scripts: `validation/wetbulb_gate/01_download_isd.py`, `02_extract_agera5_points.py`,
`03_compare.py`, `04_anomaly_skill.py`. Outputs: `validation/wetbulb_gate/results/`.

## 3. First finding: in the mid-latitudes the two agree well

Start with the good news, because it sets the standard for everything else.

| Station | Wet-bulb gap at the 99th percentile, K | Tmax anomaly correlation | Tmax hit rate |
|---|---|---|---|
| Paris Orly | -0.74 | 0.98 | 0.90 |
| Moscow Vnukovo | -0.23 | 0.98 | 0.93 |
| Portland, Oregon | -0.61 | 0.96 | 0.88 |
| Phoenix | +0.09 | 0.97 | 0.88 |
| Houston | -0.51 | 0.96 | 0.79 |

(Gap is AgERA5 minus station. `03_compare.py`, `04_anomaly_skill.py`.)

Here AgERA5 is within about half a degree at the extreme, and it flags roughly
nine of every ten hot days the station sees. A heat monitor built on AgERA5 is
on firm ground in these climates.

## 4. Second finding: AgERA5 runs cool at the hot end

Across all 29 stations, AgERA5 maximum temperature is lower than the station's
highest hourly reading:

| Quantile | Median gap, AgERA5 minus station, K |
|---|---|
| 50th | -1.15 |
| 95th | -1.49 |
| 99th | -1.80 |

The gap exceeds 1 K at the 99th percentile at 21 of 29 stations, and it grows
toward the extreme (`03_compare.py`, breakdown run on `results/isd_comparison.csv`).

Two things make this a conservative figure. The station value is the maximum of
hourly readings, and at stations reporting only every three hours the true
daily maximum is higher still. So the real cool bias is, if anything, larger.

The largest gaps are at coastal and island airports: Bahrain -5.8 K, Doha
-5.5 K, Sydney -4.6 K, Dhahran -4.4 K, Singapore -3.7 K. That pattern points to
representativeness more than to error (interpretation): a 0.1 degree cell on a
coast blends land with sea-moderated air, while the airport thermometer sits on
hot tarmac. In Indonesia the same thing shows at scale: across 183 sites AgERA5
maximum temperature is a median of 2.45 K below the station.

**What it means.** Absolute temperature statements from AgERA5 ("it reached
45 C") will read low in many places. Statements relative to AgERA5's own
climate are not affected by a constant offset.

## 5. Third finding: the humid-heat peak is missed, for two different reasons

This is the result that changed the design.

Against the observed daily maximum wet-bulb, AgERA5's afternoon wet-bulb is
lower by a median of **1.6 K at the 99th percentile**, and by more than 1 K at
20 of 29 stations. The effect on day counts is far larger than the number
suggests, because humid-heat thresholds sit in the thin tail of the distribution:

| Level | Stations where it occurs | AgERA5 days per year as a share of observed (median) | Stations outside a factor of two |
|---|---|---|---|
| Wet-bulb at or above 26 C | 23 | 0.47 | 13 |
| Wet-bulb at or above 28 C | 20 | 0.05 | 19 |

At 28 C, AgERA5 sees about one day for every twenty the stations record. Some
examples, in days per year at or above 28 C (station, then AgERA5): Kolkata 105
and 14; Shahbaz air base at Jacobabad 88 and 8; Abu Dhabi 77 and 16; Bangkok 40
and 0.6; Chennai 35 and 3.

The interesting part is that the shortfall has two separate causes, and they
live in different regions.

### 5a. On the Gulf coast the peak comes at the wrong hour

Compare AgERA5 not with the station's daily maximum wet-bulb but with the
station's wet-bulb **at the hour of maximum temperature**:

| Station | Gap against wet-bulb at the hour of Tmax, K | Gap against daily maximum wet-bulb, K |
|---|---|---|
| Bahrain | 0.00 | -1.60 |
| Doha | +0.12 | -1.50 |
| Dhahran | +0.67 | -2.40 |
| Abu Dhabi | -0.26 | -2.33 |
| Kuwait | -0.66 | -4.30 |

At the hour of maximum temperature AgERA5 is essentially right. But on the Gulf
the most humid heat does not happen then. It comes when moist sea air arrives,
often in the evening or at night, at a lower temperature and a much higher
dewpoint. A method that pairs the day's maximum temperature with the day's mean
humidity cannot see that peak, however good the data. This half of the problem
is the definition, not the dataset. Across all stations the same switch of
reference cuts the median gap from 1.6 K to 0.7 K.

### 5b. In inland South Asia the air in AgERA5 is too dry

| Station | Mean dewpoint bias, K | Wet-bulb gap at the 99th percentile, K |
|---|---|---|
| Shahbaz air base (Jacobabad) | -3.19 | -3.12 |
| Nawabshah | -2.57 | -2.82 |
| Delhi Safdarjung | -2.17 | -1.82 |
| Ahmedabad | -2.02 | -2.36 |
| Hyderabad | -2.00 | -2.73 |

Here the gap is the same whichever station reference is used, and it tracks a
dewpoint that is 2 to 3 K too low. These are intensely irrigated plains. A
plausible cause (interpretation, not tested here) is that the reanalysis does
not represent irrigation moisture. This is the region where humid heat is most
dangerous, and it is where the dataset is driest relative to observation.

**What it means.** No absolute wet-bulb product can be published from AgERA5
daily data. The pre-stated test was: fail if the 99th percentile gap exceeds
1 K or day counts differ by more than a factor of two. It failed on both. The
monitor therefore never states an absolute wet-bulb value or a physiological
threshold. Reopening this needs hourly data, so the true daily maximum can be
computed, plus a station-based correction.

## 6. Fourth finding: near the equator AgERA5 loses the day-to-day signal

So far the subject was level. Now timing.

| Stations | Variable | Anomaly correlation, median (range) | Hit rate, median |
|---|---|---|---|
| 29 ISD | maximum temperature | 0.87 (0.65 to 0.98) | 0.71 |
| 29 ISD | minimum temperature | 0.81 (0.55 to 0.97) | 0.65 |
| 29 ISD | wet-bulb | 0.81 (0.44 to 0.97) | 0.55 |
| 183 wxgrid, Indonesia | maximum temperature | 0.56 (0.12 to 0.77) | 0.38 |
| 183 wxgrid, Indonesia | minimum temperature | 0.39 (-0.03 to 0.73) | 0.34 |

(`04_anomaly_skill.py`.)

The global median is respectable. The bottom of the range is not, and it is all
in one kind of climate:

| Station | Tmax anomaly correlation | Tmax hit rate | Wet-bulb hit rate |
|---|---|---|---|
| Singapore Changi | 0.65 | 0.43 | 0.27 |
| Lagos | 0.69 | 0.51 | 0.37 |
| Jakarta Observatory | 0.70 | 0.45 | 0.40 |
| Jakarta Soekarno-Hatta | 0.72 | 0.54 | 0.25 |
| Manaus | 0.74 | 0.42 | 0.25 |

In the equatorial tropics AgERA5 catches fewer than half of the hot days a
station records, and about a quarter of the humid ones. The Indonesian network
says the same with many more sites.

Why (interpretation): day-to-day temperature there varies by well under a
degree, and it is driven by local convection, cloud and sea breeze that a
31 km model does not place on the right day. The dataset's own error is the
same size as the signal.

## 7. Fifth finding: the skill can be predicted without any station

This is the most useful result, because stations are sparse and a global
monitor needs a rule that works everywhere.

Skill follows the **spread of AgERA5's own daily anomalies** at the cell. Across
the 29 ISD stations the rank correlation between that spread and the anomaly
correlation with the station is **+0.94** for maximum temperature, +0.88 for
minimum temperature and +0.84 for wet-bulb.

| AgERA5 anomaly spread, K | Station-variable pairs | Anomaly correlation, median | Hit rate, median |
|---|---|---|---|
| below 0.75 | 257 | 0.44 | 0.34 |
| 0.75 to 1.0 | 86 | 0.60 | 0.41 |
| 1.0 to 1.5 | 42 | 0.69 | 0.45 |
| 1.5 to 2.5 | 24 | 0.85 | 0.68 |
| above 2.5 | 15 | 0.96 | 0.79 |

Where the weather makes temperature swing by several degrees, AgERA5 follows
it. Where the swing is under a degree, it mostly does not. The spread is
available at every one of the 2.4 million land cells, so it gives a confidence
map with no station needed: low below 1.0 K, reduced from 1.0 to 1.5 K, normal
above. The decision taken is to show low-confidence areas, marked as such, and
not to hide them.

## 8. Sixth finding: the 0.1 degree grid is finer than the information in it

A separate experiment looked at 11 by 11 cell windows around 17 locations
(`validation/first_look/hx_neff.py`). Annual heatwave day counts in adjacent
cells correlate between 0.90 and 0.998. Among the 121 cells of a window there
are only about 1.0 to 1.5 effectively independent values.

This matches how the product is built, according to its documentation: ERA5 at
about 31 km is interpolated to 0.1 degree and then adjusted by a regression
trained on a higher-resolution model, not on observations. The fine grid adds
terrain-related detail to the mean climate. It does not add independent weather.

**What it means.** Stations a few kilometres apart can differ on a given day;
neighbouring AgERA5 cells cannot. Statistics that assume neighbouring cells are
independent are inflated about tenfold, and "share of a district affected" is
close to all-or-nothing for small districts.

## 9. Seventh finding: some long-term behaviour looks wrong, and stations have not yet been used to check it

These came from the single-cell experiments, not from the station comparison,
and they are listed here because stations are the only way to settle them.

- **The Indus plain appears to be cooling its heat extremes.** At the Jacobabad cell, days above the calendar 90th percentile of maximum temperature fall from 17.0 percent in 1979 to 1990 to 7.9 percent in 2021 to 2026 (`validation/first_look/hx_analyse.py`). Irrigation and aerosols could produce a real effect; a reanalysis artefact could produce the same number.
- **Humid heat at Manaus vanishes.** Humid heat spell days fall from 6.4 a year in 1991 to 2020 to zero in 2021 to 2025 while temperature spells rise (`validation/heat_spell_prototype/01_prototype.py`). That is hard to believe physically and points to an inconsistency in the humidity record.
- **Tropical exceedance explodes.** In 2021 to 2026 the share of days above the 1991 to 2020 calendar 90th percentile reaches 25 percent for maximum temperature at Singapore and 40 percent for minimum temperature at Lagos, against 1 to 3 percent in 1979 to 1990. Real warming in a narrow-range climate does this, and so would a step in the observing system.

None of these has been checked against station trends. Until they are, no
trend from AgERA5 should be published for these regions without that caveat.

### 9a. The first such check: three patches of sudden recent warmth

When the confidence classes were mapped for every land cell
(`validation/confidence_map/01_confidence_map.py`), 1,388 cells with an ordinary
day-to-day spread showed a third or more of 2021 to 2025 days above an
approximate 90th percentile of 1991 to 2020. They form 33 patches. The three
largest were checked against 14 NOAA ISD-Lite stations
(`validation/confidence_map/02_patch_check.py`, results in
`results/patch_check.txt`), with the reading rule written before the run.

| Patch | AgERA5 shift 2021 to 2025, patch / rest of box | Station shift | AgERA5 minus station, change after 2020 | Reading |
|---|---|---|---|---|
| Northern Japan (609 cells) | +1.70 / +1.13 K | +1.15 to +1.43 K at 6 stations | median 0.50 K | real, overstated |
| Bhutan and Sikkim Himalaya (110 cells) | +1.84 / +0.74 K | +0.82 and +0.91 K at 2 stations | +0.8 and +1.3 K | artefact |
| Eastern Tibetan Plateau (273 cells) | +2.38 / +0.75 K | +0.66 to +0.96 K at 4 stations near the patch | +0.9 to +1.7 K | artefact |

**Northern Japan is real warming, exaggerated.** Six stations around southern
Hokkaido and northern Honshu show 1.2 to 1.4 K, in every month, with 2023 to
2025 the warmest years. AgERA5 shows 1.5 to 2.2 K at the same cells. The gap
between the two has also drifted steadily for thirty years, from about -0.5 K
in the 1990s to +0.5 K in the 2010s, so AgERA5 warms faster than the stations
there by roughly 1 K over the record. A trend map in this region would
overstate.

**The two high-mountain patches are a step in the data, not in the climate.**
The patch anomaly jumps in a single year: on the eastern Tibetan Plateau from
+0.4 K in 2019 to +1.9 K in 2020, and it stays there. The stations at Madoi
and Qumarleb, each within 10 km of patch cells at about 4,200 m, show +0.8 K
where AgERA5 shows +2.3 K, and AgERA5 minus station was within 0.4 K of zero
for thirty years before moving to +1.5 K. The excess is concentrated in the
cold half of the year (+3 to +4 K from November to April, about +1 K from May
to September), and the surrounding cells do not share it. That pattern is what
a change in snow or land-surface treatment would produce, but the cause was not
identified: nothing in the AgERA5 or ERA5 documentation was checked for a
change in 2020.

What this means for the monitor: a fixed threshold in these cells flags heat
that did not happen. The 30 smaller patches (the Zagros, eastern Sudan and
others) were not checked. A screen for single-year steps that neighbours do
not share is needed before any map of recent heat is published, and it has not
been built.

### 9a-2. A second step, in 2007, along the coast of northern Japan

A screen for such steps (`validation/step_screen/01_step_screen.py`) missed both
of its targets and was not accepted, but one of its "false alarms" turned out
to be a finding. It flagged 104 cells around the Tsugaru Strait with a break in
2008. Following that up with 19 stations
(`validation/step_screen/02_tsugaru_check.py`, `results/tsugaru_check.txt`):

- At 9 of the 19 stations the monthly difference AgERA5 minus station is better described by a single step than by a steady drift, and the step falls between June and October 2007 in every one of the nine. Its size is 0.65 to 1.70 K: Mutsu 1.70, Esashi 1.47, Tomakomai 1.02, Hakodate 0.89, Fukaura 0.84, Muroran 0.73, Suttsu 0.71, Otaru 0.71.
- All nine are on the coast. The inland or sheltered stations (Sapporo, Kutchan, Iwamizawa, Chitose, the second Aomori and Hachinohe records) show no step.
- The stations did not change. Every station reported 24 times a day throughout 2003 to 2012, and coastal minus inland station differences show no step of 0.5 K in 2007 to 2009 (the largest is 0.43 K at Fukaura).

So what looked like thirty years of drift in section 9a is mostly one step in
2007, in AgERA5, at coastal cells. A likely cause: ERA5 is reported to change
its sea surface temperature source from HadISST2 to OSTIA on 1 September 2007
(ECMWF forum thread and ERA Report 26, both seen only as search summaries; the
ERA5 documentation itself was not read). That would move the air temperature
of cells next to the sea and leave inland cells alone. It is an inference from
the date and the coastal pattern, not a demonstrated cause.

By the rule written before the run the formal verdict was "not shown", because
the rule expected the step only at flagged cells and it is much wider than
that: only one station sits on a flagged cell.

Why it matters more than the mountain step: the 1991 to 2020 baseline straddles
2007. At affected coastal cells the second half of the baseline is about 1 K
warmer than the first for a reason that is not climate, which inflates both the
trend and every count of recent heat.

Other coasts were then checked in AgERA5 alone
(`validation/step_screen/03_coastal_2007.py`, `results/coastal_2007.txt`): the
change across 2007 at each cell beyond what the interior of its region did.
2007 does stand out (18 percent of cells near water change by 0.5 K or more,
against 7 percent in a typical other year), and the method recovers all nine
Japanese station cells with sizes close to the station steps. But it is not a
worldwide coastal step. Outside northern Japan the affected cells are almost
all on Arctic coasts: the Kara Sea and the Ob estuary (about +1.6 K), the
Laptev, Beaufort and Chukchi coasts, the Gulf of Finland, and the Canadian
Arctic islands with the opposite sign. Sea ice is the common factor there, and
since Arctic sea ice really did fall sharply in 2007, a real change and a
change of data source cannot be separated without stations. Tropical and most
mid-latitude coasts show nothing. Northern Japan is the one place where the
step is both large and shown by stations to be wrong.

Limits: two stations is thin evidence for the Bhutan and Sikkim patch; ISD-Lite
is not quality controlled; station moves were not checked; a station at 4,300 m
in a valley and a 0.1 degree cell of mountain terrain are not the same place.

## 9b. Things learned about AgERA5 itself along the way

These were found before any station was opened, by reading the files and the
product documentation. They explain part of what the stations later showed.

- **The humidity extremes are not observations.** The file metadata says minimum relative humidity is derived from the 24 hour maximum temperature and the mean vapour pressure, and the documentation says the maximum is derived the same way from minimum temperature. So "afternoon humidity" in AgERA5 is the daily mean moisture placed against the afternoon temperature. This is the root of section 5a.
- **Minimum relative humidity is not the same as dewpoint with maximum temperature.** At 17 test cells the two differed by a mean of 0.1 to 5.7 relative humidity points, largest at Dhahran, because mean vapour pressure is not vapour pressure at mean dewpoint (`validation/first_look/hx_analyse.py`). The comparison in this document uses dewpoint directly.
- **Maximum relative humidity is saturated much of the time.** It is at or above 99.5 percent on 30 to 54 percent of days at Paris, Moscow, Portland, Singapore and Sydney cells, so a "night wet-bulb" would mostly repeat minimum temperature (same script).
- **A common shortcut formula would have made things worse.** The Stull (2011) wet-bulb formula, which needs no pressure, changed the count of days above a wet-bulb level by up to four times against a pressure-aware solve (Jacobabad at 28 C: 16.0 against 3.8 days a year), and read 1.25 K high on average at La Paz, at 3,800 m (same script). Its published validity range excludes relative humidity below 5 percent.
- **There is no surface pressure variable.** Pressure has to be estimated from elevation.
- **"Local day" is approximate.** The documentation describes days built from fixed time windows by longitude zone, so the day boundary can sit a few hours from true local midnight. A late-night minimum near a zone edge can land on the neighbouring date.
- **The correction is towards a model.** AgERA5 is ERA5 at about 31 km interpolated to 0.1 degree and adjusted by regression towards ECMWF's higher-resolution forecast model, trained on two years, not towards station observations. Agreement with stations was never built in.
- **Variables do not end on the same day.** In the 2026 files, temperature ends on 15 September, dewpoint, humidity, wind and radiation on 16 September, and precipitation on 1 September (measured by reading each file's time axis). A monitor has to compute the last common date, not assume one.
- **Only land is present, and Antarctica is.** 2,395,758 of 6,483,600 cells hold data on a sample day. An all-year heatwave index fired at Dome C at -32 C, which is why polar ice is excluded.
- **Reading is slow.** Seventeen small windows over six variables and the full record took about 33 minutes cold.

## 10. Where the station side is the weak one

The disagreement is not all AgERA5's fault, and a fair account says where
the reference is shaky.

- **ISD-Lite is not quality controlled**, which is why every comparison here uses the 99th percentile and never the maximum. The repeat with quality-controlled HadISD (section 10b) shows this caution was enough: quality control changed some record maxima and almost nothing else.
- **Reporting frequency varies.** Stations with eight observations a day miss the true peak, which makes the station side read low and the gap look smaller than it is.
- **A station is a point.** Many are airports; several are on coasts. Some of every gap is the difference between a point and 120 square kilometres.
- **The Indonesian data is mid-way through cleaning.** In the wxgrid project the rainfall record has been quality controlled; temperature and humidity have not. Known issues include minimum above maximum, swapped columns and day labels that can be off by one. The comparison used the best of three day offsets, but the very low Indonesian skill figures are probably pessimistic. The ISD stations in the same climate (Jakarta, Singapore) score better than the Indonesian median, which supports that reading.
- **The sample is thin in places.** There is no high-latitude station, one high-altitude station (Nairobi), and none in the Sahel beyond Niamey.

## 10b. The check on the check: repeating it with HadISD

The obvious objection to sections 3 to 7 is that ISD-Lite is raw. HadISD is the
Met Office Hadley Centre's quality-controlled version of the same NOAA archive:
observations that fail its tests are removed. The whole comparison was run
again with HadISD version 3.4.3.2025f (`05_download_hadisd.py`,
`06_compare_hadisd.py`, output `results/hadisd_summary.txt`).

26 of the 29 stations are in HadISD. Tejgaon in Dhaka, Jakarta Observatory and
Lagos Murtala Muhammed are not, which is itself a comment on those records.

| Measure, same 26 stations | HadISD | ISD-Lite |
|---|---|---|
| Daily maximum wet-bulb, median gap at the 99th percentile | -1.69 K | -1.75 K |
| Stations with that gap over 1 K | 18 of 26 | 18 of 26 |
| Days at or above 28 C wet-bulb, AgERA5 as a share of observed | 0.05 | 0.05 |
| Wet-bulb at the hour of Tmax, median gap at the 99th percentile | -0.66 K | -0.69 K |
| Maximum temperature, median gap at the 99th percentile | -1.76 K | -1.68 K |
| Dewpoint, median bias | -0.36 K | -0.36 K |
| Tmax anomaly correlation, median | 0.88 | 0.88 |
| Tmax hit rate, median | 0.72 | 0.71 |
| Wet-bulb hit rate, median | 0.56 | 0.57 |
| Rank correlation of skill with anomaly spread, Tmax | +0.93 | +0.94 |

**Nothing changes.** Every conclusion holds to within a tenth of a degree or
two hundredths of a correlation.

What quality control did change is the single highest values, and only at some
stations. The record wet-bulb at Manaus falls from 34.3 to 30.8 C, at Nairobi
from 26.0 to 22.7 C, at Niamey from 33.2 to 31.0 C, at Shahbaz air base from
37.7 to 36.5 C. Those were bad observations in the raw file. But on the Gulf
coast the extremes survive quality control untouched: 36.1 C at Dhahran,
35.3 C at Bahrain, 35.0 C at Doha. HadISD keeps them as valid observations. The
highest value AgERA5 produces at those three cells in 47 years is 31.0 to
31.3 C. Whether each individual reading is right is beyond this test; what the
test shows is that a quality-controlled archive holds humid-heat values
3.7 to 5.1 K above anything AgERA5 reaches there.

HadISD is provided under the Non-Commercial Government Licence, Crown
copyright, Met Office. It is used here for validation only and is not
redistributed. HadISD.3.4.3.2025f data were obtained from
http://www.metoffice.gov.uk/hadobs/hadisd on 2026-11-21.

## 11. What changed in the monitor because of this

| Before | After | Because |
|---|---|---|
| Two lenses: unusual for the place, and dangerous for a body | One lens: unusual for the place and date | the humid-heat level cannot be trusted (section 5) |
| Wet-bulb bands tied to physiological limits | No absolute wet-bulb anywhere | 1.6 K low at the 99th percentile; one day in twenty at 28 C |
| Every cell treated alike | A confidence class per cell, shown on the map | skill follows anomaly spread (section 7) |
| Hot spot statistics on 0.1 degree cells | Statistics on coarser bins, and only if a null test passes | neighbours are near-copies (section 8) |
| Area shares for every district | Shares only for units with enough cells | same reason |
| Trends shown as measured | Trends carry a homogeneity caveat until checked against stations | section 9 |

What survived intact: relative indicators in the mid-latitudes, the subtropics
and the monsoon regions, where anomaly correlations are 0.8 to 0.98.

## 12. What is still not known

1. Whether the confidence thresholds are right. They lean on Indonesian data that is not yet clean; they may be too strict.
2. How much of the world's land falls in each confidence class. The map has not been drawn. *Since answered: the classes are now computed for every land cell and hatched on the dashboard map; the low class covers 17 percent of land (`docs/detector-v1-frozen.md`).*
3. Whether the long-term oddities in section 9 are real. This needs station trend comparisons.
4. How large the constant-humidity assumption error is away from the Gulf. Only hourly data can show it.
5. How the comparison looks at the scale the dashboard uses, a province, where averaging should help AgERA5.
6. Whether the surviving Gulf extremes above 35 C are individually correct. HadISD accepts them; an independent check would need the original station records.

## 13. Reproducing this

```
bash tools/py.sh validation/wetbulb_gate/01_download_isd.py
bash tools/py.sh validation/wetbulb_gate/02_extract_agera5_points.py
bash tools/py.sh validation/wetbulb_gate/03_compare.py
bash tools/py.sh -W ignore validation/wetbulb_gate/04_anomaly_skill.py
```

| Result in this document | File |
|---|---|
| Sections 3, 4, 5 | `validation/wetbulb_gate/results/summary.txt`, `isd_comparison.csv`, `wxgrid_comparison.csv` |
| Sections 6, 7 | `validation/wetbulb_gate/results/anomaly_skill.txt`, `anomaly_skill.csv` |
| Section 10b | `validation/wetbulb_gate/results/hadisd_summary.txt`, `hadisd_comparison.csv`, `hadisd_skill.csv` (scripts `05_download_hadisd.py`, `06_compare_hadisd.py`) |
| Section 8 | `validation/first_look/hx_neff.txt` |

`wxgrid_comparison.csv` and `anomaly_skill.csv` hold one row per wxgrid station and are not
in the repository (gitignored); the scripts above rebuild them.
| Section 9 | `validation/first_look/hx_results.txt`, `validation/heat_spell_prototype/results/summary.txt` |

Data: NOAA Integrated Surface Database (ISD-Lite), public bucket
`noaa-isd-pds`; HadISD 3.4.3.2025f, Met Office Hadley Centre (Dunn et al. 2012,
2014, 2016; Dunn 2019; Smith et al. 2011, as the provider asks); AgERA5, Copernicus Climate Change Service, doi
10.24381/cds.6c68c9bb; ETOPO1, NOAA NGDC; Indonesian station records through
the wxgrid project. The AgERA5 construction described in section 8 is from the
ECMWF product documentation. Station values from the
wxgrid dataset are not reproduced here beyond summary statistics.
