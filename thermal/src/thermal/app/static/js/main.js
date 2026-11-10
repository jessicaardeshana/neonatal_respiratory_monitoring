// App shell: tabs, playback clock, run loading.
import { h, clamp } from "./util.js";
import { buildMonitor } from "./monitor.js";

const TABS = [
  { id: "monitor", label: "Monitor", ready: true },
  { id: "pipeline", label: "Pipeline", ready: false, blurb: "Click through all seven processing stages, from raw pixels to the apnea decision, with a plain-language explanation of each." },
  { id: "lab", label: "Lab", ready: false, blurb: "Sliders for breathing rate, pauses, incubator temperature, noise, head movement and camera glitches. Watch the result change." },
  { id: "results", label: "Results & limits", ready: false, blurb: "Accuracy numbers, the incubator study, and an honest list of what is not met or not tested yet." },
  { id: "device", label: "Device", ready: false, blurb: "Detect a thermal camera when one is plugged in and show the live feed through the same pipeline." },
];

const app = document.getElementById("app"), tabsEl = document.getElementById("tabs");

const state = {
  run: null, t: 0, playing: false, speed: 1, dirty: true, tab: "monitor",
  play() { if (this.t >= this.run.meta.duration_s - 0.05) this.t = 0; this.playing = true; this.dirty = true; },
  pause() { this.playing = false; this.dirty = true; },
  toggle() { this.playing ? this.pause() : this.play(); },
  seek(t) { this.t = clamp(t, 0, this.run.meta.duration_s); this.dirty = true; },
  redraw() { this.dirty = true; },
};

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

async function boot() {
  const views = {};
  try {
    state.run = await api("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  } catch (e) {
    app.replaceChildren(h("div", { class: "loading" }, h("div", { class: "err" }, "Could not run the simulation. Is the server running? ", String(e))));
    return;
  }
  document.querySelector("#source-badge span").textContent = state.run.source.label;

  const monitor = buildMonitor(state);
  views.monitor = h("section", { class: "view", id: "view-monitor" }, monitor.el);
  for (const t of TABS.filter(t => !t.ready)) {
    views[t.id] = h("section", { class: "view", id: `view-${t.id}`, hidden: true },
      h("div", { class: "card placeholder" }, h("div", {}, h("h2", {}, t.label), h("p", {}, t.blurb), h("p", { style: "margin-top:14px;color:var(--faint)" }, "Coming in the next build steps."))));
  }
  app.replaceChildren(...Object.values(views));
  monitor.setRun(state.run);

  const buttons = TABS.map(t => h("button", { class: "tab", role: "tab", "aria-selected": String(t.id === state.tab), onclick: () => select(t.id) },
    t.label, t.ready ? null : h("span", { class: "soon" }, "soon")));
  tabsEl.replaceChildren(...buttons);
  function select(id) {
    state.tab = id;
    TABS.forEach((t, i) => { buttons[i].setAttribute("aria-selected", String(t.id === id)); views[t.id].hidden = t.id !== id; });
    state.dirty = true;
  }

  addEventListener("keydown", e => {
    if (e.target.closest("input, select, textarea") || state.tab !== "monitor") return;
    if (e.code === "Space") { e.preventDefault(); state.toggle(); }
    else if (e.code === "ArrowRight") state.seek(state.t + (state.playing ? 5 : 1 / state.run.meta.fs));
    else if (e.code === "ArrowLeft") state.seek(state.t - (state.playing ? 5 : 1 / state.run.meta.fs));
    else if (e.key === "s" || e.key === "S") monitor.toggleScale();
  });
  addEventListener("resize", () => { monitor.relayout(); state.redraw(); });

  let last = performance.now();
  (function loop(now) {
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    if (state.playing) {
      state.t += dt * state.speed;
      if (state.t >= state.run.meta.duration_s) { state.t = state.run.meta.duration_s; state.playing = false; }
      state.dirty = true;
    }
    if (state.dirty && state.tab === "monitor") { state.dirty = false; monitor.update(state.t); }
    requestAnimationFrame(loop);
  })(last);
  window.__app = state;  // handy for debugging in the browser console
}
boot();
