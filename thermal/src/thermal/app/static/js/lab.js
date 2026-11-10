// Lab: change the simulation with sliders and watch the REAL pipeline's result update.
// Every change reruns the pipeline on the server (about a second); the whole recording is shown at once.
import { h, fmtTime } from "./util.js";
import { drawChart, COLORS } from "./chart.js";

const GROUPS = [
  ["Breathing", ["rate_bpm", "rate_change", "rate_change_time_s", "rate_after_bpm"]],
  ["Breathing pause (apnea)", ["apnea", "apnea_start_s", "apnea_len_s"]],
  ["Environment and camera", ["ambient_c", "noise_x", "head", "ffc"]],
  ["Detector and recording", ["min_pause_s", "duration_s"]],
];
const DEPENDS = { rate_change_time_s: "rate_change", rate_after_bpm: "rate_change", apnea_start_s: "apnea", apnea_len_s: "apnea" };
const M = { l: 52, r: 16, t: 8 };
const nums = a => a.filter(v => v != null);
const fmtVal = (c, v) => c.key === "noise_x" ? `${(+v).toFixed(2).replace(/0$/, "")}×` : c.key === "ambient_c" ? `${(+v).toFixed(1)} °C` : `${v} ${c.unit || ""}`.trim();

export function buildLab(state) {
  let schema = null, params = null, labRun = state.run, timer = null, seq = 0, ctl = null, busy = false, error = "", activePreset = "story";
  const inputs = {};   // key -> { c, row, input, val }
  const root = h("div", { class: "lab" });

  // ---------------------------------------------------------------- controls column
  const presetBox = h("div", { class: "presets" });
  const ctlBody = h("div", { class: "lab-ctl-body" });
  const pill = h("span", { class: "pill" }, "");
  const resetBtn = h("button", { class: "btn", onclick: () => applyPreset("story") }, "Reset");
  const ctlCard = h("aside", { class: "card lab-controls" },
    h("div", { class: "card-title" }, h("span", {}, "Lab controls"), h("span", { style: "display:flex;gap:8px;align-items:center" }, pill, resetBtn)),
    presetBox, ctlBody);

  // ---------------------------------------------------------------- results column
  const vDot = h("span", { class: "vdot" }), vTitle = h("b", {}, "—"), vSub = h("span", {}, "");
  const tiles = h("div", { class: "tiles" }), notes = h("ul", { class: "notes" });
  const errEl = h("div", { class: "lab-err", hidden: true });
  const verdict = h("section", { class: "card verdict" },
    h("div", { class: "v-main" }, vDot, h("div", {}, vTitle, vSub)), tiles, notes);
  const mk = (title, note) => ({ canvas: h("canvas", { "aria-label": title }), head: h("div", { class: "chart-head" }, h("b", {}, title), h("span", {}, note)) });
  const cSig = mk("Breathing signal", "cleaned, °C"), cRate = mk("Breathing rate", "estimate vs simulation truth, breaths/min"), cStr = mk("Breathing strength", "vs the pause threshold, °C RMS");
  const watch = h("button", { class: "btn primary", onclick: () => { state.loadRun(labRun); state.goto("monitor"); } }, "Watch this in the Monitor");
  const legend = h("div", { class: "legend", style: "margin:0" },
    h("span", {}, h("i", { class: "box", style: "background:rgba(214,162,74,.5)" }), "Simulated true pause"),
    h("span", {}, h("i", { class: "box", style: "background:rgba(214,90,90,.6)" }), "Detected apnea"),
    h("span", {}, h("i", { class: "box", style: "background:rgba(111,159,212,.6)" }), "Signal lost"),
    h("span", {}, h("i", { style: "background:#d6a24a" }), "Camera recalibration"));
  const graphs = h("section", { class: "card charts lab-charts" },
    h("div", { class: "lab-charts-head" }, legend, watch),
    ...[cSig, cRate, cStr].map(c => h("div", { class: "chart-block" }, c.head, c.canvas)));
  root.append(ctlCard, h("div", { class: "lab-results" }, verdict, errEl, graphs));

  // ---------------------------------------------------------------- build controls from the server's schema
  function buildControls() {
    const by = Object.fromEntries(schema.controls.map(c => [c.key, c]));
    ctlBody.replaceChildren();
    for (const [title, keys] of GROUPS) {
      const grp = h("div", { class: "grp" }, h("h4", {}, title));
      for (const key of keys) {
        const c = by[key]; if (!c) continue;
        const val = h("span", { class: "val num" }), row = h("div", { class: "ctl-row", title: c.help || "" });
        let input;
        if (c.kind === "range") {
          input = h("input", { type: "range", min: c.min, max: c.max, step: c.step, "aria-label": c.label });
          input.addEventListener("input", () => { params[key] = +input.value; limits(); refreshLabels(); schedule(); });
          row.append(h("div", { class: "ctl-top" }, h("label", {}, c.label), val), input);
        } else if (c.kind === "toggle") {
          input = h("input", { type: "checkbox", role: "switch", "aria-label": c.label });
          input.addEventListener("change", () => { params[key] = input.checked; refreshLabels(); schedule(); });
          row.classList.add("toggle"); row.append(h("label", {}, input, h("span", { class: "sw" }), h("span", {}, c.label)));
        } else {
          input = h("div", { class: "seg", role: "group", "aria-label": c.label }, ...c.options.map(([v, l]) => h("button", { "aria-pressed": "false", "data-v": v }, l)));
          input.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; params[key] = b.dataset.v; refreshLabels(); schedule(); });
          row.append(h("div", { class: "ctl-top" }, h("label", {}, c.label)), input);
        }
        inputs[key] = { c, row, input, val }; grp.append(row);
      }
      ctlBody.append(grp);
    }
    presetBox.replaceChildren(h("div", { class: "lbl" }, "Try a setup"),
      h("div", { class: "chips" }, ...schema.presets.map(p => h("button", { class: "chip", "data-p": p.id, title: p.desc, onclick: () => applyPreset(p.id) }, p.label))));
  }

  // dependent limits: the pause must end before the recording does, and so on
  function limits() {
    const D = params.duration_s;
    const a = inputs.apnea_len_s, st = inputs.apnea_start_s, rc = inputs.rate_change_time_s;
    if (st) { st.input.max = Math.max(+st.input.min, D - 10 - params.apnea_len_s); params.apnea_start_s = Math.min(params.apnea_start_s, +st.input.max); }
    if (a) { a.input.max = Math.min(60, Math.max(5, D - 10 - params.apnea_start_s)); params.apnea_len_s = Math.min(params.apnea_len_s, +a.input.max); }
    if (rc) { rc.input.max = D - 20; params.rate_change_time_s = Math.min(params.rate_change_time_s, D - 20); }
  }
  function refreshLabels() {
    for (const [key, { c, row, input, val }] of Object.entries(inputs)) {
      const v = params[key];
      if (c.kind === "range") { input.value = v; val.textContent = fmtVal(c, v); }
      else if (c.kind === "toggle") input.checked = !!v;
      else input.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.v === v)));
      const dep = DEPENDS[key]; row.classList.toggle("off", !!dep && !params[dep]);
      if (dep && c.kind === "range") input.disabled = !params[dep];
    }
    activePreset = (schema.presets.find(p => JSON.stringify({ ...schema.defaults, ...p.params }) === JSON.stringify(params)) || {}).id || null;
    presetBox.querySelectorAll(".chip").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.p === activePreset)));
  }
  function applyPreset(id) {
    const p = schema.presets.find(x => x.id === id); params = { ...schema.defaults, ...p.params };
    limits(); refreshLabels(); schedule(0);
  }

  // ---------------------------------------------------------------- live rerun
  function schedule(delay = 300) { clearTimeout(timer); setPill("Updating…"); timer = setTimeout(run, delay); }
  function setPill(t) { pill.textContent = t; pill.style.visibility = t ? "visible" : "hidden"; }
  async function run() {
    const my = ++seq; ctl?.abort(); ctl = new AbortController(); busy = true;
    try {
      const res = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params), signal: ctl.signal });
      if (my !== seq) return;
      if (!res.ok) {
        const j = await res.json().catch(() => ({})); const m = Array.isArray(j.detail) ? j.detail[0]?.msg : j.detail;
        error = (m || `Server error ${res.status}`).replace(/^Value error, /, ""); showResult();
      } else { labRun = await res.json(); error = ""; showResult(); }
    } catch (e) { if (e.name !== "AbortError") { error = `Could not reach the server: ${e}`; showResult(); } }
    finally { if (my === seq) { busy = false; setPill(""); } }
  }

  // ---------------------------------------------------------------- results
  function showResult() {
    errEl.hidden = !error; errEl.textContent = error;
    const r = labRun, v = r.verdict, s = r.summary;
    vDot.className = `vdot ${v.level}`; vTitle.textContent = v.title; vSub.textContent = v.sub;
    const tile = (k, val, sub, cls = "") => h("div", { class: `tile ${cls}` }, h("em", {}, k), h("b", { class: "num" }, val), h("small", {}, sub));
    tiles.replaceChildren(
      tile("Pause found", s.pauses_injected ? `${s.pauses_found} of ${s.pauses_injected}` : "none injected", s.pauses_injected ? (s.pauses_found === s.pauses_injected ? "alarm raised" : "no alarm") : "nothing to find", s.pauses_injected && s.pauses_found < s.pauses_injected ? "warn" : ""),
      tile("Rate error", s.rate_mae_time == null ? "—" : `${s.rate_mae_time.toFixed(1)}`, s.rate_mae_time == null ? "no readings" : "breaths/min, average"),
      tile("No reading", `${Math.round((1 - (s.rate_answered ?? 0)) * 100)}%`, "of windows with no rate shown", (s.rate_answered ?? 0) < 0.9 ? "warn" : ""),
      tile("Signal lost", `${Math.round(s.signal_lost_fraction * 100)}%`, "of the recording", s.signal_lost_fraction > 0.3 ? "bad" : ""),
      tile("Glitches", `${s.ffc_detected} of ${s.ffc_injected}`, "repaired"));
    notes.replaceChildren(...r.notes.slice(0, 4).map(n => h("li", { class: n.kind }, h("i"), n.text)));
    state.redraw();
  }

  function draw() {
    const r = labRun; if (!r || !schema) return;
    const st = r.stages, g = r.grid_t, D = r.meta.duration_s, ap = st.apnea;
    const bands = r.truth.pauses.map(([a, b]) => ({ x0: a, x1: b, color: "rgba(214,162,74,.10)" }));
    for (const e of ap.events) bands.push({ x0: e.start, x1: e.end, color: e.kind === "apnea" ? "rgba(214,90,90,.16)" : "rgba(111,159,212,.16)" });
    const lines = st.ffc.step_times.map(s => ({ x: s, color: COLORS.warn, dash: [4, 4], width: 1 }));
    const common = { x: [0, D], bands, lines, margin: M, xTicks: 9, xFmt: v => fmtTime(v) };
    const sm = Math.max(0.15, Math.max(0, ...nums(st.filtered.nostril).map(Math.abs)) * 1.25);
    drawChart(cSig.canvas, { ...common, noXLabels: true, y: [-sm, sm], yTicks: 2, yFmt: v => (v > 0 ? "+" : "") + v.toFixed(1), series: [{ xs: g, ys: st.filtered.nostril, color: COLORS.accent, width: 1.6 }] });
    const rs = st.rate, all = [...nums(r.truth.rate.bpm), ...nums(rs.time), ...nums(rs.spectral)];
    drawChart(cRate.canvas, { ...common, noXLabels: true, y: [Math.max(0, Math.floor(Math.min(...all) - 2)), Math.ceil(Math.max(...all) + 2)], yTicks: 3, yFmt: v => v.toFixed(0), series: [
      { xs: r.truth.rate.t, ys: r.truth.rate.bpm, color: "rgba(214,162,74,.75)", width: 1.4, dash: [5, 4] },
      { xs: rs.t_end, ys: rs.spectral, color: COLORS.blue, width: 1.4, dots: 2 }, { xs: rs.t_end, ys: rs.time, color: COLORS.accent, width: 1.6, dots: 2 }] });
    const em = Math.max(0.05, Math.max(0, ...nums(ap.envelope)) * 1.12);
    drawChart(cStr.canvas, { ...common, y: [0, em], yTicks: 2, yFmt: v => v.toFixed(2), series: [
      { xs: g, ys: ap.baseline, color: "rgba(142,153,166,.55)", width: 1.2, dash: [5, 4] }, { xs: g, ys: ap.threshold, color: COLORS.alarm, width: 1.3 },
      { xs: g, ys: ap.envelope, color: COLORS.accent, width: 1.7, fill: "rgba(107,183,170,.10)" }] });
  }

  return {
    el: root,
    async start() {
      schema = await (await fetch("/api/schema")).json(); params = { ...state.run.params }; labRun = state.run;
      buildControls(); limits(); refreshLabels(); showResult();
    },
    update() { draw(); },
    enter() { state.redraw(); },
    relayout() {},
  };
}
