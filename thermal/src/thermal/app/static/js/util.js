// Small helpers shared by every view.
export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
export const lerp = (a, b, t) => a + (b - a) * t;

/** Rightmost index i with arr[i] <= x (arr ascending). Returns -1 if x is before the first element. */
export function bisect(arr, x) {
  let lo = 0, hi = arr.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] <= x) lo = mid + 1; else hi = mid; }
  return lo - 1;
}

/** 83.4 -> "01:23" (or "01:23.4" with tenths). */
export function fmtTime(s, tenths = false) {
  s = Math.max(0, s);
  const m = Math.floor(s / 60), r = s - m * 60;
  const body = tenths ? r.toFixed(1).padStart(4, "0") : String(Math.floor(r)).padStart(2, "0");
  return `${String(m).padStart(2, "0")}:${body}`;
}

/** Tiny DOM builder: h("div", {class: "x", onclick: fn}, child, "text"). */
export function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(kid));
  return e;
}

export const svgIcon = (path, size = 24, extra = "") =>
  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" ${extra}>${path}</svg>`;
export const ICON = {
  play: '<path d="M7 4.5v15l13-7.5z" fill="currentColor" stroke="none"/>',
  pause: '<rect x="6" y="4.5" width="4.2" height="15" rx="1" fill="currentColor" stroke="none"/><rect x="13.8" y="4.5" width="4.2" height="15" rx="1" fill="currentColor" stroke="none"/>',
  alert: '<path d="M12 3 2.5 20h19z"/><path d="M12 10v4.5M12 17.5v.01"/>',
};
