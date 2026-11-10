// Minimal canvas line charts: crisp on HiDPI, no libraries, works offline.
import { bisect } from "./util.js";

const FONT = '12px ui-sans-serif, -apple-system, "Segoe UI", Inter, sans-serif';
export const COLORS = { grid: "#1d2b3d", axis: "#5f7087", text: "#8a9bb0", accent: "#38d9c8", alarm: "#ff4d5e",
  warn: "#ffb547", blue: "#5aa9ff", good: "#3ddc97", white: "#e8eef6" };

/** Size a canvas to its CSS box at device pixel ratio; returns a context drawing in CSS pixels. */
export function fitCanvas(canvas) {
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  const w = Math.max(10, canvas.clientWidth), hgt = Math.max(10, canvas.clientHeight);
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(hgt * dpr)) {
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(hgt * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h: hgt };
}

/** Nice round tick values covering [lo, hi]. */
export function ticks(lo, hi, n = 5) {
  const span = hi - lo, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || raw;
  const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

/**
 * Draw a time-series chart.
 *  o.x = [x0, x1], o.y = [y0, y1]; o.margin = {l,r,t,b}
 *  o.bands  = [{x0, x1, color, label?}]           shaded time spans
 *  o.lines  = [{x, color, dash?, label?}]         vertical markers
 *  o.series = [{xs, ys, color, width?, fill?, from?, to?}]  polylines (null y breaks the line)
 *  o.hlines = [{y, color, dash?, label?}]
 */
export function drawChart(canvas, o) {
  const { ctx, w, h } = fitCanvas(canvas);
  const m = { l: 46, r: 14, t: 12, b: 26, ...(o.margin || {}) };
  const pw = w - m.l - m.r, ph = h - m.t - m.b;
  const X = v => m.l + (v - o.x[0]) / (o.x[1] - o.x[0]) * pw;
  const Y = v => m.t + (1 - (v - o.y[0]) / (o.y[1] - o.y[0])) * ph;
  ctx.clearRect(0, 0, w, h);
  ctx.font = FONT; ctx.textBaseline = "middle";

  // grid + y labels
  ctx.lineWidth = 1;
  for (const v of ticks(o.y[0], o.y[1], o.yTicks || 4)) {
    const y = Math.round(Y(v)) + 0.5;
    ctx.strokeStyle = v === 0 ? "#2b3d55" : COLORS.grid; ctx.beginPath(); ctx.moveTo(m.l, y); ctx.lineTo(w - m.r, y); ctx.stroke();
    ctx.fillStyle = COLORS.text; ctx.textAlign = "right"; ctx.fillText(o.yFmt ? o.yFmt(v) : v.toFixed(1), m.l - 8, y);
  }
  // x labels
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  for (const v of ticks(o.x[0], o.x[1], o.xTicks || 6)) {
    const x = Math.round(X(v)) + 0.5;
    ctx.strokeStyle = COLORS.grid; ctx.beginPath(); ctx.moveTo(x, m.t); ctx.lineTo(x, m.t + ph); ctx.stroke();
    ctx.fillStyle = COLORS.text; ctx.fillText(o.xFmt ? o.xFmt(v) : String(v), x, h - m.b + 7);
  }
  ctx.save(); ctx.beginPath(); ctx.rect(m.l, m.t, pw, ph); ctx.clip();

  for (const b of o.bands || []) {
    const x0 = Math.max(m.l, X(b.x0)), x1 = Math.min(m.l + pw, X(b.x1));
    if (x1 <= x0) continue;
    ctx.fillStyle = b.color; ctx.fillRect(x0, m.t, x1 - x0, ph);
    if (b.label) { ctx.fillStyle = b.labelColor || COLORS.text; ctx.font = "600 11px " + FONT.split("px ")[1]; ctx.textAlign = "left"; ctx.textBaseline = "top";
      ctx.fillText(b.label, x0 + 8, m.t + 7 + (b.labelDy || 0)); ctx.font = FONT; }
  }
  for (const hl of o.hlines || []) {
    const y = Y(hl.y); ctx.strokeStyle = hl.color; ctx.setLineDash(hl.dash || [5, 4]); ctx.beginPath(); ctx.moveTo(m.l, y); ctx.lineTo(w - m.r, y); ctx.stroke(); ctx.setLineDash([]);
    if (hl.label) { ctx.fillStyle = hl.color; ctx.textAlign = "right"; ctx.textBaseline = "bottom"; ctx.fillText(hl.label, w - m.r - 6, y - 3); }
  }
  for (const s of o.series || []) {
    const i0 = Math.max(0, bisect(s.xs, o.x[0]) - 1), i1 = Math.min(s.xs.length - 1, bisect(s.xs, o.x[1]) + 1);
    const stop = s.to != null ? Math.min(i1, bisect(s.xs, s.to)) : i1;
    ctx.beginPath(); let pen = false, first = null, last = null;
    for (let i = i0; i <= stop; i++) {
      const v = s.ys[i];
      if (v == null) { pen = false; continue; }
      const x = X(s.xs[i]), y = Y(v);
      if (!pen) { ctx.moveTo(x, y); pen = true; first = first ?? x; } else ctx.lineTo(x, y);
      last = x;
    }
    ctx.lineJoin = "round"; ctx.lineWidth = s.width || 2; ctx.strokeStyle = s.color; ctx.stroke();
    if (s.fill && first != null) {
      ctx.lineTo(last, Y(Math.max(o.y[0], 0))); ctx.lineTo(first, Y(Math.max(o.y[0], 0))); ctx.closePath();
      ctx.fillStyle = s.fill; ctx.fill();
    }
  }
  for (const l of o.lines || []) {
    const x = Math.round(X(l.x)) + 0.5;
    ctx.strokeStyle = l.color; ctx.lineWidth = l.width || 1.5; ctx.setLineDash(l.dash || []); ctx.beginPath(); ctx.moveTo(x, m.t); ctx.lineTo(x, m.t + ph); ctx.stroke(); ctx.setLineDash([]);
    if (l.label) { ctx.fillStyle = l.color; ctx.textAlign = l.align || "left"; ctx.textBaseline = "top"; ctx.fillText(l.label, x + (l.align === "right" ? -6 : 6), m.t + (l.dy || 24)); }
  }
  ctx.restore();
  return { X, Y, m, pw, ph, w, h };
}
