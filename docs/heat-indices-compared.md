# How the Heat Explorer heat spell compares with published heat indices

Heat Explorer uses its own definition of a heat spell (detector version 1.0,
[detector-v1-frozen.md](detector-v1-frozen.md)). This page sets it beside the
indices people are most likely to know, says where it differs, and says where
it is the weaker choice.

The ingredients are not new. A three-day average of daily mean
temperature and a percentile threshold are both borrowed ideas. What differs is
the purpose. The standard indices give one number per year for climate trend
studies. Heat Explorer gives a state for every day and place, with a severity
class, for monitoring.

## How each claim here was checked

| Index | Source | Checked |
|---|---|---|
| WSDI, TX90p, TN90p | [ETCCDI list of 27 core indices](http://etccdi.pacificclimate.org/list_27_indices.shtml) | read on 2026-11-23 |
| Excess Heat Factor (EHF) | Nairn and Fawcett (2015), [doi:10.3390/ijerph120100227](https://doi.org/10.3390/ijerph120100227) | read on 2026-11-23 |
| HWDI | Frich et al. (2002), Climate Research 19, 193-212, Table 1 | read on 2026-11-23 |
| Heat Explorer | [detector-v1-frozen.md](detector-v1-frozen.md) | this repository |

Two more families are named at the end and not compared, because their sources
could not be opened.

## Side by side

| | WSDI (ETCCDI) | HWDI | EHF | Heat Explorer 1.0 |
|---|---|---|---|---|
| Temperature used | daily maximum | daily maximum | three-day average of daily mean | three-day average of daily mean |
| Daily mean made from | not used | not used | the maximum and the minimum that follows it | the maximum and the minimum that follows it |
| Threshold | 90th percentile for the calendar day, 5-day window | the calendar-day normal plus 5 °C | 95th percentile of all days of the year | 90th percentile for the calendar day (15-day window) **and** above the all-year median; **or** above the all-year 95th percentile |
| Baseline | 1961 to 1990 | 1961 to 1990 | 1971 to 2000 | 1991 to 2020 |
| Shortest run | 6 days | more than 5 days | one three-day period | 3 flagged days in a row |
| Severity | none | none | severe at the 85th percentile of positive EHF (taken over 1958 to 2011), extreme at 3 times that | severe above the calendar-day 95th percentile, extreme above the 99th |
| Recent weather | not used | not used | yes: compared with the previous 30 days | not used |
| What comes out | days per year | the longest such run in the year, in days | a value in °C² for each day | a class for each day and grid cell |

Notes on the table:

- HWDI is not one of the ETCCDI indices. The ETCCDI list has one heat-duration
  index, WSDI. HWDI is one of the ten indicators of Frich et al. (2002), whose
  Table 1 gives it as the "maximum period > 5 consecutive days with Tmax > 5 °C
  above the 1961-1990 daily Tmax normal".
- The ETCCDI page gives WSDI as the "annual count of days with at least 6
  consecutive days when TX > 90th percentile".
- EHF is the product of two parts: how far the three-day mean is above the
  all-year 95th percentile, and how far it is above the mean of the previous 30
  days (never counted as less than 1). A heatwave needs the first part to be
  positive.

## Where Heat Explorer differs

1. **It is a daily state, not a yearly count.** WSDI answers "how many warm
   spell days did this year have". Heat Explorer answers "is this place in a
   heat spell on this date, which day of the spell is it, and how severe".
2. **It keeps short events.** A run of 3 days is enough, where WSDI needs 6.
3. **It counts the night.** The daily mean includes the minimum that follows the
   maximum, so a hot day followed by a warm night scores higher than a hot day
   alone. WSDI looks at the maximum only. EHF makes the same choice as Heat
   Explorer.
4. **It asks two questions of a day.** "Is it hot for this date" and "is it hot
   for this place at all". A calendar-day test alone calls a mild winter
   anomaly a warm spell. An all-year test alone (EHF) cannot see unusual heat
   outside the hottest months. Heat Explorer flags a day that passes the
   calendar-day test and is above the place's median for the whole year, or that
   passes the all-year test.
5. **Severity is even through the year.** Severe and extreme are set against the
   calendar day, so they mean the same in April as in July. EHF severity is set
   against the distribution of EHF itself.
6. **It is summarised by place.** Shares of land area for each country, province
   and district, and events with a start, a length, a size in degree-days and a
   rank since 1979.
7. **It says where not to trust it.** Low-confidence climates and cells with a
   known break in the source data are marked on the map
   ([agera5-vs-stations.md](agera5-vs-stations.md)).
8. **It was tested on documented events.** One registered test on events not
   used to build it: 9 of 10 admin units and 8 of 10 locations came out severe
   on the documented day (`validation/heldout_suite_3/`).

## Where Heat Explorer is the weaker choice

- **It is not a standard.** Its numbers cannot be compared with published WSDI
  or EHF values, and it has not been peer reviewed. For a trend study that must
  be comparable with the literature, use the ETCCDI indices.
- **It has no link to health.** EHF was designed with health outcomes in mind
  and includes acclimatisation to recent weather. Heat Explorer does neither.
- **The test is small.** Nine of ten is compatible with a true success rate from
  about 55 to 100 percent. There is no false-alarm test beyond base rates.
- **The lowest class is uneven through the year.** The all-year test admits
  ordinary midsummer days, so spell days are 6 to 8 percent of days in some warm
  months and 20 to 44 percent in the hottest month. The severe and extreme
  classes do not have this problem.
- **The baseline is fixed on 1991 to 2020** with no adjustment for warming since,
  so recent years are flagged far more often.
- **It lags.** The three-day average and the 3-day rule mean a new spell first
  shows on its third day, and the newest day shown is two days behind the data.
- **It is temperature only.** It is not a measure of heat stress on the body.
  The humid layer on the dashboard is experimental and is not a wet-bulb or
  heat-index reading.

The last five points are from the "Known limits" section of
[detector-v1-frozen.md](detector-v1-frozen.md).

## Not compared here

- **Percentile heatwave definitions and their yearly "aspects"** (number,
  frequency, duration, magnitude, amplitude), Perkins and Alexander (2013),
  [doi:10.1175/JCLI-D-12-00383.1](https://doi.org/10.1175/JCLI-D-12-00383.1).
  Probably the closest published relative of the calendar-day part of the Heat
  Explorer flag. Not compared because the paper could not be opened on
  2026-11-23.
- **Heat Wave Magnitude Index daily**, Russo et al. (2015),
  [doi:10.1088/1748-9326/10/12/124003](https://doi.org/10.1088/1748-9326/10/12/124003).
  Not compared, for the same reason.
- **Heat stress indices** that combine temperature with humidity, wind or
  sunshine (heat index, WBGT, UTCI). They measure a different thing: the load on
  a person, not how unusual the temperature is for the place.
