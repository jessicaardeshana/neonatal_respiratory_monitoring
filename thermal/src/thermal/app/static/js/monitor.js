// Monitor screen: thermal video, breathing rate, status/alarm, and the live signal strip.
import { bisect, clamp, fmtTime, h, svgIcon, ICON } from "./util.js";
import { drawChart, COLORS } from "./chart.js";
import { ThermalPlayer, drawColorbar } from "./player.js";

const STRIP_S = 30; // the strip always shows the last 30 s of measuring

/** Everything the screen needs to know about moment ``t``, derived from the pipeline's real output. */
export function describe(run, t) {
  const m = run.meta, st = run.stages, ev = st.apnea.events;
  const out = { rate: null, quality: null, progress: null, strength: null, alarm: null, lost: null, suspected: null };
  const ri = bisect(st.rate.t_end, t);
  if (ri < 0) out.progress = clamp(t / m.window_s, 0, 1);
  else { out.rateIdx = ri; out.quality = st.rate.quality[ri]; }
  const gi = bisect(run.grid_t, t);
  if (gi >= 0) {
    const e = st.apnea.envelope[gi], b = st.apnea.baseline[gi], th = st.apnea.threshold[gi];
    if (e != null && b != null && b > 0) out.strength = e / b;
    if (e != null && th != null && e < th) {  // envelope below threshold right now: how long has it been?
      let j = gi; while (j > 0 && st.apnea.envelope[j - 1] != null && st.apnea.threshold[j - 1] != null && st.apnea.envelope[j - 1] < st.apnea.threshold[j - 1]) j--;
      out.suspected = (run.grid_t[gi] - run.grid_t[j]) + (1 - m.k * m.k) * m.envelope_window_s; // envelope reacts late
    }
  }
  out.alarm = ev.find(e => e.kind === "apnea" && e.declared_at <= t && t < e.end) || null;
  out.lost = ev.find(e => e.kind === "signal_lost" && e.declared_at <= t && t < e.end) || null;
  return out;
}

export function buildLog(run) {
  const items = [], st = run.stages, m = run.meta;
  if (st.rate.t_end.length) items.push({ t: st.rate.t_end[0], kind: "good", title: "First reading ready", sub: `The ${m.window_s} s window is full` });
  for (const s of st.ffc.step_times) items.push({ t: s, kind: "info", title: "Camera recalibration detected", sub: "Frozen frame and level jump repaired automatically" });
  for (const e of st.apnea.events) {
    if (e.kind === "apnea") {
      items.push({ t: e.declared_at, kind: "alarm", title: "Apnea alarm raised", sub: `No breathing for ${m.min_pause_s} s or more (began about ${fmtTime(e.start)})` });
      items.push({ t: e.end, kind: "good", title: "Breathing resumed", sub: `Pause lasted about ${Math.round(e.end - e.start)} s` });
    } else {
      items.push({ t: e.declared_at, kind: "warn", title: "Signal lost", sub: "Breathing cannot be seen: signal too weak" });
      items.push({ t: e.end, kind: "good", title: "Signal back", sub: "Breathing visible again" });
    }
  }
  return items.sort((a, b) => a.t - b.t);
}

export function buildMonitor(state) {
  let run = null, log = [], logShown = -1, estimator = "time", yMax = 1;
  const root = h("div", { class: "monitor" });

  // ---- alarm banner
  const alarmText = h("span"), alarmSecs = h("small");
  const alarm = h("div", { class: "banner", role: "alert" }, h("span", { html: svgIcon(ICON.alert, 30) }), alarmText, alarmSecs);
  root.append(h("div", { class: "alarm-slot" }, alarm));

  // ---- thermal card
  const canvas = h("canvas"), cbCanvas = h("canvas"), cbLabels = h("div", { class: "cb-labels" });
  const overlayTitle = h("span", {}, "Play the story"), overlaySub = h("small", {}, "");
  const overlay = h("button", { class: "play-overlay", "aria-label": "Play the story", onclick: () => state.play() },
    h("div", { class: "disc", html: svgIcon(ICON.play, 38, 'style="color:#04211e;margin-left:4px"') }), overlayTitle, overlaySub);
  const nosVal = h("b", { class: "num" }, "—"), ctlVal = h("b", { class: "num" }, "—");
  const modeSeg = h("div", { class: "seg", role: "group", "aria-label": "Temperature scale" },
    h("button", { "aria-pressed": "true", "data-m": "face", title: "Zoom the color scale to face temperatures so breathing is visible" }, "Face range"),
    h("button", { "aria-pressed": "false", "data-m": "scene", title: "Show the whole scene, room to face" }, "Full scene"));
  const roiSeg = h("div", { class: "seg", role: "group", "aria-label": "Region boxes" },
    h("button", { "aria-pressed": "true", "data-r": "1" }, "Boxes on"), h("button", { "aria-pressed": "false", "data-r": "0" }, "Off"));
  const thermalCard = h("section", { class: "card thermal" },
    h("div", { class: "card-title" }, h("span", {}, "Thermal camera"), h("span", { class: "tag sim" }, "SIMULATED · 80×60 PX")),
    h("div", { class: "stage" }, h("div", { class: "canvas-wrap" }, canvas, overlay), h("div", { class: "colorbar" }, cbCanvas, cbLabels)),
    h("div", { class: "readouts" },
      h("div", { class: "readout" }, h("label", {}, h("i", { style: "background:#38d9c8" }), "Nostril"), nosVal),
      h("div", { class: "readout" }, h("label", {}, h("i", { style: "background:#3ddc97" }), "Cheek (control)"), ctlVal),
      h("div", { style: "display:flex;flex-direction:column;gap:8px;justify-content:center" }, modeSeg, roiSeg)));
  thermalCard.querySelectorAll(".readout b").forEach(b => b.append(h("em", {}, "°C")));
  root.append(thermalCard);

  // ---- rate card
  const rateNum = h("div", { class: "rate-value num" }, "—");
  const ringNum = h("b", {}, "0s"), ring = h("div", { class: "ring", style: "--p:0" }, ringNum);
  const rateUnit = h("div", { class: "rate-unit" }, "BREATHS / MIN");
  const rateCap = h("div", { class: "rate-caption" }, "");
  const truthLine = h("div", { class: "truth-line num" }, "");
  const qBar = h("span"), qVal = h("span", { class: "num" }, "—"), sBar = h("span"), sVal = h("span", { class: "num" }, "—");
  const estSeg = h("div", { class: "seg", role: "group", "aria-label": "Rate estimator" },
    h("button", { "aria-pressed": "true", "data-e": "time", title: "Counts the spacing between breaths" }, "Counting"),
    h("button", { "aria-pressed": "false", "data-e": "spectral", title: "Finds the dominant frequency" }, "Spectrum"));
  const rateCard = h("section", { class: "card rate" },
    h("div", { class: "card-title" }, h("span", {}, "Breathing rate"), estSeg),
    h("div", { class: "rate-hero" }, rateNum, ring, rateUnit, rateCap, truthLine),
    h("div", { class: "meter" }, h("div", { class: "meter-head" }, h("span", {}, "Signal quality"), qVal), h("div", { class: "bar" }, qBar)),
    h("div", { class: "meter" }, h("div", { class: "meter-head" }, h("span", {}, "Breathing strength vs. normal"), sVal),
      h("div", { class: "bar" }, sBar, h("i", { style: "left:16.7%", title: "Pause threshold: 25% of normal" }))));
  root.append(rateCard);

  // ---- status card
  const chipTitle = h("div", {}, "—"), chipSub = h("small", {}, ""), chipDot = h("span", { class: "dot" });
  const chip = h("div", { class: "chip idle" }, chipDot, h("div", {}, chipTitle, chipSub));
  const logEl = h("ul", { class: "log" });
  const statusCard = h("section", { class: "card status" }, h("div", { class: "card-title" }, h("span", {}, "Status"), h("span", { class: "tag" }, "WHAT THE SOFTWARE SEES")),
    chip, h("div", { class: "card-title", style: "margin:22px 0 0" }, h("span", {}, "Event log")), logEl);
  root.append(statusCard);

  // ---- signal card
  const strip = h("canvas", { id: "strip", "aria-label": "Breathing signal, last 30 seconds" });
  const overview = h("canvas", { id: "overview", "aria-label": "Whole recording. Click to jump." });
  const playBtn = h("button", { class: "play-btn", "aria-label": "Play or pause", onclick: () => state.toggle() });
  const clock = h("div", { class: "clock num" }, "00:00");
  const speedSeg = h("div", { class: "seg", role: "group", "aria-label": "Playback speed" },
    ...[1, 2, 4, 8].map(s => h("button", { "aria-pressed": String(s === 1), "data-s": s }, `${s}×`)));
  const legend = h("div", { class: "legend" },
    h("span", {}, h("i", { style: "background:#38d9c8" }), "Breathing signal (cleaned)"),
    h("span", {}, h("i", { class: "box", style: "background:rgba(255,181,71,.55)" }), "Simulated true pause"),
    h("span", {}, h("i", { class: "box", style: "background:rgba(255,77,94,.65)" }), "Detected apnea"),
    h("span", {}, h("i", { style: "background:#ffb547" }), "Camera recalibration"));
  const signalCard = h("section", { class: "card signal" },
    h("div", { class: "card-title" }, h("span", {}, "Breathing signal · last 30 seconds"), h("span", { class: "tag sim" }, "TRUE PAUSE SHOWN FOR THE DEMO ONLY")),
    strip, overview, h("div", { class: "transport" }, playBtn, clock, speedSeg, legend),
    h("div", { class: "hint" }, "Click the bar above to jump. Space = play/pause, ← → = step, S = full scene colors."));
  root.append(signalCard);

  // ---- wiring
  const player = new ThermalPlayer(canvas, () => state.redraw());
  modeSeg.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return;
    player.mode = b.dataset.m; modeSeg.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); paintColorbar(); state.redraw(); });
  roiSeg.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return;
    player.showRois = b.dataset.r === "1"; roiSeg.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); state.redraw(); });
  estSeg.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return;
    estimator = b.dataset.e; estSeg.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); state.redraw(); });
  speedSeg.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return;
    state.speed = +b.dataset.s; speedSeg.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); });
  overview.addEventListener("pointerdown", e => { overview.setPointerCapture(e.pointerId); seek(e); });
  overview.addEventListener("pointermove", e => { if (e.buttons) seek(e); });
  function seek(e) { const r = overview.getBoundingClientRect(); const f = clamp((e.clientX - r.left - 14) / (r.width - 28), 0, 1); state.seek(f * run.meta.duration_s); }
  function paintColorbar() { const [lo, hi] = player.range(); drawColorbar(cbCanvas, cbLabels, lo, hi); }

  // ---- per-frame update
  function update(t) {
    if (!run) return;
    const m = run.meta, st = run.stages, d = describe(run, t);
    // thermal
    const r = player.draw(t);
    if (r) { nosVal.firstChild.nodeValue = r.nostril.toFixed(2); ctlVal.firstChild.nodeValue = r.control.toFixed(2); }
    // rate
    const arr = estimator === "time" ? st.rate.time : st.rate.spectral;
    const val = d.rateIdx != null ? arr[d.rateIdx] : null;
    const alarmOn = !!d.alarm, lostOn = !!d.lost;
    ring.style.display = d.progress != null ? "grid" : "none";
    rateNum.style.display = d.progress != null ? "none" : "";
    if (d.progress != null) { ring.style.setProperty("--p", (d.progress * 100).toFixed(1)); ringNum.textContent = `${Math.floor(t)}s`; rateCap.textContent = `Measuring… the first reading needs a ${m.window_s} s window`; }
    else if (val != null) { rateNum.textContent = val.toFixed(1); rateNum.className = "rate-value num"; rateCap.textContent = estimator === "time" ? "Counting the time between breaths" : "Dominant frequency of the breathing signal"; }
    else { rateNum.textContent = "—"; rateNum.className = "rate-value num " + (alarmOn ? "alarm" : "dim"); rateCap.textContent = alarmOn ? "No breathing detected" : "No reliable reading: the signal is too weak or irregular"; }
    const ti = bisect(run.truth.rate.t, t);
    truthLine.textContent = ti >= 0 && run.truth.rate.bpm[ti] != null ? `Simulation truth: ${run.truth.rate.bpm[ti].toFixed(1)} breaths/min` : "";
    // meters
    const q = d.quality; qBar.style.width = `${clamp((q ?? 0) * 100, 0, 100)}%`; qVal.textContent = q == null ? "measuring…" : `${Math.round(q * 100)}%`;
    qBar.style.background = q != null && q < 0.5 ? "var(--warn)" : "var(--accent)";
    const s = d.strength; sBar.style.width = `${clamp((s ?? 0) / 1.5 * 100, 0, 100)}%`; sVal.textContent = s == null ? "measuring…" : `${Math.round(s * 100)}%`;
    sBar.style.background = s != null && s < m.k ? "var(--alarm)" : "var(--accent)";
    // status chip + banner
    let cls = "idle", title = "Measuring", sub = "Building the first reading";
    if (alarmOn) { cls = "alarm"; title = "Apnea alarm"; sub = `No breathing for ${Math.round(t - d.alarm.start)} s`; }
    else if (lostOn) { cls = "warn"; title = "Signal lost"; sub = "Breathing cannot be seen"; }
    else if (d.suspected != null && d.suspected > 1) { cls = "warn"; title = "Pause suspected"; sub = `Breathing strength is very low · ${Math.round(d.suspected)} s of ${m.min_pause_s} s`; }
    else if (d.progress == null) { cls = val != null ? "good" : "warn"; title = val != null ? "Breathing detected" : "No reliable reading"; sub = val != null ? "Rate is being tracked" : "Waiting for a clearer signal"; }
    chip.className = `chip ${cls}`; chipTitle.textContent = title; chipSub.textContent = sub;
    alarm.classList.toggle("on", alarmOn);
    if (alarmOn) { alarmText.textContent = "APNEA ALARM: no breathing detected"; alarmSecs.textContent = `${Math.round(t - d.alarm.start)} s without breathing`; }
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
    overlay.hidden = state.playing || (started && !ended);
    overlayTitle.textContent = ended ? "Replay the story" : "Play the story";
    overlaySub.textContent = ended ? "" : "About 3 minutes of simulated measuring: steady breathing, a speed-up, a pause and a recovery";
    playBtn.innerHTML = svgIcon(state.playing ? ICON.pause : ICON.play, 20, state.playing ? "" : 'style="margin-left:2px"');
    clock.innerHTML = `${fmtTime(t)} <span>/ ${fmtTime(m.duration_s)}</span>`;
    drawStrip(t); drawOverview(t);
  }

  function drawStrip(t) {
    const st = run.stages, x0 = Math.max(0, t - STRIP_S), ev = st.apnea.events;
    const bands = run.truth.pauses.filter(([a]) => a < t).map(([a, b]) => ({ x0: a, x1: Math.min(b, t), color: "rgba(255,181,71,.10)", label: "SIMULATED TRUE PAUSE", labelColor: COLORS.warn, labelDy: 0 }));
    for (const e of ev) if (e.declared_at <= t) bands.push({ x0: e.start, x1: Math.min(e.end, t), color: e.kind === "apnea" ? "rgba(255,77,94,.17)" : "rgba(90,169,255,.16)", label: e.kind === "apnea" ? "APNEA DETECTED" : "SIGNAL LOST", labelColor: e.kind === "apnea" ? "#ff8a96" : COLORS.blue, labelDy: 18 });
    const lines = st.ffc.step_times.filter(s => s <= t).map(s => ({ x: s, color: COLORS.warn, dash: [4, 4], label: "calibration glitch (repaired)" }));
    lines.push({ x: t, color: "rgba(232,238,246,.85)", width: 1.5 });
    drawChart(strip, { x: [x0, x0 + STRIP_S], y: [-yMax, yMax], margin: { l: 52, r: 16, t: 12, b: 26 }, yTicks: 4,
      xFmt: v => fmtTime(v), yFmt: v => (v > 0 ? "+" : "") + v.toFixed(1), bands, lines,
      series: [{ xs: run.grid_t, ys: st.filtered.nostril, color: COLORS.accent, width: 2.2, to: t }] });
  }

  function drawOverview(t) {
    const st = run.stages, D = run.meta.duration_s, env = st.apnea.envelope, ev = st.apnea.events;
    const top = Math.max(...env.filter(v => v != null)) * 1.15;
    const bands = run.truth.pauses.filter(([a]) => a < t).map(([a, b]) => ({ x0: a, x1: Math.min(b, t), color: "rgba(255,181,71,.12)" }));
    for (const e of ev) if (e.declared_at <= t) bands.push({ x0: e.start, x1: Math.min(e.end, t), color: "rgba(255,77,94,.22)" });
    const lines = st.ffc.step_times.filter(s => s <= t).map(s => ({ x: s, color: COLORS.warn, dash: [3, 3], width: 1 }));
    lines.push({ x: t, color: "#e8eef6", width: 2 });
    drawChart(overview, { x: [0, D], y: [0, top], margin: { l: 14, r: 14, t: 6, b: 20 }, yTicks: 2, yFmt: () => "", xTicks: 8, xFmt: v => fmtTime(v), bands, lines,
      series: [{ xs: run.grid_t, ys: env, color: "rgba(138,155,176,.35)", width: 1.2 }, { xs: run.grid_t, ys: env, color: COLORS.accent, width: 1.8, fill: "rgba(56,217,200,.16)", to: t }] });
  }

  return {
    el: root,
    setRun(r) {
      run = r; log = buildLog(r); logShown = -1; player.setRun(r);
      const mx = Math.max(...r.stages.filtered.nostril.filter(v => v != null).map(Math.abs));
      yMax = Math.max(0.15, mx * 1.3);
      paintColorbar();
    },
    toggleScale() { modeSeg.querySelector(`button[data-m="${player.mode === "face" ? "scene" : "face"}"]`).click(); },
    update,
  };
}
