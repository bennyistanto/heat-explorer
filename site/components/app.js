// Heat Explorer page logic. Reads the files written by pipeline/web_products.py (formats are
// described there and in data/manifest.json). One long page: the first screen stands alone,
// the sections below tell the story of the selected place.
import * as ml from "npm:maplibre-gl@4.7.1";

const maplibregl = ml.default ?? ml;   // version 4 bundles its worker, which Framework can self-host as one file
import * as Plot from "npm:@observablehq/plot";

const NR = 1801, NC = 3600, LAT_TOP = 85, LAT_BOT = -60;
const RGB = {0: [231, 230, 225], 1: [240, 190, 140], 2: [217, 120, 60], 3: [116, 41, 12]};
const C = {spell: "#f0be8c", severe: "#d9783c", extreme: "#74290c", land: "#e7e6e1", ink2: "#52514e"};
const TIERS = ["No widespread severe heat", "Severe heat in part of the area", "Severe heat over most of the area"];
const LEVELS = {adm0: "Country", adm1: "Province", adm2: "District"};
const DAY = 86400000, EPOCH = Date.UTC(1979, 0, 1);
const $ = (id) => document.getElementById(id);
const el = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; };
const iso = (t) => new Date(EPOCH + t * DAY).toISOString().slice(0, 10);
const fmt = (t, year = true) => new Date(EPOCH + t * DAY).toLocaleDateString("en-GB", {day: "numeric", month: "short", ...(year ? {year: "numeric"} : {}), timeZone: "UTC"});
const ordinal = (n) => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th");

async function pixels(file) {
  const bmp = await createImageBitmap(await file.blob(), {colorSpaceConversion: "none", premultiplyAlpha: "none"});
  const c = new OffscreenCanvas(bmp.width, bmp.height), x = c.getContext("2d", {willReadFrequently: true});
  x.drawImage(bmp, 0, 0);
  return x.getImageData(0, 0, bmp.width, bmp.height).data;
}
async function readBin(file) {
  const buf = await file.arrayBuffer(), n = new DataView(buf).getUint32(0, true);
  const head = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, n)));
  let at = 4 + n;
  const arr = {};
  for (const a of head.arrays) {
    const len = a.shape.reduce((p, q) => p * q, 1), size = a.dtype === "uint16" ? 2 : 1;
    arr[a.name] = size === 2 ? new Uint16Array(buf.slice(at, at + 2 * len)) : new Uint8Array(buf, at, len);
    at += size * len;
  }
  return {head, arr};
}

export async function start(files) {
  const t00 = performance.now(), timing = [], mark = (k) => timing.push([k, Math.round(performance.now() - t00)]);
  const need = (p) => { if (!files[p]) throw new Error("file not in the build: " + p); return files[p]; };
  const cache = new Map();
  const once = (key, make) => { if (!cache.has(key)) cache.set(key, make()); return cache.get(key); };
  const [man, admins, latest] = await Promise.all([need("manifest.json").json(), need("admins.json").json(), need("latest.json").json()]);
  mark("json");
  const T = Math.round((Date.parse(man.last_date) - EPOCH) / DAY) + 1;       // days in the series
  const dayOf = (isoDate) => Math.round((Date.parse(isoDate) - EPOCH) / DAY);
  // the days the daily map can show: the recent window first, then each listed past event
  const PERIODS = (man.periods || [{name: "Recent days", start: man.daily_window[0], end: man.daily_window[1]}]).map((q) => {
    const a = dayOf(q.start), b = dayOf(q.end);
    return {name: q.name, bbox: q.bbox || null, focus: q.focus || null, days: Array.from({length: b - a + 1}, (_, i) => a + i)};
  });
  const curT = () => PERIODS[S.p].days[S.k];
  const NM = man.monthly ? man.monthly.months : 0, M0 = man.monthly ? man.monthly.first : "1979-01";
  const monthKey = (m) => { const y = +M0.slice(0, 4) + Math.floor((+M0.slice(5) - 1 + m) / 12), mo = ((+M0.slice(5) - 1 + m) % 12) + 1; return `${y}-${String(mo).padStart(2, "0")}`; };
  const monthName = (m) => new Date(monthKey(m) + "-01T00:00:00Z").toLocaleDateString("en-GB", {month: "long", year: "numeric", timeZone: "UTC"});
  const isMonth = () => S.layer === "mspell" || S.layer === "msevere";
  const [maskPx, admPx, parentBuf] = await Promise.all([pixels(need("static/mask.png")), pixels(need("static/adm2.png")), need("static/adm2_parent.bin").arrayBuffer()]);
  mark("static images");
  const parent = new Uint16Array(parentBuf);
  const N = NR * NC, mask = new Uint8Array(N), cell = {adm2: new Int32Array(N), adm1: new Int16Array(N), adm0: new Int16Array(N)};
  for (let i = 0; i < N; i++) {
    mask[i] = maskPx[4 * i];
    const a2 = ((admPx[4 * i] << 16) | (admPx[4 * i + 1] << 8) | admPx[4 * i + 2]) - 1;
    const a1 = a2 >= 0 && parent[a2] !== 65535 ? parent[a2] : -1;
    cell.adm2[i] = a2; cell.adm1[i] = a1; cell.adm0[i] = a1 >= 0 ? admins.adm1[a1].adm0 : -1;
  }
  mark("cell lookups");
  const dayCache = new Map();                                                // decoded days, most recently used last; each is 6.5 MB, so only a few are kept
  const daily = (k) => {
    if (dayCache.has(k)) { const v = dayCache.get(k); dayCache.delete(k); dayCache.set(k, v); return v; }
    const pr = (async () => {
      const px = await pixels(need(`daily/${iso(k)}.png`)), out = new Uint8Array(N);   // k is the day, counted from 1979-01-01
      for (let i = 0; i < N; i++) out[i] = px[4 * i];                        // one byte: bits 0-1 class shown, bits 2-7 day of the spell, 255 sea
      return out;
    })();
    dayCache.set(k, pr);
    pr.catch(() => dayCache.delete(k));                                       // a failed download is forgotten, so the next try fetches again
    while (dayCache.size > 8) dayCache.delete(dayCache.keys().next().value);
    return pr;
  };
  const Y0 = man.annual_years[0], NY = man.annual_years[1] - Y0 + 1;
  const yearCache = new Map();
  const yearly = (name, y) => {                                               // days in the year in a heat spell, or severe: one byte per cell, 254 = 254 or more, 255 sea
    const key = name + y;
    if (!yearCache.has(key)) {
      yearCache.set(key, (async () => { const px = await pixels(need(`annual/${name}_${Y0 + y}.png`)), out = new Uint8Array(N); for (let i = 0; i < N; i++) out[i] = px[4 * i]; return out; })());
      while (yearCache.size > 4) yearCache.delete(yearCache.keys().next().value);
    }
    return yearCache.get(key);
  };
  const weekCache = new Map();
  const weekly = (w) => {                                                     // highest class shown in week w (0 = the week ending on the last day): 0 to 3, 255 sea
    if (!weekCache.has(w)) weekCache.set(w, (async () => { const px = await pixels(need(man.weekly[w].file)), out = new Uint8Array(N); for (let i = 0; i < N; i++) out[i] = px[4 * i]; return out; })());
    return weekCache.get(w);
  };
  const evCache = new Map();                                                  // weeks of one past event, worked out here from its daily maps; kept for one event at a time
  const eventWeek = (pi, days) => {
    const key = pi + ":" + days[0];
    for (const k of evCache.keys()) if (!k.startsWith(pi + ":")) evCache.delete(k);
    if (!evCache.has(key)) {
      const pr = (async () => {
        const out = new Uint8Array(N);
        for (let n = 0; n < days.length; n++) {
          const px = await pixels(need(`daily/${iso(days[n])}.png`));          // not through the day cache: these are read once and dropped
          for (let i = 0; i < N; i++) { const v = px[4 * i]; if (v === 255) out[i] = 255; else if ((v & 3) > out[i]) out[i] = v & 3; }
        }
        return out;
      })();
      evCache.set(key, pr);
      pr.catch(() => evCache.delete(key));
    }
    return evCache.get(key);
  };
  // the small maps to draw, oldest first: {a, b, get}, a and b the first and last day
  const frameList = () => {
    if (S.p === 0) {
      const out = [];
      for (let w = Math.min(7, man.weekly.length - 1); w >= 0; w--) out.push({a: dayOf(man.weekly[w].start), b: dayOf(man.weekly[w].end), get: () => weekly(w)});
      return out;
    }
    const d = PERIODS[S.p].days, out = [], pi = S.p;
    for (let e = d.length; e > 0 && out.length < 8; e -= 7) {                 // runs of seven days counted back from the last day shown; the oldest run can be shorter
      const run = d.slice(Math.max(0, e - 7), e);
      out.unshift({a: run[0], b: run[run.length - 1], get: () => eventWeek(pi, run)});
    }
    return out;
  };
  let lineSetsP = null;                                                       // boundary lines with their bounding boxes, loaded once
  const lineSets = () => lineSetsP || (lineSetsP = (async () => {
    const out = {};
    for (const k of ["countries", "coast", "provinces"]) {
      if (!files[`static/${k}.json`]) continue;
      out[k] = (await files[`static/${k}.json`].json()).lines.coordinates.map((pts) => {
        let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
        for (const q of pts) { if (q[0] < x0) x0 = q[0]; if (q[0] > x1) x1 = q[0]; if (q[1] < y0) y0 = q[1]; if (q[1] > y1) y1 = q[1]; }
        return {p: pts, b: [x0, y0, x1, y1]};
      });
    }
    return out;
  })());
  async function drawWeeks(wrap, arr, id) {
    const LS = await lineSets();                                   // up to eight small maps of one unit, oldest week first
    let r0 = NR, r1 = -1, c0 = NC, c1 = -1;
    for (let i = 0; i < N; i++) if (arr[i] === id) { const r = Math.floor(i / NC), c = i % NC; if (r < r0) r0 = r; if (r > r1) r1 = r; if (c < c0) c0 = c; if (c > c1) c1 = c; }
    if (r1 < 0 || c1 - c0 >= 1800) { wrap.append(el(`<p class="ph">These maps cannot be drawn for a place that crosses the 180th meridian.</p>`)); return; }
    // a margin around the place: at least one cell, more for a small place so it is seen with its surroundings (10 rows or more),
    // and enough on the short side that every small map comes out between about 4:3 and 3:2 on the ground
    const h0 = r1 - r0 + 1, w0 = c1 - c0 + 1, cosl = Math.cos((90 - 0.1 * (r0 + r1) / 2) * Math.PI / 180);
    let nrT = Math.max(h0 + 2, 10), ncT = Math.max(w0 + 2, Math.ceil(1.3 * nrT / cosl));
    if (ncT * cosl / nrT > 1.5) nrT = Math.ceil(ncT * cosl / 1.5);
    const padR = Math.ceil((nrT - h0) / 2), padC = Math.ceil((ncT - w0) / 2);
    r0 = Math.max(0, r0 - padR); r1 = Math.min(NR - 1, r1 + padR); c0 = Math.max(0, c0 - padC); c1 = Math.min(NC - 1, c1 + padC);
    const nr = r1 - r0 + 1, ncol = c1 - c0 + 1, aspect = ncol * Math.cos((90 - 0.1 * (r0 + r1) / 2) * Math.PI / 180) / nr;
    for (const fr of frameList()) {
      const code = await fr.get();
      if (!wrap.isConnected) return;                                          // the story was redrawn meanwhile
      const cvs = document.createElement("canvas"), K = Math.max(1, Math.ceil(480 / ncol));   // pixels per grid cell: every small map is drawn about 480 pixels wide, so lines stay thin and sharp
      cvs.width = ncol * K; cvs.height = nr * K;
      const g = cvs.getContext("2d"), im = g.createImageData(ncol * K, nr * K), px = new Uint32Array(im.data.buffer), Wp = ncol * K, OUTP = pack([243, 242, 238]);
      for (let r = 0; r < nr; r++) for (let c = 0; c < ncol; c++) {
        const i = (r0 + r) * NC + c0 + c, v = code[i];
        if (v === 255) continue;
        const col = arr[i] === id ? COL[v] : OUTP;
        for (let y = 0; y < K; y++) for (let x = 0; x < K; x++) px[(r * K + y) * Wp + c * K + x] = col;
      }
      g.putImageData(im, 0, 0);
      // coast, province and country lines from the boundary geometry, drawn over the cells
      const west = -180.05 + 0.1 * c0, north = 90.05 - 0.1 * r0, bb = [west, north - 0.1 * nr, west + 0.1 * ncol, north];
      const stroke = (set, style, width) => {
        if (!set) return;
        g.strokeStyle = style; g.lineWidth = width; g.lineJoin = "round";
        g.beginPath();
        for (const L of set) {
          if (L.b[0] > bb[2] || L.b[2] < bb[0] || L.b[1] > bb[3] || L.b[3] < bb[1]) continue;
          for (let n = 0; n < L.p.length; n++) { const x = (L.p[n][0] - west) * 10 * K, y = (north - L.p[n][1]) * 10 * K; if (n) g.lineTo(x, y); else g.moveTo(x, y); }
        }
        g.stroke();
      };
      stroke(LS.provinces, "rgba(40,39,36,0.55)", 1.2);
      stroke(LS.coast, "rgba(40,39,36,0.65)", 1.4);
      stroke(LS.countries, "rgba(11,11,11,0.9)", 2.2);
      cvs.style.aspectRatio = aspect.toFixed(3);
      cvs.setAttribute("role", "img");
      cvs.setAttribute("aria-label", `Highest heat class reached in each grid cell, ${iso(fr.a)} to ${iso(fr.b)}`);
      const box = el(`<div><div class="lab">${fr.a === fr.b ? fmt(fr.a, false) : `${fmt(fr.a, false)} to ${fmt(fr.b, false)}`}</div></div>`);
      box.prepend(cvs);
      wrap.append(box);
    }
  }
  const humCache = new Map();
  const humidDay = (k) => {                                                   // EXPERIMENTAL layer: 1 in a humid heat spell, 0 not, 255 sea
    if (!humCache.has(k)) {
      humCache.set(k, (async () => { const px = await pixels(need(`humid/${iso(k)}.png`)), out = new Uint8Array(N); for (let i = 0; i < N; i++) out[i] = px[4 * i]; return out; })());
      while (humCache.size > 6) humCache.delete(humCache.keys().next().value);
    }
    return humCache.get(k);
  };
  let maskHum = null;                                                         // this layer's own confidence (bits 0-1), with the data-suspect bit of the main mask
  const humidMask = async () => {
    if (!maskHum) { const px = await pixels(need("static/mask_humid.png")); maskHum = new Uint8Array(N); for (let i = 0; i < N; i++) maskHum[i] = (px[4 * i] & 3) | (mask[i] & 4); }
    return maskHum;
  };
  const fixedCache = new Map();
  const fixedLayer = (name) => {                                              // layers with one picture: trend, season status
    if (!fixedCache.has(name)) fixedCache.set(name, (async () => { const px = await pixels(need(`static/${name}.png`)), out = new Uint8Array(N); for (let i = 0; i < N; i++) out[i] = px[4 * i]; return out; })());
    return fixedCache.get(name);
  };
  const isFixed = () => S.layer === "trend" || S.layer === "season";
  const hasHumid = !!man.humid && !!files["static/mask_humid.png"];
  const isYear = () => S.layer === "spell" || S.layer === "severe";
  const HUMCOL = [31, 122, 140];                                              // a blue-green, clearly not the orange family of the temperature layer
  const monthCache = new Map();
  const monthlyLayer = (name, m) => {                                         // days in the month in a heat spell, or severe: 0 to 31, 255 sea
    const key = name + m;
    if (!monthCache.has(key)) {
      monthCache.set(key, (async () => { const px = await pixels(need(`monthly/${MONTHLY[name].file}_${monthKey(m)}.png`)), out = new Uint8Array(N); for (let i = 0; i < N; i++) out[i] = px[4 * i]; return out; })());
      while (monthCache.size > 6) monthCache.delete(monthCache.keys().next().value);
    }
    return monthCache.get(key);
  };
  const YEARLY = {spell: {cap: 150, title: "Days in a heat spell in the year"}, severe: {cap: 120, title: "Severe or extreme days in the year"}};
  const esc = (v) => String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const nameOf = (level, row) => {                                           // some units have no name in the source
    const u = admins[level][row];
    if (u.name) return u.name;
    if (level === "adm1") return `Unnamed area in ${nameOf("adm0", u.adm0)}`;
    return `Unnamed territory${u.iso3 ? " (" + u.iso3 + ")" : ""}`;
  };
  const SOUTH = Math.round((90 - LAT_BOT) / 0.1);                             // rows beyond this are south of 60 S: not drawn, not selectable
  const country = (a0) => once("a" + a0, () => readBin(need(`admin/${admins.adm0[a0].id}.bin`)));
  const countryArch = (a0) => once("r" + a0, async () => {                    // numbers for the days of the listed past events
    const f = files[`admin_arch/${admins.adm0[a0].id}.bin`];
    if (!f) return null;
    const b = await readBin(f);
    b.pos = new Map(b.head.days.map((d, i) => [d, i]));
    return b;
  });
  const districts = (a0) => once("b" + a0, () => files[`admin2/${admins.adm0[a0].id}.bin`] ? readBin(files[`admin2/${admins.adm0[a0].id}.bin`]) : null);
  const events = (a0) => once("e" + a0, () => need(`events/${admins.adm0[a0].id}.json`).json());

  // ---------- state
  const S = {p: 0, k: PERIODS[0].days.length - 1, level: "adm1", sel: null, pt: null, msg: "", layer: "sev", y: NY - 1, m: NM - 1};
  let best = -1, score = 0;                                                   // start on the province with the most severe area on the latest date
  admins.adm1.forEach((u, i) => { const v = latest.adm1.tier[i] === 2 ? latest.adm1.severe[i] * u.area_km2 : 0; if (v > score) { score = v; best = i; } });
  if (best >= 0) S.sel = {adm1: best, adm0: admins.adm1[best].adm0, adm2: -1};
  const selectAt = (row, col) => {                                            // choose the unit under a grid cell, or none
    const i = row * NC + col;
    if (cell.adm1[i] >= 0 && row <= SOUTH) { S.sel = {adm2: cell.adm2[i], adm1: cell.adm1[i], adm0: cell.adm0[i]}; S.msg = ""; }
    else { S.sel = null; S.msg = mask[i] === 255 || row > SOUTH ? "This point is at sea or outside the mapped area. Click on land to choose a place." : "This point is on land that belongs to no admin unit in the boundary set, so there is no area summary for it. The reading for the point is below."; }
  };
  let linked = false;                                                         // a link can carry the level, the date and the point or province
  {
    const q = new URLSearchParams(location.hash.slice(1));
    if (LEVELS[q.get("lvl")]) S.level = q.get("lvl");
    if (q.get("d")) { const want = dayOf(q.get("d")); for (let pi = 0; pi < PERIODS.length; pi++) { const kk = PERIODS[pi].days.indexOf(want); if (kk >= 0) { S.p = pi; S.k = kk; break; } } }
    const pt = (q.get("pt") || "").split(",").map(Number);
    if (pt.length === 2 && pt.every(Number.isFinite) && Math.abs(pt[0]) <= 90) {
      const row = Math.round((90 - pt[0]) / 0.1), col = ((Math.round((pt[1] + 180) / 0.1) % NC) + NC) % NC;
      S.pt = {row, col, lat: pt[0], lon: pt[1]}; selectAt(row, col); linked = true;
    } else if (q.get("u")) {
      const j = admins.adm1.findIndex((u) => u.id === q.get("u"));
      if (j >= 0) { S.sel = {adm1: j, adm0: admins.adm1[j].adm0, adm2: -1}; S.want2 = q.get("d2"); linked = true; }
    }
  }

  // ---------- map
  const ym = (la) => Math.log(Math.tan(Math.PI / 4 + la * Math.PI / 360));
  const H = Math.round(NC * (ym(LAT_TOP) - ym(LAT_BOT)) / (2 * Math.PI));
  const srcRow = new Int32Array(H);
  for (let y = 0; y < H; y++) {
    const la = (2 * Math.atan(Math.exp(ym(LAT_TOP) - (y + 0.5) * (ym(LAT_TOP) - ym(LAT_BOT)) / H)) - Math.PI / 2) * 180 / Math.PI;
    srcRow[y] = Math.max(0, Math.min(NR - 1, Math.round((90 - la) / 0.1)));
  }
  const cv = document.createElement("canvas");
  cv.width = NC; cv.height = H;
  const ctx = cv.getContext("2d"), img = ctx.createImageData(NC, H), out = new Uint32Array(img.data.buffer);
  const pack = ([r, g, b]) => (255 << 24) | (b << 16) | (g << 8) | r;
  const mix = (a, b, f) => a.map((v, i) => Math.round(v + (b[i] - v) * f));
  // hatch and dots are a tint of the class beneath them (towards dark on the light classes, towards white on the dark ones), so the class stays readable
  const COL = [pack(RGB[0]), pack(RGB[1]), pack(RGB[2]), pack(RGB[3]), 0];
  const INKP = pack([11, 11, 11]);
  const HATCHC = [0, 1, 2, 3].map((c) => pack(mix(RGB[c], c >= 2 ? [255, 255, 255] : [60, 59, 56], 0.5))).concat(0);
  const DOTC = [0, 1, 2, 3].map((c) => pack(mix(RGB[c], c >= 2 ? [255, 255, 255] : [11, 11, 11], 0.8))).concat(0);
  const RAMP = [[239, 237, 231], [240, 190, 140], [217, 120, 60], [116, 41, 12]];
  const rampAt = (f) => { const q = Math.min(Math.max(f, 0), 1) * 3, i = Math.min(Math.floor(q), 2); return mix(RAMP[i], RAMP[i + 1], q - i); };
  for (const k of Object.keys(YEARLY)) {
    const lut = new Uint32Array(256), hatch = new Uint32Array(256), dot = new Uint32Array(256);
    for (let v = 0; v < 255; v++) {
      const rgb = v === 0 ? RGB[0] : rampAt(v / YEARLY[k].cap), dark = v / YEARLY[k].cap > 0.55;
      lut[v] = pack(rgb); hatch[v] = pack(mix(rgb, dark ? [255, 255, 255] : [60, 59, 56], 0.5)); dot[v] = pack(mix(rgb, dark ? [255, 255, 255] : [11, 11, 11], 0.8));
    }
    Object.assign(YEARLY[k], {lut, hatch, dot});
  }
  const lutSet = (colour) => {                                                // colour(v) -> rgb for byte values 0 to 254
    const o = {lut: new Uint32Array(256), hatch: new Uint32Array(256), dot: new Uint32Array(256)};
    for (let v = 0; v < 255; v++) { const rgb = colour(v), dark = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2] < 140; o.lut[v] = pack(rgb); o.hatch[v] = pack(mix(rgb, dark ? [255, 255, 255] : [60, 59, 56], 0.5)); o.dot[v] = pack(mix(rgb, dark ? [255, 255, 255] : [11, 11, 11], 0.8)); }
    return o;
  };
  const TREND_CAP = 20;                                                       // days per decade at the ends of the colour scale
  const TREND = lutSet((v) => { if (v === 0) return RGB[0]; const d = Math.max(-1, Math.min(1, (v - 128) / 2 / TREND_CAP)); return d >= 0 ? mix([246, 232, 214], [116, 41, 12], d) : mix([222, 235, 247], [24, 84, 160], -d); });
  const SEASON = lutSet((v) => v === 1 ? [235, 104, 52] : v === 2 ? [161, 79, 176] : v === 5 ? [127, 163, 199] : v >= 10 ? mix([217, 120, 60], [116, 41, 12], Math.min(1, (v - 12) / 6)) : RGB[0]);
  const MONTHLY = {mspell: {...lutSet((v) => v === 0 ? RGB[0] : rampAt(v / 31)), title: "Days in a heat spell in the month", cap: "31 days", file: "spell"},
    msevere: {...lutSet((v) => v === 0 ? RGB[0] : rampAt(v / 20)), title: "Severe or extreme days in the month", cap: "20 or more days", file: "severe"}};
  const HUMID = {lut: new Uint32Array(256), hatch: new Uint32Array(256), dot: new Uint32Array(256)};
  for (const v of [0, 1]) { const rgb = v ? HUMCOL : RGB[0]; HUMID.lut[v] = pack(rgb); HUMID.hatch[v] = pack(mix(rgb, v ? [255, 255, 255] : [60, 59, 56], 0.5)); HUMID.dot[v] = pack(mix(rgb, v ? [255, 255, 255] : [11, 11, 11], 0.8)); }
  const selCells = () => S.sel ? (S.level === "adm2" && S.sel.adm2 >= 0 ? [cell.adm2, S.sel.adm2] : S.level === "adm0" ? [cell.adm0, S.sel.adm0] : [cell.adm1, S.sel.adm1]) : null;
  async function drawMap(my) {
    const yr = S.layer === "sev" ? null : S.layer === "humid" ? HUMID : S.layer === "trend" ? TREND : S.layer === "season" ? SEASON : isMonth() ? MONTHLY[S.layer] : YEARLY[S.layer];
    const code = S.layer === "humid" ? await humidDay(curT()) : isFixed() ? await fixedLayer(S.layer) : isMonth() ? await monthlyLayer(S.layer, S.m) : yr ? await yearly(S.layer, S.y) : await daily(curT());
    const mk = S.layer === "humid" ? await humidMask() : mask, td = performance.now();
    if (my !== undefined && my !== token) return;                             // a newer render has started: do not paint an older day over it
    for (let y = 0; y < H; y++) {
      const r = srcRow[y] * NC;
      for (let x = 0; x < NC; x++) {
        const i = r + x, v0 = code[i];
        let v = 0;
        if (v0 !== 255) {
          const m = mk[i], hatched = (m & 1) && (x + y) % 5 === 0, dotted = (m & 4) && x % 2 === 0 && y % 2 === 0;
          if (yr) v = dotted ? yr.dot[v0] : hatched ? yr.hatch[v0] : yr.lut[v0];
          else { const c = v0 & 3; v = dotted ? DOTC[c] : hatched ? HATCHC[c] : COL[c]; }
        }
        out[y * NC + x] = v;
      }
    }
    ctx.putImageData(img, 0, 0);
    const src = map.getSource("layer");
    if (src) { src.play(); src.pause(); map.triggerRepaint(); }
    if (window.__heat) window.__heat.drawMs = Math.round(performance.now() - td);
  }
  // outline of the selected unit, traced along the edges of its grid cells and drawn as a line above the cells
  let outlineKey = "";
  function drawOutline() {
    const sc0 = selCells(), sc = sc0 && sc0[1] >= 0 ? sc0 : null, key = sc ? S.level + sc[1] : "", src = map.getSource("sel");
    if (!src || key === outlineKey) return;
    outlineKey = key;
    const lines = [];
    if (sc) {
      const [arr, id] = sc, lon = (c) => -180.05 + 0.1 * c, lat = (r) => 90.05 - 0.1 * r;
      for (let r = 0; r <= SOUTH; r++) {
        let top = -1, bot = -1;
        for (let c = 0; c <= NC; c++) {
          const i = r * NC + c, inside = c < NC && arr[i] === id;
          const t = inside && (r === 0 || arr[i - NC] !== id), b = inside && arr[i + NC] !== id;
          if (t && top < 0) top = c; else if (!t && top >= 0) { lines.push([[lon(top), lat(r)], [lon(c), lat(r)]]); top = -1; }
          if (b && bot < 0) bot = c; else if (!b && bot >= 0) { lines.push([[lon(bot), lat(r + 1)], [lon(c), lat(r + 1)]]); bot = -1; }
          if (inside && (c === 0 || arr[i - 1] !== id)) lines.push([[lon(c), lat(r)], [lon(c), lat(r + 1)]]);
          if (inside && (c === NC - 1 || arr[i + 1] !== id)) lines.push([[lon(c + 1), lat(r)], [lon(c + 1), lat(r + 1)]]);
        }
      }
    }
    src.setData({type: "Feature", properties: {}, geometry: {type: "MultiLineString", coordinates: lines}});
  }
  function unitBounds(arr, id) {
    let r0 = NR, r1 = -1, c0 = NC, c1 = -1;
    for (let i = 0; i < N; i++) if (arr[i] === id) { const r = Math.floor(i / NC), c = i % NC; if (r < r0) r0 = r; if (r > r1) r1 = r; if (c < c0) c0 = c; if (c > c1) c1 = c; }
    return r1 < 0 || c1 - c0 >= 1800 ? null : [[-180 + 0.1 * c0 - 12, Math.max(-58, 90 - 0.1 * r1 - 8)], [-180 + 0.1 * c1 + 12, Math.min(83, 90 - 0.1 * r0 + 8)]];
  }
  const map = new maplibregl.Map({container: "map", attributionControl: false, renderWorldCopies: false, maxZoom: 7, minZoom: 0.6, center: [15, 22], zoom: 1.1,
    style: {version: 8, sources: {}, layers: [{id: "bg", type: "background", paint: {"background-color": "#fbfaf7"}}]}});
  map.addControl(new maplibregl.NavigationControl({showCompass: false}), "top-left");
  map.addControl(new maplibregl.AttributionControl({compact: true, customAttribution: "Data: AgERA5, Copernicus Climate Change Service. Boundaries: FieldMaps and OpenStreetMap contributors (ODbL)."}), "top-right");
  const pin = new maplibregl.Marker({element: el(`<div class="herepin"></div>`)});
  mark("map created");
  await new Promise((res) => map.on("load", res));
  mark("map loaded");
  document.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");   // start collapsed: the credit is also in the page footer
  map.addSource("layer", {type: "canvas", canvas: cv, animate: false, coordinates: [[-180.05, LAT_TOP], [179.95, LAT_TOP], [179.95, LAT_BOT], [-180.05, LAT_BOT]]});
  map.addLayer({id: "layer", type: "raster", source: "layer", paint: {"raster-resampling": "nearest", "raster-fade-duration": 0}});
  map.addSource("sel", {type: "geojson", data: {type: "Feature", properties: {}, geometry: {type: "MultiLineString", coordinates: []}}});
  map.addLayer({id: "sel-halo", type: "line", source: "sel", paint: {"line-color": "#ffffff", "line-width": 4, "line-opacity": 0.9}});
  map.addLayer({id: "sel", type: "line", source: "sel", paint: {"line-color": "#0b0b0b", "line-width": 1.6}});
  map.on("click", (e) => {
    const row = Math.round((90 - e.lngLat.lat) / 0.1), col = ((Math.round((e.lngLat.lng + 180) / 0.1) % NC) + NC) % NC;
    if (row < 0 || row >= NR) return;
    S.pt = {row, col, lat: e.lngLat.lat, lon: e.lngLat.lng};
    pin.setLngLat([-180 + 0.1 * col, 90 - 0.1 * row]).addTo(map);
    selectAt(row, col);
    $("find").value = "";
    render(true);
  });
  if (S.pt) pin.setLngLat([-180 + 0.1 * S.pt.col, 90 - 0.1 * S.pt.row]).addTo(map);
  window.__heat = {map, S, timing};
  // country lines and names, for orientation only; loaded after the first screen is up
  async function addOutlines() {
    if (!files["static/countries.json"]) return;
    const c = await files["static/countries.json"].json();
    map.addSource("countries", {type: "geojson", data: {type: "Feature", properties: {}, geometry: c.lines}});
    map.addLayer({id: "countries", type: "line", source: "countries", paint: {"line-color": "#3f3e3a", "line-opacity": 0.55, "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.4, 5, 1]}}, "sel-halo");
    if (files["static/coast.json"]) {
      const co = await files["static/coast.json"].json();
      map.addSource("coast", {type: "geojson", data: {type: "Feature", properties: {}, geometry: co.lines}});
      map.addLayer({id: "coast", type: "line", source: "coast", paint: {"line-color": "#3f3e3a", "line-opacity": 0.7, "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.4, 5, 1]}}, "countries");
    }
    let provAsked = false;                                                    // province borders are fetched the first time the map is zoomed in far enough to show them
    const provinces = async () => {
      if (provAsked || map.getZoom() < 3.5 || !files["static/provinces.json"]) return;
      provAsked = true;
      const pr = await files["static/provinces.json"].json();
      map.addSource("provinces", {type: "geojson", data: {type: "Feature", properties: {}, geometry: pr.lines}});
      map.addLayer({id: "provinces", type: "line", source: "provinces", minzoom: 3.5, paint: {"line-color": "#52514e", "line-opacity": 0.5, "line-width": ["interpolate", ["linear"], ["zoom"], 3.5, 0.3, 7, 0.9]}}, "countries");
    };
    map.on("zoomend", provinces);
    provinces();
    const marks = c.labels.filter((l) => l.name && l.name !== "None" && l.name !== "nan").map((l) => ({rank: l.rank, on: false, m: new maplibregl.Marker({element: el(`<div class="cname">${l.name.replace(/</g, "&lt;")}</div>`)}).setLngLat([l.lon, l.lat])}));
    const show = () => {
      const z = map.getZoom(), n = z < 1.6 ? 8 : z < 2.4 ? 22 : z < 3.2 ? 55 : z < 4 ? 110 : 400, b = map.getBounds();
      for (const k of marks) {
        const want = k.rank <= n && b.contains(k.m.getLngLat());
        if (want && !k.on) k.m.addTo(map); else if (!want && k.on) k.m.remove();
        k.on = want;
      }
    };
    map.on("moveend", show);
    show();
  }

  // ---------- what is selected, and its numbers on the chosen date
  async function unitData() {
    if (!S.sel) return null;
    const t = curT(), a0 = S.sel.adm0;
    if (!files[`admin/${admins.adm0[a0].id}.bin`])             // below the cell floor: the build has no area shares for this country
      return {t, a0, shown: null, story: null, note: `${nameOf("adm0", a0)} has fewer than ${man.settings.cell_floor} grid cells, so it has no area share. The reading for the clicked point is below.`};
    const cf = await country(a0), ev = await events(a0);
    const ar = t < T - cf.head.trailing ? await countryArch(a0) : null;       // a past event's day: its numbers are in the past-events file
    const pick = (level, row) => {
      const u = cf.head.units.findIndex((q) => q.level === level && q.row === row);
      if (u < 0) return null;
      const e = ev.units.find((q) => q.level === level && q.row === row), tr = cf.head.trailing, ts = t - (T - tr);
      const ua = ar ? ar.head.units.findIndex((q) => q.level === level && q.row === row) : -1, na = ar ? ar.head.days.length : 0;
      const nu = cf.head.units.length, dnN = cf.arr.daynight ? cf.arr.daynight.length / (nu * 4) : 0, huN = cf.arr.humid ? cf.arr.humid.length / nu : 0;
      // value on day q: from the trailing arrays of the main file, else from the past-events file, else undefined
      const get = (main, n, per, arc, q, c = 0) => {
        const i = q - (T - n);
        if (main && i >= 0 && i < n) return main[u * per * n + c * n + i];
        const j = ua >= 0 ? ar.pos.get(q) : undefined;
        return j === undefined || !arc ? undefined : arc[ua * per * na + c * na + j];
      };
      const sevAt = (q) => get(cf.arr.severe, tr, 1, ar && ar.arr.severe, q), extAt = (q) => get(cf.arr.extreme, tr, 1, ar && ar.arr.extreme, q);
      const ddAt = (q) => get(cf.arr.degdays, tr, 1, ar && ar.arr.degdays, q), dnAt = (c, q) => get(cf.arr.daynight, dnN, 4, ar && ar.arr.daynight, q, c), huAt = (q) => get(cf.arr.humid, huN, 1, ar && ar.arr.humid, q);
      return {level, row, name: nameOf(level, row), cells: admins[level][row].cells, t,
        spell: cf.arr.spell.subarray(u * T, (u + 1) * T), severe: cf.arr.severe.subarray(u * tr, (u + 1) * tr), extreme: cf.arr.extreme.subarray(u * tr, (u + 1) * tr), tr,
        now: {spell: cf.arr.spell[u * T + t], severe: sevAt(t) ?? 255, extreme: extAt(t) ?? 255}, ev: e, sevAt, extAt, ddAt, dnAt, huAt,
        trend: cf.head.units[u].trend || null, season: cf.arr.season ? Array.from(cf.arr.season.subarray(u * 4, u * 4 + 4)) : null,
        hu: cf.arr.humid ? {share: huAt(t), base: cf.arr.humid_days[u * 2] / 10, rec: cf.arr.humid_days[u * 2 + 1] / 10} : null,
        dn: cf.arr.daynight ? {a: cf.arr.daynight, at: u * 4 * (cf.arr.daynight.length / (cf.head.units.length * 4)), n: cf.arr.daynight.length / (cf.head.units.length * 4)} : null,
        dd: cf.arr.degdays ? cf.arr.degdays.subarray(u * tr, (u + 1) * tr) : null,
        annual: cf.arr.annual_spell ? cf.arr.annual_spell.subarray(u * (cf.arr.annual_spell.length / cf.head.units.length), (u + 1) * (cf.arr.annual_spell.length / cf.head.units.length)) : null};
    };
    const prov = pick("adm1", S.sel.adm1), ctry = pick("adm0", a0);
    let shown = S.level === "adm0" ? ctry : prov, note = "", dist = null, dlist = null;
    if (S.level === "adm2") {
      const df = await districts(a0);
      dlist = df ? df.head.units.filter((q) => q.adm1 === S.sel.adm1).map((q) => ({row: q.row, name: q.name || "Unnamed district"})).sort((a, b) => a.name.localeCompare(b.name)) : [];
      if (S.want2 && df) { const w = df.head.units.find((q) => q.id === S.want2); if (w) S.sel.adm2 = w.row; S.want2 = null; }   // district named in the link
      const u = df && S.sel.adm2 >= 0 ? df.head.units.findIndex((q) => q.row === S.sel.adm2) : -1;
      if (u >= 0) {
        const n = df.head.trailing, k = t - (T - n), dname = df.head.units[u].name || `Unnamed district in ${nameOf("adm1", S.sel.adm1)}`;
        if (k >= 0 && k < n) dist = {level: "adm2", id: df.head.units[u].id, name: dname, cells: df.head.units[u].cells, now: {spell: df.arr.spell[u * n + k], severe: df.arr.severe[u * n + k], extreme: df.arr.extreme[u * n + k]},
          spark: Array.from(df.arr.spell.subarray(u * n, u * n + k + 1)).slice(-60), sparkSev: Array.from(df.arr.severe.subarray(u * n, u * n + k + 1)).slice(-60)};
        else {                                                                // a day outside the district file: count the district's cells on that day's map
          const code = await daily(t), arr2 = cell.adm2, id2 = S.sel.adm2;
          let w0 = 0, w1 = 0, w2 = 0, w3 = 0;
          for (let i = 0; i < N; i++) if (arr2[i] === id2) {
            const raw = code[i];
            if (raw === 255) continue;
            const w = Math.cos((90 - 0.1 * Math.floor(i / NC)) * Math.PI / 180), c = raw & 3;
            w0 += w; if (c >= 1) w1 += w; if (c >= 2) w2 += w; if (c === 3) w3 += w;
          }
          const pc = (v) => w0 ? Math.floor(100 * v / w0 + 1e-9) : 255;
          dist = {level: "adm2", id: df.head.units[u].id, name: dname, cells: df.head.units[u].cells, now: {spell: pc(w1), severe: pc(w2), extreme: pc(w3)}, spark: null, sparkSev: null};
        }
      } else note = S.sel.adm2 < 0 ? "No district is chosen yet: click the map inside one. Showing the province." : `This district has fewer than ${man.settings.cell_floor} grid cells, so it has no area share of its own. Showing ${prov ? "its province" : "its country"}.`;
    }
    if (!shown && S.level !== "adm2") note = `This unit has fewer than ${man.settings.cell_floor} grid cells, so it has no area share of its own.`;
    return {t, prov, ctry, dist, shown: dist || shown || prov || ctry, story: (S.level === "adm0" ? ctry : prov) || ctry, note, a0, dlist};
  }
  const trustCache = new Map();
  function trust(level, row) {                                               // percent of the unit's land area: low confidence, reduced, data suspect
    const key = level + row;
    if (!trustCache.has(key)) {
      const arr = cell[level];
      let n = 0, low = 0, red = 0, sus = 0;
      for (let i = 0; i < N; i++) if (arr[i] === row) { const w = Math.cos((90 - 0.1 * Math.floor(i / NC)) * Math.PI / 180), m = mask[i]; n += w; if (m & 1) low += w; if (m & 2) red += w; if (m & 4) sus += w; }
      const p = (v) => n ? Math.round(100 * v / n) : 0;
      trustCache.set(key, {low: p(low), red: p(red), sus: p(sus)});
    }
    return trustCache.get(key);
  }
  // the caveat that must open any sentence about a unit that is mostly low confidence, or a quarter or more data suspect
  // where the evidence behind each caution is written up: sections of docs/agera5-vs-stations.md in the repository
  const DOC = "https://github.com/bennyistanto/heat-explorer/blob/main/docs/agera5-vs-stations.md";
  const EVID = {low: "#6-fourth-finding-near-the-equator-agera5-loses-the-day-to-day-signal", rule: "#7-fifth-finding-the-skill-can-be-predicted-without-any-station",
    sus: "#9a-the-first-such-check-three-patches-of-sudden-recent-warmth", humid: "#5-third-finding-the-humid-heat-peak-is-missed-for-two-different-reasons"};
  const evid = (k, words) => `<a href="${DOC}${EVID[k]}" target="_blank" rel="noopener">${words}</a>`;
  const caveat = (tr) => (tr.low > 50 ? "Low confidence: the signal is weak in this climate. " : "") + (tr.sus >= 25 ? `A known break in the source data affects ${tr.sus}% of this area. ` : "");
  const tierOf = (sev) => sev === 255 ? -1 : sev >= 50 ? 2 : sev >= 25 ? 1 : 0;
  function eventAt(u, t) {
    if (!u || !u.ev) return null;
    const e = u.ev, i = e.start.findIndex((s, j) => s <= t && t <= s + e.days[j] - 1);
    if (i < 0) return {n: e.start.length};
    const r = {n: e.start.length, i, start: e.start[i], days: e.days[i], day: t - e.start[i] + 1, size: e.size[i], peak: e.peak[i], rank: 1 + e.size.filter((s) => s > e.size[i]).length,
      open: !!e.open && i === e.start.length - 1, whole: t < e.start[i] + e.days[i] - 1};   // open: may still grow; its size and length are as of the last date
    if (u.ddAt && (r.open || r.whole)) {                                      // the chosen date is inside the event: its size up to that date, if every day since its start is published
      let sz = 0, pk = 0, all = true;
      const path = [];
      for (let q = r.start; q <= t; q++) {
        const v = u.ddAt(q);
        if (v === undefined) { all = false; break; }
        sz += v / 1000; pk = Math.max(pk, u.spell[q]); path.push({days: q - r.start + 1, peak: pk / 100, size: Math.round(sz * 100) / 100});
      }
      if (all) { r.path = path; r.sizeTo = Math.round(sz * 100) / 100; r.rankTo = 1 + e.size.filter((v, j) => j !== i && v > r.sizeTo).length; }
    }
    return r;
  }
  // how the rank of the event on the chosen date is put into words, in one place
  function eventWords(e, t) {
    if (e.rankTo !== undefined) {
      const after = e.open ? "it was still running on the last day of data" : `the whole event went on to rank ${ordinal(e.rank)}`;
      return {rank: e.rankTo, k4: `largest event here since 1979, by its size up to ${fmt(t)}; ${after}`,
        tail: ` It was day ${e.day} of an event that ranked ${ordinal(e.rankTo)} of ${e.n} here since 1979 by its size up to that date; ${after}.`,
        lead: `this is day ${e.day}. By its size up to this date (${e.sizeTo.toFixed(1)} degree-days) it ranks ${ordinal(e.rankTo)} among ${e.n} events here since 1979; ${after}.`};
    }
    if (e.open) return {rank: e.rank, k4: `largest event here since 1979, so far: still running, size as of ${fmt(T - 1)}`,
      tail: ` It was day ${e.day} of an event that is still running and so far ranks ${ordinal(e.rank)} of ${e.n} here since 1979 (size as of ${fmt(T - 1)}).`,
      lead: `this is day ${e.day} of an event that was still running on ${fmt(T - 1)}, the last day of data. By its size so far it ranks ${ordinal(e.rank)} among ${e.n} events here since 1979; that rank uses its size on ${fmt(T - 1)}, not on the chosen date.`};
    return {rank: e.rank, k4: "largest event here since 1979" + (e.whole ? ", counting the whole event" : ""),
      tail: ` It was day ${e.day} of an event that ranks ${ordinal(e.rank)} of ${e.n} here since 1979${e.whole ? ", counting the whole event" : ""}.`,
      lead: `this is day ${e.day} of ${e.days} days. By size it ranks ${ordinal(e.rank)} among ${e.n} events here since 1979${e.whole ? ", counting the whole event" : ""}.`};
  }
  async function hereReading() {
    if (!S.pt) return null;
    const code = await daily(curT());
    let land = 0, spell = 0, sev = 0;
    for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
      const r = S.pt.row + dr, c = (S.pt.col + dc + NC) % NC;
      if (r < 0 || r >= NR) continue;
      const raw = code[r * NC + c], v = raw === 255 ? 4 : raw & 3;
      if (v !== 4) { land++; if (v >= 1) spell++; if (v >= 2) sev++; }
    }
    return {land, spell, sev, severe: land > 0 && sev > land / 2, m: mask[S.pt.row * NC + S.pt.col], centre: code[S.pt.row * NC + S.pt.col] === 255 ? 4 : code[S.pt.row * NC + S.pt.col] & 3, run: code[S.pt.row * NC + S.pt.col] === 255 ? 0 : code[S.pt.row * NC + S.pt.col] >> 2};
  }

  // ---------- first screen
  function spark(vals, sev, t0) {
    const W = 320, Hh = 86, p = {l: 2, r: 2, t: 6, b: 16}, n = vals.length;
    const x = (i) => p.l + i * (W - p.l - p.r) / Math.max(1, n - 1), y = (v) => p.t + (1 - v / 100) * (Hh - p.t - p.b);
    const line = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const svg = $("spark");
    svg.innerHTML = `<line x1="${p.l}" x2="${W - p.r}" y1="${y(0)}" y2="${y(0)}" stroke="#c3c2b7" vector-effect="non-scaling-stroke"/>
      <line x1="${p.l}" x2="${W - p.r}" y1="${y(100)}" y2="${y(100)}" stroke="#e1e0d9" stroke-dasharray="2 3" vector-effect="non-scaling-stroke"/>
      <path d="${line}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z" fill="#d9783c" opacity="0.18"/><path d="${line}" fill="none" stroke="#b24d1c" stroke-width="2" vector-effect="non-scaling-stroke"/>
      <line id="cross" y1="${p.t}" y2="${y(0)}" stroke="#52514e" vector-effect="non-scaling-stroke" style="display:none"/>
      <text x="${p.l}" y="${Hh - 3}" font-size="10" fill="#898781">${fmt(t0)}</text><text x="${W - p.r}" y="${Hh - 3}" font-size="10" fill="#898781" text-anchor="end">${fmt(t0 + n - 1)}</text>
      <text x="${W - p.r}" y="${y(100) - 2}" font-size="10" fill="#898781" text-anchor="end">100%</text>`;
    const tip = $("tip"), cross = svg.querySelector("#cross");
    svg.onmousemove = (e) => {
      const r = svg.getBoundingClientRect(), i = Math.max(0, Math.min(n - 1, Math.round((e.clientX - r.left) / r.width * (n - 1))));
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.style.display = "";
      tip.style.display = "block"; tip.style.left = (x(i) / W * r.width) + "px"; tip.style.top = (y(vals[i]) / Hh * r.height) + "px";
      tip.textContent = `${fmt(t0 + i)}: ${vals[i]}% of land area in a heat spell` + (sev ? `, ${sev[i]}% severe or extreme` : "");
    };
    svg.onmouseleave = () => { tip.style.display = "none"; cross.style.display = "none"; };
  }
  async function renderPanel(d, my) {
    const t = curT();
    $("hdate").textContent = `${fmt(0)} to ${fmt(T - 1)}`;
    const yrl = isYear() ? {title: YEARLY[S.layer].title, capText: YEARLY[S.layer].cap + " or more days", label: String(Y0 + S.y), first: String(Y0)}
      : isMonth() ? {title: MONTHLY[S.layer].title, capText: MONTHLY[S.layer].cap, label: monthName(S.m), first: monthName(0)} : null, hum = S.layer === "humid";
    const fx = isFixed();
    $("sdate").textContent = S.layer === "trend" ? `${Y0} to ${Y0 + NY - 1}` : S.layer === "season" ? `12 weeks to ${fmt(T - 1)}` : yrl ? yrl.label : fmt(t);
    $("sfirst").textContent = fx ? "" : yrl ? yrl.first : fmt(PERIODS[S.p].days[0]);
    $("period").style.display = yrl || fx ? "none" : "";
    $("slider").disabled = fx;
    $("layernote").textContent = fx ? `This map does not change with the slider. The panel beside it describes ${fmt(t)}.` : yrl ? `The map shows ${yrl.label}. The panel beside it describes ${fmt(t)}.` : "";
    $("layernote").style.display = yrl || fx ? "" : "none";
    $("leg-trend").style.display = S.layer === "trend" ? "" : "none"; $("leg-season").style.display = S.layer === "season" ? "" : "none";
    $("leg-daily").style.display = yrl || hum || fx ? "none" : ""; $("leg-yearly").style.display = yrl ? "" : "none"; $("leg-humid").style.display = hum ? "" : "none";
    $("leg-conf").textContent = hum ? "Low confidence for this layer: its own signal is weak here" : "Low confidence: weak signal here";
    if (yrl) { $("leg-title").textContent = yrl.title; $("leg-cap").textContent = yrl.capText; } else $("leg-title").textContent = hum ? "Humid heat spell (experimental)" : S.layer === "trend" ? `Trend in heat spell days, ${Y0} to ${Y0 + NY - 1}` : S.layer === "season" ? "Season status" : "Heat spell severity";
    document.querySelectorAll("#levels button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.level === S.level)));
    const here = await hereReading();
    if (my !== undefined && my !== token) return;
    $("slider").setAttribute("aria-valuetext", yrl ? yrl.label : fmt(t));
    const dp = $("dpick"), ds = $("dsel");                                    // districts of the selected province, so one can be chosen without a mouse
    dp.style.display = d && d.dlist && d.dlist.length ? "" : "none";
    if (d && d.dlist && ds.dataset.for !== String(S.sel.adm1)) {
      ds.dataset.for = String(S.sel.adm1);
      ds.innerHTML = `<option value="">Choose a district</option>` + d.dlist.map((q) => `<option value="${q.row}">${esc(q.name)}</option>`).join("");
    }
    if (d && d.dlist) ds.value = S.sel.adm2 >= 0 && d.dlist.some((q) => q.row === S.sel.adm2) ? String(S.sel.adm2) : "";
    $("pinname").textContent = d && d.shown ? d.shown.name : "No place selected"; $("pindate").textContent = "on " + fmt(t) + ", data to " + fmt(T - 1);
    $("hname").textContent = S.pt ? `${Math.abs(S.pt.lat).toFixed(2)}° ${S.pt.lat >= 0 ? "N" : "S"}, ${Math.abs(S.pt.lon).toFixed(2)}° ${S.pt.lon >= 0 ? "E" : "W"}` : "no point chosen";
    if (!here) { $("hstatus").textContent = "Click the map for a reading at a point"; $("hchip").style.background = C.land; $("hdetail").textContent = ""; }
    else if (!here.land) { $("hstatus").textContent = "No land here"; $("hchip").style.background = C.land; $("hdetail").textContent = ""; }
    else {
      const inSpell = here.spell > here.land / 2;
      $("hstatus").textContent = here.severe ? "Severe heat here" : inSpell ? "In a heat spell here" : "No heat spell here";
      $("hchip").style.background = here.severe ? C.severe : inSpell ? C.spell : C.land;
      $("hdetail").textContent = `${here.sev} of the ${here.land} grid cells around this point are severe or extreme and ${here.spell} are in a heat spell. The cell under the marker is ${["not in a heat spell", "in a heat spell", "severe", "extreme", "sea"][here.centre]}` +
        (here.centre >= 1 && here.centre <= 3 ? `, on day ${here.run}${here.run >= 62 ? " or more" : ""} of its heat spell.` : ".") +
        ((here.m & 1) ? " Low confidence: the signal is weak in this climate." : "") + ((here.m & 4) ? " Data suspect: a known break in the source data." : "");
    }
    if (!d || !d.shown) {
      $("plvl").textContent = d ? "Country" : ""; $("pname").textContent = d ? nameOf("adm0", d.a0) : S.msg ? "No place selected" : "Click the map to choose a place"; $("pparent").textContent = "";
      $("pstatus").textContent = d ? "No area share for this place" : ""; $("pchip").style.background = C.land; $("pcaveat").style.display = "none";
      for (const id of ["n1", "n2", "n3", "n4", "k3", "k4", "pcells"]) $(id).textContent = "";
      $("phumid").style.display = "none";
      const note = d ? d.note : S.msg;
      $("spark").innerHTML = ""; $("pnote").textContent = note; $("pnote").style.display = note ? "" : "none"; $("sentence").textContent = note;
      return;
    }
    const u = d.shown, parentName = u.level === "adm0" ? "" : u.level === "adm1" ? nameOf("adm0", d.a0) : `${nameOf("adm1", S.sel.adm1)}, ${nameOf("adm0", d.a0)}`;
    $("plvl").textContent = LEVELS[u.level];
    $("pname").textContent = u.name;
    $("pparent").textContent = parentName;
    const tier = tierOf(u.now.severe), nm = u.name || "this area";
    const tr = trust(u.level, u.level === "adm2" ? S.sel.adm2 : u.row), cav = caveat(tr);
    $("pstatus").textContent = (tier < 0 ? "No value" : TIERS[tier]) + " on " + fmt(t);
    $("pcaveat").textContent = tr.low || tr.red || tr.sus ? `${tr.low}% of this area is low confidence` + (tr.red ? `, ${tr.red}% reduced confidence` : "") + (tr.sus ? `, ${tr.sus}% data suspect` : "") + "." : "";
    $("pcaveat").style.display = tr.low || tr.red || tr.sus ? "" : "none";
    $("pcaveat").classList.toggle("warn", tr.low > 50 || tr.sus >= 25);
    const hu = u.hu;                                                          // experimental line: never part of the status or the sentence
    $("phumid").style.display = hu ? "" : "none";
    if (hu) $("phumid").textContent = `Humid heat spell (experimental): ${hu.share === undefined ? "not published for" : hu.share + "% of land area on"} ${fmt(t)}. Humid spell days a year here: ${hu.base.toFixed(0)} in 1991 to 2020, ${hu.rec.toFixed(0)} in 2021 to 2025.`;
    $("pchip").style.background = [C.land, C.severe, C.extreme][Math.max(0, tier)];
    $("n1").innerHTML = u.now.spell + "<small>%</small>";
    $("n2").innerHTML = u.now.severe + "<small>%</small>";
    const e = u.level === "adm2" ? null : eventAt(u, t);
    if (e && e.i !== undefined) {
      $("n3").innerHTML = "Day " + e.day;
      $("k3").textContent = "of an event that began " + fmt(e.start);
      const ew = eventWords(e, t);
      $("n4").innerHTML = ordinal(ew.rank) + "<small> of " + e.n + "</small>";
      $("k4").textContent = ew.k4;
    } else {
      $("n3").innerHTML = e ? "None" : "n/a"; $("k3").textContent = e ? "no event on this date" : "events are not computed for districts";
      $("n4").innerHTML = e ? e.n : "n/a"; $("k4").textContent = e ? "events here since 1979" : "";
    }
    if (u.level === "adm2") { if (u.spark) spark(u.spark, u.sparkSev, t - u.spark.length + 1); else $("spark").innerHTML = `<text x="2" y="40" font-size="11" fill="#6b6963">No 60-day line for a district on this date.</text>`; }
    else {
      const n = Math.min(60, t + 1), sv = [];
      for (let q = t - n + 1; q <= t; q++) sv.push(u.sevAt(q));
      spark(Array.from(u.spell.subarray(t - n + 1, t + 1)), sv.some((v) => v === undefined) ? null : sv, t - n + 1);
    }
    $("pnote").textContent = d.note;
    $("pnote").style.display = d.note ? "" : "none";
    const lic0 = S.sel.adm1 >= 0 ? admins.adm1[S.sel.adm1].licence : "", checked = (man.boundaries.source_licences_checked_by_owner || {})[admins.adm0[d.a0].name];
    const lic = lic0.startsWith("Other") && checked ? checked : lic0;
    $("pcells").textContent = u.cells.toLocaleString("en-GB") + " grid cells of about 10 km." + (lic ? ` Boundary source licence: ${lic}.` : "");
    const ev = e && e.i !== undefined ? eventWords(e, t).tail : "";
    $("sentence").textContent = `${cav}On ${fmt(t)}, ${u.now.spell}% of ${nm}'s land area was in a heat spell, and ${u.now.severe}% of its land area was severe or extreme.${ev}`;
  }

  // ---------- story
  const story = $("story");
  const section = (title, lead) => { const s = el(`<section><h2>${title}</h2><p class="lead">${lead}</p></section>`); story.append(s); return s; };
  const block = (s, title, how) => { s.append(el(`<h3>${title}</h3>`)); if (how) s.append(el(`<p class="how"><b>How to read this.</b> ${how}</p>`)); };
  // Each titled block of the story becomes: the words before its chart, the chart, the words after it.
  // On a wide screen the stylesheet puts the chart on the left and the words beside it; on a narrow one they stay in reading order.
  const isFig = (n) => n.matches("svg, figure, canvas, table, .frames");
  const twoCol = () => {
    for (const sec of story.querySelectorAll("section")) {
      const kids = [...sec.children], groups = [];
      for (const n of kids) { if (n.tagName === "H3") groups.push([n]); else if (groups.length) groups[groups.length - 1].push(n); }
      for (const g of groups) {
        const at = g.findIndex(isFig);
        if (at < 0) continue;                                                 // words only: left as it is
        let last = at; for (let n = at; n < g.length; n++) if (isFig(g[n])) last = n;
        const blk = el(`<div class="blk"><div class="side top"></div><div class="fig"></div><div class="side bot"></div></div>`);
        g[0].before(blk);
        g.forEach((n, i) => blk.children[i < at ? 0 : i <= last ? 1 : 2].append(n));
        if (!blk.children[2].children.length) blk.children[2].remove();
      }
    }
  };
  const key = (items) => el(`<div class="key">${items.map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`).join("")}</div>`);
  const po = {style: {fontSize: "12px", fontFamily: "inherit", background: "transparent"}, marginLeft: 44, marginBottom: 30};
  function renderStory(d) {
    story.innerHTML = "";
    if (!d || !d.story) return;
    const u = d.story, t = d.t, W = Math.min(1100, story.clientWidth || 1000), D = (tt) => new Date(EPOCH + tt * DAY);
    const tr = trust(u.level, u.row), cav = caveat(tr), nm = esc(u.name || "this area");
    if (cav) story.append(el(`<p class="ph warn"><b>Read with care.</b> ${cav}This applies to every chart and number below. ${[tr.low > 50 ? evid("low", "Why the signal is weak here: the comparison with weather stations") : "", tr.sus >= 25 ? evid("sus", "How the break was found") : ""].filter(Boolean).join(". ")}.</p>`));
    if (d.dist || (S.level === "adm2")) story.append(el(`<p class="ph">The sections below are for ${nm}, the ${LEVELS[u.level].toLowerCase()} this district belongs to. Full histories are not published for districts.</p>`));
    { // 1
      const s = section("How much of it was in heat on the chosen date?", `${cav}On ${fmt(t)}, ${u.now.spell}% of ${nm}'s land area was in a heat spell: ${u.now.extreme}% of the land area extreme, ${u.now.severe - u.now.extreme}% severe and ${u.now.spell - u.now.severe}% in the lowest class.`);
      block(s, "Share of land area in a heat spell, by class, last 90 days", "Each day's column adds up to the share of land in a heat spell. Darker is more severe. A day's class describes that day only and does not change afterwards.");
      s.append(key([[C.extreme, "Extreme"], [C.severe, "Severe"], [C.spell, "Heat spell"]]));
      const rows = [], tips = [];
      let unknown = false;
      for (let q = Math.max(0, t - 89); q <= t; q++) {
        const sp = u.spell[q], sv = u.sevAt(q), ex = u.extAt(q);
        if (sv === undefined || ex === undefined) {                           // the split by class is published for the last year and the days of the listed events
          unknown = true;
          rows.push({date: D(q), cls: "unknown", v: sp / 100});
          tips.push({date: D(q), top: sp / 100, t: `${fmt(q)}\nIn a heat spell ${sp}%\n(class not published for this day)`});
          continue;
        }
        rows.push({date: D(q), cls: "spell", v: (sp - sv) / 100}, {date: D(q), cls: "severe", v: (sv - ex) / 100}, {date: D(q), cls: "extreme", v: ex / 100});
        tips.push({date: D(q), top: sp / 100, t: `${fmt(q)}\nExtreme ${ex}%\nSevere ${sv - ex}%\nHeat spell ${sp - sv}%`});
      }
      if (unknown) s.append(key([["#cfcdc4", "In a heat spell, class not published for that day"]]));
      s.append(Plot.plot({...po, ariaLabel: `Stacked columns: share of land area in a heat spell by class, each day of the 90 days to ${fmt(t)}`, width: W, height: 220, y: {label: "share of land area", tickFormat: "%", domain: [0, 1], grid: true}, x: {label: null},
        color: {domain: ["spell", "severe", "extreme", "unknown"], range: [C.spell, C.severe, C.extreme, "#cfcdc4"]},
        marks: [Plot.rectY(rows, {x: "date", y: "v", fill: "cls", interval: "day", order: ["extreme", "severe", "spell", "unknown"], insetLeft: 0.5, insetRight: 0.5}), Plot.ruleY([0], {stroke: "#c3c2b7"}),
          Plot.tip(tips, Plot.pointerX({x: "date", y: "top", title: "t"}))]}));
      if (u.dn && u.dnAt(0, t) !== undefined) {
        const DNC = {night: "#2a78d6", day: "#eb6834", both: "#1baf7a", off: "#cfcdc4"}, r2 = [], tip2 = [];
        for (let q = Math.max(0, t - 89); q <= t; q++) {
          const dy = u.dnAt(0, q), ni = u.dnAt(1, q), bo = u.dnAt(2, q), of = u.dnAt(3, q);
          if (dy === undefined) continue;                                     // published for the last year and the days of the listed events
          r2.push({date: D(q), cls: "both", v: bo / 100}, {date: D(q), cls: "day", v: dy / 100}, {date: D(q), cls: "night", v: ni / 100}, {date: D(q), cls: "off", v: of / 100});
          tip2.push({date: D(q), top: (bo + dy + ni + of) / 100, t: `${fmt(q)}\nDay and night ${bo}%\nDay only ${dy}%\nNight only ${ni}%\nOutside the warm season ${of}%`});
        }
        block(s, "Hot days and hot nights, last 90 days", "A day counts as hot when the maximum is above its usual top tenth for the date, a night when the minimum is. \"Both\" means no relief at night. The classes never overlap, so a column is the share of land area that was hot by day, by night, or both. Grey is land that was hot for the date but outside its own warm half of the year: shown, not counted as heat. This is this project's own measure and has not been tested on documented events.");
        s.append(key([[DNC.night, "Hot night only"], [DNC.day, "Hot day only"], [DNC.both, "Hot day and hot night"], [DNC.off, "Outside the warm season"]]));
        s.append(Plot.plot({...po, ariaLabel: `Stacked columns: share of land area hot by day, by night, or both, each day of the 90 days to ${fmt(t)}`, width: W, height: 200,
          y: {label: "share of land area", tickFormat: "%", domain: [0, 1], grid: true}, x: {label: null}, color: {domain: ["night", "day", "both", "off"], range: [DNC.night, DNC.day, DNC.both, DNC.off]},
          marks: [Plot.rectY(r2, {x: "date", y: "v", fill: "cls", interval: "day", order: ["both", "day", "night", "off"], insetLeft: 0.5, insetRight: 0.5}), Plot.ruleY([0], {stroke: "#c3c2b7"}),
            Plot.tip(tip2, Plot.pointerX({x: "date", y: "top", title: "t"}))]}));
      }
      if (u.hu && u.hu.share !== undefined) {
        block(s, "Humid heat (experimental)");
        s.append(el(`<p>On ${fmt(t)}, ${u.hu.share}% of ${nm}'s land area was in a humid heat spell: three or more days in a row when heat and humidity together were unusual for the date. This is a yes or no reading, with no severity.</p>`));
        s.append(el(`<p class="ph warn"><b>Experimental.</b> Humid heat here is judged against 1991 to 2020. The humidity record in the source data drifts, so recent years are flagged far more often than the past for reasons that are partly not climate. Here it was flagged on ${u.hu.base.toFixed(0)} days a year in 1991 to 2020 and on ${u.hu.rec.toFixed(0)} days a year in 2021 to 2025, averaged over the land area. It takes no part in the status, the events, the ranks or the trend on this page, and it is not a wet-bulb reading: the source data is too low in absolute humid heat to give one. Evidence: ${evid("humid", "humid heat against weather stations")}.</p>`));
      }
      s.append(el(`<p class="ph">${u.dn ? "" : "Hot days against hot nights are not in this build. "}${u.hu ? "" : "Humid heat is not in this build."}</p>`));
    }
    const e = u.ev, cur = eventAt(u, t), evs = e.start.map((st, i) => ({start: st, days: e.days[i], peak: e.peak[i] / 100, size: e.size[i], cur: cur && cur.i === i}));
    { // 2
      const lead = cur && cur.i !== undefined
        ? `${cav}The event on this date began on ${fmt(cur.start)}; ${eventWords(cur, t).lead}`
        : `${nm} is not in an event on this date. It has ${e.start.length} events on record since 1979.`;
      const s = section("Is it lasting, and for how long?", lead);
      block(s, "Every event on record", "Each dot is one event: how long it lasted (across) and the largest share of land it covered (up). Bigger dots were larger in degree-days; darker dots are more recent. The event on the chosen date, if there is one, is ringed and labelled; when that date is inside the event, a line shows how it grew day by day up to then. An event needs at least a quarter of the land area in a heat spell, so no dot sits below 25%.");
      const decs = ["1970s", "1980s", "1990s", "2000s", "2010s", "2020s"], greys = ["#e3e1da", "#cfcdc4", "#b3b1a8", "#8f8d85", "#6a6862", "#3f3e3a"];
      s.append(el(`<div class="key">${decs.map((q, i) => `<span><i style="background:${greys[i]};border-radius:50%"></i>${q}</span>`).join("")}<span><i style="background:${C.extreme};border-radius:50%;outline:2px solid #0b0b0b;outline-offset:1px"></i>Event on the chosen date (ringed)</span></div>`));
      const mid = !!(cur && cur.path), curPts = mid ? [cur.path[cur.path.length - 1]] : evs.filter((q) => q.cur);   // mid: the chosen date is inside the event
      const pts = evs.map((q) => ({...q, decade: Math.floor(D(q.start).getUTCFullYear() / 10) * 10 + "s"}));
      s.append(Plot.plot({...po, ariaLabel: `Scatter of ${evs.length} events: duration against the largest share of land area covered`, width: W, height: 380, marginRight: 60,
        x: {type: "log", label: "duration, days", tickFormat: (q) => q, grid: true}, y: {label: "largest share of land area covered", tickFormat: "%", domain: [0.2, 1.02], grid: true},
        r: {range: [2.5, 16], domain: [0, Math.max(1, ...pts.map((q) => q.size))]}, color: {domain: decs, range: greys},
        marks: [Plot.dot(pts.filter((q) => !q.cur || (mid && !cur.open)), {x: "days", y: "peak", r: "size", fill: "decade", stroke: "#fff", strokeWidth: 1, fillOpacity: 0.9}),
          ...(mid ? [Plot.line(cur.path, {x: "days", y: "peak", stroke: C.extreme, strokeWidth: 2})] : []),
          Plot.dot(curPts, {x: "days", y: "peak", r: "size", fill: mid || (cur && cur.open) ? "#fff" : C.extreme, stroke: "#0b0b0b", strokeWidth: 2.5}),
          Plot.text(curPts, {x: "days", y: "peak", text: () => mid ? `this event on ${fmt(t, false)}` : cur && cur.open ? "this event, still running" : "this event", dy: -20, fontWeight: 600, fill: "#0b0b0b", stroke: "#fff", strokeWidth: 3}),
          Plot.tip(pts, Plot.pointer({x: "days", y: "peak", title: (q) => `${fmt(q.start)} to ${fmt(q.start + q.days - 1)}\n${q.days} days, peak ${Math.round(q.peak * 100)}% of land\nsize ${q.size} degree-days`}))]}));
    }
    { // 3
      const s = section("Has it happened before?", `The table lists the largest events at ${u.name}; the picture shows every day since 1979.`);
      block(s, "Every day since 1979", "One row per year, one column per calendar date, up to the chosen date. Darker means more of the land was in a heat spell that day. 29 February is left out so that every date lines up between years.");
      s.append(el(`<div class="key"><span>0%</span><span class="ramp" style="background:linear-gradient(90deg,#efede7,#f0be8c,#d9783c,#74290c)"></span><span>100% of land area in a heat spell</span><span><i style="background:repeating-linear-gradient(135deg,#fbfaf7 0 3px,#bdbbb2 3px 4px)"></i>after the chosen date</span></div>`));
      const y0 = 1979, ny = D(t).getUTCFullYear() - y0 + 1, ch = 14, cw = (1100 - 70) / 365, cm = document.createElement("canvas");
      cm.width = 1100; cm.height = ny * ch + 40; cm.className = "matrix";
      cm.setAttribute("role", "img"); cm.setAttribute("aria-label", `Grid of every day from 1979 to ${fmt(t)}, one row per year, shaded by the share of ${u.name}'s land area in a heat spell`);
      s.append(cm);                                                        // in the page before drawing, so text can resolve its font
      const g = cm.getContext("2d");
      const stops = [[239, 237, 231], [240, 190, 140], [217, 120, 60], [116, 41, 12]];
      const col = (v) => { const q = Math.min(v / 100, 1) * 3, i = Math.min(Math.floor(q), 2), f = q - i; return `rgb(${stops[i].map((a, k) => Math.round(a + (stops[i + 1][k] - a) * f)).join(",")})`; };
      const cellOf = new Map();
      for (let q = 0; q <= t; q++) {
        const dt = D(q), yy = dt.getUTCFullYear(), y = yy - y0, leap = (yy % 4 === 0 && yy % 100 !== 0) || yy % 400 === 0;
        let doy = Math.round((Date.UTC(yy, dt.getUTCMonth(), dt.getUTCDate()) - Date.UTC(yy, 0, 1)) / DAY);
        if (leap && doy === 59) continue;                                     // 29 February has no column of its own
        if (leap && doy > 59) doy--;
        g.fillStyle = col(u.spell[q]); g.fillRect(60 + doy * cw, 26 + y * ch, cw + 0.5, ch - 1);
        cellOf.set(y * 400 + doy, q);
        if (q === t && doy < 364) {                                           // the rest of the last year has not happened yet on the chosen date
          const pc = document.createElement("canvas"); pc.width = pc.height = 6;
          const pg = pc.getContext("2d"); pg.fillStyle = "#fbfaf7"; pg.fillRect(0, 0, 6, 6); pg.strokeStyle = "#bdbbb2"; pg.beginPath(); pg.moveTo(0, 6); pg.lineTo(6, 0); pg.stroke();
          g.fillStyle = g.createPattern(pc, "repeat"); g.fillRect(60 + (doy + 1) * cw, 26 + y * ch, (364 - doy) * cw, ch - 1);
        }
      }
      g.fillStyle = "#52514e"; g.font = "20px system-ui"; g.textBaseline = "middle"; g.textAlign = "right";
      for (let y = 0; y < ny; y += 5) g.fillText(y0 + y, 54, 26 + y * ch + ch / 2);
      g.textAlign = "left"; g.textBaseline = "alphabetic";
      ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].forEach((m, i) => g.fillText(m, 60 + [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334][i] * cw, 18));
      const hov = $("hov");
      cm.onmousemove = (ev) => {
        const b = cm.getBoundingClientRect(), x = (ev.clientX - b.left) / b.width * 1100, yy = (ev.clientY - b.top) / b.height * cm.height, q = cellOf.get(Math.floor((yy - 26) / ch) * 400 + Math.floor((x - 60) / cw));
        if (q === undefined || x < 60) { hov.style.display = "none"; return; }
        hov.textContent = `${fmt(q)}: ${u.spell[q]}% of land in a heat spell`; hov.style.display = "block";
        hov.style.left = Math.min(ev.clientX + 12, innerWidth - hov.offsetWidth - 8) + "px"; hov.style.top = (ev.clientY - 30) + "px";
      };
      cm.onmouseleave = () => { hov.style.display = "none"; };
      block(s, "The largest events on record, by size");
      const ranked = [...evs].sort((a, b) => b.size - a.size), top = ranked.slice(0, 8);
      const rk = (q) => { const n = 1 + evs.filter((z) => z.size > q.size).length; return n + (evs.some((z) => z !== q && z.size === q.size) ? " equal" : ""); };   // the same rule as the first screen
      if (cur && cur.i !== undefined && !top.some((q) => q.cur)) top.push(ranked.find((q) => q.cur));
      s.append(el(`<table class="ev"><thead><tr><th>Rank</th><th>Dates</th><th>Days</th><th>Peak share of land</th><th>Size, degree-days</th></tr></thead><tbody>${top.map((q) =>
        `<tr class="${q.cur ? "cur" : ""}"><td>${rk(q)}</td><td>${fmt(q.start)} to ${fmt(q.start + q.days - 1)}</td><td>${q.days}</td><td>${Math.round(q.peak * 100)}%</td><td>${q.size.toFixed(1)}</td></tr>`).join("")}</tbody></table>`));
      s.append(el(`<p class="how">Size is in degree-days: each day, how many degrees the places in a heat spell are above their heat threshold, averaged over the whole land area, then added up over the event. It is this project's own measure, and it favours summer events.</p>`));
    }
    {
      if (man.weekly && man.weekly.length) {
        const past = S.p !== 0, fl = frameList(), nf = fl.length, evName = PERIODS[S.p].name.split(": ").slice(1).join(": ");
        const se = u.season, seTxt = !past && se && se[0] !== 255 ? ` In the week to ${fmt(T - 1)}, ${se[0]}% of its land area was newly in a heat spell, ${se[1]}% was in one again after a break, ${se[2]}% was still in one from the week before, and ${se[3]}% was no longer in one.` : "";
        const s = section("Where inside it, and is it the same places again?", past
          ? `Week by week, where the heat sat inside ${nm} over the days shown for the past event "${evName}": ${fmt(fl[0].a)} to ${fmt(fl[nf - 1].b)}.`
          : `Week by week, where the heat sat inside ${nm} in the eight weeks to ${fmt(T - 1)}.${seTxt}`);
        if (past) block(s, `Highest class reached in each week of the days shown for this event`, `Each small map is one run of seven days, oldest first, counted back from ${fmt(fl[nf - 1].b)}${fl[0].b - fl[0].a < 6 ? "; the first run is shorter" : ""}. A cell takes the colour of the most severe class it reached in that run. The days shown are the event's listed dates with five days added before and after${PERIODS[S.p].days.length > 56 ? ", and only the last eight weeks of them are drawn" : ""}. These maps follow the event chosen in the Period menu, not the date on the slider.`);
        else block(s, "Highest class reached in each of the last eight weeks", "Each small map is one week, oldest first. A cell takes the colour of the most severe class it reached that week. Read left to right to see where the heat started and how it moved. These weeks end on the last day of data, not on the date chosen with the slider.");
        s.append(key([[C.extreme, "Extreme"], [C.severe, "Severe"], [C.spell, "Heat spell"], [C.land, "Not in a heat spell"], ["#f3f2ee", "Outside this place"]]));
        s.append(el(`<p class="how">Dark lines are country borders; lighter lines are coasts and province borders. They are for orientation: the numbers count grid cells, so a line can cut through a coloured cell.</p>`));
        const wrap = el(`<div class="frames"></div>`);
        s.append(wrap);
        drawWeeks(wrap, cell[u.level], u.row).catch((err) => { console.error(err); weekCache.clear(); evCache.clear(); wrap.append(el(`<p class="ph">The weekly maps could not be loaded.</p>`)); });
      } else {
        const s = section("Where inside it, and is it the same places again?", "Not in this build.");
        s.append(el(`<p class="ph">Week-by-week maps of where the heat sat inside this place are not in this build.</p>`));
      }
    }
    { // 4
      const yr0 = 1979, yrN = man.annual_years[1], ann = [];
      if (u.annual) for (let y = yr0; y <= yrN; y++) ann.push({y, v: u.annual[y - yr0] / 10});
      else for (let y = yr0; y <= yrN; y++) { let a = 0; const q0 = Math.round((Date.UTC(y, 0, 1) - EPOCH) / DAY), q1 = Math.round((Date.UTC(y + 1, 0, 1) - EPOCH) / DAY); for (let q = q0; q < q1; q++) a += u.spell[q] / 100; ann.push({y, v: Math.round(a * 10) / 10}); }
      const sl = [];
      for (let i = 0; i < ann.length; i++) for (let j = i + 1; j < ann.length; j++) sl.push((ann[j].v - ann[i].v) / (ann[j].y - ann[i].y));
      sl.sort((a, b) => a - b);
      const slope = sl[Math.floor(sl.length / 2)], med = [...ann.map((q) => q.v)].sort((a, b) => a - b)[Math.floor(ann.length / 2)], ymid = (yr0 + yrN) / 2;
      const s = section("Is it becoming more common?", `${cav}From ${yr0} to ${yrN} the number of heat spell days per year, averaged over ${u.name}'s land area, changed by ${slope > 0 ? "+" : ""}${(slope * 10).toFixed(1)} days per decade.`);
      block(s, "Heat spell days per year, averaged over the land area", "Each dot is one year. The line is the typical change over the whole period; a single extreme year barely moves it.");
      s.append(Plot.plot({...po, ariaLabel: `Heat spell days per year averaged over the land area, ${yr0} to ${yrN}, with a trend line`, width: W, height: 260, x: {label: null, tickFormat: "d"}, y: {label: "days per year", grid: true, zero: true},
        marks: [Plot.ruleY([0], {stroke: "#c3c2b7"}), Plot.line([yr0, yrN].map((y) => ({y, v: med + (y - ymid) * slope})), {x: "y", y: "v", stroke: C.severe, strokeWidth: 2}),
          Plot.dot(ann, {x: "y", y: "v", r: 4, fill: "#52514e", stroke: "#fff", strokeWidth: 1}), Plot.tip(ann, Plot.pointerX({x: "y", y: "v", title: (q) => `${q.y}: ${q.v} days`}))]}));
      if (u.trend) {
        const pm = Math.max(u.trend[1], u.trend[2]), f = (v) => v < 0.001 ? "below 0.001" : v.toFixed(3);
        s.append(el(`<p>${pm < 0.05 ? "A change of this size is unlikely to be chance alone" : "This change cannot be told apart from no trend"}: the Mann-Kendall test gives p ${f(u.trend[1])}, and p ${f(u.trend[2])} after allowing for one year resembling the next. The test is for this one place; it makes no allowance for looking at many places.</p>`));
      }
      s.append(el(`<p class="ph"><b>Before reading a trend here.</b> The source is a reanalysis whose inputs change over the years, which can add or hide a trend, and the yardstick is fixed on 1991 to 2020 and not adjusted for warming. Recent years therefore count more heat spell days almost everywhere.</p>`));
    }
    { // 5
      const low = tr.low, red = tr.red, sus = tr.sus, p = (v) => v;
      const s = section("How far to trust this", "Three things decide how much weight these numbers can bear here.");
      s.append(el(`<ul>
        <li><b>Confidence.</b> ${p(low)}% of this unit's land area is in the low-confidence class and ${p(red)}% in the reduced class. Where day-to-day temperature varies little, a small shift crosses the thresholds on many days, and the data follows observed hot days less well. Low-confidence areas are hatched on the map. Evidence: ${evid("low", "the comparison with weather stations")} and ${evid("rule", "the rule that sets the classes")}.</li>
        <li><b>Data suspect: ${p(sus)}% of this unit.</b> ${man.counts.data_suspect_cells.toLocaleString("en-GB")} grid cells in three regions have a known break in the source data, shown by weather stations. They are marked on the map and kept in every number. Evidence: ${evid("sus", "how the breaks were found")}.</li>
        <li><b>Based on ${u.cells.toLocaleString("en-GB")} grid cells</b> of about 10 km. Every share is of land area, not of people.</li>
        <li><b>The yardstick.</b> Severe and extreme are relative to the time of year in this place's own 1991 to 2020 climate. The heat spell test also counts days that are simply among the hottest of the year here, so the lowest class is not always unusual for its date. Neither is adjusted for warming since 2020.</li>
        <li><b>No uncertainty is quantified</b> in this build.</li></ul>`));
    }
    { // 6
      const s = section("Method and credits", "Short version.");
      s.append(el(`<ul>
        <li><b>Heat spell.</b> The three-day average of daily mean temperature is above its usual top tenth for the date and above the year's median, or above the top twentieth for the whole year, for at least three days in a row. This is this project's definition (detector version ${man.detector_version}).</li>
        <li><b>As shown.</b> A place is shown in a heat spell from the third day in a row. The newest day shown is two days behind the newest data.</li>
        <li><b>Severity.</b> A spell day is severe when it is among roughly the hottest 1 day in 20 for that time of year in 1991 to 2020, and extreme when among the hottest 1 in 100.</li>
        <li><b>Status of an area.</b> "Most of the area" means half or more of the land area is severe or extreme; "part of the area" means a quarter or more. The half level was tested on documented events; the quarter level is a setting chosen from how often it is met.</li>
        <li><b>Here.</b> The reading for a point uses the 9 grid cells around it, about 33 km across. It says severe when more than half are severe or extreme, and in a heat spell when more than half are in one. The second rule is this page's own and has not been tested.</li>
        <li><b>Event.</b> At least a quarter of the area in a heat spell for three days or more, with gaps of up to two days joined. Its size is in degree-days above the heat threshold. In climates with little day-to-day variation this rule can join a whole season into one event.</li>
        <li><b>Data.</b> AgERA5, Copernicus Climate Change Service, DOI 10.24381/cds.6c68c9bb. Data to ${fmt(T - 1)}; built ${man.built.slice(0, 10)}.</li>
        <li><b>Compared with other indices.</b> The heat spell here is not WSDI, the Excess Heat Factor or any other published index, and its numbers cannot be set beside theirs. <a href="${DOC.replace("agera5-vs-stations.md", "heat-indices-compared.md")}" target="_blank" rel="noopener">How it differs, and where it is the weaker choice</a>.</li>
        <li><b>Boundaries.</b> ${man.boundaries.credit || "FieldMaps edge-matched subnational boundaries, ODbL."} Borders and names are shown as the sources give them and do not express any view on the status of a territory or its borders.</li></ul>`));
    }
  }

  // ---------- wiring
  let token = 0;
  async function render(full) {
    const my = ++token;
    let d;
    try { d = await unitData(); } catch (err) {
      console.error(err);
      $("pnote").textContent = "The data for this place could not be loaded."; $("pnote").style.display = "";
      return;
    }
    if (my !== token) return;
    drawOutline();
    // the map layer and the panel are drawn separately: if the layer cannot be loaded, the panel and the story still update
    const results = await Promise.allSettled([drawMap(my), renderPanel(d, my)]);
    if (my !== token) return;
    const failed = results.find((q) => q.status === "rejected");
    if (failed) {
      console.error(failed.reason);
      humCache.clear(); monthCache.clear(); yearCache.clear(); fixedCache.clear();
      $("pnote").textContent = "The map layer for this date could not be loaded. Move the slider or reload the page to try again."; $("pnote").style.display = "";
    }
    if (my !== token) return;
    const link = new URLSearchParams({lvl: S.level, d: iso(curT())});
    if (S.pt) link.set("pt", S.pt.lat.toFixed(2) + "," + S.pt.lon.toFixed(2)); else if (S.sel && S.sel.adm1 >= 0) { link.set("u", admins.adm1[S.sel.adm1].id); if (d && d.dist) link.set("d2", d.dist.id); }
    history.replaceState(null, "", "#" + link.toString());
    for (const k of [S.k - 1, S.k + 1]) if (k >= 0 && k < PERIODS[S.p].days.length) daily(PERIODS[S.p].days[k]).catch(() => {});   // warm the neighbouring days so the slider does not wait on a download
    if (full && my === token) { const ts = performance.now(); renderStory(d); twoCol(); window.__heat.storyMs = Math.round(performance.now() - ts); }
  }
  const slider = $("slider");
  if (!hasHumid) $("layer").querySelector('option[value="humid"]')?.remove();
  for (const k of ["trend", "season"]) if (!files[`static/${k}.png`]) $("layer").querySelector(`option[value="${k}"]`)?.remove();
  for (const k of ["mspell", "msevere"]) if (!NM) $("layer").querySelector(`option[value="${k}"]`)?.remove();
  const setSlider = () => { slider.max = isMonth() ? NM - 1 : isYear() ? NY - 1 : PERIODS[S.p].days.length - 1; slider.value = isMonth() ? S.m : isYear() ? S.y : S.k; };
  const psel = $("period");                                                   // which run of days the slider moves through
  psel.innerHTML = PERIODS.map((q, i) => `<option value="${i}">${esc(q.name)}</option>`).join("");
  psel.value = String(S.p);
  psel.addEventListener("change", async () => {
    S.p = +psel.value;
    S.k = S.p === 0 ? PERIODS[0].days.length - 1 : Math.floor(PERIODS[S.p].days.length / 2);       // a past event opens on its middle day
    setSlider();
    const bb = PERIODS[S.p].bbox;
    if (bb) {                                                                 // a past event: move the map to its region and choose the province there with the most severe area that day
      map.fitBounds([[bb[0], bb[1]], [bb[2], bb[3]]], {animate: false, padding: 20});
      const code = await daily(curT()), sev = new Map(), any = new Map(), inBox = new Map();
      const r0 = Math.max(0, Math.round((90 - bb[3]) / 0.1)), r1 = Math.min(SOUTH, Math.round((90 - bb[1]) / 0.1));
      const c0 = Math.max(0, Math.round((bb[0] + 180) / 0.1)), c1 = Math.min(NC - 1, Math.round((bb[2] + 180) / 0.1));
      for (let r = r0; r <= r1; r++) {
        const w = Math.cos((90 - 0.1 * r) * Math.PI / 180);
        for (let c = c0; c <= c1; c++) {
          const i = r * NC + c, a1 = cell.adm1[i], raw = code[i];
          if (a1 < 0 || raw === 255 || !admins.adm1[a1].series) continue;
          inBox.set(a1, (inBox.get(a1) || 0) + 1);
          const cl = raw & 3;
          if (cl >= 1) any.set(a1, (any.get(a1) || 0) + w);
          if (cl >= 2) sev.set(a1, (sev.get(a1) || 0) + w);
        }
      }
      // only provinces that lie mostly inside the event's view, so a large neighbour that just reaches into it is not chosen
      const inside = (m) => [...m].filter(([a1]) => inBox.get(a1) >= 0.6 * admins.adm1[a1].cells).sort((x, y) => y[1] - x[1])[0];
      // the event's own focus place decides the province; the most severe province in view is only the fallback
      const fo = PERIODS[S.p].focus, fi = fo ? Math.round((90 - fo[0]) / 0.1) * NC + ((Math.round((fo[1] + 180) / 0.1) % NC) + NC) % NC : -1;
      const top = fi >= 0 && cell.adm1[fi] >= 0 && admins.adm1[cell.adm1[fi]].series ? [cell.adm1[fi]] : inside(sev) || inside(any);
      if (top) { S.sel = {adm1: top[0], adm0: admins.adm1[top[0]].adm0, adm2: -1}; S.level = "adm1"; S.pt = null; S.msg = ""; pin.remove(); $("find").value = ""; }
    }
    render(true);
  });
  setSlider();
  slider.addEventListener("input", () => { if (isMonth()) S.m = +slider.value; else if (isYear()) S.y = +slider.value; else S.k = +slider.value; render(false); });
  $("layer").addEventListener("change", () => { S.layer = $("layer").value; setSlider(); render(false); });
  $("dsel").addEventListener("change", () => {
    if ($("dsel").value === "") return;
    S.sel.adm2 = +$("dsel").value; S.level = "adm2"; S.pt = null; S.msg = ""; pin.remove();
    render(true);
  });
  slider.addEventListener("change", () => render(true));
  document.querySelectorAll("#levels button").forEach((b) => b.addEventListener("click", () => { S.level = b.dataset.level; render(true); }));
  // a place can also be chosen by name, without a mouse
  const places = new Map();
  admins.adm0.forEach((u, i) => { if (u.series) places.set(nameOf("adm0", i), {level: "adm0", row: i}); });
  admins.adm1.forEach((u, i) => { if (u.series) places.set(`${nameOf("adm1", i)}, ${nameOf("adm0", u.adm0)}`, {level: "adm1", row: i}); });
  $("places").innerHTML = [...places.keys()].sort().map((k) => `<option value="${esc(k).replace(/"/g, "&quot;")}">`).join("");
  $("find").addEventListener("change", () => {
    const hit = places.get($("find").value);
    if (!hit) return;
    S.level = hit.level; S.msg = ""; S.pt = null; pin.remove();
    S.sel = hit.level === "adm0" ? {adm0: hit.row, adm1: admins.adm1.findIndex((u) => u.adm0 === hit.row && u.series), adm2: -1} : {adm0: admins.adm1[hit.row].adm0, adm1: hit.row, adm2: -1};
    const b = unitBounds(cell[hit.level], hit.row);
    if (b) map.fitBounds(b, {animate: false});
    render(true);
  });
  const pinbar = $("pin");
  addEventListener("scroll", () => pinbar.classList.toggle("on", scrollY > innerHeight * 0.7), {passive: true});
  $("pintop").addEventListener("click", () => scrollTo({top: 0, behavior: "smooth"}));
  await render(true);
  mark("first render");
  addOutlines().catch((e) => console.warn("country lines not drawn:", e));
  if (S.sel && !S.pt) {                                                      // frame the starting province, unless a place was already clicked
    const b0 = unitBounds(cell.adm1, S.sel.adm1);
    if (b0) map.fitBounds(b0, {animate: false});
  } else if (S.pt && linked) map.jumpTo({center: [S.pt.lon, S.pt.lat], zoom: 4});
}
