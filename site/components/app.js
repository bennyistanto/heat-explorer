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

// The map layers are PNG files whose bytes are codes, not colours. They are decoded here and not read back from a canvas,
// because browsers with fingerprinting protection add noise to canvas pixels, which would change the codes.
// Returns one byte per pixel (greyscale files) or three (colour files). 8-bit, not interlaced, as pipeline/web_products.py writes them.
async function decodePng(file) {
  const b = new Uint8Array(await file.arrayBuffer()), dv = new DataView(b.buffer, b.byteOffset, b.byteLength), idat = [];
  let at = 8, w = 0, h = 0, ch = 0;
  while (at + 12 <= b.length) {
    const len = dv.getUint32(at), tag = String.fromCharCode(b[at + 4], b[at + 5], b[at + 6], b[at + 7]);
    if (tag === "IHDR") {
      w = dv.getUint32(at + 8); h = dv.getUint32(at + 12);
      ch = b[at + 17] === 0 ? 1 : b[at + 17] === 2 ? 3 : 0;
      if (!ch || b[at + 16] !== 8 || b[at + 20] !== 0) throw new Error("png of a kind this reader does not handle");
    } else if (tag === "IDAT") idat.push(b.subarray(at + 8, at + 8 + len));
    else if (tag === "IEND") break;
    at += 12 + len;
  }
  if (!w || !idat.length) throw new Error("not a png");
  const raw = new Uint8Array(await new Response(new Blob(idat).stream().pipeThrough(new DecompressionStream("deflate"))).arrayBuffer());
  const rb = w * ch, out = new Uint8Array(rb * h);
  if (raw.length !== (rb + 1) * h) throw new Error("png size does not match its header");
  for (let y = 0; y < h; y++) {                                               // undo the row filters
    const f = raw[y * (rb + 1)], src = y * (rb + 1) + 1, o = y * rb, up = o - rb;
    if (f === 0) out.set(raw.subarray(src, src + rb), o);
    else if (f === 1) for (let x = 0; x < rb; x++) out[o + x] = raw[src + x] + (x >= ch ? out[o + x - ch] : 0);
    else if (f === 2) for (let x = 0; x < rb; x++) out[o + x] = raw[src + x] + (y ? out[up + x] : 0);
    else if (f === 3) for (let x = 0; x < rb; x++) out[o + x] = raw[src + x] + (((x >= ch ? out[o + x - ch] : 0) + (y ? out[up + x] : 0)) >> 1);
    else if (f === 4) for (let x = 0; x < rb; x++) {
      const A = x >= ch ? out[o + x - ch] : 0, B = y ? out[up + x] : 0, C = x >= ch && y ? out[up + x - ch] : 0, q = A + B - C;
      const pa = Math.abs(q - A), pb = Math.abs(q - B), pc = Math.abs(q - C);
      out[o + x] = raw[src + x] + (pa <= pb && pa <= pc ? A : pb <= pc ? B : C);
    } else throw new Error("png row filter " + f);
  }
  return {w, h, ch, data: out};
}
async function viaCanvas(file, ch) {                                          // only where the browser cannot inflate, or the file is of another kind
  const bmp = await createImageBitmap(await file.blob(), {colorSpaceConversion: "none", premultiplyAlpha: "none"});
  const c = new OffscreenCanvas(bmp.width, bmp.height), x = c.getContext("2d", {willReadFrequently: true});
  x.drawImage(bmp, 0, 0);
  const px = x.getImageData(0, 0, bmp.width, bmp.height).data, n = bmp.width * bmp.height, out = new Uint8Array(n * ch);
  bmp.close();
  for (let i = 0; i < n; i++) for (let k = 0; k < ch; k++) out[i * ch + k] = px[4 * i + k];
  return out;
}
async function pixels(file, ch = 1) {                                         // ch bytes per pixel: 1 for the code layers, 3 for the district raster
  if (typeof DecompressionStream === "function") {
    try { const d = await decodePng(file); if (d.ch === ch) return d.data; } catch (err) { console.warn(err); }
  }
  return viaCanvas(file, ch);
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
  const once = (key, make) => {
    if (!cache.has(key)) { const v = make(); cache.set(key, v); if (v && v.catch) v.catch(() => cache.delete(key)); }   // a failed download is forgotten, so the next try fetches again
    return cache.get(key);
  };
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
  const [maskPx, admPx, parentBuf] = await Promise.all([pixels(need("static/mask.png")), pixels(need("static/adm2.png"), 3), need("static/adm2_parent.dat").arrayBuffer()]);
  mark("static images");
  const parent = new Uint16Array(parentBuf);
  const N = NR * NC, mask = new Uint8Array(N), cell = {adm2: new Int32Array(N), adm1: new Int16Array(N), adm0: new Int16Array(N)};
  for (let i = 0; i < N; i++) {
    mask[i] = maskPx[i];
    const a2 = ((admPx[3 * i] << 16) | (admPx[3 * i + 1] << 8) | admPx[3 * i + 2]) - 1;
    const a1 = a2 >= 0 && parent[a2] !== 65535 ? parent[a2] : -1;
    cell.adm2[i] = a2; cell.adm1[i] = a1; cell.adm0[i] = a1 >= 0 ? admins.adm1[a1].adm0 : -1;
  }
  mark("cell lookups");
  const dayCache = new Map();                                                // decoded days, most recently used last; each is 6.5 MB, so only a few are kept
  const daily = (k) => {
    if (dayCache.has(k)) { const v = dayCache.get(k); dayCache.delete(k); dayCache.set(k, v); return v; }
    const pr = (async () => {
      const px = await pixels(need(`daily/${iso(k)}.png`)), out = new Uint8Array(N);   // k is the day, counted from 1979-01-01
      for (let i = 0; i < N; i++) out[i] = px[i];                        // one byte: bits 0-1 class shown, bits 2-7 day of the spell, 255 sea
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
      yearCache.set(key, (async () => { const px = await pixels(need(`annual/${name}_${Y0 + y}.png`)), out = new Uint8Array(N); for (let i = 0; i < N; i++) out[i] = px[i]; return out; })());
      while (yearCache.size > 4) yearCache.delete(yearCache.keys().next().value);
    }
    return yearCache.get(key);
  };
  const weekCache = new Map();
  const weekly = (w) => {                                                     // highest class shown in week w (0 = the week ending on the last day): 0 to 3, 255 sea
    if (!weekCache.has(w)) weekCache.set(w, (async () => { const px = await pixels(need(man.weekly[w].file)), out = new Uint8Array(N); for (let i = 0; i < N; i++) out[i] = px[i]; return out; })());
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
          for (let i = 0; i < N; i++) { const v = px[i]; if (v === 255) out[i] = 255; else if ((v & 3) > out[i]) out[i] = v & 3; }
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
  })().catch((err) => { lineSetsP = null; throw err; }));
  async function drawWeeks(wrap, arr, id) {
    const LS = await lineSets();                                   // up to eight small maps of one unit, oldest week first
    let r0 = NR, r1 = -1, c0 = NC, c1 = -1;
    const ext = (ra, rb, ca, cb) => { r0 = NR; r1 = -1; c0 = NC; c1 = -1; for (let r = ra; r <= rb; r++) for (let c = ca; c <= cb; c++) if (arr[r * NC + c] === id) { if (r < r0) r0 = r; if (r > r1) r1 = r; if (c < c0) c0 = c; if (c > c1) c1 = c; } };
    ext(0, NR - 1, 0, NC - 1);
    const vb = PERIODS[S.p].bbox;
    if (vb && c1 - c0 >= 1800)                                                // a place too wide to draw, in a past event: only the part inside the event's view
      ext(Math.max(0, Math.round((90 - vb[3]) / 0.1)), Math.min(NR - 1, Math.round((90 - vb[1]) / 0.1)), Math.max(0, Math.round((vb[0] + 180) / 0.1)), Math.min(NC - 1, Math.round((vb[2] + 180) / 0.1)));
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
      humCache.set(k, (async () => { const px = await pixels(need(`humid/${iso(k)}.png`)), out = new Uint8Array(N); for (let i = 0; i < N; i++) out[i] = px[i]; return out; })());
      while (humCache.size > 6) humCache.delete(humCache.keys().next().value);
    }
    return humCache.get(k);
  };
  let maskHum = null;                                                         // this layer's own confidence (bits 0-1), with the data-suspect bit of the main mask
  const humidMask = async () => {
    if (!maskHum) { const px = await pixels(need("static/mask_humid.png")); maskHum = new Uint8Array(N); for (let i = 0; i < N; i++) maskHum[i] = (px[i] & 3) | (mask[i] & 4); }
    return maskHum;
  };
  const fixedCache = new Map();
  const fixedLayer = (name) => {                                              // layers with one picture: trend, season status
    if (!fixedCache.has(name)) fixedCache.set(name, (async () => { const px = await pixels(need(`static/${name}.png`)), out = new Uint8Array(N); for (let i = 0; i < N; i++) out[i] = px[i]; return out; })());
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
      monthCache.set(key, (async () => { const px = await pixels(need(`monthly/${MONTHLY[name].file}_${monthKey(m)}.png`)), out = new Uint8Array(N); for (let i = 0; i < N; i++) out[i] = px[i]; return out; })());
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
  const country = (a0) => once("a" + a0, () => readBin(need(`admin/${admins.adm0[a0].id}.dat`)));
  const countryArch = (a0) => once("r" + a0, async () => {                    // numbers for the days of the listed past events
    const f = files[`admin_arch/${admins.adm0[a0].id}.dat`];
    if (!f) return null;
    const b = await readBin(f);
    b.pos = new Map(b.head.days.map((d, i) => [d, i]));
    return b;
  });
  const districts = (a0) => once("b" + a0, () => files[`admin2/${admins.adm0[a0].id}.dat`] ? readBin(files[`admin2/${admins.adm0[a0].id}.dat`]) : null);
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
    if (q.get("d")) {
      const want = dayOf(q.get("d")), first = q.get("p") ? dayOf(q.get("p")) : NaN;
      const has = PERIODS.map((pp, pi) => pi).filter((pi) => PERIODS[pi].days.includes(want));
      const pi = has.find((i) => i > 0 && PERIODS[i].days[0] === first) ?? has[0];   // the period the link names, else the first that holds the date
      if (pi !== undefined) { S.p = pi; S.k = PERIODS[pi].days.indexOf(want); }
    }
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
  const TREND = lutSet((v) => { if (v === 0) return RGB[0]; const d = Math.max(-1, Math.min(1, (v - 128) / 2 / TREND_CAP)); return d >= 0 ? mix([240, 196, 150], [116, 41, 12], d) : mix([176, 208, 236], [24, 84, 160], -d); });
  const SEASON = lutSet((v) => v === 1 ? [240, 196, 25] : v === 2 ? [161, 79, 176] : v === 5 ? [127, 163, 199] : v >= 10 ? mix([217, 120, 60], [116, 41, 12], Math.min(1, (v - 12) / 6)) : RGB[0]);
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
    if (!files[`admin/${admins.adm0[a0].id}.dat`])             // below the cell floor: the build has no area shares for this country
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
      return {rank: e.rankTo, k4: `largest event on record here, by its size up to ${fmt(t)}; ${after}`,
        tail: ` It was day ${e.day} of an event that ranked ${ordinal(e.rankTo)} of ${e.n} here on record (1979 to ${fmt(T - 1)}) by its size up to that date; ${after}.`,
        lead: `this is day ${e.day}. By its size up to this date (${e.sizeTo.toFixed(1)} degree-days) it ranks ${ordinal(e.rankTo)} among ${e.n} events here on record (1979 to ${fmt(T - 1)}); ${after}.`};
    }
    if (e.open) return {rank: e.rank, k4: `largest event on record here, so far: still running, size as of ${fmt(T - 1)}`,
      tail: ` It was day ${e.day} of an event that is still running and so far ranks ${ordinal(e.rank)} of ${e.n} here on record (1979 to ${fmt(T - 1)}) (size as of ${fmt(T - 1)}).`,
      lead: `this is day ${e.day} of an event that was still running on ${fmt(T - 1)}, the last day of data. By its size so far it ranks ${ordinal(e.rank)} among ${e.n} events here on record (1979 to ${fmt(T - 1)}); that rank uses its size on ${fmt(T - 1)}, not on the chosen date.`};
    return {rank: e.rank, k4: "largest event on record here" + (e.whole ? ", counting the whole event" : ""),
      tail: ` It was day ${e.day} of an event that ranks ${ordinal(e.rank)} of ${e.n} here on record (1979 to ${fmt(T - 1)})${e.whole ? ", counting the whole event" : ""}.`,
      lead: `this is day ${e.day} of ${e.days} days. By size it ranks ${ordinal(e.rank)} among ${e.n} events here on record (1979 to ${fmt(T - 1)})${e.whole ? ", counting the whole event" : ""}.`};
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
    $("layernote").textContent = S.level === "adm2" ? (fx ? `This map does not change with the slider. The panel beside it describes ${fmt(t)}.` : yrl ? `The map shows ${yrl.label}. The panel beside it describes ${fmt(t)}.` : "")
      : fx ? "This map does not change with the slider. The panel and the page below describe the same thing as the map." : yrl ? `The map, the panel beside it and the page below all describe ${yrl.label}.` : "";
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
    $("k1").textContent = "of land area in a heat spell"; $("k2").textContent = "of land area severe or extreme"; $("sparkh").textContent = "Share of land area in a heat spell, 60 days to the chosen date";
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
    const lic0 = S.sel.adm1 >= 0 ? admins.adm1[S.sel.adm1].licence : "", checked = (man.boundaries.source_licences_checked || {})[admins.adm0[d.a0].name];
    const lic = lic0.startsWith("Other") && checked ? checked : lic0;
    $("pcells").textContent = u.cells.toLocaleString("en-GB") + " grid cells of about 10 km." + (lic ? ` Boundary source licence: ${lic}.` : "");
    const ev = e && e.i !== undefined ? eventWords(e, t).tail : "";
    $("sentence").textContent = `${cav}On ${fmt(t)}, ${u.now.spell}% of ${nm}'s land area was in a heat spell, and ${u.now.severe}% of its land area was severe or extreme.${ev}`;
    if (S.layer !== "sev" && u.level !== "adm2") layerPanel(u, t, cav, my);   // the other layers: the panel is about what the map shows
  }

  // ---------- the side panel for the layers other than the daily one: it describes what the map shows, not the chosen date
  function sparkAny(vals, top, tipOf, firstLab, lastLab, topLab) {
    const W = 320, Hh = 86, p = {l: 2, r: 2, t: 6, b: 16}, n = vals.length;
    const x = (i) => p.l + i * (W - p.l - p.r) / Math.max(1, n - 1), y = (v) => p.t + (1 - Math.min(1, v / top)) * (Hh - p.t - p.b);
    const line = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const svg = $("spark");
    svg.innerHTML = `<line x1="${p.l}" x2="${W - p.r}" y1="${y(0)}" y2="${y(0)}" stroke="#c3c2b7" vector-effect="non-scaling-stroke"/>
      <line x1="${p.l}" x2="${W - p.r}" y1="${y(top)}" y2="${y(top)}" stroke="#e1e0d9" stroke-dasharray="2 3" vector-effect="non-scaling-stroke"/>
      <path d="${line}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z" fill="#d9783c" opacity="0.18"/><path d="${line}" fill="none" stroke="#b24d1c" stroke-width="2" vector-effect="non-scaling-stroke"/>
      <line id="cross" y1="${p.t}" y2="${y(0)}" stroke="#52514e" vector-effect="non-scaling-stroke" style="display:none"/>
      <text x="${p.l}" y="${Hh - 3}" font-size="10" fill="#898781">${firstLab}</text><text x="${W - p.r}" y="${Hh - 3}" font-size="10" fill="#898781" text-anchor="end">${lastLab}</text>
      <text x="${W - p.r}" y="${y(top) - 2}" font-size="10" fill="#898781" text-anchor="end">${topLab}</text>`;
    const tip = $("tip"), cross = svg.querySelector("#cross");
    svg.onmousemove = (e) => {
      const r = svg.getBoundingClientRect(), i = Math.max(0, Math.min(n - 1, Math.round((e.clientX - r.left) / r.width * (n - 1))));
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.style.display = "";
      tip.style.display = "block"; tip.style.left = (x(i) / W * r.width) + "px"; tip.style.top = (y(vals[i]) / Hh * r.height) + "px";
      tip.textContent = tipOf(i);
    };
    svg.onmouseleave = () => { tip.style.display = "none"; cross.style.display = "none"; };
  }
  function layerPanel(u, t, cav, my) {
    const L = S.layer, nm = u.name || "this area", yN = man.annual_years[1];
    const set = (i, v, k) => { $("n" + i).innerHTML = v; $("k" + i).textContent = k; };
    const head = (text, colour, sparkTitle, sentence) => { $("pstatus").textContent = text; $("pchip").style.background = colour; $("sparkh").textContent = sparkTitle; $("sentence").textContent = cav + sentence; };
    const pctOf = (q0, q1) => Array.from(u.spell.subarray(Math.max(0, q0), Math.min(q1, T)));
    const live = () => my === undefined || my === token;
    if (L === "spell" || L === "severe") {
      const Y = Y0 + S.y, years = yearRow(u), me = years.find((q) => q.y === Y), rank = 1 + years.filter((q) => q.v > me.v).length;
      const usual = median(years.filter((q) => q.y >= 1991 && q.y <= 2020).map((q) => q.v)), q0 = dayIx(Y), vals = pctOf(q0, dayIx(Y + 1));
      let pk = 0; vals.forEach((v, i) => { if (v > vals[pk]) pk = i; });
      const sent = `In ${Y}, ${nm} had ${me.v.toFixed(1)} heat spell days, averaged over its land area: the ${ordinal(rank)} most of the ${years.length} years from 1979 to ${yN}. A usual year in 1991 to 2020 had ${usual.toFixed(1)}.`;
      head(`${Y}: ${me.v >= 1.5 * usual ? "far more heat than usual" : me.v > usual ? "more heat than usual" : "no more heat than usual"}`, me.v >= 1.5 * usual ? C.extreme : me.v > usual ? C.severe : C.land, `Share of land area in a heat spell, each day of ${Y}`, sent);
      sparkAny(vals, 100, (i) => `${fmt(q0 + i)}: ${vals[i]}% of land area in a heat spell`, fmt(q0, false), fmt(q0 + vals.length - 1, false), "100%");
      if (L === "spell") {
        set(1, me.v.toFixed(1), `heat spell days in ${Y}, averaged over the land area`);
        set(2, usual.toFixed(1), "in a usual year, 1991 to 2020");
        set(3, ordinal(rank) + `<small> of ${years.length}</small>`, `most heat spell days among the years 1979 to ${yN}`);
        set(4, vals[pk] + "<small>%</small>", `of land area in a heat spell on the widest day, ${fmt(q0 + pk)}`);
      } else {
        set(1, "…", `severe or extreme days in ${Y} on half of the land area, or more`);
        set(2, "…", "of the heat spell days were severe or extreme");
        set(3, "…", "severe or extreme days on the most affected tenth of the land, or more");
        set(4, "…", "of the land area had at least one severe or extreme day");
        Promise.all([yearly("spell", S.y), yearly("severe", S.y)]).then(([sp, sv]) => {
          if (!live() || S.layer !== "severe") return;
          const cells = unitCells(u.level, u.row), res = spread(sv, cells, YBINS);
          let a = 0, b = 0;
          for (let k = 0; k < cells.ix.length; k++) { const x = sp[cells.ix[k]], z = sv[cells.ix[k]]; if (x === 255 || z === 255) continue; a += cells.w[k] * x; b += cells.w[k] * z; }
          $("n1").innerHTML = res.q(0.5); $("n2").innerHTML = (a ? Math.round(100 * b / a) : 0) + "<small>%</small>"; $("n3").innerHTML = res.q(0.9); $("n4").innerHTML = Math.round(100 - res.share[0]) + "<small>%</small>";
          $("sentence").textContent = `${cav}In ${Y}, half of ${nm}'s land area had ${res.q(0.5)} or more severe or extreme days, and ${a ? Math.round(100 * b / a) : 0}% of its heat spell days were severe or extreme, counted on the map's cells.`;
        }).catch((err) => console.error(err));
      }
      return;
    }
    if (L === "mspell" || L === "msevere") {
      const mkey = monthKey(S.m), Y = +mkey.slice(0, 4), mo = +mkey.slice(5) - 1, mname = monthName(S.m), q0 = dayIx(Y, mo, 1), vals = pctOf(q0, dayIx(Y, mo + 1, 1));
      const calName = new Date(Date.UTC(2001, mo, 1)).toLocaleDateString("en-GB", {month: "long", timeZone: "UTC"}), same = [];
      for (let y = 1979; y <= Y0 + NY; y++) { const a = dayIx(y, mo, 1), b = dayIx(y, mo + 1, 1); if (b <= T) same.push({y, v: spanDays(u, a, b)}); }
      const me = same.find((q) => q.y === Y), rank = 1 + same.filter((q) => q.v > me.v).length, usual = median(same.filter((q) => q.y >= 1991 && q.y <= 2020).map((q) => q.v));
      let pk = 0; vals.forEach((v, i) => { if (v > vals[pk]) pk = i; });
      const half = vals.filter((v) => v >= 50).length;
      head(`${mname}: ${me.v >= 1.5 * usual && me.v >= 1 ? "far more heat than usual" : me.v > usual ? "more heat than usual" : "no more heat than usual"}`, me.v >= 1.5 * usual && me.v >= 1 ? C.extreme : me.v > usual ? C.severe : C.land, `Share of land area in a heat spell, each day of ${mname}`,
        `In ${mname}, ${nm} had ${me.v.toFixed(1)} heat spell days, averaged over its land area: the ${ordinal(rank)} most for a ${calName} in ${same.length} years. A usual ${calName} in 1991 to 2020 had ${usual.toFixed(1)}.`);
      sparkAny(vals, 100, (i) => `${fmt(q0 + i)}: ${vals[i]}% of land area in a heat spell`, fmt(q0, false), fmt(q0 + vals.length - 1, false), "100%");
      if (L === "mspell") {
        set(1, me.v.toFixed(1), `heat spell days in ${mname}, averaged over the land area`);
        set(2, usual.toFixed(1), `in a usual ${calName}, 1991 to 2020`);
        set(3, ordinal(rank) + `<small> of ${same.length}</small>`, `most heat spell days among the months of ${calName} since 1979`);
        set(4, vals[pk] + "<small>%</small>", `of land area in a heat spell on the widest day, ${fmt(q0 + pk)}`);
      } else {
        let hs = 0, known = 0;
        for (let i = 0; i < vals.length; i++) { const sv = u.sevAt(q0 + i); if (sv !== undefined && sv !== 255) { known++; if (sv >= 50) hs++; } }
        set(1, String(half), `days of ${mname} with half or more of the land in a heat spell`);
        set(2, known ? String(hs) : "n/a", known ? "days with half or more of the land severe or extreme" : "severe share by day is not published for this month");
        set(3, "…", `severe or extreme days in ${mname} on half of the land area, or more`);
        set(4, "…", "severe or extreme days on the most affected tenth of the land, or more");
        monthlyLayer("msevere", S.m).then((code) => {
          if (!live() || S.layer !== "msevere") return;
          const res = spread(code, unitCells(u.level, u.row), MBINS);
          $("n3").innerHTML = res.q(0.5); $("n4").innerHTML = res.q(0.9);
        }).catch((err) => console.error(err));
      }
      return;
    }
    if (L === "season") {
      const se = u.season, ok = se && se[0] !== 255, vals = pctOf(T - 84, T), v = (i) => (ok ? se[i] + "<small>%</small>" : "n/a");
      head(`Season status, week to ${fmt(T - 1)}`, ok && se[2] >= 25 ? C.severe : ok && se[0] + se[1] >= 25 ? "#f0c419" : C.land, `Share of land area in a heat spell, 12 weeks to ${fmt(T - 1)}`,
        ok ? `In the week to ${fmt(T - 1)}, ${se[0]}% of ${nm}'s land area was newly in a heat spell, ${se[1]}% was in one again after a break, ${se[2]}% was still in one from the week before, and ${se[3]}% was no longer in one.` : `Season status is not published for ${nm}.`);
      set(1, v(0), "of land area newly in a heat spell: none in the 11 weeks before");
      set(2, v(1), "in one again, after a break");
      set(3, v(2), "still in one from the week before");
      set(4, v(3), "no longer in one: was the week before");
      sparkAny(vals, 100, (i) => `${fmt(T - vals.length + i)}: ${vals[i]}% of land area in a heat spell`, fmt(T - vals.length, false), fmt(T - 1, false), "100%");
      return;
    }
    if (L === "trend") {
      const years = yearRow(u), a = years.slice(0, 10), b = years.slice(-10), av = (g) => g.reduce((x, q) => x + q.v, 0) / g.length, top = Math.max(1, ...years.map((q) => q.v));
      const slope = u.trend ? u.trend[0] : NaN, pm = u.trend ? Math.max(u.trend[1], u.trend[2]) : NaN, pass = pm < 0.05;
      head(!u.trend ? "No trend computed" : pass ? (slope > 0 ? "More heat spell days over time" : "Fewer heat spell days over time") : "No trend that passes the test", pass ? (slope > 0 ? C.severe : "#1854a0") : C.land, `Heat spell days per year, 1979 to ${yN}`,
        u.trend ? `From 1979 to ${yN}, heat spell days per year in ${nm} changed by ${slope > 0 ? "+" : ""}${slope.toFixed(1)} days per decade; ${pass ? "a change of this size is unlikely to be chance alone" : "this cannot be told apart from no trend"}.` : `No trend is computed for ${nm}.`);
      set(1, u.trend ? (slope > 0 ? "+" : "") + slope.toFixed(1) : "n/a", "heat spell days per decade, change over the record");
      set(2, av(a).toFixed(1), `days a year in ${a[0].y} to ${a[a.length - 1].y}`);
      set(3, av(b).toFixed(1), `days a year in ${b[0].y} to ${b[b.length - 1].y}`);
      set(4, "…", "of the land area has an upward trend that passes the test on the map");
      sparkAny(years.map((q) => q.v), top, (i) => `${years[i].y}: ${years[i].v.toFixed(1)} heat spell days`, "1979", String(yN), top.toFixed(0) + " days");
      fixedLayer("trend").then((code) => {
        if (!live() || S.layer !== "trend") return;
        const cells = unitCells(u.level, u.row);
        let all = 0, up = 0;
        for (let k = 0; k < cells.ix.length; k++) { const v = code[cells.ix[k]]; if (v === 255) continue; all += cells.w[k]; if (v > 128) up += cells.w[k]; }
        $("n4").innerHTML = (all ? Math.round(100 * up / all) : 0) + "<small>%</small>";
      }).catch((err) => console.error(err));
      return;
    }
    // humid heat (experimental)
    const hu = u.hu, h = hu ? u.huAt(t) : undefined, okH = h !== undefined && h !== 255, n = Math.min(60, t + 1), vals = [];
    for (let q = t - n + 1; q <= t; q++) { const x = hu ? u.huAt(q) : undefined; vals.push(x === undefined || x === 255 ? 0 : x); }
    head(`Humid heat (experimental) on ${fmt(t)}`, okH && h >= 50 ? css(HUMCOL) : C.land, `Share of land area in a humid heat spell, ${n} days to the chosen date`,
      okH ? `On ${fmt(t)}, ${h}% of ${nm}'s land area was in a humid heat spell and ${u.now.spell}% was in a heat spell judged on temperature. Humid heat is experimental and takes no part in the status, the events or the ranks.` : `Humid heat is not published for ${nm} on ${fmt(t)}.`);
    set(1, okH ? h + "<small>%</small>" : "n/a", "of land area in a humid heat spell");
    set(2, u.now.spell + "<small>%</small>", "of land area in a heat spell, on temperature alone");
    set(3, hu ? hu.base.toFixed(0) : "n/a", "humid heat spell days a year, 1991 to 2020");
    set(4, hu ? hu.rec.toFixed(0) : "n/a", "days a year, 2021 to 2025: part of the rise is drift in the source data");
    sparkAny(vals, 100, (i) => `${fmt(t - n + 1 + i)}: ${vals[i]}% of land area in a humid heat spell`, fmt(t - n + 1, false), fmt(t, false), "100%");
  }

  // ---------- story
  const story = $("story");
  const section = (title, lead) => { const s = el(`<section><h2>${title}</h2><p class="lead">${lead}</p></section>`); story.append(s); return s; };
  const block = (s, title, how) => { s.append(el(`<h3>${title}</h3>`)); if (how) s.append(el(`<p class="how"><b>How to read this.</b> ${how}</p>`)); };
  // Each titled block of the story becomes: the words before its chart, the chart, the words after it.
  // On a wide screen the stylesheet puts the chart on the left and the words beside it; on a narrow one they stay in reading order.
  const isFig = (n) => n.matches("svg, figure, canvas, table, .frames, .lensfig");
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
  const po = {style: {fontSize: "12px", fontFamily: "inherit", background: "transparent"}, marginLeft: 44, marginBottom: 36};
  // ---------- the opening section of the story: one per map layer, so the page under the map is about what the map shows
  const dayIx = (y, m = 0, d = 1) => Math.round((Date.UTC(y, m, d) - EPOCH) / DAY);
  const spanDays = (u, q0, q1) => { let a = 0; for (let q = Math.max(0, q0); q < Math.min(q1, T); q++) a += u.spell[q] / 100; return a; };   // heat spell days, averaged over the land area
  const css = (c) => `rgb(${c[0]},${c[1]},${c[2]})`;
  const cellsCache = new Map();
  const unitCells = (level, row) => {                                         // the unit's grid cells and their area weights
    const key = level + row;
    if (!cellsCache.has(key)) {
      const arr = cell[level], ix = [];
      for (let i = 0; i < N; i++) if (arr[i] === row) ix.push(i);
      const w = new Float32Array(ix.length);
      for (let k = 0; k < ix.length; k++) w[k] = Math.cos((90 - 0.1 * Math.floor(ix[k] / NC)) * Math.PI / 180);
      cellsCache.set(key, {ix, w});
      while (cellsCache.size > 6) cellsCache.delete(cellsCache.keys().next().value);
    }
    return cellsCache.get(key);
  };
  const median = (a) => { const b = [...a].sort((x, y) => x - y); return b.length ? b[Math.floor(b.length / 2)] : NaN; };
  // share of the unit's land area in each bin of a layer's cell values; bins = [[lo, hi, label, colour], ...]
  const spread = (code, cells, bins) => {
    const tot = new Float64Array(bins.length), vals = [];
    let all = 0;
    for (let k = 0; k < cells.ix.length; k++) {
      const v = code[cells.ix[k]];
      if (v === 255) continue;
      all += cells.w[k]; vals.push([v, cells.w[k]]);
      for (let b = 0; b < bins.length; b++) if (v >= bins[b][0] && v <= bins[b][1]) { tot[b] += cells.w[k]; break; }
    }
    vals.sort((x, y) => x[0] - y[0]);
    const q = (f) => { let acc = 0; for (const [v, w] of vals) { acc += w; if (acc >= f * all) return v; } return NaN; };
    return {share: Array.from(tot, (v) => all ? 100 * v / all : 0), q, n: vals.length};
  };
  const spreadBar = (res, bins) => {
    const box = el(`<div class="spread"><div class="bar"></div><div class="key"></div></div>`);
    res.share.forEach((p, b) => {
      if (p < 0.05) return;
      box.firstChild.append(el(`<span style="width:${p.toFixed(2)}%;background:${bins[b][3]}" title="${esc(bins[b][2])}: ${p.toFixed(0)}% of land area"></span>`));
      box.lastChild.append(el(`<span><i style="background:${bins[b][3]}"></i>${esc(bins[b][2])} <b>${p < 1 ? "under 1" : p.toFixed(0)}%</b></span>`));
    });
    return box;
  };
  // 100 small squares, one per percent of the land area; parts = [[percent, colour, label], ...]
  const waffle = (parts) => {
    const fl = parts.map((p) => Math.floor(p[0])), order = parts.map((p, i) => [p[0] - fl[i], i]).sort((a, b) => b[0] - a[0]);
    let left = 100 - fl.reduce((a, b) => a + b, 0);
    for (const [, i] of order) { if (left <= 0) break; fl[i]++; left--; }
    const box = el(`<div class="waffle" role="img" aria-label="${esc(parts.map((p) => `${p[2]} ${Math.round(p[0])}%`).join(", "))}"></div>`);
    parts.forEach((p, i) => { for (let k = 0; k < fl[i]; k++) box.append(el(`<i style="background:${p[1]}" title="${esc(p[2])}"></i>`)); });
    return box;
  };
  const yearRow = (u) => { const yN = man.annual_years[1], out = []; for (let y = 1979; y <= yN; y++) out.push({y, v: spanDays(u, dayIx(y), dayIx(y + 1))}); return out; };
  // one stripe per year, coloured by heat spell days; pick(y) is called when a stripe is clicked
  const stripes = (years, chosen, pick) => {
    const top = Math.max(1, ...years.map((q) => q.v)), w = 100 / years.length;
    const box = el(`<div class="stripes"><div class="row"></div><div class="ax"><span>${years[0].y}</span><span>${years[years.length - 1].y}</span></div></div>`);
    for (const q of years) {
      const s = el(`<span class="${q.y === chosen ? "on" : ""}" style="width:${w}%;background:${css(rampAt(q.v / top))}" title="${q.y}: ${q.v.toFixed(1)} heat spell days"></span>`);
      if (pick) { s.tabIndex = 0; s.setAttribute("role", "button"); s.setAttribute("aria-label", `Show ${q.y}`); s.addEventListener("click", () => pick(q.y)); s.addEventListener("keydown", (ev) => { if (ev.key === "Enter") pick(q.y); }); }
      box.firstChild.append(s);
    }
    return box;
  };
  // the year as a ring: one spoke per day, its length the share of land in a heat spell; the dashed line is the usual share for the date
  const yearRing = (u, Y, days, rank, nYears) => {
    const q0 = dayIx(Y), n = dayIx(Y + 1) - q0, R0 = 62, R1 = 196, c = 220, parts = [];
    const pt = (i, r) => { const a = 2 * Math.PI * i / n - Math.PI / 2; return [c + r * Math.cos(a), c + r * Math.sin(a)]; };
    for (const f of [0.5, 1]) parts.push(`<circle cx="${c}" cy="${c}" r="${R0 + (R1 - R0) * f}" fill="none" stroke="#e1e0d9" stroke-width="1"/>`);
    parts.push(`<text x="${c}" y="${c - R0 - (R1 - R0) * 0.5 - 3}" class="tk">50% of land</text><text x="${c}" y="${c - R1 - 3}" class="tk">100%</text>`);
    const sw = 2 * Math.PI * ((R0 + R1) / 2) / n;
    for (let i = 0; i < n && q0 + i < T; i++) {
      const s = u.spell[q0 + i] / 100;
      if (s <= 0) continue;
      const a = pt(i, R0), b = pt(i, R0 + (R1 - R0) * s);
      parts.push(`<line x1="${a[0].toFixed(1)}" y1="${a[1].toFixed(1)}" x2="${b[0].toFixed(1)}" y2="${b[1].toFixed(1)}" stroke="${css(rampAt(0.25 + 0.75 * s))}" stroke-width="${Math.max(1.4, sw * 0.9).toFixed(2)}"/>`);
    }
    const usual = [];                                                         // median share for each calendar day over the baseline
    for (let i = 0; i < 365; i++) {
      const v = [];
      for (let y = 1991; y <= 2020; y++) { const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0; v.push(u.spell[dayIx(y) + i + (leap && i >= 59 ? 1 : 0)] / 100); }
      const p = pt(i * n / 365, R0 + (R1 - R0) * median(v));
      usual.push(p[0].toFixed(1) + "," + p[1].toFixed(1));
    }
    parts.push(`<polygon points="${usual.join(" ")}" fill="none" stroke="#3f3e3a" stroke-width="1" stroke-dasharray="3 3"/>`);
    parts.push(`<circle cx="${c}" cy="${c}" r="${R0}" fill="#fbfaf7" stroke="#c3c2b7" stroke-width="1"/>`);
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].forEach((mn, m) => {
      const i = dayIx(Y, m, 1) - q0, a = pt(i, R1 + 2), b = pt(i, R1 + 8), t = pt(i + 15, R1 + 15);
      parts.push(`<line x1="${a[0].toFixed(1)}" y1="${a[1].toFixed(1)}" x2="${b[0].toFixed(1)}" y2="${b[1].toFixed(1)}" stroke="#898781" stroke-width="1"/><text x="${t[0].toFixed(1)}" y="${(t[1] + 4).toFixed(1)}" class="mo">${mn}</text>`);
    });
    parts.push(`<text x="${c}" y="${c - 16}" class="yr">${Y}</text><text x="${c}" y="${c + 12}" class="big">${days.toFixed(1)}</text><text x="${c}" y="${c + 28}" class="sm">heat spell days</text><text x="${c}" y="${c + 43}" class="sm">${ordinal(rank)} of ${nYears} years</text>`);
    return el(`<svg class="ring" viewBox="0 0 440 440" role="img" aria-label="Ring calendar of ${Y}: share of land area in a heat spell on each day, against the usual share for the date in 1991 to 2020">${parts.join("")}</svg>`);
  };
  const YBINS = [[0, 0, "No days", "#e7e6e1"], [1, 10, "1 to 10 days", css(rampAt(0.2))], [11, 25, "11 to 25", css(rampAt(0.4))], [26, 50, "26 to 50", css(rampAt(0.6))], [51, 100, "51 to 100", css(rampAt(0.8))], [101, 254, "over 100", css(rampAt(1))]];
  const MBINS = [[0, 0, "No days", "#e7e6e1"], [1, 3, "1 to 3 days", css(rampAt(0.2))], [4, 7, "4 to 7", css(rampAt(0.4))], [8, 14, "8 to 14", css(rampAt(0.6))], [15, 21, "15 to 21", css(rampAt(0.8))], [22, 31, "22 or more", css(rampAt(1))]];
  const later = (host, make, what) => make().then((node) => { if (host.isConnected) host.replaceChildren(...[].concat(node)); })
    .catch((err) => { console.error(err); if (host.isConnected) host.replaceChildren(el(`<p class="ph">${what} could not be loaded.</p>`)); });

  // Returns the standard sections to keep after the opening one. "sev" (the daily map) keeps the whole story and has no opening section.
  function renderLens(u, t, W) {
    const nm = esc(u.name || "this area"), L = S.layer, yN = man.annual_years[1];
    if (L === "sev") return new Set([1, 2, 3, "where", 4, 5, 6]);
    if (L === "spell") {
      const Y = Y0 + S.y, years = yearRow(u), me = years.find((q) => q.y === Y), rank = 1 + years.filter((q) => q.v > me.v).length;
      const usual = median(years.filter((q) => q.y >= 1991 && q.y <= 2020).map((q) => q.v));
      const s = section(`${Y} in ${nm}`, `In ${Y}, ${nm} had ${me.v.toFixed(1)} heat spell days, averaged over its land area: the ${ordinal(rank)} most of the ${years.length} years from 1979 to ${yN}. A usual year in 1991 to 2020 had ${usual.toFixed(1)}.`);
      block(s, `The year as a ring`, `Read it clockwise from January at the top. Each spoke is one day; the longer and darker it is, the more of the land was in a heat spell that day. The dashed line is the usual share for that date in 1991 to 2020, so spokes that reach past it mark days with more heat than usual.`);
      const fig = el(`<div class="lensfig"></div>`);
      fig.append(yearRing(u, Y, me.v, rank, years.length));
      s.append(fig);
      block(s, `Every year since 1979`, `One stripe per year, darker for more heat spell days. The outlined stripe is ${Y}. Click a stripe to move the map and this page to that year.`);
      const f2 = el(`<div class="lensfig"></div>`);
      f2.append(stripes(years, Y, (y) => { S.y = y - Y0; setSlider(); render(true); }));
      s.append(f2);
      block(s, `How evenly the heat was spread in ${Y}`, `The map coloured each grid cell by its days in a heat spell in ${Y}. This bar sorts ${nm}'s land area by that count. A year can be heavy in one corner and light in the rest.`);
      const f3 = el(`<div class="lensfig"><p class="ph">Counting the map's cells.</p></div>`);
      s.append(f3);
      later(f3, async () => {
        const res = spread(await yearly(L, S.y), unitCells(u.level, u.row), YBINS);
        return [spreadBar(res, YBINS), el(`<p class="lensnote">Half of the land area had ${res.q(0.5)} or more heat spell days in ${Y}; the most affected tenth had ${res.q(0.9)} or more. Counted on ${res.n.toLocaleString("en-GB")} grid cells. The map counts a spell from its first day, the area figures above from its third, so the map's counts run a little higher.</p>`)];
      }, "The map's cells");
      return new Set([3, 5, 6]);
    }
    if (L === "severe") {                                                     // a cut across the place: how much of the year's heat was severe, and where
      const Y = Y0 + S.y, cells = unitCells(u.level, u.row);
      let r0 = NR, r1 = -1, c0 = NC, c1 = -1;
      for (const i of cells.ix) { const r = Math.floor(i / NC), c = i % NC; if (r < r0) r0 = r; if (r > r1) r1 = r; if (c < c0) c0 = c; if (c > c1) c1 = c; }
      const ns = (r1 - r0) >= (c1 - c0) * Math.cos((90 - 0.05 * (r0 + r1)) * Math.PI / 180), dir = ns ? "north to south" : "west to east";
      const s = section(`Severe heat in ${Y} in ${nm}`, `How much of the heat of ${Y} was severe or extreme, and where across ${nm}. Counting the map's cells.`);
      block(s, `A cut from ${dir}`, `${nm} is sliced into bands from ${dir}. For each band, the pale shape is the average number of heat spell days in ${Y} and the dark shape is how many of them were severe or extreme. Where the dark shape fills most of the pale one, the heat that came was mostly of the stronger kind.`);
      s.append(key([[C.spell, "Days in a heat spell"], [C.extreme, "Of which severe or extreme"]]));
      const fig = el(`<div class="lensfig"><p class="ph">Counting the map's cells.</p></div>`);
      s.append(fig);
      const child = u.level === "adm0" ? "adm1" : "adm2", childWord = child === "adm1" ? "provinces" : "districts";
      block(s, `The ${childWord} with the most severe days`, `The ${childWord} of ${nm}, ranked by their severe or extreme days in ${Y}, each the average of its own grid cells. The last column is the share of its heat spell days that were severe or extreme.`);
      const fT = el(`<div class="lensfig"><p class="ph">Counting the map's cells.</p></div>`);
      s.append(fT);
      block(s, `${Y} against the year before`, `Each bar is a share of ${nm}'s land area, sorted by how many more or fewer severe or extreme days it had in ${Y} than in ${Y - 1}. Orange bars to the right of zero had more; blue bars to the left had fewer.`);
      const fD = el(`<div class="lensfig"><p class="ph">Counting the map's cells.</p></div>`);
      s.append(fD);
      later(fig, async () => {
        const [sp, sv] = await Promise.all([yearly("spell", S.y), yearly("severe", S.y)]);
        try {                                                                 // the table of places inside
          const arr = cell[child], g = new Map();
          for (let k = 0; k < cells.ix.length; k++) {
            const i = cells.ix[k], a = sp[i], b = sv[i], id = arr[i];
            if (a === 255 || b === 255 || id < 0) continue;
            const q = g.get(id) || {w: 0, a: 0, b: 0, n: 0};
            q.w += cells.w[k]; q.a += cells.w[k] * a; q.b += cells.w[k] * b; q.n++; g.set(id, q);
          }
          let names = null;
          if (child === "adm2") { const df = await districts(S.sel.adm0); names = new Map(df ? df.head.units.map((q) => [q.row, q.name]) : []); }
          const rowsT = [...g].filter(([, q]) => q.n >= man.settings.cell_floor).map(([id, q]) => ({name: child === "adm1" ? nameOf("adm1", id) : (names.get(id) || "Unnamed district"), sev: q.b / q.w, sp: q.a / q.w})).sort((x, y) => y.sev - x.sev);
          if (fT.isConnected) fT.replaceChildren(rowsT.length >= 2
            ? el(`<table class="ev"><thead><tr><th>Rank</th><th>${child === "adm1" ? "Province" : "District"}</th><th>Severe or extreme days</th><th>Heat spell days</th><th>Share severe</th></tr></thead><tbody>${rowsT.slice(0, 10).map((q, i) =>
              `<tr><td>${i + 1}</td><td>${esc(q.name)}</td><td>${q.sev.toFixed(0)}</td><td>${q.sp.toFixed(0)}</td><td>${q.sp > 0 ? Math.round(100 * q.sev / q.sp) + "%" : "n/a"}</td></tr>`).join("")}</tbody></table>`)
            : el(`<p class="ph">${nm} has fewer than two ${childWord} with ${man.settings.cell_floor} grid cells or more, so there is nothing to rank.</p>`),
            ...(rowsT.length > 10 ? [el(`<p class="lensnote">The first 10 of ${rowsT.length} ${childWord}. Those with fewer than ${man.settings.cell_floor} grid cells are left out.</p>`)] : []));
        } catch (err) { console.error(err); if (fT.isConnected) fT.replaceChildren(el(`<p class="ph">The table could not be built.</p>`)); }
        try {                                                                 // the change from the year before
          if (S.y < 1) throw new Error("first year");
          const pv = await yearly("severe", S.y - 1), E = [], H = new Float64Array(21);
          let all = 0, more = 0, fewer = 0;
          for (let k = 0; k < cells.ix.length; k++) {
            const i = cells.ix[k], b = sv[i], c = pv[i];
            if (b === 255 || c === 255) continue;
            const d = b - c, w = cells.w[k];
            all += w; if (d > 0) more += w; else if (d < 0) fewer += w;
            H[Math.max(0, Math.min(20, Math.round(d / 5) + 10))] += w;
          }
          for (let b = 0; b < 21; b++) if (H[b] > 0) E.push({x1: (b - 10) * 5 - 2.5, x2: (b - 10) * 5 + 2.5, v: H[b] / all, mid: (b - 10) * 5});
          if (fD.isConnected) fD.replaceChildren(Plot.plot({...po, ariaLabel: `Share of land area by the change in severe or extreme days from ${Y - 1} to ${Y}`, width: Math.min(W, 760), height: 240, x: {label: `change in severe or extreme days, ${Y} minus ${Y - 1}`, tickFormat: (v) => (v > 0 ? "+" : "") + v}, y: {label: "share of land area", tickFormat: "%", grid: true},
            marks: [Plot.rectY(E, {x1: "x1", x2: "x2", y: "v", fill: (q) => (q.mid > 0 ? C.severe : q.mid < 0 ? "#1854a0" : "#b9b7ae"), insetLeft: 1, insetRight: 1, title: (q) => `${q.mid > 0 ? "+" : ""}${q.mid} days (to the nearest 5): ${(q.v * 100).toFixed(0)}% of land area`}), Plot.ruleY([0], {stroke: "#c3c2b7"}), Plot.ruleX([0], {stroke: "#3f3e3a", strokeDasharray: "3 3"})]}),
            el(`<p class="lensnote">${Math.round(100 * more / all)}% of the land area had more severe or extreme days in ${Y} than in ${Y - 1}, and ${Math.round(100 * fewer / all)}% had fewer. Changes beyond 50 days are drawn in the end bars.</p>`));
        } catch (err) { if (fD.isConnected) fD.replaceChildren(el(`<p class="ph">${S.y < 1 ? "1979 is the first year on record, so there is no year before it to compare with." : "The year before could not be loaded."}</p>`)); }
        const span = ns ? r1 - r0 + 1 : c1 - c0 + 1, nb = Math.max(1, Math.min(40, span)), W0 = new Float64Array(nb), A = new Float64Array(nb), B = new Float64Array(nb);
        let ta = 0, tb = 0;
        for (let k = 0; k < cells.ix.length; k++) {
          const i = cells.ix[k], a = sp[i], b = sv[i];
          if (a === 255 || b === 255) continue;
          const band = Math.min(nb - 1, Math.floor(((ns ? Math.floor(i / NC) - r0 : i % NC - c0) / span) * nb)), w = cells.w[k];
          W0[band] += w; A[band] += w * a; B[band] += w * b; ta += w * a; tb += w * b;
        }
        const rows = [];
        for (let b = 0; b < nb; b++) if (W0[b] > 0) rows.push({pos: ns ? 90 - 0.1 * (r0 + (b + 0.5) * span / nb) : -180 + 0.1 * (c0 + (b + 0.5) * span / nb), spell: A[b] / W0[b], sev: B[b] / W0[b]});
        const lead = s.querySelector(".lead"), pc = ta ? Math.round(100 * tb / ta) : 0, top = rows.reduce((x, q) => (q.sev > x.sev ? q : x), rows[0]);
        if (lead) lead.textContent = `In ${Y}, ${pc}% of the heat spell days in ${u.name || "this area"} were severe or extreme, counted on the map's cells. The band with the most severe days is near ${Math.abs(top.pos).toFixed(1)}° ${ns ? (top.pos >= 0 ? "N" : "S") : (top.pos >= 0 ? "E" : "W")}, with ${top.sev.toFixed(0)} of them.`;
        const deg = (v) => Math.abs(v).toFixed(v % 1 ? 1 : 0) + "°" + (ns ? (v >= 0 ? "N" : "S") : (v >= 0 ? "E" : "W"));
        const plot = ns
          ? Plot.plot({...po, ariaLabel: `Heat spell days and severe days in ${Y} by latitude band`, width: Math.min(W, 520), height: 420, marginLeft: 56, x: {label: "days in the year, average of the band", grid: true}, y: {label: null, tickFormat: deg},
            marks: [Plot.areaX(rows, {y: "pos", x: "spell", fill: C.spell, curve: "monotone-y"}), Plot.areaX(rows, {y: "pos", x: "sev", fill: C.extreme, curve: "monotone-y"}), Plot.ruleX([0], {stroke: "#c3c2b7"}),
              Plot.tip(rows, Plot.pointerY({y: "pos", x: "spell", title: (q) => `${deg(q.pos)}\nHeat spell days ${q.spell.toFixed(0)}\nSevere or extreme ${q.sev.toFixed(0)}`}))]})
          : Plot.plot({...po, ariaLabel: `Heat spell days and severe days in ${Y} by longitude band`, width: W, height: 280, y: {label: "days in the year, average of the band", grid: true}, x: {label: null, tickFormat: deg},
            marks: [Plot.areaY(rows, {x: "pos", y: "spell", fill: C.spell, curve: "monotone-x"}), Plot.areaY(rows, {x: "pos", y: "sev", fill: C.extreme, curve: "monotone-x"}), Plot.ruleY([0], {stroke: "#c3c2b7"}),
              Plot.tip(rows, Plot.pointerX({x: "pos", y: "spell", title: (q) => `${deg(q.pos)}\nHeat spell days ${q.spell.toFixed(0)}\nSevere or extreme ${q.sev.toFixed(0)}`}))]});
        return [plot, el(`<p class="lensnote">Each band is the average of its grid cells, weighted by area. Both counts are the map's, which count a spell from its first day.</p>`)];
      }, "The map's cells");
      return new Set([5, 6]);
    }
    if (L === "mspell") {
      const mkey = monthKey(S.m), Y = +mkey.slice(0, 4), mo = +mkey.slice(5) - 1, mname = monthName(S.m);
      const calName = new Date(Date.UTC(2001, mo, 1)).toLocaleDateString("en-GB", {month: "long", timeZone: "UTC"});
      const yEnd = new Date(EPOCH + (T - 1) * DAY).getUTCFullYear(), grid = [];
      for (let y = 1979; y <= yEnd; y++) for (let m = 0; m < 12; m++) {
        const q0 = dayIx(y, m, 1), q1 = dayIx(y, m + 1, 1), mi = (y - +M0.slice(0, 4)) * 12 + m - (+M0.slice(5) - 1);
        if (q1 <= T && mi >= 0 && mi < NM) grid.push({y, m, mi, v: spanDays(u, q0, q1)});
      }
      const same = grid.filter((q) => q.m === mo), me = grid.find((q) => q.mi === S.m), rank = 1 + same.filter((q) => q.v > me.v).length;
      const usual = median(same.filter((q) => q.y >= 1991 && q.y <= 2020).map((q) => q.v));
      const s = section(`${mname} in ${nm}`, `In ${mname}, ${nm} had ${me.v.toFixed(1)} heat spell days, averaged over its land area: the ${ordinal(rank)} most for a ${calName} in ${same.length} years. A usual ${calName} in 1991 to 2020 had ${usual.toFixed(1)}.`);
      block(s, `Every month since 1979`, `One row per year, one column per month, darker for more heat spell days in that month. Read down a column to follow one month through the years; the outlined cell is ${mname}. Click a cell to move the map and this page to that month.`);
      const top = Math.max(1, ...grid.map((q) => q.v)), cw = 30, ch = 9, x0 = 34, y0 = 16, rows = yEnd - 1979 + 1, parts = [];
      "JFMAMJJASOND".split("").forEach((c, m) => parts.push(`<text x="${x0 + m * cw + cw / 2}" y="11" class="mo">${c}</text>`));
      for (let y = 1979; y <= yEnd; y++) if (y % 5 === 0 || y === 1979) parts.push(`<text x="${x0 - 5}" y="${y0 + (y - 1979) * ch + ch - 1}" class="yl">${y}</text>`);
      for (const q of grid) parts.push(`<rect data-mi="${q.mi}" x="${x0 + q.m * cw}" y="${y0 + (q.y - 1979) * ch}" width="${cw - 1}" height="${ch - 1}" fill="${q.v < 0.05 ? "#efede7" : css(rampAt(0.12 + 0.88 * q.v / top))}"${q.mi === S.m ? ` class="on"` : ""}><title>${monthName(q.mi)}: ${q.v.toFixed(1)} heat spell days</title></rect>`);
      const g = el(`<svg class="mgrid" viewBox="0 0 ${x0 + 12 * cw + 2} ${y0 + rows * ch + 2}" role="img" aria-label="Grid of heat spell days in every month since 1979">${parts.join("")}</svg>`);
      g.addEventListener("click", (ev) => { const mi = ev.target && ev.target.getAttribute && ev.target.getAttribute("data-mi"); if (mi !== null && mi !== undefined) { S.m = +mi; setSlider(); render(true); } });
      const fig = el(`<div class="lensfig"></div>`);
      fig.append(g);
      s.append(fig);
      block(s, `Every ${calName} on record`, `Each dot is one ${calName}, placed by its heat spell days; darker dots are more recent. The ringed dot is ${mname} and the grey line is the usual value for 1991 to 2020.`);
      s.append(Plot.plot({...po, ariaLabel: `Heat spell days in every ${calName} from 1979, with ${Y} marked`, width: W, height: 120, marginBottom: 36, x: {label: "heat spell days in the month, averaged over the land area", grid: true, nice: true}, y: {axis: null, domain: [-1, 1]},
        marks: [Plot.ruleX([usual], {stroke: "#898781", strokeWidth: 2}), Plot.dot(same, {x: "v", y: 0, r: 5, fill: (q) => css(mix([200, 198, 190], [60, 59, 56], (q.y - 1979) / (yEnd - 1979))), fillOpacity: 0.85, title: (q) => `${calName} ${q.y}: ${q.v.toFixed(1)} days`}),
          Plot.dot([me], {x: "v", y: 0, r: 9, stroke: C.extreme, strokeWidth: 2.5, fill: "none"}), Plot.text([me], {x: "v", y: 0, text: () => String(Y), dy: -18, fontWeight: 600})]}));
      const byV = [...grid].sort((x, y) => y.v - x.v), myAll = 1 + grid.filter((q) => q.v > me.v).length, topM = byV.slice(0, 10);
      if (!topM.includes(me)) topM.push(me);
      block(s, `The heaviest months on record`, `Every month since 1979, of any time of year, ranked by its heat spell days. ${mname} is ${ordinal(myAll)} of ${grid.length}.`);
      s.append(el(`<table class="ev"><thead><tr><th>Rank</th><th>Month</th><th>Heat spell days</th><th>Against a usual month of that name</th></tr></thead><tbody>${topM.map((q) => {
        const us = median(grid.filter((z) => z.m === q.m && z.y >= 1991 && z.y <= 2020).map((z) => z.v));
        return `<tr class="${q === me ? "cur" : ""}"><td>${1 + grid.filter((z) => z.v > q.v).length}</td><td>${monthName(q.mi)}</td><td>${q.v.toFixed(1)}</td><td>${q.v - us >= 0 ? "+" : ""}${(q.v - us).toFixed(1)}</td></tr>`;
      }).join("")}</tbody></table>`));
      return new Set([5, 6]);
    }
    if (L === "msevere") {                                                    // the month as a wall calendar
      const mkey = monthKey(S.m), Y = +mkey.slice(0, 4), mo = +mkey.slice(5) - 1, mname = monthName(S.m), q0 = dayIx(Y, mo, 1), nd = dayIx(Y, mo + 1, 1) - q0;
      const days = [];
      for (let d = 0; d < nd && q0 + d < T; d++) { const sv = u.sevAt(q0 + d); days.push({d: d + 1, q: q0 + d, sp: u.spell[q0 + d], sv: sv === undefined || sv === 255 ? null : sv}); }
      const anySev = days.some((q) => q.sv !== null), half = days.filter((q) => q.sp >= 50).length, halfSev = days.filter((q) => q.sv !== null && q.sv >= 50).length, peak = days.reduce((x, q) => (q.sp > x.sp ? q : x), days[0]);
      const s = section(`${mname}, day by day, in ${nm}`, `On ${half} of the ${days.length} days of ${mname}, half or more of ${nm}'s land area was in a heat spell${anySev ? `, and on ${halfSev} of them half or more was severe or extreme` : ""}. The widest day was ${fmt(peak.q)}, with ${peak.sp}%.`);
      block(s, `The month as a calendar`, `One tile per day, Monday first. The tile's colour is the share of land in a heat spell that day: darker is more. ${anySev ? "The dark square inside a tile is the share that was severe or extreme: a square that fills the tile means all of the land." : "The share that was severe or extreme is published day by day only for the latest year and the days of the listed past events, so for this month the tiles show heat spells of any class."}`);
      const tile = 56, gap = 5, off = (new Date(EPOCH + q0 * DAY).getUTCDay() + 6) % 7, rowsN = Math.ceil((off + days.length) / 7), parts = [];
      ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].forEach((w, i) => parts.push(`<text x="${i * (tile + gap) + tile / 2}" y="11" class="wd">${w}</text>`));
      for (const q of days) {
        const k = off + q.d - 1, x = (k % 7) * (tile + gap), y = 18 + Math.floor(k / 7) * (tile + gap), f = q.sp / 100, side = q.sv ? tile * Math.sqrt(q.sv / 100) : 0;
        parts.push(`<g><title>${fmt(q.q)}: ${q.sp}% of land in a heat spell${q.sv !== null ? `, ${q.sv}% severe or extreme` : ""}</title><rect x="${x}" y="${y}" width="${tile}" height="${tile}" rx="4" fill="${q.sp ? css(rampAt(0.1 + 0.55 * f)) : "#efede7"}"/>`
          + (side > 1 ? `<rect x="${(x + (tile - side) / 2).toFixed(1)}" y="${(y + (tile - side) / 2).toFixed(1)}" width="${side.toFixed(1)}" height="${side.toFixed(1)}" rx="2" fill="${C.extreme}"/>` : "")
          + `<text x="${x + 5}" y="${y + 13}" class="dn${side > tile * 0.75 ? " inv" : ""}">${q.d}</text></g>`);
      }
      const fig = el(`<div class="lensfig"></div>`);
      fig.append(el(`<svg class="mcal" viewBox="0 0 ${7 * (tile + gap) - gap} ${18 + rowsN * (tile + gap)}" role="img" aria-label="Calendar of ${mname}: share of land area in a heat spell on each day">${parts.join("")}</svg>`));
      fig.append(key([[css(rampAt(0.2)), "Little of the land in a heat spell"], [css(rampAt(0.65)), "All of it"]].concat(anySev ? [[C.extreme, "Share severe or extreme (size of the square)"]] : [])));
      const note = el(`<p class="lensnote">Counting the map's cells.</p>`);
      fig.append(note);
      s.append(fig);
      const band = days.map((q) => {
        const v = [];
        for (let y = 1991; y <= 2020; y++) { const qq = dayIx(y, mo, q.d); if (new Date(EPOCH + qq * DAY).getUTCMonth() === mo) v.push(u.spell[qq] / 100); }
        v.sort((x, y) => x - y);
        return {d: q.d, sp: q.sp / 100, lo: v[Math.floor(0.1 * (v.length - 1))], md: v[Math.floor(0.5 * (v.length - 1))], hi: v[Math.ceil(0.9 * (v.length - 1))]};
      });
      const above = band.filter((q) => q.sp > q.hi).length;
      block(s, `The month against its usual range`, `The dark line is the share of land in a heat spell on each day of ${mname}. The grey band is where that share fell on the same date in nine years out of ten in 1991 to 2020, and the dashed line is the middle year. On ${above} of the ${band.length} days the month was above the band.`);
      s.append(Plot.plot({...po, ariaLabel: `Share of land area in a heat spell on each day of ${mname}, against the range for the same dates in 1991 to 2020`, width: W, height: 240, x: {label: "day of the month", ticks: band.filter((q) => q.d === 1 || q.d % 5 === 0).map((q) => q.d)}, y: {label: "share of land area", tickFormat: "%", grid: true, domain: [0, 1]},
        marks: [Plot.areaY(band, {x: "d", y1: "lo", y2: "hi", fill: "#d9d7cf", curve: "step"}), Plot.lineY(band, {x: "d", y: "md", stroke: "#6b6963", strokeDasharray: "3 3", curve: "step"}),
          Plot.lineY(band, {x: "d", y: "sp", stroke: C.extreme, strokeWidth: 2.2}), Plot.dot(band, {x: "d", y: "sp", r: 2.5, fill: C.extreme, title: (q) => `Day ${q.d}: ${(q.sp * 100).toFixed(0)}% of land; usual range ${(q.lo * 100).toFixed(0)}% to ${(q.hi * 100).toFixed(0)}%`})]}));
      const wide = [...days].sort((x, y) => y.sp - x.sp || x.d - y.d).slice(0, 5);
      block(s, `The five widest days`, `The days of ${mname} when the most land was in a heat spell.`);
      s.append(el(`<table class="ev"><thead><tr><th>Rank</th><th>Date</th><th>Land in a heat spell</th><th>Of which severe or extreme</th></tr></thead><tbody>${wide.map((q, i) =>
        `<tr><td>${i + 1}</td><td>${fmt(q.q)}</td><td>${q.sp}%</td><td>${q.sv === null ? "not published for this day" : q.sv + "%"}</td></tr>`).join("")}</tbody></table>`));
      (async () => {
        const res = spread(await monthlyLayer(L, S.m), unitCells(u.level, u.row), MBINS);
        if (note.isConnected) note.textContent = `On the map's own count, half of the land area had ${res.q(0.5)} or more severe or extreme days in ${mname}, and the most affected tenth had ${res.q(0.9)} or more.`;
      })().catch((err) => { console.error(err); if (note.isConnected) note.textContent = ""; });
      return new Set([5, 6]);
    }
    if (L === "season") {
      const s = section(`Where the season stands in ${nm}`, `In the week to ${fmt(T - 1)}: where heat is new, where it is back, where it has gone on for weeks, and where it has just ended. This uses the latest 12 weeks of data, whatever date the slider shows.`);
      block(s, `The land area in 100 squares`, `Each square is one percent of ${nm}'s land area, coloured as on the map. Yellow is heat that is new, purple is heat that came back after a break, the oranges are heat that has gone on for two weeks or more (darker is longer), and blue is where it has just ended.`);
      const f1 = el(`<div class="lensfig"><p class="ph">Counting the map's cells.</p></div>`);
      s.append(f1);
      block(s, `How long the heat has gone on`, `Of the land still in a heat spell, how many weeks in a row it has been in one. A cell counts for a week when it was in a heat spell on at least one day of it.`);
      const f2 = el(`<div class="lensfig"></div>`);
      s.append(f2);
      later(f1, async () => {
        const code = await fixedLayer("season"), cells = unitCells(u.level, u.row), run = new Float64Array(13);
        let all = 0, nw = 0, ag = 0, en = 0;
        for (let k = 0; k < cells.ix.length; k++) { const v = code[cells.ix[k]], w = cells.w[k]; if (v === 255) continue; all += w; if (v === 1) nw += w; else if (v === 2) ag += w; else if (v === 5) en += w; else if (v >= 10) run[Math.min(12, v - 10)] += w; }
        const p = (v) => all ? 100 * v / all : 0, short = p(run[2] + run[3]), mid = p(run[4] + run[5] + run[6] + run[7]), long = p(run.slice(8).reduce((a, b) => a + b, 0)), still = short + mid + long;
        const none = Math.max(0, 100 - p(nw) - p(ag) - p(en) - still);
        const rows = [];
        for (let k = 2; k <= 12; k++) if (run[k] > 0) rows.push({k: k === 12 ? "12" : String(k), v: p(run[k]) / 100});
        f2.replaceChildren(rows.length ? Plot.plot({...po, ariaLabel: "Share of land area still in a heat spell, by weeks in a row", width: Math.min(W, 620), height: 200, x: {label: "weeks in a row, to the latest week", domain: ["2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]}, y: {label: "share of land area", tickFormat: "%", grid: true},
          marks: [Plot.barY(rows, {x: "k", y: "v", fill: (q) => css(mix([217, 120, 60], [116, 41, 12], Math.min(1, (+q.k - 2) / 6))), title: (q) => `${q.k} weeks in a row: ${(q.v * 100).toFixed(0)}% of land area`}), Plot.ruleY([0], {stroke: "#c3c2b7"})]})
          : el(`<p class="ph">No part of ${nm} has been in a heat spell for two weeks in a row.</p>`));
        return [waffle([[p(nw), "#f0c419", "New"], [p(ag), "#a14fb0", "Again after a break"], [short, "#d9783c", "Still, 2 to 3 weeks"], [mid, "#a8501f", "Still, 4 to 7 weeks"], [long, "#74290c", "Still, 8 weeks or more"], [p(en), "#7fa3c7", "Just ended"], [none, "#e7e6e1", "None of these"]]),
          key([["#f0c419", `New ${p(nw).toFixed(0)}%`], ["#a14fb0", `Again ${p(ag).toFixed(0)}%`], ["#d9783c", `Still, 2 to 3 weeks ${short.toFixed(0)}%`], ["#a8501f", `4 to 7 weeks ${mid.toFixed(0)}%`], ["#74290c", `8 weeks or more ${long.toFixed(0)}%`], ["#7fa3c7", `Just ended ${p(en).toFixed(0)}%`], ["#e7e6e1", `None of these ${none.toFixed(0)}%`]]),
          el(`<p class="lensnote">${still >= 1 ? `${still.toFixed(0)}% of the land area is still in a heat spell from the week before` : "Almost none of the land area is still in a heat spell from the week before"}; ${p(nw).toFixed(0)}% is in one for the first time in 12 weeks. This grouping is this project's own and has not been tested on documented events.</p>`)];
      }, "The season status layer");
      return new Set(["where", 5, 6]);
    }
    if (L === "trend") {
      const years = yearRow(u), dec = [];
      for (let a = 1979; a <= yN; a += 10) { const g = years.filter((q) => q.y >= a && q.y < a + 10); dec.push({a, b: Math.min(a + 9, yN), v: g.reduce((x, q) => x + q.v, 0) / g.length, n: g.length}); }
      const first = dec[0], last = dec[dec.length - 1];
      const s = section(`Then and now in ${nm}`, `In ${first.a} to ${first.b}, ${nm} had ${first.v.toFixed(1)} heat spell days a year, averaged over its land area. In ${last.a} to ${last.b} it had ${last.v.toFixed(1)}${last.n < 10 ? ` (${last.n} years)` : ""}.`);
      block(s, `Decade by decade`, `Each dot is one year. Each step is the average of ten years, so the staircase shows the change without drawing a line through it. The last step covers ${last.n} years.`);
      s.append(Plot.plot({...po, ariaLabel: `Heat spell days per year with ten-year averages drawn as steps, 1979 to ${yN}`, width: W, height: 260, x: {label: null, tickFormat: "d"}, y: {label: "heat spell days per year", grid: true},
        marks: [Plot.dot(years, {x: "y", y: "v", r: 2.5, fill: "#898781", title: (q) => `${q.y}: ${q.v.toFixed(1)} days`}),
          Plot.link(dec, {x1: (q) => q.a - 0.4, x2: (q) => q.b + 0.4, y1: "v", y2: "v", stroke: C.severe, strokeWidth: 3}),
          Plot.text(dec, {x: (q) => (q.a + q.b) / 2, y: "v", text: (q) => q.v.toFixed(1), dy: -9, fontWeight: 600, fill: C.extreme})]}));
      // which part of the year changed: each calendar month, the earlier half of the record against the later half
      const mid = Math.floor((1979 + yN) / 2), MN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], mrows = [];
      for (let m = 0; m < 12; m++) {
        let a = 0, na = 0, b = 0, nb2 = 0;
        for (let y = 1979; y <= yN; y++) { const v = spanDays(u, dayIx(y, m, 1), dayIx(y, m + 1, 1)); if (y <= mid) { a += v; na++; } else { b += v; nb2++; } }
        mrows.push({m: MN[m], a: a / na, b: b / nb2});
      }
      const gain = mrows.reduce((x, q) => (q.b - q.a > x.b - x.a ? q : x), mrows[0]);
      block(s, `Which months changed`, `One row per calendar month. The grey dot is the average number of heat spell days in that month in 1979 to ${mid}; the coloured dot is the average in ${mid + 1} to ${yN}. The longer the line between them, the more that month changed. Orange lines are more heat, blue lines less.`);
      s.append(key([["#898781", `1979 to ${mid}`], [C.severe, `${mid + 1} to ${yN}: more`], ["#1854a0", `${mid + 1} to ${yN}: fewer`]]));
      s.append(Plot.plot({...po, ariaLabel: `Heat spell days in each calendar month, 1979 to ${mid} against ${mid + 1} to ${yN}`, width: Math.min(W, 760), height: 330, marginLeft: 44, x: {label: "heat spell days in the month, average of the period", grid: true, nice: true}, y: {label: null, domain: MN},
        marks: [Plot.link(mrows, {y1: "m", y2: "m", x1: "a", x2: "b", stroke: (q) => (q.b >= q.a ? C.severe : "#1854a0"), strokeWidth: 3}), Plot.dot(mrows, {y: "m", x: "a", r: 4.5, fill: "#898781"}),
          Plot.dot(mrows, {y: "m", x: "b", r: 5.5, fill: (q) => (q.b >= q.a ? C.severe : "#1854a0"), title: (q) => `${q.m}: ${q.a.toFixed(1)} then, ${q.b.toFixed(1)} now`})]}));
      const pm = u.trend ? Math.max(u.trend[1], u.trend[2]) : NaN, f = (v) => (v < 0.001 ? "below 0.001" : v.toFixed(3));
      const note = el(`<p class="lensnote">${gain.b > gain.a ? `The month that gained most is ${gain.m}: ${gain.a.toFixed(1)} days then, ${gain.b.toFixed(1)} now.` : "No month gained heat spell days."} ${u.trend ? `For the whole year the change is ${u.trend[0] > 0 ? "+" : ""}${u.trend[0].toFixed(1)} days per decade; ${pm < 0.05 ? "a change of this size is unlikely to be chance alone" : "this cannot be told apart from no trend"} (Mann-Kendall p ${f(u.trend[1])}, and ${f(u.trend[2])} after allowing for one year resembling the next).` : ""} <span class="cellnote"></span> The source is a reanalysis whose inputs change over the years, which can add or hide a trend, and the yardstick is fixed on 1991 to 2020.</p>`);
      s.append(note);
      block(s, `The decades in numbers`, `For each ten years: the average, and the heaviest and lightest single year.`);
      s.append(el(`<table class="ev"><thead><tr><th>Years</th><th>Average, days a year</th><th>Heaviest year</th><th>Lightest year</th><th>Change from the first decade</th></tr></thead><tbody>${dec.map((q) => {
        const g = years.filter((z) => z.y >= q.a && z.y <= q.b), hi = g.reduce((x, z) => (z.v > x.v ? z : x), g[0]), lo = g.reduce((x, z) => (z.v < x.v ? z : x), g[0]);
        return `<tr><td>${q.a} to ${q.b}</td><td>${q.v.toFixed(1)}</td><td>${hi.y} (${hi.v.toFixed(1)})</td><td>${lo.y} (${lo.v.toFixed(1)})</td><td>${q === first ? "" : (q.v - first.v >= 0 ? "+" : "") + (q.v - first.v).toFixed(1)}</td></tr>`;
      }).join("")}</tbody></table>`));
      (async () => {
        const code = await fixedLayer("trend"), cells = unitCells(u.level, u.row);
        let all = 0, up = 0, dn = 0;
        for (let k = 0; k < cells.ix.length; k++) { const v = code[cells.ix[k]], w = cells.w[k]; if (v === 255) continue; all += w; if (v > 128) up += w; else if (v > 0 && v < 128) dn += w; }
        const sp = note.querySelector(".cellnote");
        if (sp && all) sp.textContent = `On the map, ${Math.round(100 * up / all)}% of the land area has an upward trend that passes the test and ${Math.round(100 * dn / all)}% a downward one.`;
      })().catch((err) => console.error(err));
      return new Set([5, 6]);
    }
    // humid heat (experimental)
    const r = [], has = u.hu && u.huAt;
    let nH = 0, more = 0;
    if (has) for (let q = Math.max(0, t - 89); q <= t; q++) { const h = u.huAt(q); if (h === undefined || h === 255) continue; nH++; if (h > u.spell[q]) more++; r.push({date: new Date(EPOCH + q * DAY), up: u.spell[q] / 100, down: -h / 100, h, sp: u.spell[q], q}); }
    const s = section(`Heat and humid heat in ${nm}`, has && nH ? `${cavShort(u)}Over the ${nH} days to ${fmt(t)} with a humid reading, humid heat covered more of ${nm} than the temperature heat spell did on ${more} of them.` : `Humid heat is not published for ${nm} on these dates.`);
    if (has && nH) {
      block(s, `Two measures, back to back`, `Above the line, in orange: the share of land in a heat spell judged on temperature alone. Below the line, in blue-green: the share in a humid heat spell, where heat and humidity together were unusual for the date. Where the lower shape is the larger one, the air was more unusual for its humidity than for its temperature.`);
      s.append(key([[C.severe, "Heat spell (temperature)"], [css(HUMCOL), "Humid heat spell (experimental)"]]));
      s.append(Plot.plot({...po, ariaLabel: `Share of land area in a heat spell above the axis and in a humid heat spell below it, ${nH} days to ${fmt(t)}`, width: W, height: 300, x: {label: null}, y: {label: "share of land area", grid: true, domain: [-1, 1], tickFormat: (v) => Math.abs(v * 100) + "%"},
        marks: [Plot.areaY(r, {x: "date", y: "up", fill: C.severe, fillOpacity: 0.85, curve: "step"}), Plot.areaY(r, {x: "date", y: "down", fill: css(HUMCOL), fillOpacity: 0.85, curve: "step"}), Plot.ruleY([0], {stroke: "#3f3e3a"}),
          Plot.tip(r, Plot.pointerX({x: "date", y: 0, title: (q) => `${fmt(q.q)}\nHeat spell ${q.sp}% of land\nHumid heat spell ${q.h}% of land`}))]}));
      block(s, `One measure against the other`, `Each dot is one day: how much of the land was in a heat spell (across) and how much was in a humid heat spell (up). Darker dots are more recent. Dots above the dashed line are days when humid heat was the wider of the two.`);
      s.append(Plot.plot({...po, ariaLabel: `Each day's share of land in a heat spell against its share in a humid heat spell, ${nH} days to ${fmt(t)}`, width: Math.min(W, 460), height: 420, marginBottom: 40, x: {label: "share of land in a heat spell", tickFormat: "%", domain: [0, 1], grid: true}, y: {label: "share in a humid heat spell", tickFormat: "%", domain: [0, 1], grid: true},
        marks: [Plot.link([{a: 0, b: 1}], {x1: "a", y1: "a", x2: "b", y2: "b", stroke: "#898781", strokeDasharray: "4 4"}),
          Plot.dot(r, {x: "up", y: (q) => q.h / 100, r: 4, fill: (q, i) => css(mix([190, 214, 218], HUMCOL, i / Math.max(1, r.length - 1))), stroke: "#fff", strokeWidth: 0.5, title: (q) => `${fmt(q.q)}
Heat spell ${q.sp}%
Humid heat spell ${q.h}%`})]}));
      const humTop = [...r].sort((x, y) => y.h - x.h || x.q - y.q).slice(0, 5);
      block(s, `The widest humid heat days`, `The five days in this window when humid heat covered the most land, with the temperature heat spell share on the same day.`);
      s.append(el(`<table class="ev"><thead><tr><th>Rank</th><th>Date</th><th>Humid heat spell</th><th>Heat spell</th><th>Wider measure</th></tr></thead><tbody>${humTop.map((q, i) =>
        `<tr><td>${i + 1}</td><td>${fmt(q.q)}</td><td>${q.h}%</td><td>${q.sp}%</td><td>${q.h > q.sp ? "Humid heat" : q.h < q.sp ? "Heat spell" : "Equal"}</td></tr>`).join("")}</tbody></table>`));
      s.append(el(`<p class="ph warn"><b>Experimental.</b> Humid heat here was flagged on ${u.hu.base.toFixed(0)} days a year in 1991 to 2020 and on ${u.hu.rec.toFixed(0)} days a year in 2021 to 2025, averaged over the land area. The humidity record in the source data drifts, so part of that rise is not climate. It is a yes or no reading with no severity, and it is not a wet-bulb temperature. Evidence: ${evid("humid", "humid heat against weather stations")}.</p>`));
    }
    return new Set([5, 6]);
  }
  const cavShort = (u) => caveat(trust(u.level, u.row));
  function renderStory(d) {
    story.innerHTML = "";
    if (!d || !d.story) return;
    const u = d.story, t = d.t, W = Math.min(1100, story.clientWidth || 1000), D = (tt) => new Date(EPOCH + tt * DAY);
    const tr = trust(u.level, u.row), cav = caveat(tr), nm = esc(u.name || "this area");
    if (cav) story.append(el(`<p class="ph warn"><b>Read with care.</b> ${cav}This applies to every chart and number below. ${[tr.low > 50 ? evid("low", "Why the signal is weak here: the comparison with weather stations") : "", tr.sus >= 25 ? evid("sus", "How the break was found") : ""].filter(Boolean).join(". ")}.</p>`));
    if (d.dist || (S.level === "adm2")) story.append(el(`<p class="ph">The sections below are for ${nm}, the ${LEVELS[u.level].toLowerCase()} this district belongs to. Full histories are not published for districts.</p>`));
    const want = renderLens(u, t, W);                                         // the opening section for the layer on the map, and which standard sections follow it
    if (want.has(1)) { // 1
      const s = section("How much of it was in heat on the chosen date?", `${cav}On ${fmt(t)}, ${u.now.spell}% of ${nm}'s land area was in a heat spell: ${u.now.extreme}% of the land area extreme, ${u.now.severe - u.now.extreme}% severe and ${u.now.spell - u.now.severe}% in the lowest class.`);
      block(s, `Share of land area in a heat spell, by class, 90 days to ${fmt(t)}`, "Each day's column adds up to the share of land in a heat spell. Darker is more severe. A day's class describes that day only and does not change afterwards.");
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
        block(s, `Hot days and hot nights, 90 days to ${fmt(t)}`, (r2.length < 4 * Math.min(90, t + 1) ? "Days with no column were not published for this measure. " : "") + "A day counts as hot when the maximum is above its usual top tenth for the date, a night when the minimum is. \"Both\" means no relief at night. The classes never overlap, so a column is the share of land area that was hot by day, by night, or both. Grey is land that was hot for the date but outside its own warm half of the year: shown, not counted as heat. This is this project's own measure and has not been tested on documented events.");
        s.append(key([[DNC.night, "Hot night only"], [DNC.day, "Hot day only"], [DNC.both, "Hot day and hot night"], [DNC.off, "Outside the warm season"]]));
        s.append(Plot.plot({...po, ariaLabel: `Stacked columns: share of land area hot by day, by night, or both, each day of the 90 days to ${fmt(t)}`, width: W, height: 200,
          y: {label: "share of land area", tickFormat: "%", domain: [0, 1], grid: true}, x: {label: null, domain: [D(Math.max(0, t - 89)), D(t + 1)]}, color: {domain: ["night", "day", "both", "off"], range: [DNC.night, DNC.day, DNC.both, DNC.off]},
          marks: [Plot.rectY(r2, {x: "date", y: "v", fill: "cls", interval: "day", order: ["both", "day", "night", "off"], insetLeft: 0.5, insetRight: 0.5}), Plot.ruleY([0], {stroke: "#c3c2b7"}),
            Plot.tip(tip2, Plot.pointerX({x: "date", y: "top", title: "t"}))]}));
      }
      if (u.hu && u.hu.share !== undefined) {
        block(s, "Humid heat (experimental)");
        s.append(el(`<p>On ${fmt(t)}, ${u.hu.share}% of ${nm}'s land area was in a humid heat spell: three or more days in a row when heat and humidity together were unusual for the date. This is a yes or no reading, with no severity.</p>`));
        s.append(el(`<p class="ph warn"><b>Experimental.</b> Humid heat here is judged against 1991 to 2020. The humidity record in the source data drifts, so recent years are flagged far more often than the past for reasons that are partly not climate. Here it was flagged on ${u.hu.base.toFixed(0)} days a year in 1991 to 2020 and on ${u.hu.rec.toFixed(0)} days a year in 2021 to 2025, averaged over the land area. It takes no part in the status, the events, the ranks or the trend on this page, and it is not a wet-bulb reading: the source data is too low in absolute humid heat to give one. Evidence: ${evid("humid", "humid heat against weather stations")}.</p>`));
      }
      if (!u.dn || !u.hu) s.append(el(`<p class="ph">${u.dn ? "" : "Hot days against hot nights are not in this build. "}${u.hu ? "" : "Humid heat is not in this build."}</p>`));
    }
    const e = u.ev, cur = eventAt(u, t), evs = e.start.map((st, i) => ({start: st, days: e.days[i], peak: e.peak[i] / 100, size: e.size[i], cur: cur && cur.i === i}));
    if (want.has(2)) { // 2
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
    if (want.has(3)) { // 3
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
    if (want.has("where")) {
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
        const go = () => drawWeeks(wrap, cell[u.level], u.row).catch((err) => { console.error(err); weekCache.clear(); evCache.clear(); wrap.append(el(`<p class="ph">The weekly maps could not be loaded.</p>`)); });
        if ("IntersectionObserver" in window) {                               // the daily maps behind them are only fetched once the reader scrolls near
          const io = new IntersectionObserver((en) => { if (en.some((q) => q.isIntersecting)) { io.disconnect(); go(); } }, {rootMargin: "800px"});
          io.observe(wrap);
        } else go();
      } else {
        const s = section("Where inside it, and is it the same places again?", "Not in this build.");
        s.append(el(`<p class="ph">Week-by-week maps of where the heat sat inside this place are not in this build.</p>`));
      }
    }
    if (want.has(4)) { // 4
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
    if (want.has(5)) { // 5
      const low = tr.low, red = tr.red, sus = tr.sus, p = (v) => v;
      const s = section("How far to trust this", "Three things decide how much weight these numbers can bear here.");
      s.append(el(`<ul>
        <li><b>Confidence.</b> ${p(low)}% of this unit's land area is in the low-confidence class and ${p(red)}% in the reduced class. Where day-to-day temperature varies little, a small shift crosses the thresholds on many days, and the data follows observed hot days less well. Low-confidence areas are hatched on the map. Evidence: ${evid("low", "the comparison with weather stations")} and ${evid("rule", "the rule that sets the classes")}.</li>
        <li><b>Data suspect: ${p(sus)}% of this unit.</b> ${man.counts.data_suspect_cells.toLocaleString("en-GB")} grid cells in three regions have a known break in the source data, shown by weather stations. They are marked on the map and kept in every number. Evidence: ${evid("sus", "how the breaks were found")}.</li>
        <li><b>Based on ${u.cells.toLocaleString("en-GB")} grid cells</b> of about 10 km. Every share is of land area, not of people.</li>
        <li><b>The yardstick.</b> Severe and extreme are relative to the time of year in this place's own 1991 to 2020 climate. The heat spell test also counts days that are simply among the hottest of the year here, so the lowest class is not always unusual for its date. Neither is adjusted for warming since 2020.</li>
        <li><b>No uncertainty is quantified</b> in this build.</li></ul>`));
    }
    if (want.has(6)) { // 6
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
      $("pname").textContent = "Could not load this place";
      $("pnote").textContent = "The data for this place could not be loaded. Choose it again, or reload the page, to try once more."; $("pnote").style.display = "";
      drawMap(my).catch((e2) => console.error(e2));                           // the map itself can still be shown
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
    if (S.p > 0) link.set("p", iso(PERIODS[S.p].days[0]));
    if (S.pt) link.set("pt", S.pt.lat.toFixed(2) + "," + S.pt.lon.toFixed(2)); else if (S.sel && S.sel.adm1 >= 0) { link.set("u", admins.adm1[S.sel.adm1].id); if (d && d.dist) link.set("d2", d.dist.id); }
    try { history.replaceState(null, "", "#" + link.toString()); } catch (err) { /* some browsers limit how often the address may change */ }
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
    ++token;                                                                  // a draw still under way must not print the old place under the new date
    S.p = +psel.value;
    S.k = S.p === 0 ? PERIODS[0].days.length - 1 : Math.floor(PERIODS[S.p].days.length / 2);       // a past event: its middle day, until the place is known
    setSlider();
    const bb = PERIODS[S.p].bbox, pi = S.p;
    if (bb) try {                                                             // a past event: move the map to its region and choose a province there
      map.fitBounds([[bb[0], bb[1]], [bb[2], bb[3]]], {animate: false, padding: 20});
      // the event's own focus place decides the province: its cell, or failing that a cell next to it (a focus on the coast can fall in the sea)
      const fo = PERIODS[pi].focus;
      let top = null;
      if (fo) {
        const fr = Math.round((90 - fo[0]) / 0.1), fc = ((Math.round((fo[1] + 180) / 0.1) % NC) + NC) % NC;
        for (const [dr, dc] of [[0, 0], [0, -1], [0, 1], [-1, 0], [1, 0], [-1, -1], [-1, 1], [1, -1], [1, 1]]) {
          const r = fr + dr, c = (fc + dc + NC) % NC, a1 = r >= 0 && r < NR ? cell.adm1[r * NC + c] : -1;
          if (a1 >= 0 && admins.adm1[a1].series) { top = [a1]; break; }
        }
      }
      if (!top) {                                                             // no focus: the province in view with the most severe area on the middle day
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
        top = inside(sev) || inside(any);
      }
      if (pi !== S.p) return;                                                 // another period was chosen meanwhile
      if (top) {
        S.sel = {adm1: top[0], adm0: admins.adm1[top[0]].adm0, adm2: -1}; S.level = "adm1"; S.pt = null; S.msg = ""; pin.remove(); $("find").value = "";
        // open on the day of the event when most of that province was severe or extreme, not on a quiet day
        const d = await unitData(), u = d && d.shown;
        if (pi !== S.p) return;
        if (u) {
          let bk = -1, bv = 0;
          PERIODS[pi].days.forEach((q, k) => { const v = u.sevAt(q); if (v !== undefined && v !== 255 && v > bv) { bv = v; bk = k; } });
          if (bk >= 0) { S.k = bk; setSlider(); }
        }
      }
    } catch (err) { console.error(err); }
    render(true);
  });
  setSlider();
  slider.addEventListener("input", () => { if (isMonth()) S.m = +slider.value; else if (isYear()) S.y = +slider.value; else S.k = +slider.value; render(false); });
  $("layer").addEventListener("change", () => { S.layer = $("layer").value; setSlider(); render(true); });   // the story under the map follows the layer
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
  $("find").addEventListener("input", () => $("find").setCustomValidity(""));
  $("find").addEventListener("change", () => {
    const hit = places.get($("find").value);
    if (!hit) {
      if ($("find").value.trim()) { $("find").setCustomValidity("No country or province has that name. Choose one from the list."); $("find").reportValidity(); }
      return;
    }
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
