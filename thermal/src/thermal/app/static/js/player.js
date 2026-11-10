// Thermal video player: pulls frames from the server in chunks, colors them, draws ROI boxes.
import { bisect, clamp } from "./util.js";

const CHUNK = 64, ROWS = 60, COLS = 80;

// Inferno-style palette, 256 steps, built from anchor colors.
const STOPS = [[0, 0, 4], [27, 12, 66], [74, 12, 107], [120, 28, 109], [165, 44, 96], [207, 68, 70], [237, 105, 37], [251, 155, 6], [247, 208, 60], [252, 255, 164]];
export const LUT = (() => {
  const out = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i++) {
    const p = i / 255 * (STOPS.length - 1), k = Math.min(STOPS.length - 2, Math.floor(p)), f = p - k;
    for (let c = 0; c < 3; c++) out[i * 3 + c] = STOPS[k][c] + (STOPS[k + 1][c] - STOPS[k][c]) * f;
  }
  return out;
})();
export const rgb = i => `rgb(${LUT[i * 3]},${LUT[i * 3 + 1]},${LUT[i * 3 + 2]})`;

export class ThermalPlayer {
  constructor(canvas, onFrameReady) {
    this.canvas = canvas; this.ctx = canvas.getContext("2d");
    this.off = document.createElement("canvas"); this.off.width = COLS; this.off.height = ROWS;
    this.offCtx = this.off.getContext("2d"); this.img = this.offCtx.createImageData(COLS, ROWS);
    this.chunks = new Map(); this.pending = new Set(); this.onFrameReady = onFrameReady;
    this.mode = "face"; this.showRois = true; this.last = null;
    this.zoom = true; this.crop = { r0: 22, r1: 50, c0: 26, c1: 54 };  // nose + cheek area
  }
  setRun(run) { this.run = run; this.chunks.clear(); this.pending.clear(); this.last = null; this.ft = run.frame_times; }
  frameIndexAt(t) { return clamp(bisect(this.ft, t), 0, this.ft.length - 1); }
  range() { return this.run.meta.temp_range[this.mode]; }

  async _load(c) {
    if (this.chunks.has(c) || this.pending.has(c) || c * CHUNK >= this.ft.length) return;
    this.pending.add(c);
    const runId = this.run.run_id;
    try {
      const res = await fetch(`/api/frames?run=${runId}&start=${c * CHUNK}&count=${CHUNK}`);
      if (!res.ok) throw new Error(`frames ${res.status}`);
      const arr = new Int16Array(await res.arrayBuffer());
      if (this.run.run_id === runId) { this.chunks.set(c, arr); this.onFrameReady?.(); }
    } catch (e) { console.warn(e); } finally { this.pending.delete(c); }
  }

  /** Raw frame (Int16Array of centi-degC) or null if its chunk has not arrived yet. */
  frame(i) {
    const c = Math.floor(i / CHUNK);
    this._load(c); this._load(c + 1); this._load(c + 2);
    const ch = this.chunks.get(c);
    return ch ? ch.subarray((i - c * CHUNK) * COLS * ROWS, (i - c * CHUNK + 1) * COLS * ROWS) : null;
  }
  roiMean(f, box) {
    const [r0, r1, c0, c1] = box; let s = 0;
    for (let r = r0; r < r1; r++) for (let c = c0; c < c1; c++) s += f[r * COLS + c];
    return s / ((r1 - r0) * (c1 - c0)) / 100;
  }

  /** Draw the frame at time t. Returns {nostril, control} temperatures, or null while buffering. */
  draw(t) {
    const i = this.frameIndexAt(t);
    const f = this.frame(i) || this.last;
    const { w, h } = this._size();
    this.ctx.fillStyle = "#000"; this.ctx.fillRect(0, 0, w, h);
    if (!f) return null;
    if (f !== this.last) this.last = f;
    const [lo, hi] = this.range(), d = this.img.data;
    for (let p = 0; p < COLS * ROWS; p++) {
      const k = Math.round(clamp((f[p] / 100 - lo) / (hi - lo), 0, 1) * 255);
      d[p * 4] = LUT[k * 3]; d[p * 4 + 1] = LUT[k * 3 + 1]; d[p * 4 + 2] = LUT[k * 3 + 2]; d[p * 4 + 3] = 255;
    }
    this.offCtx.putImageData(this.img, 0, 0);
    this.ctx.imageSmoothingEnabled = true; this.ctx.imageSmoothingQuality = "high";
    const k = this._view();
    this.ctx.drawImage(this.off, k.c0, k.r0, k.c1 - k.c0, k.r1 - k.r0, 0, 0, w, h);
    if (this.showRois) this._rois(w, h, k);
    const rois = this.run.rois;
    return { nostril: this.roiMean(f, rois.nostril), control: this.roiMean(f, rois.control), ready: !!this.chunks.get(Math.floor(i / CHUNK)) };
  }
  _view() { return this.zoom ? this.crop : { r0: 0, r1: ROWS, c0: 0, c1: COLS }; }
  _size() {
    const dpr = Math.max(1, window.devicePixelRatio || 1), cw = this.canvas.clientWidth, ch = this.canvas.clientHeight;
    if (this.canvas.width !== Math.round(cw * dpr)) { this.canvas.width = Math.round(cw * dpr); this.canvas.height = Math.round(ch * dpr); }
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { w: cw, h: ch };
  }
  _rois(w, h, k) {
    const sx = w / (k.c1 - k.c0), sy = h / (k.r1 - k.r0), ctx = this.ctx;
    const items = [["nostril", "#9be0d3", "NOSE", []], ["control", "#a9dcb9", "CHEEK", []], ["reference", "#e4e8ed", "BACKGROUND", [5, 4]]];
    ctx.font = "600 10px ui-sans-serif, -apple-system, sans-serif"; ctx.textBaseline = "bottom";
    for (const [key, col, label, dash] of items) {
      const [r0, r1, c0, c1] = this.run.rois[key];
      if (r1 <= k.r0 || r0 >= k.r1 || c1 <= k.c0 || c0 >= k.c1) continue;  // outside the zoomed view
      const x = (c0 - k.c0) * sx, y = (r0 - k.r0) * sy;
      ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.setLineDash(dash);
      ctx.strokeRect(x, y, (c1 - c0) * sx, (r1 - r0) * sy); ctx.setLineDash([]);
      const tw = ctx.measureText(label).width + 8;
      ctx.fillStyle = "rgba(14,17,22,.8)"; ctx.fillRect(x, y - 14, tw, 13);
      ctx.fillStyle = col; ctx.textAlign = "left"; ctx.fillText(label, x + 4, y - 3);
    }
  }
}

/** Vertical color bar + labels for the active temperature range. */
export function drawColorbar(canvas, labelsEl, lo, hi) {
  const h = canvas.clientHeight || 200; canvas.width = 12; canvas.height = h;
  const ctx = canvas.getContext("2d");
  for (let y = 0; y < h; y++) { ctx.fillStyle = rgb(Math.round((1 - y / (h - 1)) * 255)); ctx.fillRect(0, y, 12, 1); }
  labelsEl.innerHTML = [hi, (hi * 3 + lo) / 4, (hi + lo) / 2, (hi + lo * 3) / 4, lo].map(v => `<span>${v.toFixed(1)}°</span>`).join("");
}
