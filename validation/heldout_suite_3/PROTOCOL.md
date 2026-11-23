# Third held-out event suite: protocol

Written on 2026-11-21 (evening), **before any detector output for these units,
places or dates was computed or looked at**. A third set was wanted
after two candidates were adopted the same evening: the calendar-day class and
the location readout. Neither has been tested on events it was not built from.

This file and `events.csv` are the registration. After the run they may be
annotated, never edited. Any departure is listed under "Deviations" in the
results file.

## What is tested

Two things, judged separately:

- **A. The calendar-day class at admin level.** `validation/detector_v3/detector.py`, field `cls_day`: a spell day is severe above its calendar-day 95th percentile, extreme above the 99th. Fixed 1991 to 2020 thresholds, three-day minimum, live labelling.
- **B. The location readout.** For a named place, the 3 by 3 block of cells around it, same class and labelling.

## The ranking bar, settled here before the run

The first two suites required the event's window total to rank in the top 3 of
47 years. That rule is dropped as a pass condition, for reasons that do not
depend on any result:

1. The product makes no claim that an event is among the three largest on record. It reports a rank as a number, whatever it is.
2. Most sources do not say how rare their event is. Eight of the ten sources used here give no return period. Requiring "top 3 of 47" asks for a rarity nobody documented.
3. Where sources did give one (1 in 10 to 1 in 30 years), a true event of that rarity ranks outside the top 3 of 47 years a fair share of the time by chance alone.

The rank is still computed and reported for every unit.

**What this change would have done to the earlier suites, stated plainly:**
judged on "severe on the day" alone, the first suite would read 8 of 9 and the
second 9 of 10, both above their bars. Those suites stay recorded as NOT
ACCEPTED under the rules they were registered with. This suite cannot be
compared with them as if the rules were the same, and it uses a different
class.

## How events entered the set

- **Stated dates only.** Every window is the date range in the source's title or heading.
- **Warm part of the year only.** Events the source dates to the cool season at their location were left out, because the product says it does not show winter warmth: Morocco February 2024, Central Asia November 2023 and March 2025, Europe October 2023. One month-long entry was left out as not an event (western United States, 2 to 31 July 2023).
- **Units by the mechanical rule of the second suite**, with one addition made before any data was read: a unit already run in an earlier suite is skipped and the next place taken.
  1. the adm1 unit containing the first place named, below country level, with a temperature attached;
  2. else the adm1 unit containing the first place below country level listed as affected;
  3. else the adm1 unit containing the centre of the stated analysis box.
- **Readout place:** the first named city or locality with a temperature attached; else the first city listed as affected. A place that is one of the 17 tuning cells (Delhi, Paris, Portland and others) is skipped and the next taken.

## Events

| Event | Window | Unit, and why | Readout place, and why |
|---|---|---|---|
| India and Pakistan, Apr 2025 | 14 to 15 Apr 2025 | Balochistan: "up to 49 C" | Jaipur: New Delhi is a tuning cell; Jaipur is the next city named |
| Western United States, Jul 2024 | 5 to 7 Jul 2024 | California: Portland (Oregon) was run before; next with a temperature is Death Valley, 129 F on 7 July | Death Valley: Portland is a tuning cell |
| Eastern Mediterranean, Jun 2024 | 11 to 14 Jun 2024 | Attica: no place below country level has a temperature; Athens is the first city listed | Athens |
| India, May 2024 | 26 to 29 May 2024 | Punjab (India): New Delhi was run before; Jalandhar is the next place listed | Jalandhar |
| Brazil, Mar 2024 | 15 to 18 Mar 2024 | Rio de Janeiro state: Rio de Janeiro, 42 C | Rio de Janeiro |
| Brazil, Nov 2023 | 13 to 19 Nov 2023 | Minas Gerais: Aracuai, 44.8 C | Aracuai |
| Western Europe, Sep 2023 | 3 to 10 Sep 2023 | Auvergne-Rhone-Alpes: Heathrow (England) and Paris (Ile-de-France) were run before; Lyon is the next city listed | Lyon |
| France, Aug 2023 | 21 to 23 Aug 2023 | Auvergne-Rhone-Alpes: Toulouse, Auch and Narbonne are in Occitanie, run before; next with a temperature is Aiguille du Midi | Toulouse, 42.4 C |
| Southern Europe, Jul 2023 | 15 to 25 Jul 2023 | Catalunya: "in excess of 45 C" | Rome, 40.8 C |
| South Sudan, Feb 2025 | 22 to 28 Feb 2025 | Central Equatoria: Juba is the only place named | Juba |

Sources, each read in full on 2026-11-21: nine ClimaMeter pages under
https://www.climameter.org/ (`20250414-15-india-pakistan-heatwave`,
`20240705-07-western-us-heatwave`,
`20240611-14-june-eastern-mediterranean-heatwave`, `20240526-29-india-heatwave`,
`20240315-18-brazil-heatwave`, `20231113-19-brazil-heatwave`,
`20230903-10-september-european-heatwave`,
`20230820-23-late-summer-french-heatwave`,
`20230715-25-cerberus-heatwave-in-southern-europe`) and World Weather
Attribution, 7 Mar 2025:
https://www.worldweatherattribution.org/women-and-girls-continue-to-bear-disproportionate-impacts-of-heatwaves-in-south-sudan-that-have-become-a-constant-threat/

Notes on windows: the France page is titled 20 to 23 August but its heading and
text give 21 to 23; 21 to 23 is used. The eastern Mediterranean page gives a
longer period (3 to 27 June) with "peak intensity" on 11 to 14 June, which is
its title and is used. Place coordinates are from general knowledge, listed in
`events.csv`.

## Measures and pass rules

- `share_sev`: share of the unit's area that is severe or extreme (calendar-day class, live labelling).
- **A, admin:** `share_sev` reaches 0.50 on at least one window day.
- **B, readout:** more than half of the land cells in the 3 by 3 block are severe or extreme (same class and labelling) on at least one window day.
- **Base rate:** for A and for B, the share of other years 1979 to 2025 meeting the same condition on the same dates. **Sharp** when 0.15 or less.

**A is accepted** when at least 8 of 10 units meet it and the median base rate
is 0.15 or less. **B is accepted** on the same terms for the readout. If a
median base rate is above 0.15, that result is "not informative".

A warning about what a pass can mean: with ten events, 8 of 10 is compatible
with a true success rate anywhere from about 45 to 97 percent (95 percent
interval). The suite can show a method is not broken. It cannot show it is
reliable.

## Cases expected to be hard, said in advance

- **Auvergne-Rhone-Alpes, August 2023.** The rule reached it through a mountain summit. The event the source describes was centred on the south-west; the readout at Toulouse is where it should show.
- **Catalunya with a readout at Rome.** The unit and the readout are in different countries because the rule treats them separately.
- **Balochistan and California** are very large units (3,179 and 4,172 cells). Half the area severe in a 2 or 3 day window is a demanding test; the readout is the fairer one there.
- **Attica** has 35 cells.
- **Central Equatoria** is low confidence.
- **Rio de Janeiro, March 2024:** the source's headline number is a heat index of 62 C, a humid event; this test uses temperature only.

## What will be reported regardless of outcome

For every event: A, B, both base rates, the first live severe day at unit and
at readout, and the rank of the window total with the year ranked first. The
low-confidence unit separately.

## What this suite cannot show

- Ten events; see the interval above.
- No false-alarm test beyond the base rates.
- Nine of ten sources are one group's rapid analyses, which pick events by impact and media attention.
- Class cuts and thresholds are still taken from the full baseline (critique item A5).

## What was known when this was written

Annual means and confidence classes of all cells; results of both earlier
held-out suites for their own units; the diagnosis runs for Maryland, Makkah
province and Sindh. Nothing from any detector for the ten units, the ten
readout places or the dates listed here.

---

Note added 2026-11-23, after the run: the second sentence of the opening
paragraph was reworded for style. Nothing else in this file was changed; the
registered text is in the git history.
