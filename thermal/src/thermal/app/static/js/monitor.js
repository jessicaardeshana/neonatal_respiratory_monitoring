// Monitor screen: one screen, no scrolling. A small nose view, the rate, status and meters on top,
// and three graphs stacked on ONE shared time axis (signal, rate, breathing strength) so they compare at a glance.
import { bisect, clamp, fmtTime, h, svgIcon, ICON } from "./util.js";
import { drawChart, COLORS } from "./chart.js";
import { ThermalPlayer, drawColorbar } from "./player.js";

const WINDOWS = [{ id: "30", label: "Last 30 s", s: 30 }, { id: "60", label: "Last 60 s", s: 60 }, { id: "all", label: "Whole recording", s: 0 }];
const M = { l: 52, r: 16, t: 8 };  // identical margins on every chart so the time axes line up

/** Everything the screen needs to know about moment ``t``, derived from the pipeline's real output. */
export function describe(run, t) {
  const m = run.meta, st = run.stages, ev = st.apnea.events;
  const out = { quality: null, progress: null, strength: null, alarm: null, lost: null, suspected: null };
  const ri = bisect(st.rate.t_end, t);
  if (ri < 0) out.progress = clamp(t / m.window_s, 0, 1); else { out.rateIdx = ri; out.quality = st.rate.quality[ri]; }
  const gi = bisect(run.grid_t, t);
  if (gi >= 0) {
    const e = st.apnea.envelope[gi], b = st.apnea.baseline[gi], th = st.apnea.threshold[gi];
    if (e != null && b != null && b > 0) out.strength = e / b;
    if (e != null && th != null && e < th) {  // envelope below threshold right now: for how long?
      let j = gi; while (j > 0 && st.apnea.envelope[j - 1] != null && st.apnea.threshold[j - 1] != null && st.apnea.envelope[j - 1] < st.apnea.threshold[j - 1]) j--;
      out.suspected = (run.grid_t[gi] - run.grid_t[j]) + (1 - m.k * m.k) * m.envelope_window_s;  // the envelope reacts late
    }
  }
  out.alarm = ev.find(e => e.kind === "apnea" && e.declared_at <= t && t < e.end) || null;
  out.lost = ev.find(e => e.kind === "signal_lost" && e.declared_at <= t && t < e.end) || null;
  return out;
}

export function buildLog(run) {
  const items = [], st = run.stages, m = run.meta;
  if (st.rate.t_end.length) items.push({ t: st.rate.t_end[0], kind: "good", title: "First reading ready", sub: `The ${m.window_s} s window is full` });
  for (const s of st.ffc.step_times) items.push({ t: s, kind: "info", title: "Camera recalibration", sub: "Frozen frame and level jump repaired" });
  for (const e of st.apnea.events) {
    if (e.kind === "apnea") {
      items.push({ t: e.declared_at, kind: "alarm", title: "Apnea alarm raised", sub: `No breathing for ${m.min_pause_s} s or more (began about ${fmtTime(e.start)})` });
      items.push({ t: e.end, kind: "good", title: "Breathing resumed", sub: `Pause lasted about ${Math.round(e.end - e.start)} s` });
    } else {
      items.push({ t: e.declared_at, kind: "warn", title: "Signal lost", sub: "Breathing cannot be seen" });
      items.push({ t: e.end, kind: "good", title: "Signal back", sub: "Breathing visible again" });
    }
  }
  return items.sort((a, b) => a.t - b.t);
}

const seg = (label, items, onPick) => {
  const el = h("div", { class: "seg", role: "group", "aria-label": label }, ...items.map(([val, text, on, tip]) => h("button", { "aria-pressed": String(!!on), "data-v": val, title: tip || "" }, text)));
  el.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return;
    el.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); onPick(b.dataset.v); });
  return el;
};

export function buildMonitor(state) {
  let run = null, log = [], logShown = -1, estimator = "time", win = WINDOWS[0], sigMax = 1, rateRange = [0, 30], strMax = 1;
  const root = h("div", { class: "monitor" });

  // ---- status bar (fixed height)
  const sTitle = h("b", {}, "Ready"), sSub = h("small", {}, ""), sRight = h("span", { class: "right" }, "");
  const sIcon = h("span", { html: svgIcon(ICON.alert, 18), style: "display:none" });
  const sbar = h("div", { class: "sbar", role: "status" }, sIcon, sTitle, sSub, sRight);
  root.append(sbar);

  // ---- top row
  const canvas = h("canvas"), cbCanvas = h("canvas"), cbLabels = h("div", { class: "cb-labels" });
  const wrap = h("div", { class: "canvas-wrap" }, canvas);
  const nosVal = h("b", { class: "num" }, "—"), ctlVal = h("b", { class: "num" }, "—");
  const viewSeg = seg("View", [["zoom", "Zoom", true, "Zoomed to the nose and cheek"], ["full", "Full", false, "The whole camera frame"]], v => { player.zoom = v === "zoom"; wrap.classList.toggle("full", !player.zoom); state.redraw(); });
  const scaleSeg = seg("Colors", [["face", "Face", true, "Color scale zoomed to face temperatures, so breathing shows"], ["scene", "Scene", false, "Color scale spans room to face"]], v => { player.mode = v; paintColorbar(); state.redraw(); });
  const thermalCard = h("section", { class: "card thermal" },
    h("div", { class: "card-title" }, h("span", {}, "Thermal camera"), h("span", { class: "tag sim" }, "SIMULATED")),
    h("div", { class: "thermal-body" },
      h("div", { class: "stage" }, wrap, h("div", { class: "colorbar" }, cbCanvas, cbLabels)),
      h("div", { class: "thermal-side" },
        h("div", { class: "readouts" },
          h("div", { class: "readout" }, h("label", {}, h("i", { style: "background:#9be0d3" }), "Nose"), nosVal),
          h("div", { class: "readout" }, h("label", {}, h("i", { style: "background:#a9dcb9" }), "Cheek"), ctlVal)),
        h("div", { class: "controls" }, viewSeg, scaleSeg))));
  thermalCard.querySelectorAll(".readout b").forEach(b => b.append(h("em", {}, "°C")));

  const rateNum = h("div", { class: "rate-value num" }, "—");
  const ringNum = h("b", {}, "0s"), ring = h("div", { class: "ring", style: "--p:0" }, ringNum);
  const rateCap = h("div", { class: "rate-caption" }), truthLine = h("em", { class: "num" });
  const estSeg = seg("Rate method", [["time", "Count", true, "Counts the time between breaths"], ["spectral", "Spectrum", false, "Finds the dominant frequency"]], v => { estimator = v; state.redraw(); });
  const rateCard = h("section", { class: "card rate", style: "display:flex;flex-direction:column" },
    h("div", { class: "card-title" }, h("span", {}, "Breathing rate"), estSeg),
    h("div", { class: "rate-hero" }, rateNum, ring, h("div", { class: "rate-unit" }, "BREATHS / MIN", truthLine), rateCap));

  const qBar = h("span"), qVal = h("b", { class: "num" }, "—"), sBar = h("span"), sVal = h("b", { class: "num" }, "—");
  const meters = h("section", { class: "card" }, h("div", { class: "card-title" }, h("span", {}, "What the software sees")),
    h("div", { class: "meter" }, h("div", { class: "meter-head" }, h("span", {}, "Signal quality"), qVal), h("div", { class: "bar" }, qBar),
      h("div", { class: "meter-note" }, "How clearly one rhythm stands out. Below 50%, no rate is shown.")),
    h("div", { class: "meter", style: "margin-bottom:0" }, h("div", { class: "meter-head" }, h("span", {}, "Breathing strength vs. normal"), sVal),
      h("div", { class: "bar" }, sBar, h("i", { style: "left:16.7%", title: "Pause threshold: 25% of normal" })),
      h("div", { class: "meter-note" }, "The red mark is the pause threshold (25% of normal).")));

  const logEl = h("ul", { class: "log" });
  const logCard = h("section", { class: "card" }, h("div", { class: "card-title" }, h("span", {}, "Event log")), logEl);
  root.append(h("div", { class: "top" }, thermalCard, rateCard, meters, logCard));

  // ---- comparison graphs on a shared time axis
  const mk = (id, title, note) => ({ canvas: h("canvas", { id, "aria-label": title }), head: h("div", { class: "chart-head" }, h("b", {}, title), h("span", {}, note)) });
  const cSig = mk("c-sig", "Breathing signal", "cleaned temperature swing at the nose, °C"),
        cRate = mk("c-rate", "Breathing rate", "estimate vs simulation truth, breaths/min"),
        cStr = mk("c-str", "Breathing strength", "vs the pause threshold, °C RMS");
  const startTitle = h("span", {}, "Play the story"), startSub = h("small", {}, "");
  const startOverlay = h("button", { class: "start-overlay", "aria-label": "Play the story", onclick: () => state.play() },
    h("div", { class: "disc", html: svgIcon(ICON.play, 30, 'style="color:#0e1116;margin-left:3px"') }), startTitle, startSub);
  const charts = h("section", { class: "card charts" },
    ...[cSig, cRate, cStr].map(c => h("div", { class: "chart-block" }, c.head, c.canvas)), startOverlay);
  root.append(charts);

  // ---- transport + scrubber
  const overview = h("canvas", { id: "overview", "aria-label": "Whole recording. Click to jump." });
  const playBtn = h("button", { class: "play-btn", "aria-label": "Play or pause", title: "Space", onclick: () => state.toggle() });
  const clock = h("div", { class: "clock num" }, "00:00");
  const speedSeg = seg("Playback speed", [1, 2, 4, 8].map((s, i) => [s, `${s}×`, i === 0]), v => { state.speed = +v; });
  const winSeg = seg("Time window", WINDOWS.map((w, i) => [w.id, w.label, i === 0]), v => { win = WINDOWS.find(w => w.id === v); state.redraw(); });
  const legend = h("div", { class: "legend" },
    h("span", {}, h("i", { class: "box", style: "background:rgba(214,162,74,.5)" }), "Simulated true pause (demo only)"),
    h("span", {}, h("i", { class: "box", style: "background:rgba(214,90,90,.6)" }), "Detected apnea"),
    h("span", {}, h("i", { style: "background:#d6a24a" }), "Camera recalibration"));
  root.append(h("section", { class: "card dock" }, h("div", { class: "transport" }, playBtn, clock, h("span", { class: "lbl" }, "Speed"), speedSeg, h("span", { class: "lbl" }, "Graphs show"), winSeg, legend), overview));

  // ---- wiring
  const player = new ThermalPlayer(canvas, () => state.redraw());
  overview.addEventListener("pointerdown", e => { overview.setPointerCapture(e.pointerId); seek(e); });
  overview.addEventListener("pointermove", e => { if (e.buttons) seek(e); });
  function seek(e) { const r = overview.getBoundingClientRect(); state.seek(clamp((e.clientX - r.left - 14) / (r.width - 28), 0, 1) * run.meta.duration_s); }
  function paintColorbar() { const [lo, hi] = player.range(); cbCanvas.style.height = `${wrap.clientHeight || 104}px`; drawColorbar(cbCanvas, cbLabels, lo, hi); }

  // ---- per-frame update
  function update(t) {
    if (!run) return;
    const m = run.meta, st = run.stages, d = describe(run, t);
    const r = player.draw(t);
    if (r) { nosVal.firstChild.nodeValue = r.nostril.toFixed(2); ctlVal.firstChild.nodeValue = r.control.toFixed(2); }

    const arr = estimator === "time" ? st.rate.time : st.rate.spectral;
    const val = d.rateIdx != null ? arr[d.rateIdx] : null, alarmOn = !!d.alarm, lostOn = !!d.lost;
    ring.style.display = d.progress != null ? "grid" : "none"; rateNum.style.display = d.progress != null ? "none" : "";
    if (d.progress != null) { ring.style.setProperty("--p", (d.progress * 100).toFixed(1)); ringNum.textContent = `${Math.floor(t)}s`; rateCap.textContent = `First reading needs a ${m.window_s} s window`; }
    else if (val != null) { rateNum.textContent = val.toFixed(1); rateNum.className = "rate-value num"; rateCap.textContent = estimator === "time" ? "Counting the time between breaths" : "Dominant frequency of the signal"; }
    else { rateNum.textContent = "—"; rateNum.className = "rate-value num " + (alarmOn ? "alarm" : "dim"); rateCap.textContent = alarmOn ? "No breathing detected" : "No reliable reading"; }
    const ti = bisect(run.truth.rate.t, t);
    truthLine.textContent = ti >= 0 && run.truth.rate.bpm[ti] != null ? `  ·  simulation truth ${run.truth.rate.bpm[ti].toFixed(1)}` : "";

    const q = d.quality; qBar.style.width = `${clamp((q ?? 0) * 100, 0, 100)}%`; qVal.textContent = q == null ? "measuring…" : `${Math.round(q * 100)}%`;
    qBar.style.background = q != null && q < 0.5 ? "var(--warn)" : "var(--accent)";
    const s = d.strength; sBar.style.width = `${clamp((s ?? 0) / 1.5 * 100, 0, 100)}%`; sVal.textContent = s == null ? "measuring…" : `${Math.round(s * 100)}%`;
    sBar.style.background = s != null && s < m.k ? "var(--alarm)" : "var(--accent)";

    // status bar
    let cls = "", title = "Measuring", sub = `First reading needs a ${m.window_s} s window`, right = "";
    if (alarmOn) { cls = "alarm"; title = "APNEA ALARM"; sub = "No breathing detected"; right = `${Math.round(t - d.alarm.start)} s without breathing`; }
    else if (lostOn) { cls = "warn"; title = "Signal lost"; sub = "Breathing cannot be seen"; }
    else if (d.suspected != null && d.suspected > 1) { cls = "warn"; title = "Pause suspected"; sub = "Breathing strength is very low"; right = `${Math.round(d.suspected)} s of ${m.min_pause_s} s`; }
    else if (d.progress == null) { cls = val != null ? "good" : "warn"; title = val != null ? "Breathing detected" : "No reliable reading"; sub = val != null ? "Rate is being tracked" : "Waiting for a clearer signal"; }
    else right = `${Math.floor(t)} s of ${m.window_s} s`;
    sbar.className = `sbar ${cls}`; sTitle.textContent = title; sSub.textContent = sub; sRight.textContent = right;
    sIcon.style.display = alarmOn ? "" : "none";

    // log
    const shown = log.filter(i => i.t <= t).length;
    if (shown !== logShown) {
      logShown = shown; logEl.replaceChildren();
      const vis = log.filter(i => i.t <= t).reverse();
      if (!vis.length) logEl.append(h("li", { class: "log-empty" }, "Nothing yet. Press play."));
      for (const i of vis) logEl.append(h("li", { class: i.kind }, h("time", { class: "num" }, fmtTime(i.t)), h("i"), h("div", {}, i.title, h("em", {}, i.sub))));
    }

    // overlay + transport
    const started = t > 0.05, ended = t >= m.duration_s - 0.05;
    startOverlay.hidden = state.playing || (started && !ended);
    startTitle.textContent = ended ? "Replay the story" : "Play the story";
    startSub.textContent = ended ? "" : "About 3 minutes of simulated measuring: steady breathing, a speed-up, a pause and a recovery";
    playBtn.innerHTML = svgIcon(state.playing ? ICON.pause : ICON.play, 16, state.playing ? "" : 'style="margin-left:2px"');
    clock.innerHTML = `${fmtTime(t)} <span>/ ${fmtTime(m.duration_s)}</span>`;
    drawCharts(t); drawOverview(t);
  }

  function xRange(t) { const D = run.meta.duration_s; if (!win.s) return [0, D]; const x0 = Math.max(0, t - win.s); return [x0, x0 + win.s]; }

  function drawCharts(t) {
    const st = run.stages, ev = st.apnea.events, x = xRange(t), long = !win.s || win.s > 30;
    const bands = run.truth.pauses.filter(([a]) => a < t).map(([a, b]) => ({ x0: a, x1: Math.min(b, t), color: "rgba(214,162,74,.10)" }));
    for (const e of ev) if (e.declared_at <= t) bands.push({ x0: e.start, x1: Math.min(e.end, t), color: e.kind === "apnea" ? "rgba(214,90,90,.16)" : "rgba(111,159,212,.16)" });
    const lines = st.ffc.step_times.filter(s => s <= t).map(s => ({ x: s, color: COLORS.warn, dash: [4, 4], width: 1 }));
    lines.push({ x: t, color: "rgba(228,232,237,.8)", width: 1.2 });
    const common = { x, bands, lines, margin: M, xTicks: long ? 8 : 6, xFmt: v => fmtTime(v) };

    drawChart(cSig.canvas, { ...common, noXLabels: true, y: [-sigMax, sigMax], yTicks: 2, yFmt: v => (v > 0 ? "+" : "") + v.toFixed(1),
      series: [{ xs: run.grid_t, ys: st.filtered.nostril, color: COLORS.accent, width: 1.8, to: t }] });

    const rs = st.rate, shown = [];
    for (const [xs, ys] of [[run.truth.rate.t, run.truth.rate.bpm], [rs.t_end, estimator === "time" ? rs.time : rs.spectral]])
      xs.forEach((tx, i) => { if (tx >= x[0] && tx <= t && ys[i] != null) shown.push(ys[i]); });
    const lo = shown.length ? Math.min(...shown) : rateRange[0], hi = shown.length ? Math.max(...shown) : rateRange[1];
    const mid = (lo + hi) / 2, half = Math.max(4, (hi - lo) / 2 + 1.5);  // always at least an 8 breaths/min tall view
    drawChart(cRate.canvas, { ...common, noXLabels: true, y: [Math.max(0, Math.floor(mid - half)), Math.ceil(mid + half)], yTicks: 3, yFmt: v => v.toFixed(0),
      series: [{ xs: run.truth.rate.t, ys: run.truth.rate.bpm, color: "rgba(214,162,74,.75)", width: 1.4, dash: [5, 4], to: t },
               { xs: rs.t_end, ys: estimator === "time" ? rs.time : rs.spectral, color: COLORS.accent, width: 2, dots: 2.4, to: t }] });

    drawChart(cStr.canvas, { ...common, y: [0, strMax], yTicks: 2, yFmt: v => v.toFixed(2),
      series: [{ xs: run.grid_t, ys: st.apnea.baseline, color: "rgba(142,153,166,.55)", width: 1.2, dash: [5, 4], to: t },
               { xs: run.grid_t, ys: st.apnea.threshold, color: COLORS.alarm, width: 1.3, to: t },
               { xs: run.grid_t, ys: st.apnea.envelope, color: COLORS.accent, width: 1.8, fill: "rgba(107,183,170,.10)", to: t }] });
  }

  function drawOverview(t) {
    const st = run.stages, D = run.meta.duration_s, env = st.apnea.envelope, ev = st.apnea.events;
    const bands = run.truth.pauses.filter(([a]) => a < t).map(([a, b]) => ({ x0: a, x1: Math.min(b, t), color: "rgba(214,162,74,.14)" }));
    for (const e of ev) if (e.declared_at <= t) bands.push({ x0: e.start, x1: Math.min(e.end, t), color: "rgba(214,90,90,.22)" });
    const lines = st.ffc.step_times.filter(s => s <= t).map(s => ({ x: s, color: COLORS.warn, dash: [3, 3], width: 1 }));
    lines.push({ x: t, color: "#e4e8ed", width: 2 });
    drawChart(overview, { x: [0, D], y: [0, strMax], margin: { l: 14, r: 14, t: 3, b: 16 }, yTicks: 1, yFmt: () => "", xTicks: 9, xFmt: v => fmtTime(v), bands, lines,
      series: [{ xs: run.grid_t, ys: env, color: "rgba(142,153,166,.35)", width: 1 }, { xs: run.grid_t, ys: env, color: COLORS.accent, width: 1.4, fill: "rgba(107,183,170,.14)", to: t }] });
  }

  const nums = (a) => a.filter(v => v != null);
  return {
    el: root,
    setRun(r) {
      run = r; log = buildLog(r); logShown = -1; player.setRun(r);
      sigMax = Math.max(0.15, Math.max(...nums(r.stages.filtered.nostril).map(Math.abs)) * 1.25);
      const rates = [...nums(r.truth.rate.bpm), ...nums(r.stages.rate.time), ...nums(r.stages.rate.spectral)];
      rateRange = [Math.max(0, Math.floor(Math.min(...rates) - 2)), Math.ceil(Math.max(...rates) + 2)];
      strMax = Math.max(0.05, Math.max(...nums(r.stages.apnea.envelope)) * 1.12);
      paintColorbar();
    },
    toggleScale() { scaleSeg.querySelector(`button[data-v="${player.mode === "face" ? "scene" : "face"}"]`).click(); },
    update,
    relayout() { paintColorbar(); },
  };
}
