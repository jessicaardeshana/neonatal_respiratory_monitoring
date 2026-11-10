// Pipeline view: click through the seven processing stages. Every plot is the REAL pipeline output
// (simulated input). Left: stages. Middle: before/after plots. Right: plain-language explanation.
import { bisect, clamp, fmtTime, h, svgIcon, ICON } from "./util.js";
import { drawChart, fitCanvas, COLORS } from "./chart.js";
import { ThermalPlayer, LUT } from "./player.js";

const WINDOWS = [{ id: "30", label: "Last 30 s", s: 30 }, { id: "60", label: "Last 60 s", s: 60 }, { id: "all", label: "Whole recording", s: 0 }];
const M = { l: 52, r: 16, t: 8 };
const SOFT = { amber: "rgba(214,162,74,.12)", red: "rgba(214,90,90,.16)", blue: "rgba(111,159,212,.16)" };
const nums = a => a.filter(v => v != null);
const FACE = COLORS.accent, CHEEK = "#a9dcb9", BG = "#8e99a6", TRUTH = "rgba(214,162,74,.8)";

// ------------------------------------------------------------------ the words
const STAGES = [
  { id: "frames", title: "Frames & regions", sub: "Where we look", layout: "split",
    what: "The camera gives a 60×80 grid of temperatures about 8.7 times a second. We draw three small boxes: one under the nostrils where breath flows, one on the cheek where there is no airflow, and one on the background wall where there is no body at all.",
    why: "Breathing changes the temperature of only a tiny patch. The cheek and the background boxes are lie detectors: if they wiggle with the breathing, something other than breath is going on.",
    how: "In the simulation the boxes sit at known positions. With a real camera you draw the nose box by hand (automatic nose finding is future work).",
    look: "The nose box warms and cools. The cheek and background boxes stay almost flat." },
  { id: "average", title: "Average the box", sub: "Many pixels → one number", layout: "split",
    what: "Inside the nose box we average all the pixels into one number per frame. Strung together over time, those numbers are the raw breathing signal.",
    why: "One clean number per frame is far easier to analyze than 18 jittery pixels, and averaging cancels random sensor noise.",
    how: "Mean of the box (the default). Taking the hottest pixel instead is possible, but our tests found it noisier at newborn breathing speeds.",
    look: "Each rise is an exhale (warm air), each fall an inhale (cool air). The swing is about a degree." },
  { id: "ffc", title: "Repair camera glitches", sub: "Calibration clicks", layout: "stack2", compare: true,
    what: "Every couple of minutes the camera closes a shutter to recalibrate (FFC). The picture freezes for a moment and the whole image's temperature jumps. We detect both and patch the frozen frames with a straight line.",
    why: "A sudden jump looks exactly like the start of a breath. Left alone, the software would count calibration clicks as breathing: our tests show fake breath-sized bumps appear when this step is off.",
    how: "A frozen frame is identical to the one before it. A jump is the whole-scene average moving by more than 0.05 °C in one frame, which breathing (a tiny patch) can never do. Real cameras do this every 2-3 minutes; the demo speeds it up.",
    look: "Amber marks show the repaired frames. The level jump is still there: the next stage removes it." },
  { id: "background", title: "Remove drift & jumps", sub: "Subtract the background", layout: "stack2", compare: true,
    what: "The background patch cannot breathe, but it sees the same slow warming and the same calibration jump as the nose. We subtract what the background sees from the nose signal.",
    why: "Drift and jumps affect every pixel in the same way; breathing affects only the nose. So subtracting the background removes everything except breathing.",
    how: "The background trace is lined up with the nose at the start of the recording, then subtracted. No tuning needed.",
    look: "Top: nose and background drift and jump together. Bottom: after subtracting, the staircase is gone and only the breathing wiggle remains." },
  { id: "bandpass", title: "Keep only breathing speeds", sub: "Band-pass filter", layout: "l5", compare: true,
    what: "We keep only rhythms between 6 and 42 breaths a minute (adult setting; newborns use 30-90) and discard everything slower, such as drift, or faster, such as noise.",
    why: "Breathing lives in a known range of speeds. Anything outside it is not breathing, so removing it makes the real rhythm clear.",
    how: "A standard smooth filter, applied forwards and backwards so it adds no delay. The band comes from the adult or newborn profile.",
    look: "On the right (a spectrum: how big each rhythm is), the breathing peak survives while slow drift and fast noise fall away." },
  { id: "rate", title: "Read the breathing rate", sub: "Two methods agree", layout: "l6",
    what: "Two independent methods look at the last 30 seconds. Counting finds the peaks (one per breath) and measures the time between them. The spectrum finds the strongest repeating rhythm.",
    why: "Two methods that agree give confidence. A quality score says how much of the signal sits at one rhythm; if it is below 50% we show no number rather than a wrong one.",
    how: "A 30 second window means the spectrum cannot separate rates closer than 2 breaths/min on its own, so the peak is interpolated. A longer window is steadier but reacts slower.",
    look: "Peaks are marked on the signal, the highest bump in the spectrum is the rate, and both numbers should agree. Move to the pause and watch the number disappear." },
  { id: "apnea", title: "Decide: is breathing stopping?", sub: "Apnea alarm", layout: "l7",
    what: "We measure how big the breathing swing is (its strength) and compare it with what is normal for this baby over the last few minutes. If it drops below a quarter of normal for about 20 seconds, we raise an apnea alarm.",
    why: "A pause of 20 seconds or more is the clinical definition of apnea. Learning \"normal\" from the recent past adapts to each baby, and the baseline is frozen during a pause so it never learns that a pause is normal.",
    how: "Strength = a 4 second average of the signal size. Normal = the median over the last 3 minutes. Threshold = 25% of normal. The alarm needs about 20 s (with 1.5 s of tolerance).",
    look: "Strength dips below the red line at the pause. The alarm is raised only after the dip has lasted long enough, and clears when breathing returns." },
];

// ------------------------------------------------------------------ small helpers
function visRange(items, x0, x1, { pad = 0.14, minSpan = 0.2 } = {}) {
  let lo = Infinity, hi = -Infinity;
  for (const [xs, ys, off = 0] of items) {
    const i0 = Math.max(0, bisect(xs, x0)), i1 = Math.min(xs.length - 1, bisect(xs, x1));
    for (let i = i0; i <= i1; i++) { const v = ys[i]; if (v != null) { lo = Math.min(lo, v + off); hi = Math.max(hi, v + off); } }
  }
  if (!isFinite(lo)) return [0, 1];
  const span = Math.max(minSpan, hi - lo), mid = (lo + hi) / 2, half = span / 2 * (1 + pad * 2);
  return [mid - half, mid + half];
}
function placeholder(canvas, text) {
  const { ctx, w, h: hh } = fitCanvas(canvas); ctx.clearRect(0, 0, w, hh);
  ctx.fillStyle = COLORS.text; ctx.font = "13px ui-sans-serif, -apple-system, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(text, w / 2, hh / 2);
}
function drawLanes(canvas, { x, t, lanes }) {
  const { ctx, w, h: hh } = fitCanvas(canvas), l = 52, r = 16, laneH = (hh - 26) / lanes.length;
  ctx.clearRect(0, 0, w, hh); ctx.font = "11.5px ui-sans-serif, -apple-system, sans-serif";
  const X = v => l + (v - x[0]) / (x[1] - x[0]) * (w - l - r);
  lanes.forEach((ln, i) => {
    const y = 4 + i * laneH;
    ctx.fillStyle = "#12171d"; ctx.fillRect(l, y, w - l - r, laneH - 4);
    ctx.fillStyle = COLORS.text; ctx.textAlign = "right"; ctx.textBaseline = "middle"; ctx.fillText(ln.label, l - 8, y + (laneH - 4) / 2);
    for (const [a, b] of ln.spans) { const x0 = Math.max(l, X(a)), x1 = Math.min(w - r, X(Math.min(b, t))); if (x1 > x0) { ctx.fillStyle = ln.color; ctx.fillRect(x0, y, x1 - x0, laneH - 4); } }
  });
  const tx = Math.round(X(t)) + 0.5; ctx.strokeStyle = "rgba(228,232,237,.8)"; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(tx, 2); ctx.lineTo(tx, hh - 20); ctx.stroke();
  ctx.fillStyle = COLORS.text; ctx.textAlign = "center"; ctx.textBaseline = "top";
  for (let v = Math.ceil(x[0] / 10) * 10; v <= x[1]; v += (x[1] - x[0]) > 100 ? 30 : 10) ctx.fillText(fmtTime(v), X(v), hh - 16);
}

export function buildPipeline(state) {
  let run = null, pendingFocus = true, stageIdx = 0, win = WINDOWS[0], compare = "stacked", slots = [], wData = null, sData = null, wKey = "", sKey = "", wBusy = false, sBusy = false;
  const root = h("div", { class: "pipe" });

  // ---- stepper (left)
  const stepBtns = STAGES.map((s, i) => h("button", { class: "step", "aria-current": String(i === 0), onclick: () => select(i) },
    h("span", { class: "n" }, String(i + 1)), h("span", { class: "tt" }, h("b", {}, s.title), h("small", {}, s.sub))));
  const stepper = h("nav", { class: "card stepper", "aria-label": "Pipeline stages" }, h("div", { class: "card-title" }, h("span", {}, "Pipeline")), ...stepBtns,
    h("div", { class: "step-foot" }, "Frames in, breathing rate and apnea alarm out. Every plot is the real pipeline; only the camera is simulated."));

  // ---- middle: header, chart area, transport
  const stageTitle = h("h2", {}), stageNote = h("span", { class: "tag sim" }, "SIMULATED INPUT");
  const chips = h("div", { class: "chips" });
  const cmpSeg = h("div", { class: "seg", role: "group", "aria-label": "Compare" }, ...[["stacked", "Before / after"], ["overlay", "Overlay"]].map(([v, l]) => h("button", { "aria-pressed": String(v === "stacked"), "data-v": v }, l)));
  cmpSeg.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; compare = b.dataset.v;
    cmpSeg.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); build(); state.redraw(); });
  const winSeg = h("div", { class: "seg", role: "group", "aria-label": "Time window" }, ...WINDOWS.map((w, i) => h("button", { "aria-pressed": String(i === 0), "data-v": w.id }, w.label)));
  winSeg.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; win = WINDOWS.find(w => w.id === b.dataset.v);
    winSeg.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); sKey = ""; state.redraw(); });
  const statsEl = h("div", { class: "stats" });
  const body = h("div", { class: "stage-body" });
  const playBtn = h("button", { class: "play-btn", "aria-label": "Play or pause", onclick: () => state.toggle() });
  const clock = h("div", { class: "clock num" }), scrub = h("input", { type: "range", min: "0", max: "1000", value: "0", "aria-label": "Playhead" });
  scrub.addEventListener("input", () => state.seek(scrub.value / 1000 * run.meta.duration_s));
  const speedSeg = h("div", { class: "seg", role: "group", "aria-label": "Speed" }, ...[1, 2, 4, 8].map((s, i) => h("button", { "aria-pressed": String(i === 0), "data-v": s }, `${s}×`)));
  speedSeg.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; state.speed = +b.dataset.v; speedSeg.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); });
  const main = h("section", { class: "card stage-main" },
    h("div", { class: "stage-head" }, h("div", { class: "ttl" }, stageTitle, stageNote), h("div", { class: "ctl" }, cmpSeg, winSeg)),
    h("div", { class: "stage-sub" }, chips, statsEl), body,
    h("div", { class: "transport pipe-transport" }, playBtn, clock, scrub, speedSeg));

  // ---- right: explanation
  const ex = { what: h("p"), why: h("p"), how: h("p"), look: h("p") };
  const explain = h("aside", { class: "card explain" }, h("div", { class: "card-title" }, h("span", {}, "In plain language")),
    h("h3", {}, "What this does"), ex.what, h("h3", {}, "Why we need it"), ex.why, h("h3", {}, "How it is set"), ex.how, h("h3", { class: "look" }, "Look for"), ex.look);
  root.append(stepper, main, explain);

  // ---- shared frame player (stage 1 and 2 draw from it)
  const frameCanvas = h("canvas", { style: "flex:none" }), cellCanvas = h("canvas");
  const frameWrap = h("div", { class: "frame-wrap" }, frameCanvas);  // keeps the camera's 4:3 shape
  const player = new ThermalPlayer(frameCanvas, () => state.redraw());
  player.zoom = false; player.mode = "scene";

  // ---- moments worth jumping to
  function moments() {
    const st = run.stages, m = run.meta, out = [], P = run.params;
    out.push({ label: "Steady breathing", t: m.window_s + 14 });
    if (st.ffc.step_times.length) out.push({ label: "Camera glitch", t: st.ffc.step_times[0] + 6 });
    if (P.rate_change) out.push({ label: "Speed change", t: P.rate_change_time_s + 24 });
    const ap = st.apnea.events.find(e => e.kind === "apnea");
    if (ap) out.push({ label: "The pause", t: Math.min(m.duration_s - 1, ap.declared_at + 6) });
    return out;
  }
  const focusFor = id => {
    const mo = moments(), by = l => mo.find(x => x.label === l)?.t;
    return ({ ffc: by("Camera glitch"), background: run.stages.ffc.step_times.length ? run.stages.ffc.step_times.at(-1) + 8 : undefined, apnea: by("The pause") })[id] ?? by("Steady breathing");
  };

  function select(i) {
    stageIdx = i; stepBtns.forEach((b, k) => b.setAttribute("aria-current", String(k === i)));
    const s = STAGES[i]; stageTitle.textContent = `${i + 1}. ${s.title}`;
    ex.what.textContent = s.what; ex.why.textContent = s.why; ex.how.textContent = s.how; ex.look.textContent = s.look;
    cmpSeg.style.display = s.compare ? "" : "none";
    if (!state.playing) state.seek(focusFor(s.id) ?? state.t); else state.redraw();
    build(); state.redraw();
  }

  // ---- slots: each stage lays out a few canvases and says how to draw each
  function slotEl(key, title, note, canvasEl) {
    const c = canvasEl || h("canvas", { "aria-label": title });
    return { key, c, el: h("div", { class: `slot a-${key}` }, h("div", { class: "chart-head", style: "padding-left:0" }, h("b", {}, title), h("span", {}, note || "")), c) };
  }
  function build() {
    const s = STAGES[stageIdx], single = s.compare && compare === "overlay";
    const defs = {
      frames: [["a", "One camera frame", "80×60 pixels, the three boxes marked", frameWrap], ["b", "Average temperature inside each box", "°C, over time"]],
      average: [["a", "The 18 pixels in the nose box, right now", "each cell is one pixel, °C", cellCanvas], ["b", "Their average, frame after frame", "°C: this is the raw breathing signal"]],
      ffc: single ? [["a", "Signal before and after repair", "°C"]] : [["a", "Before: raw signal with the glitch", "°C"], ["b", "After: frozen frames repaired", "°C, the level jump is still there"]],
      background: single ? [["a", "Nose signal before and after subtracting the background", "°C"]] : [["a", "Before: nose and background drift and jump together", "°C, background lined up with the nose"], ["b", "After: nose minus background", "°C, drift and jump are gone"]],
      bandpass: single ? [["a", "Signal before and after filtering", "°C, average removed so both fit"], ["c", "Which rhythms are in the signal", "x: breaths/min · red = discarded · gray = before, green = after"]]
        : [["a", "Before: signal after background removal", "°C, average removed so it fits"], ["b", "After: breathing speeds only", "°C"], ["c", "Which rhythms are in the signal", "x: breaths/min · red = discarded · gray = before, green = after"]],
      rate: [["a", "Counting: the last 30 s of signal", "one dot per detected breath"], ["b", "Spectrum: the same 30 s", "x: breaths/min · blue = the signal that counts, the rest is noise"], ["c", "The resulting rate over time", "breaths/min: estimate vs simulation truth"]],
      apnea: [["a", "Breathing signal", "°C"], ["b", "Breathing strength vs normal", "°C RMS, with the pause threshold"], ["c", "The decision", "Low = strength under the threshold · Alarm = raised after the minimum pause · Truth = the simulated pause"]],
    }[s.id];
    slots = defs.map(([k, t, n, cv]) => slotEl(k, t, n, cv));
    body.className = `stage-body L-${single ? (s.id === "bandpass" ? "l5s" : "single") : s.layout}`; body.replaceChildren(...slots.map(x => x.el));
  }

  // ---- data fetching for the stages that need server-side analysis
  async function ensureData(c) {
    const id = STAGES[stageIdx].id;
    if (id === "rate" && c.t >= run.meta.window_s) {
      const k = (Math.round(c.t * 4) / 4).toFixed(2);
      if (k !== wKey && !wBusy) { wKey = k; wBusy = true;
        try { const r = await fetch(`/api/window?run=${run.run_id}&t_end=${k}`); wData = r.ok ? await r.json() : null; } catch { wData = null; } finally { wBusy = false; state.redraw(); } }
    }
    if (id === "bandpass") {
      const x0 = win.s ? Math.max(0, c.t - win.s) : 0;
      if (c.t - x0 >= 8) { const k = `${x0.toFixed(1)}-${(Math.round(c.t * 2) / 2).toFixed(1)}`;
        if (k !== sKey && !sBusy) { sKey = k; sBusy = true;
          try { const r = await fetch(`/api/spectrum?run=${run.run_id}&t0=${x0}&t1=${c.t}`); sData = r.ok ? await r.json() : null; } catch { sData = null; } finally { sBusy = false; state.redraw(); } } }
      else sData = null;
    }
  }

  // ---- common context
  function context(t) {
    const st = run.stages, D = run.meta.duration_s, x = win.s ? [Math.max(0, t - win.s), Math.max(0, t - win.s) + win.s] : [0, D];
    const bands = run.truth.pauses.filter(([a]) => a < t).map(([a, b]) => ({ x0: a, x1: Math.min(b, t), color: SOFT.amber }));
    for (const e of st.apnea.events) if (e.declared_at <= t) bands.push({ x0: e.start, x1: Math.min(e.end, t), color: e.kind === "apnea" ? SOFT.red : SOFT.blue });
    const glitch = st.ffc.step_times.filter(s => s <= t).map(s => ({ x: s, color: COLORS.warn, dash: [4, 4], width: 1 }));
    return { run, st, t, x, bands, glitch, now: { x: t, color: "rgba(228,232,237,.8)", width: 1.2 }, long: !win.s || win.s > 30 };
  }
  const base = (c, over = {}) => ({ x: c.x, margin: M, xTicks: c.long ? 8 : 6, xFmt: v => fmtTime(v), lines: [...c.glitch, c.now], bands: c.bands, ...over });

  // ---- per stage drawing: returns a function per slot key
  function painters(c) {
    const st = c.st, g = run.grid_t, t = c.t, id = STAGES[stageIdx].id, single = STAGES[stageIdx].compare && compare === "overlay";
    const P = {};
    if (id === "frames") {
      P.a = () => {
        const bw = frameWrap.clientWidth, bh = frameWrap.clientHeight, w = Math.max(40, Math.min(bw, bh * 4 / 3));
        frameCanvas.style.width = `${w}px`; frameCanvas.style.height = `${w * 3 / 4}px`; player.draw(t);
      };
      const y = visRange([[g, st.raw.nostril], [g, st.raw.control], [g, st.raw.reference]], c.x[0], t, { minSpan: 4 });
      P.b = cv => drawChart(cv, base(c, { y, yTicks: 3, yFmt: v => v.toFixed(0), series: [
        { xs: g, ys: st.raw.reference, color: BG, width: 1.6, to: t }, { xs: g, ys: st.raw.control, color: CHEEK, width: 1.6, to: t }, { xs: g, ys: st.raw.nostril, color: FACE, width: 2, to: t }] }));
    } else if (id === "average") {
      P.a = () => drawCells(t);
      P.b = cv => drawChart(cv, base(c, { y: visRange([[g, st.raw.nostril]], c.x[0], t, { minSpan: 0.6 }), yTicks: 3, series: [{ xs: g, ys: st.raw.nostril, color: FACE, width: 2, to: t }] }));
    } else if (id === "ffc") {
      const rep = st.ffc.repaired.map(([a, b]) => ({ x0: a - 0.15, x1: b + 0.15, color: "rgba(214,162,74,.35)" })).filter(b => b.x0 < t);
      const y = visRange([[g, st.raw.nostril], [g, st.repaired.nostril]], c.x[0], t, { minSpan: 0.8 });
      const lab = c.glitch.map(l => ({ ...l, label: "level jump", dy: 6 }));
      const common = { y, yTicks: 3, bands: [...c.bands, ...rep], lines: [...lab, c.now] };
      if (single) P.a = cv => drawChart(cv, base(c, { ...common, series: [{ xs: g, ys: st.raw.nostril, color: "rgba(142,153,166,.7)", width: 1.4, to: t }, { xs: g, ys: st.repaired.nostril, color: FACE, width: 1.8, to: t }] }));
      else { P.a = cv => drawChart(cv, base(c, { ...common, noXLabels: true, series: [{ xs: g, ys: st.raw.nostril, color: "rgba(142,153,166,.95)", width: 1.8, to: t }] }));
             P.b = cv => drawChart(cv, base(c, { ...common, bands: c.bands, series: [{ xs: g, ys: st.repaired.nostril, color: FACE, width: 1.8, to: t }] })); }
    } else if (id === "background") {
      const n0 = st.repaired.nostril.find(v => v != null), r0 = st.repaired.reference.find(v => v != null), off = n0 - r0;
      const yIn = visRange([[g, st.repaired.nostril], [g, st.repaired.reference, off]], c.x[0], t, { minSpan: 0.8 });
      const yOut = visRange([[g, st.clean]], c.x[0], t, { minSpan: 0.8 });
      const bg = { xs: g, ys: st.repaired.reference.map(v => (v == null ? null : v + off)), color: BG, width: 1.6, to: t, dash: [5, 4] };
      if (single) P.a = cv => drawChart(cv, base(c, { y: visRange([[g, st.repaired.nostril], [g, st.clean]], c.x[0], t, { minSpan: 0.8 }), yTicks: 3, series: [{ xs: g, ys: st.repaired.nostril, color: "rgba(142,153,166,.7)", width: 1.4, to: t }, { xs: g, ys: st.clean, color: FACE, width: 1.8, to: t }] }));
      else { P.a = cv => drawChart(cv, base(c, { y: yIn, yTicks: 3, noXLabels: true, series: [bg, { xs: g, ys: st.repaired.nostril, color: FACE, width: 1.8, to: t }] }));
             P.b = cv => drawChart(cv, base(c, { y: yOut, yTicks: 3, series: [{ xs: g, ys: st.clean, color: FACE, width: 1.8, to: t }] })); }
    } else if (id === "bandpass") {
      const i0 = Math.max(0, bisect(g, c.x[0])), i1 = Math.max(i0 + 1, bisect(g, t));
      const seg = st.clean.slice(i0, i1 + 1).filter(v => v != null), mean = seg.reduce((a, b) => a + b, 0) / Math.max(1, seg.length);
      const cl = st.clean.map(v => (v == null ? null : v - mean)), f = st.filtered.nostril;
      const m = Math.max(0.1, ...nums(f.slice(i0, i1 + 1)).map(Math.abs), ...nums(cl.slice(i0, i1 + 1)).map(Math.abs)) * 1.15;
      const yy = { y: [-m, m], yTicks: 2, yFmt: v => (v > 0 ? "+" : "") + v.toFixed(1) };
      if (single) P.a = cv => drawChart(cv, base(c, { ...yy, series: [{ xs: g, ys: cl, color: "rgba(142,153,166,.75)", width: 1.4, to: t }, { xs: g, ys: f, color: FACE, width: 1.8, to: t }] }));
      else { P.a = cv => drawChart(cv, base(c, { ...yy, noXLabels: true, series: [{ xs: g, ys: cl, color: "rgba(142,153,166,.95)", width: 1.6, to: t }] }));
             P.b = cv => drawChart(cv, base(c, { ...yy, series: [{ xs: g, ys: f, color: FACE, width: 1.8, to: t }] })); }
      P.c = cv => sData ? drawSpectrum(cv, sData) : placeholder(cv, "Move the playhead past 8 s to see the spectrum");
    } else if (id === "rate") {
      const rs = st.rate;
      P.a = cv => wData ? drawChart(cv, { x: [wData.t0, wData.t1], y: visRange([[wData.signal_t, wData.signal]], wData.t0, wData.t1, { minSpan: 0.4 }), margin: M, xTicks: 6, xFmt: v => fmtTime(v), yTicks: 2, yFmt: v => (v > 0 ? "+" : "") + v.toFixed(1),
        lines: wData.peaks_t.map(p => ({ x: p, color: "rgba(111,159,212,.5)", dash: [2, 3], width: 1 })),
        series: [{ xs: wData.signal_t, ys: wData.signal, color: FACE, width: 1.8 }, { xs: wData.peaks_t, ys: wData.peaks_v, color: COLORS.blue, width: 0, dots: 4 }] })
        : placeholder(cv, t < run.meta.window_s ? `The first reading needs a ${run.meta.window_s} s window. Move the playhead later.` : "Loading…");
      P.b = cv => wData ? drawSpectrum(cv, { bpm: wData.bpm, filtered: wData.amp, band_bpm: wData.band_bpm, peak_bpm: wData.peak_bpm, hw: wData.snr_halfwidth_bpm, single: true }) : placeholder(cv, "");
      const all = [...nums(run.truth.rate.bpm), ...nums(rs.time), ...nums(rs.spectral)], lo = Math.max(0, Math.floor(Math.min(...all) - 2)), hi = Math.ceil(Math.max(...all) + 2);
      const win30 = wData ? [{ x0: wData.t0, x1: wData.t1, color: "rgba(111,159,212,.13)" }] : [];
      P.c = cv => drawChart(cv, base(c, { y: [lo, hi], yTicks: 3, yFmt: v => v.toFixed(0), bands: [...c.bands, ...win30], series: [
        { xs: run.truth.rate.t, ys: run.truth.rate.bpm, color: TRUTH, width: 1.4, dash: [5, 4], to: t },
        { xs: rs.t_end, ys: rs.spectral, color: COLORS.blue, width: 1.6, dots: 2.2, to: t }, { xs: rs.t_end, ys: rs.time, color: FACE, width: 1.6, dots: 2.2, to: t }] }));
    } else if (id === "apnea") {
      const ap = st.apnea, m = run.meta;
      const sm = Math.max(0.15, Math.max(...nums(st.filtered.nostril).map(Math.abs)) * 1.25), em = Math.max(0.05, Math.max(...nums(ap.envelope)) * 1.12);
      P.a = cv => drawChart(cv, base(c, { noXLabels: true, y: [-sm, sm], yTicks: 2, yFmt: v => (v > 0 ? "+" : "") + v.toFixed(1), series: [{ xs: g, ys: st.filtered.nostril, color: FACE, width: 1.8, to: t }] }));
      P.b = cv => drawChart(cv, base(c, { noXLabels: true, y: [0, em], yTicks: 2, yFmt: v => v.toFixed(2), series: [
        { xs: g, ys: ap.baseline, color: "rgba(142,153,166,.6)", width: 1.3, dash: [5, 4], to: t }, { xs: g, ys: ap.threshold, color: COLORS.alarm, width: 1.4, to: t },
        { xs: g, ys: ap.envelope, color: FACE, width: 1.9, fill: "rgba(107,183,170,.10)", to: t }] }));
      const below = []; let s0 = null;
      ap.envelope.forEach((e, i) => { const lo = e != null && ap.threshold[i] != null && e < ap.threshold[i]; if (lo && s0 == null) s0 = g[i]; if ((!lo || i === ap.envelope.length - 1) && s0 != null) { below.push([s0, g[i]]); s0 = null; } });
      P.c = cv => drawLanes(cv, { x: c.x, t, lanes: [
        { label: "Low", color: "rgba(214,162,74,.75)", spans: below }, { label: "Alarm", color: "rgba(214,90,90,.85)", spans: ap.events.filter(e => e.declared_at <= t).map(e => [e.declared_at, e.end]) },
        { label: "Truth", color: "rgba(214,162,74,.35)", spans: run.truth.pauses }] });
    }
    return P;
  }

  function drawSpectrum(cv, d) {
    const [lo, hi] = d.band_bpm, b = d.bpm, f = d.filtered.map(v => v ?? 0), cl = d.clean ? d.clean.map(v => v ?? 0) : null;
    const xmax = Math.min(100, Math.ceil(hi * 1.5 / 10) * 10);
    let top = 0; b.forEach((x, i) => { if (x >= lo && x <= hi) top = Math.max(top, f[i], cl ? cl[i] : 0); });
    top = Math.max(0.05, top * 1.25);
    const bands = [{ x0: 0, x1: lo, color: "rgba(214,90,90,.10)" }, { x0: hi, x1: xmax, color: "rgba(214,90,90,.10)" }, { x0: lo, x1: hi, color: "rgba(107,183,170,.06)" }];
    if (d.hw != null) bands.push({ x0: d.peak_bpm - d.hw, x1: d.peak_bpm + d.hw, color: "rgba(111,159,212,.20)" });
    drawChart(cv, { x: [0, xmax], y: [0, top], margin: { l: 52, r: 16, t: 8, b: 24 }, xTicks: 7, xFmt: v => v.toFixed(0), yTicks: 2, yFmt: v => v.toFixed(2), bands,
      lines: d.peak_bpm != null ? [{ x: d.peak_bpm, color: COLORS.blue, dash: [4, 3], width: 1.2, label: `${d.peak_bpm.toFixed(1)} /min`, dy: 6, align: "left" }] : [],
      series: [...(cl ? [{ xs: b, ys: cl, color: "rgba(142,153,166,.9)", width: 1.5 }] : []), { xs: b, ys: f, color: FACE, width: 2 }] });
  }

  function drawCells(t) {
    const { ctx, w, h: hh } = fitCanvas(cellCanvas); ctx.clearRect(0, 0, w, hh);
    const i = player.frameIndexAt(t), f = player.frame(i); if (!f) return placeholder(cellCanvas, "Loading frame…");
    const [r0, r1, c0, c1] = run.rois.nostril, rows = r1 - r0, cols = c1 - c0, [lo, hi] = run.meta.temp_range.face;
    const cw = Math.min((w - 8) / cols, 78), chh = Math.min((hh - 62) / rows, 58), x0 = (w - cw * cols) / 2, y0 = 6;
    ctx.font = "600 13px ui-sans-serif, -apple-system, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    let sum = 0;
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const v = f[(r0 + r) * 80 + c0 + c] / 100; sum += v; const k = Math.round(clamp((v - lo) / (hi - lo), 0, 1) * 255);
      ctx.fillStyle = `rgb(${LUT[k * 3]},${LUT[k * 3 + 1]},${LUT[k * 3 + 2]})`; ctx.fillRect(x0 + c * cw, y0 + r * chh, cw - 2, chh - 2);
      ctx.fillStyle = k > 150 ? "#14110a" : "#f3ece0"; ctx.fillText(v.toFixed(1), x0 + c * cw + (cw - 2) / 2, y0 + r * chh + (chh - 2) / 2);
    }
    ctx.fillStyle = COLORS.text; ctx.font = "13px ui-sans-serif, sans-serif"; ctx.fillText(`mean of ${rows * cols} pixels`, w / 2, y0 + rows * chh + 16);
    ctx.fillStyle = "#e4e8ed"; ctx.font = "650 22px ui-sans-serif, sans-serif"; ctx.fillText(`${(sum / (rows * cols)).toFixed(2)} °C`, w / 2, y0 + rows * chh + 40);
  }

  // ---- header chips and stats
  function renderChips() {
    chips.replaceChildren(h("span", { class: "lbl" }, "Jump to"), ...moments().map(m => h("button", { class: "chip", onclick: () => state.seek(m.t) }, m.label)));
  }
  function stats(c) {
    const id = STAGES[stageIdx].id, st = c.st, t = c.t, out = [];
    const S = (k, v, cls = "") => out.push(h("span", { class: `stat ${cls}` }, h("em", {}, k), v));
    if (id === "frames") { const r = run.rois, n = b => (b[1] - b[0]) * (b[3] - b[2]); S("Frame", "60×80 px"); S("Nose box", `${n(r.nostril)} px`); S("Cheek box", `${n(r.control)} px`); S("Background box", `${n(r.reference)} px`); }
    else if (id === "average") { const i = bisect(run.grid_t, t), lo = Math.max(0, bisect(run.grid_t, t - 8)), seg = nums(st.raw.nostril.slice(lo, i + 1)); if (seg.length) S("Swing, last 8 s", `${(Math.max(...seg) - Math.min(...seg)).toFixed(2)} °C peak to peak`); S("Frames per second", run.meta.fs.toFixed(1)); }
    else if (id === "ffc") { S("Glitches found", String(st.ffc.step_times.length)); S("Frozen frames", String(st.ffc.frozen_times.length)); if (st.ffc.step_sizes.length) S("Jump sizes", st.ffc.step_sizes.map(v => `${Math.abs(v).toFixed(2)}`).join(", ") + " °C"); }
    else if (id === "background") { const r = nums(st.raw.reference); S("Background drifted", `${(r.at(-1) - r[0] >= 0 ? "+" : "") + (r.at(-1) - r[0]).toFixed(2)} °C over the recording`); S("Glitches removed", String(st.ffc.step_times.length)); }
    else if (id === "bandpass") { S("Keeps", `${run.meta.band_hz.map(v => (v * 60).toFixed(0)).join("–")} breaths/min`); S("Profile", run.meta.profile); if (sData) { const b = sData.bpm, f = sData.filtered.map(v => v ?? 0); S("Strongest rhythm", `${b[f.indexOf(Math.max(...f))].toFixed(1)} breaths/min`, "good"); } }
    else if (id === "rate") {
      if (wData) { S("Counting", wData.time_bpm == null ? "—" : wData.time_bpm.toFixed(1)); S("Spectrum", wData.spectral_bpm == null ? "—" : wData.spectral_bpm.toFixed(1));
        S("Quality", `${Math.round(wData.quality * 100)}%`, wData.quality < 0.5 ? "warn" : "good"); S("Shown", wData.shown_time == null ? "no reading (quality < 50%)" : `${wData.shown_time.toFixed(1)} breaths/min`, wData.shown_time == null ? "warn" : "good"); }
    } else if (id === "apnea") {
      const gi = bisect(run.grid_t, t), e = st.apnea.envelope[gi], b = st.apnea.baseline[gi], k = run.meta.k;
      if (e != null && b) S("Strength vs normal", `${Math.round(e / b * 100)}%`, e / b < k ? "warn" : "good"); S("Threshold", `${Math.round(k * 100)}% of normal`); S("Minimum pause", `${run.meta.min_pause_s} s`);
      const al = st.apnea.events.find(x => x.kind === "apnea" && x.declared_at <= t && t < x.end); if (al) S("Alarm", `raised at ${fmtTime(al.declared_at)}`, "bad");
    }
    statsEl.replaceChildren(...out);
  }

  // ---- per-frame update
  function update(t) {
    if (!run) return;
    const c = context(t), P = painters(c); ensureData(c);
    slots.forEach(s => (P[s.key] || (() => {}))(s.c));
    stats(c);
    playBtn.innerHTML = svgIcon(state.playing ? ICON.pause : ICON.play, 16, state.playing ? "" : 'style="margin-left:2px"');
    clock.innerHTML = `${fmtTime(t)} <span>/ ${fmtTime(run.meta.duration_s)}</span>`;
    scrub.value = String(Math.round(t / run.meta.duration_s * 1000));
  }

  function applyStage() {
    const s = STAGES[stageIdx];
    stepBtns.forEach((b, k) => b.setAttribute("aria-current", String(k === stageIdx)));
    stageTitle.textContent = `${stageIdx + 1}. ${s.title}`;
    ex.what.textContent = s.what; ex.why.textContent = s.why; ex.how.textContent = s.how; ex.look.textContent = s.look;
    cmpSeg.style.display = s.compare ? "" : "none";
  }
  return {
    el: root,
    setRun(r) { run = r; player.setRun(r); wData = sData = null; wKey = sKey = ""; pendingFocus = true; renderChips(); applyStage(); build(); },
    update, relayout() {},
    enter() {  // jump to a good moment the first time a (new) run is shown here
      if (!run) return;
      if (pendingFocus) { pendingFocus = false; if (!state.playing) state.seek(focusFor(STAGES[stageIdx].id) ?? state.t); }
      build(); state.redraw();
    },
  };
}
