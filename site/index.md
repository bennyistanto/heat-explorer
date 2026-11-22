---
title: Heat Explorer
---

<link rel="stylesheet" href="npm:maplibre-gl@4.7.1/dist/maplibre-gl.css">
<style>
:root {--surface: #fbfaf7; --panel: #ffffff; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #6b6963; --rule: #e1e0d9; --land: #e7e6e1; --c1: #f0be8c; --c2: #d9783c; --c3: #74290c;}
#observablehq-main {max-width: none;}
#observablehq-center {margin: 0.5rem 1rem;}
.screen {height: calc(100vh - 1.5rem); min-height: 600px; display: grid; grid-template-rows: auto 1fr auto; border: 1px solid var(--rule); border-radius: 10px; overflow: hidden; background: var(--surface); font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--ink);}
.screen header {display: flex; align-items: center; gap: 16px; padding: 10px 16px; border-bottom: 1px solid var(--rule); flex-wrap: wrap;}
.screen header h1 {font-size: 26px; margin: 0; font-weight: 700; letter-spacing: -0.01em; max-width: none; display: flex; align-items: center; gap: 8px;}
.screen header h1 .logo {width: 28px; height: 28px; flex: none;}
.screen header .date {color: var(--ink-2); margin-left: auto; text-align: right;}
.screen header .date b {color: var(--ink); font-weight: 600;}
.controls {display: flex; gap: 12px; align-items: center; flex-wrap: wrap;}
.controls label {color: var(--ink-2); font-size: 12px; display: flex; gap: 6px; align-items: center;}
.controls select, .seg button {font: inherit; font-size: 13px; padding: 4px 8px; border: 1px solid var(--rule); background: var(--panel); color: var(--ink); border-radius: 6px;}
.seg {display: inline-flex;}
.seg button {border-radius: 0; margin-left: -1px; cursor: pointer;}
.seg button:first-child {border-radius: 6px 0 0 6px; margin-left: 0;}
.seg button:last-child {border-radius: 0 6px 6px 0;}
.seg button[aria-pressed="true"] {background: var(--ink); color: #fff; border-color: var(--ink);}
.screen main {display: grid; grid-template-columns: minmax(0, 1fr) 360px; min-height: 0;}
.mapwrap {position: relative; min-height: 0;}
#map {position: absolute; inset: 0; background: var(--surface);}
.legend, .slider {position: absolute; background: rgba(255,255,255,0.94); border: 1px solid var(--rule); border-radius: 8px; padding: 10px 12px; font-size: 12px; z-index: 2;}
.legend {left: 12px; bottom: 12px; max-width: 250px;}
.legend h2 {font-size: 12px; margin: 0 0 6px; font-weight: 650;}
.legend .row {display: flex; align-items: center; gap: 8px; margin: 3px 0; color: var(--ink-2);}
.sw {width: 18px; height: 12px; border-radius: 2px; flex: none; border: 1px solid rgba(0,0,0,0.08);}
.hatch {background: repeating-linear-gradient(135deg, var(--land) 0 3px, #52514e 3px 4px);}
.dots {background: radial-gradient(#0b0b0b 1px, transparent 1.2px) 0 0/4px 4px, var(--land);}
.legend .base {color: var(--ink-3); margin-top: 6px; border-top: 1px solid var(--rule); padding-top: 6px;}
.slider {right: 12px; bottom: 12px; width: 300px;}
.slider .lab {display: flex; justify-content: space-between; color: var(--ink-2);}
.slider input {width: 100%; margin: 4px 0 0;}
.slider select {width: 100%; font: inherit; font-size: 12.5px; padding: 3px 6px; margin-bottom: 6px; border: 1px solid var(--rule); border-radius: 6px; background: #fff;}
.screen aside {border-left: 1px solid var(--rule); background: var(--panel); padding: 16px 18px; overflow: auto; display: flex; flex-direction: column; gap: 14px;}
.lvl {color: var(--ink-3); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em;}
.place h2 {margin: 2px 0 0; font-size: 22px; font-weight: 650; max-width: none;}
.place .parent {color: var(--ink-2);}
.status {display: flex; align-items: center; gap: 8px; font-weight: 600;}
.chip {width: 12px; height: 12px; border-radius: 3px; background: var(--land); flex: none; border: 1px solid rgba(0,0,0,0.1);}
.nums {display: grid; grid-template-columns: 1fr 1fr; gap: 12px 16px;}
.num .v {font-size: 32px; font-weight: 650; line-height: 1.05; font-variant-numeric: tabular-nums;}
.num .v small {font-size: 15px; font-weight: 500; color: var(--ink-2); margin-left: 2px;}
.num .k {color: var(--ink-2); font-size: 12.5px; margin-top: 2px;}
.spark h3 {font-size: 12.5px; margin: 0 0 4px; font-weight: 600; color: var(--ink-2);}
.spark svg {display: block; width: 100%; height: 86px; overflow: visible;}
.sparkbox {position: relative;}
.tip {position: absolute; pointer-events: none; background: var(--ink); color: #fff; font-size: 12px; padding: 4px 7px; border-radius: 5px; white-space: nowrap; transform: translate(-50%, -130%); display: none; z-index: 3;}
.here, .notes {border-top: 1px solid var(--rule); padding-top: 10px; display: grid; gap: 4px;}
.hk, .notes {color: var(--ink-2); font-size: 12.5px;}
.notes b {color: var(--ink); font-weight: 600;}
.lag {background: #fff3c4; color: #5b4a00; font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 999px;}
.caveat {font-size: 12.5px; color: var(--ink-2); margin-top: -8px;}
.caveat.warn {background: #fff3c4; color: #5b4a00; border-radius: 8px; padding: 6px 10px; font-weight: 600; margin-top: -4px;}
#story .ph.warn {background: #fff3c4; color: #5b4a00;}
#story .ph.warn a {color: inherit; text-decoration: underline;}
.layernote {color: #5b4a00; background: #fff3c4; border-radius: 6px; padding: 4px 8px; margin-top: 6px;}
.dpick {display: flex; gap: 8px; align-items: center; font-size: 12.5px; color: var(--ink-2); margin-top: -6px;}
.dpick select {font: inherit; flex: 1; min-width: 0; padding: 3px 6px; border: 1px solid var(--rule); border-radius: 6px; background: #fff;}
#observablehq-main, #story {font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;}
.pnote {background: #fff3c4; color: #5b4a00; border-radius: 8px; padding: 8px 10px; font-size: 12px;}
.cname {font: 600 11px/1.1 system-ui, sans-serif; color: #26251f; text-shadow: 0 0 2px #fff, 0 0 2px #fff, 0 0 3px #fff; pointer-events: none; white-space: nowrap; letter-spacing: 0.02em;}
.pin {position: fixed; top: 0; left: 0; right: 0; z-index: 20; display: none; gap: 14px; align-items: baseline; padding: 8px 18px; background: rgba(255,255,255,0.96); border-bottom: 1px solid var(--rule); font: 13px/1.4 system-ui, sans-serif; color: var(--ink-2);}
.pin.on {display: flex;}
.pin b {color: var(--ink); font-size: 14px;}
.pin button {margin-left: auto; font: inherit; border: 1px solid var(--rule); background: #fff; border-radius: 6px; padding: 2px 10px; cursor: pointer;}
.controls input {font: inherit; font-size: 13px; padding: 4px 8px; border: 1px solid var(--rule); border-radius: 6px; width: 190px;}
.herepin {width: 16px; height: 16px; border-radius: 2px; background: #fff; border: 3px solid #0b0b0b; box-shadow: 0 0 0 2px #fff;}
.screen footer {border-top: 1px solid var(--rule); padding: 10px 16px; display: flex; gap: 16px; align-items: center;}
.screen footer p {margin: 0; font-size: 15px; flex: 1; max-width: none;}
.screen footer .cue {color: var(--ink-2); font-size: 12.5px; white-space: nowrap;}
#story {max-width: 1100px; margin: 0 auto; padding: 8px 8px 8px;}
#observablehq-main {min-height: 0;}
#observablehq-footer {margin-top: 1rem;}
#story section {padding: 28px 0 8px; border-top: 1px solid var(--rule);}
#story section:first-of-type {border-top: 0;}
#story h2 {font-size: 22px; margin: 0 0 6px; max-width: none;}
#story h3 {font-size: 14px; margin: 22px 0 4px; max-width: none;}
#story p {max-width: 820px;}
#story .lead {font-size: 16px; margin: 0 0 6px;}
#story .how, #story .ph {color: var(--ink-2); font-size: 13px; margin: 2px 0 8px;}
#story .ph {background: #f3f2ee; border-radius: 8px; padding: 8px 10px;}
#story ul {max-width: 820px; padding-left: 18px;}
#story li {margin: 6px 0;}
.key {display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--ink-2); margin: 4px 0 6px; align-items: center;}
.key i {display: inline-block; width: 12px; height: 12px; border-radius: 2px; margin-right: 5px; vertical-align: -1px;}
.key .ramp {display: inline-block; width: 160px; height: 10px; border-radius: 2px;}
.frames {display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px 14px; max-width: 1100px;}
.frames canvas {width: 100%; height: auto; display: block; background: #fbfaf7; border: 1px solid var(--rule); border-radius: 4px;}
.frames .lab {font-size: 12px; color: var(--ink-2); margin-top: 3px;}
canvas.matrix {width: 100%; max-width: 1100px; height: auto; display: block;}
table.ev {border-collapse: collapse; font-size: 13px; width: 100%; max-width: 820px;}
table.ev th, table.ev td {text-align: right; padding: 6px 10px; border-bottom: 1px solid var(--rule);}
table.ev th:nth-child(1), table.ev td:nth-child(1), table.ev th:nth-child(2), table.ev td:nth-child(2) {text-align: left;}
table.ev tr.cur {background: #fdf1e7; font-weight: 600;}
.hov {position: fixed; pointer-events: none; background: #0b0b0b; color: #fff; font-size: 12px; padding: 4px 7px; border-radius: 5px; display: none; z-index: 10; white-space: nowrap;}
@media (min-width: 1400px) {
  /* wide screens: chart on the left, its title, key and reading notes beside it */
  #story {max-width: 1560px; padding: 8px 24px;}
  #story .blk {display: grid; grid-template-columns: minmax(0, 1100px) minmax(280px, 400px); grid-template-rows: auto 1fr; column-gap: 36px; align-items: start; margin-top: 22px;}
  #story .blk .fig {grid-column: 1; grid-row: 1 / span 2;}
  #story .blk .side {grid-column: 2;}
  #story .blk .side h3 {margin-top: 0;}
  #story .blk .side .key {flex-wrap: wrap;}
  #story section > ul {max-width: 1560px; columns: 2; column-gap: 48px;}
  #story section > ul li {break-inside: avoid; margin-top: 0;}
}
@media (max-width: 1000px) {
  .screen {height: auto;}
  .screen main {grid-template-columns: 1fr;}
  #map {position: relative; inset: auto; height: 56vh;}
  .screen main {display: flex; flex-direction: column;}
  .mapwrap {display: contents;}
  #map {order: 1;}
  .slider {order: 2;}
  .screen aside {order: 3;}
  .legend {position: static; max-width: none; margin: 10px 12px; order: 4;}
  .slider {position: static; width: auto; margin: 0 12px 10px;}
  .screen aside {border-left: 0; border-top: 1px solid var(--rule);}
  .screen footer {flex-direction: column; align-items: flex-start;}
  .frames {grid-template-columns: repeat(2, 1fr);}
}
</style>

<div class="screen" id="top">
  <header>
    <h1><svg class="logo" viewBox="0 0 24 24" aria-hidden="true"><path d="M12.6 1.5c.5 3-1 4.800-2.700 6.600C8 10.100 6 12.100 6 15.300A6 6 0 0 0 12 21.500a6 6 0 0 0 6-6.200c0-2.300-1-4-2.100-5.400-.300 1.500-1 2.500-2 3.100.400-3.600-.300-7.800-1.300-11.500Z" fill="#d9783c"/><path d="M12 21.500a3.300 3.300 0 0 1-3.300-3.400c0-1.700 1.100-2.700 2.100-3.800.600-.700 1.100-1.400 1.200-2.400 1.800 1.600 3.300 3.600 3.300 6.200A3.300 3.300 0 0 1 12 21.500Z" fill="#74290c"/></svg>Heat Explorer</h1>
    <div class="controls">
      <label>Find
        <input id="find" list="places" placeholder="Country or province" aria-label="Find a country or province by name" autocomplete="off">
        <datalist id="places"></datalist>
      </label>
      <label>Layer
        <select id="layer" aria-label="Map layer"><option value="sev">Heat spell severity, by day</option><option value="severe">Severe days in a year</option><option value="spell">Heat spell days in a year</option><option value="msevere">Severe days in a month</option><option value="mspell">Heat spell days in a month</option><option value="season">Season status, last 12 weeks</option><option value="trend">Trend in heat spell days</option><option value="humid">Humid heat spell (experimental)</option></select>
      </label>
      <label>Summarise by
        <span class="seg" id="levels" role="group" aria-label="Admin level"><button data-level="adm0" aria-pressed="false">Country</button><button data-level="adm1" aria-pressed="true">Province</button><button data-level="adm2" aria-pressed="false">District</button></span>
      </label>
    </div>
    <span class="date">Data coverage: <b id="hdate"></b></span>
  </header>
  <main>
    <div class="mapwrap">
      <div id="map" role="application" aria-label="World map of heat spell severity on the chosen date. To choose a place without a mouse, use the Find box above the map."></div>
      <div class="legend">
        <h2 id="leg-title">Heat spell severity</h2>
        <div id="leg-yearly" style="display:none">
          <div class="row"><span>0</span><span class="ramp" style="flex:1;height:10px;border-radius:2px;background:linear-gradient(90deg,#efede7,#f0be8c,#d9783c,#74290c)"></span><span id="leg-cap"></span></div>
          <div class="row">Counted by the class of each day, including the first two days of a spell, which the daily map does not show.</div>
        </div>
        <div id="leg-trend" style="display:none">
          <div class="row"><span>-20</span><span class="ramp" style="flex:1;height:10px;border-radius:2px;background:linear-gradient(90deg,#1854a0,#deebf7 49%,#f6e8d6 51%,#74290c)"></span><span>+20 days per decade</span></div>
          <div class="row"><span class="sw" style="background:var(--land)"></span>No trend that passes the test</div>
          <div class="row">Change in heat spell days per year, on blocks of 3 by 3 cells. Coloured only where a Mann-Kendall test passes, plainly and after allowing for one year resembling the next, at a false discovery rate of 10%.</div>
          <div class="row" style="color:#5b4a00;background:#fff3c4;border-radius:6px;padding:4px 6px"><span>The source is a reanalysis whose inputs change over the years, which can add or hide a trend, and the yardstick is fixed on 1991 to 2020 and not adjusted for warming.</span></div>
        </div>
        <div id="leg-season" style="display:none">
          <div class="row"><span class="sw" style="background:#eb6834"></span>New this week: no heat spell in the 11 weeks before</div>
          <div class="row"><span class="sw" style="background:#a14fb0"></span>Again this week, after a break</div>
          <div class="row"><span class="sw" style="background:linear-gradient(90deg,#d9783c,#74290c)"></span>Still in a heat spell: 2 weeks running to 8 or more</div>
          <div class="row"><span class="sw" style="background:#7fa3c7"></span>No longer in a heat spell: was last week</div>
          <div class="row"><span class="sw" style="background:var(--land)"></span>None of these</div>
          <div class="row">For the week ending on the last day of data. This project's own grouping, not tested on events.</div>
        </div>
        <div id="leg-humid" style="display:none">
          <div class="row"><span class="sw" style="background:#1f7a8c"></span>In a humid heat spell: third day or later of unusual heat and humidity together</div>
          <div class="row"><span class="sw" style="background:var(--land)"></span>Not in a humid heat spell</div>
          <div class="row" style="color:#5b4a00;background:#fff3c4;border-radius:6px;padding:4px 6px"><span><b>Experimental.</b> Humid heat here is judged against 1991 to 2020. The humidity record in the source data drifts, so recent years are flagged far more often than the past for reasons that are partly not climate. Yes or no only: no severity, and no part in the status or ranks.</span></div>
        </div>
        <div id="leg-daily">
        <div class="row"><span class="sw" style="background:var(--c3)"></span>Extreme: roughly the hottest 1 day in 100 for the time of year</div>
        <div class="row"><span class="sw" style="background:var(--c2)"></span>Severe: roughly the hottest 1 day in 20</div>
        <div class="row"><span class="sw" style="background:var(--c1)"></span>Heat spell: third day or later that is hot for the date, or among the hottest of the year</div>
        <div class="row"><span class="sw" style="background:var(--land)"></span>Not in a heat spell</div>
        </div>
        <div class="row"><span class="sw hatch"></span><span id="leg-conf">Low confidence: weak signal here</span></div>
        <div class="row"><span class="sw dots"></span>Data suspect: a break in the source data</div>
        <div class="base">Relative to each place's own 1991 to 2020 climate. Shares are of land area. Thin lines are coasts and country borders, and province borders once you zoom in. White is sea, or land south of 60 S. Click the map to choose a place.</div>
      </div>
      <div class="slider">
        <select id="period" aria-label="Period shown: the last year, or a past event"></select>
        <div class="lab"><span id="sfirst"></span><b id="sdate"></b></div>
        <input type="range" id="slider" min="0" max="89" value="89" aria-label="Date or year shown on the map">
        <div class="layernote" id="layernote" style="display:none"></div>
      </div>
    </div>
    <aside>
      <div class="place">
        <div class="lvl" id="plvl"></div>
        <h2 id="pname">Loading</h2>
        <div class="parent" id="pparent"></div>
      </div>
      <label class="dpick" id="dpick" style="display:none">District <select id="dsel" aria-label="Choose a district of this province"></select></label>
      <div class="status" aria-live="polite"><span class="chip" id="pchip"></span><span id="pstatus"></span></div>
      <div class="caveat" id="pcaveat" style="display:none"></div>
      <div class="caveat" id="phumid" style="display:none"></div>
      <div class="nums">
        <div class="num"><div class="v" id="n1"></div><div class="k">of land area in a heat spell</div></div>
        <div class="num"><div class="v" id="n2"></div><div class="k">of land area severe or extreme</div></div>
        <div class="num"><div class="v" id="n3"></div><div class="k" id="k3"></div></div>
        <div class="num"><div class="v" id="n4"></div><div class="k" id="k4"></div></div>
      </div>
      <div class="spark">
        <h3>Share of land area in a heat spell, 60 days to the chosen date</h3>
        <div class="sparkbox"><svg id="spark" role="img" viewBox="0 0 320 86" preserveAspectRatio="none" aria-label="Share of land area in a heat spell over 60 days"></svg><div class="tip" id="tip"></div></div>
      </div>
      <div class="pnote" id="pnote" style="display:none"></div>
      <div class="here">
        <div class="lvl">Here: <span id="hname"></span></div>
        <div class="status"><span class="chip" id="hchip"></span><span id="hstatus"></span></div>
        <div class="hk" id="hdetail"></div>
      </div>
      <div class="notes"><div><b>Based on:</b> <span id="pcells"></span></div></div>
    </aside>
  </main>
  <footer>
    <p id="sentence" aria-live="polite"></p>
    <span class="cue">Scroll for the full story of this place &#8595;</span>
  </footer>
</div>
<div class="pin" id="pin"><b id="pinname"></b><span id="pindate"></span><button id="pintop" type="button">Back to the map</button></div>
<div id="story"></div>
<div class="hov" id="hov"></div>

```js
import {files} from "./data/files.js";
import {start} from "./components/app.js";

start(files);
```
