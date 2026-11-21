# Second held-out event suite: protocol

Written on 2026-11-21, **before any detector output for these units or dates
was computed or looked at**. The user asked for a second held-out set after
the first one (`validation/heldout_suite/`) came out at 6 of 9 against a bar
of 7 and nothing was frozen.

This file and `events.csv` are the registration. After the run they may be
annotated, never edited. Any departure is listed under "Deviations" in the
results file.

## What is tested, and what is the same as last time

The same detector, unchanged: `validation/detector_v3/detector.py`, fixed 1991
to 2020 thresholds, daily intensity class, three-day minimum, called once per
cell. The same measures, the same pass rules H1 to H3 with the live labelling,
the same base-rate condition. The run script is a copy of the first one with a
different output folder and pass bar.

Nothing in the detector was changed in response to the first suite. This is a
replication on new events, not a test of an improved method.

## What is different, and why

Two things were tightened in how events enter the set. Both are about the
test, neither is about the detector, and both were fixed before any data for
these units was read.

1. **Stated dates only.** Every window is a date range the source itself states. No window is built from a phrase or from a peak day. In the first suite the two phrase-based windows were the two ranking failures, and the protocol had flagged them as looser. Events whose source gives no dated window were left out: France June 2019, Mexico June 2024, the Mediterranean July 2024.
2. **Units by a mechanical rule**, so that I choose nothing:
   1. the adm1 unit containing the first place the source names, below country level, that has a temperature attached;
   2. if there is none, the adm1 unit containing the first place below country level that the source lists as affected;
   3. if there is none, the adm1 unit containing the centre of the source's stated analysis box.

## Events

Ten events, ten units, one per event. None was in either earlier suite and
none of these units has been run through any detector.

| Event | Window (as stated) | Unit | Unit rule | What the source states |
|---|---|---|---|---|
| Argentina and Paraguay, Dec 2022 | 4 to 10 Dec 2022 | Salta | 1: Rivadavia station, 46 C on 7 December, near the Bolivia and Paraguay border | 7-day mean of daily maximum; about 1 in 20 years |
| South America, Sep 2023 | 17 to 26 Sep 2023 | Mato Grosso do Sul | 3: centre of the box 11 to 28 S, 41 to 63 W | 10-day mean of daily maximum; about 1 in 30 years |
| Madagascar, Oct 2023 | 10 to 16 Oct 2023 | Analamanga | 2: Antananarivo | 7-day mean of daily maximum; about 1 in 25 years |
| Western Mediterranean, Apr 2023 | 26 to 28 Apr 2023 | Tlemcen | 1: Maghnia, above 40 C on 28 April | 3-day mean of daily maximum; about 1 in 400 years |
| Southern West Africa, Feb 2024 | 11 to 15 Feb 2024 | Ashanti | 3: centre of the box 4 to 9 N, 13 W to 9 E | 5-day mean of the heat index; about 1 in 10 years |
| Thailand and Laos, Apr 2023 | 18 to 21 Apr 2023 | Tak | 1: Tak, 45.4 C on 15 April | 4-day mean of daily maximum heat index |
| Eastern United States, Jun 2024 | 18 to 23 Jun 2024 | Maryland | 1: Baltimore, near 40 C | text says 18 to 23 June, title 19 to 23; the wider range is used |
| South-east Europe, Jul 2024 | 17 to 19 Jul 2024 | Hajdu-Bihar | 2: Debrecen | peak intensity 17 to 19 July |
| Western Europe, Jun 2025 | 20 to 22 Jun 2025 | Occitanie | 1: Lot, near 40 C | 20 to 22 June |
| Eastern United States, Jun 2025 | 23 to 25 Jun 2025 | New Jersey | 1: Newark, 39.4 C | 23 to 25 June |

Sources, each read in full on 2026-11-21:

- World Weather Attribution, 21 Dec 2022: https://www.worldweatherattribution.org/climate-change-made-record-breaking-early-season-heat-in-argentina-and-paraguay-about-60-times-more-likely/
- World Weather Attribution, 10 Oct 2023: https://www.worldweatherattribution.org/strong-influence-of-climate-change-in-uncharacteristic-early-spring-heat-in-south-america/
- World Weather Attribution, 23 Nov 2023: https://www.worldweatherattribution.org/extreme-poverty-rendering-madagascar-highly-vulnerable-to-underreported-extreme-heat-that-would-not-have-occurred-without-human-induced-climate-change/
- World Weather Attribution, 5 May 2023: https://www.worldweatherattribution.org/extreme-april-heat-in-spain-portugal-morocco-algeria-almost-impossible-without-climate-change/
- World Weather Attribution, 21 Mar 2024: https://www.worldweatherattribution.org/dangerous-humid-heat-in-southern-west-africa-about-4c-hotter-due-to-climate-change/
- World Weather Attribution, 17 May 2023: https://www.worldweatherattribution.org/extreme-humid-heat-in-south-asia-in-april-2023-largely-driven-by-climate-change-detrimental-to-vulnerable-and-disadvantaged-communities/
- ClimaMeter, 25 Jun 2024: https://www.climameter.org/20240619-23-eastern-us-heatwave
- ClimaMeter, 25 Jul 2024: https://www.climameter.org/20240717-19-july-european-heatwave
- ClimaMeter, undated: https://www.climameter.org/20250620-22-western-european-heatwave
- ClimaMeter, undated: https://www.climameter.org/20250623-25-eastern-usa-heatwave

Place coordinates used to find the containing unit are from general knowledge
(city locations), not from the sources: Antananarivo 18.91 S 47.52 E, Maghnia
34.85 N 1.73 W, Tak 16.88 N 99.13 E, Baltimore 39.29 N 76.61 W, Debrecen 47.53
N 21.63 E, Cahors (Lot) 44.45 N 1.44 E, Newark 40.73 N 74.17 W. Rivadavia was
placed in Salta from the source's description ("near the Bolivia and Paraguay
border"); several Argentine districts share the name.

## Measures and pass rules

As in `validation/heldout_suite/PROTOCOL.md`, including its Amendment 1:

- **H1, detected:** live `share_spell` reaches 0.50 on at least one window day.
- **H2, severe on the day:** live `share_sev` reaches 0.50 on at least one window day.
- **H3, stands out for the time of year:** the window total of `M` ranks in the top N against the same calendar window in every other year 1979 to 2025. N is 3, except 5 where the source calls the event about 1 in 10 years (southern West Africa).
- **Base rate b:** the share of other years meeting H2 in the same calendar window. **Sharp** when 0.15 or less.

An event **passes** when its unit meets H2 and H3.

The suite is **accepted** when at least 8 of the 10 events pass (the same
proportion as 7 of 9) **and** the median base rate is 0.15 or less. If the
median base rate is higher, the result is "not informative".

## Cases expected to be hard, said in advance

- **Ashanti, February 2024.** The source defines the event on a heat index, in a humid climate, and the unit is low confidence. The detector tested here uses temperature only. A failure would say the temperature layer misses humid events there, which is the reason a humid layer exists.
- **Tak, April 2023.** The rule picked Tak because it is the first place named with a temperature, but that temperature was recorded on 15 April, three days before the stated window. The source also defines the event on a heat index.
- **Mato Grosso do Sul, September 2023.** An earlier map of this project (`validation/step_screen/03_coastal_2007.py`) flagged an unexplained cooling of about 0.7 K across 2007 in part of this state. If that is a break in the data, the baseline here is affected. It was known before the run and the unit was not changed, because the rule chose it.
- **Analamanga and Tak** are reduced confidence; **Ashanti** is low.

## What will be reported regardless of outcome

H1, H2, H3, the rank, the base rate and "sharp" for all ten units; the first
live severe day; the year that ranks first where the event does not; and the
combined count over both held-out suites (19 events), with the caution that
the two sets were not built by the same rules.

## What this suite cannot show

- No false-alarm test beyond the base rate.
- One unit per event; ten events.
- Several windows are 3 or 4 days, which makes the ranking test noisy.
- The mechanical unit rule can pick a unit that is not where the event was worst. That is the price of not choosing.
- Class cuts are still taken from the full baseline (critique item A5).

## What was known when this was written

Annual mean temperature and the confidence class of every cell; the 2007
change map; the results of the first held-out suite for its own units.
Nothing from any detector for these ten units or these dates.
