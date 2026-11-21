# Held-out event suite: protocol

Written on 2026-11-21, **before any detector output for these units or dates
was computed or looked at**. Its purpose is the one the second method critique
asked for (item B): a test whose events, windows, units and pass rules are
fixed first. The earlier suite cannot serve, because its criteria were
rewritten after results were seen.

This file and `events.csv` are the registration. After the run they may be
annotated, never edited. Any departure is listed under "Deviations" in the
results file.

## What is tested

Detector revision 3 (`validation/detector_v3/detector.py`), fixed 1991 to
2020 thresholds, daily intensity class, three-day minimum. An admin-level
(many-cell) version must be written for this run. Before the run it must be
shown to give the same per-day output as the single-cell reference at three or
more cells; if it does not, the run does not start.

## Events

Nine events and thirteen units, in `events.csv`. None was in the earlier
suite and none of these units has been run through any detector.

| Event | Window | Primary unit | What the source states |
|---|---|---|---|
| Western Europe, July 2019 | 25 to 31 Jul 2019 | Noord-Brabant (also Vlaams Gewest) | "3-4 days" "in the last week of July 2019"; above 40 C in Belgium and the Netherlands for the first time |
| United Kingdom, July 2022 | 16 to 21 Jul 2022 | England | 40.3 C at Coningsby on 19 July; 18 and 19 July the key days; heat from Kent to North Yorkshire |
| Argentina, January 2022 | 9 to 13 Jan 2022 | Buenos Aires province (also Cordoba) | Buenos Aires 41.1 C on 11 January; Cordoba above 41 C |
| Sahel, April 2024 | 31 Mar to 4 Apr 2024 | Koulikoro (also Kayes) | 5-day event over southern Mali and Burkina Faso, 31 March to 4 April; Kayes 48.5 C on 3 April |
| Philippines, April 2024 | 15 to 29 Apr 2024 | Central Luzon | 15-day mean of daily maximum, 15 to 29 April; about a 1 in 10 year event |
| West Asia, April 2024 | 24 to 26 Apr 2024 | Amman | 3-day mean of daily maximum, 24 to 26 April; Syria, Lebanon, Israel, Palestine, Jordan; about 1 in 10 years |
| Chicago, July 1995 | 11 to 16 Jul 1995 | Cook County, adm2 (also Illinois) | peak between 13 and 14 July; 106 F at Midway on 13 July |
| Japan, July 2018 | 15 Jul to 9 Aug 2018 | Saitama | heatwave "from mid-July onward"; 41.1 C at Kumagaya, Saitama, on 23 July; station counts "as of 9th of August" |
| Saudi Arabia, June 2024 | 16 to 18 Jun 2024 | Makkah | "From June 16th to June 18th"; 51.8 C at the Grand Mosque |

Sources, each read in full unless noted, on 2026-11-21:

- World Weather Attribution, 2 Aug 2019: https://worldweatherattribution.org/human-contribution-to-the-record-breaking-july-2019-heat-wave-in-western-europe/
- Met Office, 22 Jul 2022: https://www.metoffice.gov.uk/about-us/news-and-media/media-centre/weather-and-climate-news/2022/july-heat-review
- NASA Earth Observatory, 16 Jan 2022, citing Argentina's SMN: https://science.nasa.gov/earth/earth-observatory/southern-hemisphere-scorchers-149331 (the SMN bulletin itself was not found)
- World Weather Attribution, 18 Apr 2024: https://www.worldweatherattribution.org/extreme-sahel-heatwave-that-hit-highly-vulnerable-population-at-the-end-of-ramadan-would-not-have-occurred-without-climate-change
- World Weather Attribution, 14 May 2024: https://www.worldweatherattribution.org/climate-change-made-the-deadly-heatwaves-that-hit-millions-of-highly-vulnerable-people-across-asia-more-frequent-and-extreme/
- NWS Chicago, 1995 heat wave page: https://www.weather.gov/lot/1995_heatwave
- JMA Tokyo Climate Center, 22 Aug 2018 (pages 1 to 3 and 10 to 12 of 24 read): https://www.data.jma.go.jp/tcc/data/news/press_20180822.pdf
- ClimaMeter, 20 Jun 2024: https://www.climameter.org/20240616-18-saudi-arabia-heatwave

Considered and left out because the page read gave no calendar dates: southern
Europe and the western United States, July 2023 (World Weather Attribution, 25
Jul 2023); China, summer 2022 (no primary source read).

## How windows were set

One rule, applied without looking at data:

1. Dates stated by the source are used as stated.
2. Where the source gives only peak days, the window is those days plus and minus 2 days.
3. Where the source gives a phrase: "last week of July" is 25 to 31 July; "mid-July onward" is from 15 July to the date the source's own figures run to.

## How units were set

One primary unit per event, chosen from places the source names, at adm1
unless the event is a city event (Chicago: adm2). A second unit is listed
where the source names a second place; it is reported and does not count.
Unit facts recorded before the run (cells, confidence class from the saved
confidence grid) are in `events.csv`. No unit holds a data suspect cell.

- Koulikoro surrounds Bamako, which the source names. Kayes holds the record the source cites.
- Central Luzon is my choice: the source names no Philippine region. It is 97 percent low-confidence cells, on purpose, since no low-confidence unit has ever been tested.
- Amman is my choice among the five countries the source lists.
- Saitama (39 cells) and Cook County (45) are small. They are above the 30-cell floor.

## Measures

For each unit and day, with cos-latitude weights over the unit's land cells:

- `share_spell`: share of area in a heat spell (daily class 1 or more)
- `share_sev`: share of area severe or extreme by the daily intensity class
- `M`: area mean of daily excess (zero where not in a spell)

## Pass rules

For each unit:

- **H1, detected:** `share_spell` reaches 0.50 on at least one window day.
- **H2, severe on the day:** `share_sev` reaches 0.50 on at least one window day.
- **H3, stands out for the time of year:** the window total of `M` ranks in the top N against the same calendar window in every other year 1979 to 2025. N is 3, except where the source itself says the event is about a 1 in 10 year event (Philippines, West Asia), where N is 5.
- **Base rate b:** the share of other years in which H2 is met in the same calendar window. Reported for every unit. A result is called **sharp** when b is 0.15 or less.

An event **passes** when its primary unit meets H2 and H3.

The suite is **accepted** when at least 7 of the 9 events pass **and** the
median base rate b across the nine primary units is 0.15 or less. If the
second condition fails, the criteria are too easy to mean anything and the
result is reported as "not informative", whatever the pass count.

## What will be reported regardless of outcome

- H1, H2, H3, the rank, b and "sharp" for all thirteen units.
- The first window day on which `share_sev` reached 0.50, against the source's peak day.
- The year that ranks first in each window where the event does not.
- Results for the low and reduced confidence units separately (Central Luzon, Koulikoro, Kayes). They count towards the total; a failure there is information about the confidence classes, not a reason to drop them.

## Amendment 1, made on 2026-11-21 BEFORE the run, after a review of this protocol

The review found one ambiguity and no other change was made.

**"On the day" must mean what a live monitor shows.** A run of flagged days
becomes a heat spell only on its third day. In the archive the first two days
are then labelled as spell days too, but a live map could not have shown them
on the day. H1 and H2 are therefore evaluated on the **live** labelling: a day
counts as in a spell only if it and the two days before it are all flagged.
Its class is still that day's own intensity class. The archive labelling
(first two days included) is reported beside it and does not count. H3 uses
the archive labelling, because a ranking of window totals is made afterwards.

Points checked in the review and left as they are:

- Windows: the rule gives 25 to 31 July for "last week of July 2019". If the true peak was on 24 July it falls outside. The rule stands; no data was consulted.
- The 3-day windows (West Asia, Saudi Arabia) make H3 a ranking of three days against the same three days in other years. Noisy, accepted.
- The many-cell run calls the single-cell reference once per cell, in parallel, so equality with the reference is by construction. The check at three cells is still run, through the same parallel path.
- The comparison years for H3 and the base rate are all other years from 1979 to 2025.

## What this suite cannot show

- It has no false-alarm test beyond the base rate. Whether the top-ranked years in each window were real events is not checked here.
- One unit per event. Nine events.
- Windows from phrases (Western Europe, Japan) are looser than windows from stated dates.
- The source for Argentina is a secondary page citing the national service.
- Class cuts are still taken from the full baseline, not leave-one-year-out (critique item A5). That biases recent years upward slightly and is not corrected in this run.

## What was known when this was written

Annual mean temperature and the confidence class of every cell, from earlier
runs. Nothing from any detector for these units or these dates. The
single-cell results at Paris, Moscow, Portland, Sydney, Delhi, Jacobabad,
Hyderabad and Verkhoyansk are known; none of those cells is in a unit listed
here.
