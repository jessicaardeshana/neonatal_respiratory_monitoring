// MedAxis site: signal animations, scroll reveals, small interactions.
(() => {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const css = getComputedStyle(document.documentElement);
  const C = {
    cyan: css.getPropertyValue("--cyan").trim() || "#3ee6e0",
    red: css.getPropertyValue("--red").trim() || "#ff4d5e",
    amber: css.getPropertyValue("--amber").trim() || "#ffb547",
    grid: "rgba(150,165,255,0.07)",
  };

  // ---------- canvas helper (crisp on Retina, resizes with layout)
  function setupCanvas(canvas, draw) {
    const ctx = canvas.getContext("2d");
    const cssH = Number(canvas.getAttribute("height"));
    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = canvas.clientWidth;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(cssH * dpr);
      canvas.style.height = cssH + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw.size = { w, h: cssH };
      if (draw.redraw) draw.redraw();   // resizing clears a canvas: paint it again
    }
    resize();
    new ResizeObserver(resize).observe(canvas);
    return ctx;
  }

  function drawGrid(ctx, w, h, step = 32) {
    ctx.strokeStyle = C.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = 0; x <= w; x += step) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, h); }
    for (let y = 0; y <= h; y += step) { ctx.moveTo(0, y + 0.5); ctx.lineTo(w, y + 0.5); }
    ctx.stroke();
  }

  // Only animate canvases that are on screen.
  function whenVisible(el, start, stop) {
    new IntersectionObserver(([e]) => (e.isIntersecting ? start() : stop()), { threshold: 0.05 }).observe(el);
  }

  // ---------- hero: real prototype trace, replayed like a bedside monitor
  const trace = window.MEDAXIS_TRACE;
  const hero = document.getElementById("hero-signal");
  if (hero && trace) {
    // Trim filter edge effects at both ends, then cross-fade the end into the
    // start so the replay loops without a visible jump.
    const fs = trace.fs, cut0 = Math.round(0.6 * fs), cut1 = Math.round(1.6 * fs);
    const y = trace.y.slice(cut0, trace.y.length - cut1);
    const fade = Math.round(1.0 * fs);
    for (let i = 0; i < fade; i++) {
      const a = (i + 1) / (fade + 1), j = y.length - fade + i;
      y[j] = y[j] * (1 - a) + y[i] * a;
    }
    const total = y.length / fs, off = cut0 / fs;
    const apnea = (trace.apnea || []).map(([a, b]) => [a - off, b - off]);
    const breaths = (trace.breaths || []).map((b) => b - off).filter((b) => b > 0 && b < total - 1);
    const status = document.getElementById("hero-status");
    const stateEl = document.getElementById("hero-state");
    const readout = document.getElementById("hero-readout");
    const WINDOW = 16; // seconds visible
    const draw = () => {};
    const ctx = setupCanvas(hero, draw);
    // Start just after the recorded apnea, so visitors first see ~30 s of calm
    // breathing, then the pause -> apnea alert sequence.
    let t = (apnea.length ? apnea[0][1] + 1 : 0) + WINDOW, last = null, raf = null;

    const sample = (s) => {
      const i = ((s % total) + total) % total * fs;
      const i0 = Math.floor(i), f = i - i0;
      return y[i0 % y.length] * (1 - f) + y[(i0 + 1) % y.length] * f;
    };

    function setState(tt) {
      const s = tt % total;
      const ap = apnea.find(([a, b]) => s >= a && s <= b);
      let cls = "", text = "Breathing", read = `${Math.round(trace.rate_bpm)} /min`;
      if (ap) {
        const d = s - ap[0];
        if (d >= 20) { cls = "apnea"; text = "Apnea alert"; read = `${Math.floor(d)} s`; }
        else if (d >= 10) { cls = "pause"; text = "Pause"; read = `${Math.floor(d)} s`; }
        else { text = "No breath"; read = `${Math.floor(d)} s`; }
      } else if (apnea.some(([a, b]) => s > b && s < b + 5)) { text = "Breathing resumed"; }
      status.className = "status " + cls;
      stateEl.textContent = text;
      readout.textContent = read;
      return cls;
    }

    function frame(now, once = false) {
      const { w, h } = draw.size;
      if (!once) {
        if (last !== null) t += Math.min(0.1, (now - last) / 1000);
        last = now;
      }
      ctx.clearRect(0, 0, w, h);
      drawGrid(ctx, w, h);
      const cls = setState(t);
      const pad = 18, mid = h / 2, amp = (h / 2 - pad) / 1.2;
      const x0 = t - WINDOW;
      const toX = (s) => ((s - x0) / WINDOW) * w;

      // Apnea bands (shown as they would be detected: after 10 s amber, 20 s red)
      for (let k = Math.floor(x0 / total); k <= Math.floor(t / total); k++) {
        for (const [a, b] of apnea) {
          const A = a + k * total, B = Math.min(b + k * total, t);
          if (t < A + 10) continue;
          const red = t >= A + 20;
          ctx.fillStyle = red ? "rgba(255,77,94,0.13)" : "rgba(255,181,71,0.1)";
          ctx.fillRect(toX(A), 0, toX(B) - toX(A), h);
        }
      }

      // Trace with glow; older samples fade.
      const grad = ctx.createLinearGradient(0, 0, w, 0);
      grad.addColorStop(0, "rgba(62,230,224,0)");
      grad.addColorStop(0.25, "rgba(62,230,224,0.55)");
      grad.addColorStop(1, cls === "apnea" ? C.red : C.cyan);
      ctx.strokeStyle = grad;
      ctx.lineWidth = 2.2;
      ctx.shadowColor = cls === "apnea" ? C.red : C.cyan;
      ctx.shadowBlur = 12;
      ctx.beginPath();
      const step = WINDOW / w * 1.5;
      for (let s = x0; s <= t; s += step) {
        const px = toX(s), py = mid - sample(s) * amp;
        s === x0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
      }
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Detected breaths
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      for (let k = Math.floor(x0 / total); k <= Math.floor(t / total); k++) {
        for (const b of breaths) {
          const s = b + k * total;
          if (s < x0 || s > t) continue;
          ctx.beginPath(); ctx.arc(toX(s), mid - sample(s) * amp, 2.6, 0, Math.PI * 2); ctx.fill();
        }
      }

      // Leading dot
      const ly = mid - sample(t) * amp;
      ctx.fillStyle = cls === "apnea" ? C.red : C.cyan;
      ctx.shadowColor = ctx.fillStyle; ctx.shadowBlur = 18;
      ctx.beginPath(); ctx.arc(w - 1, ly, 4.5, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur = 0;

      if (!reduced && !once) raf = requestAnimationFrame(frame);
    }
    draw.redraw = () => { if (!raf) frame(0, true); };
    draw.redraw();
    if (!reduced) whenVisible(hero, () => { if (!raf) { last = null; raf = requestAnimationFrame(frame); } },
                           () => { cancelAnimationFrame(raf); raf = null; });
  }

  // ---------- "today": illustrative noisy impedance-style signal
  const noisy = document.getElementById("noisy-signal");
  if (noisy) {
    const draw = () => {};
    const ctx = setupCanvas(noisy, draw);
    let t = 0, last = null, raf = null;
    const rnd = (s) => { const x = Math.sin(s * 12.9898) * 43758.5453; return x - Math.floor(x); };
    const sig = (s) => {
      const breath = Math.sin(s * 2 * Math.PI * 0.75) * 0.45;
      const cardiac = Math.sin(s * 2 * Math.PI * 2.3) * 0.12;          // heartbeat bleeding in
      const noise = (rnd(Math.floor(s * 40)) - 0.5) * 0.35;
      const motion = Math.max(0, Math.sin(s * 0.9)) ** 18 * 1.4 * Math.sin(s * 9); // motion artifact bursts
      const drift = Math.sin(s * 0.23) * 0.25;
      return breath + cardiac + noise + motion + drift;
    };
    function frame(now, once = false) {
      const { w, h } = draw.size;
      if (!once) {
        if (last !== null) t += Math.min(0.1, (now - last) / 1000);
        last = now;
      }
      ctx.clearRect(0, 0, w, h);
      drawGrid(ctx, w, h, 28);
      ctx.strokeStyle = "rgba(255,181,71,0.85)";
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      const W = 10;
      for (let px = 0; px <= w; px += 2) {
        const s = t - W + (px / w) * W;
        const py = h / 2 - sig(s) * (h / 4.2);
        px === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
      }
      ctx.stroke();
      if (!reduced && !once) raf = requestAnimationFrame(frame);
    }
    draw.redraw = () => { if (!raf) frame(0, true); };
    draw.redraw();
    if (!reduced) whenVisible(noisy, () => { if (!raf) { last = null; raf = requestAnimationFrame(frame); } },
                            () => { cancelAnimationFrame(raf); raf = null; });
  }

  // ---------- progress: the full prototype trace, drawn once when visible
  const proof = document.getElementById("proof-signal");
  if (proof && trace) {
    const draw = () => {};
    const ctx = setupCanvas(proof, draw);
    let progress = reduced ? 1 : 0, raf = null, started = false;
    function render() {
      const { w, h } = draw.size;
      const y = trace.y, n = y.length, total = n / trace.fs;
      ctx.clearRect(0, 0, w, h);
      for (const [a, b] of trace.apnea || []) {
        ctx.fillStyle = "rgba(255,77,94,0.14)";
        ctx.fillRect((a / total) * w, 0, ((b - a) / total) * w, h);
        if (progress * total > a + 20) {
          ctx.fillStyle = C.red;
          ctx.font = "600 10px JetBrains Mono, monospace";
          ctx.fillText("APNEA FLAG · " + Math.round(b - a) + " s", (a / total) * w + 8, 16);
        }
      }
      const upto = Math.floor(n * progress);
      ctx.strokeStyle = C.cyan; ctx.lineWidth = 1.6;
      ctx.shadowColor = C.cyan; ctx.shadowBlur = 8;
      ctx.beginPath();
      for (let i = 0; i < upto; i++) {
        const px = (i / (n - 1)) * w, py = h / 2 - y[i] * (h / 2.8);
        i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
      }
      ctx.stroke(); ctx.shadowBlur = 0;
    }
    function tick() {
      progress = Math.min(1, progress + 0.006);
      render();
      if (progress < 1) raf = requestAnimationFrame(tick);
    }
    draw.redraw = render;
    new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !started) { started = true; reduced ? render() : (raf = requestAnimationFrame(tick)); }
    }, { threshold: 0.4 }).observe(proof);
    render();
  }

  // ---------- reveals, nav, counter, team photos, copy email
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }, { threshold: 0.15, rootMargin: "0px 0px -40px 0px" });
  document.querySelectorAll(".reveal").forEach((el) => io.observe(el));

  const nav = document.getElementById("nav");
  const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 20);
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  const grams = document.getElementById("grams");
  if (grams) {
    const to = Number(grams.dataset.to);
    new IntersectionObserver(([e], obs) => {
      if (!e.isIntersecting) return;
      obs.disconnect();
      if (reduced) { grams.textContent = to; return; }
      const t0 = performance.now(), dur = 1400;
      const step = (now) => {
        const p = Math.min(1, (now - t0) / dur), eased = 1 - Math.pow(1 - p, 3);
        grams.textContent = Math.round(to * eased);
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }, { threshold: 0.6 }).observe(grams);
  }

  // Team photos: show initials until a photo file exists in assets/team/.
  document.querySelectorAll(".person").forEach((card) => {
    const img = card.querySelector("img");
    const fallback = () => {
      const d = document.createElement("div");
      d.className = "avatar";
      d.textContent = card.dataset.initials;
      d.setAttribute("aria-hidden", "true");
      img.replaceWith(d);
    };
    if (img.complete && img.naturalWidth === 0) fallback();
    else img.addEventListener("error", fallback, { once: true });
  });

  const copy = document.getElementById("copy-email");
  if (copy) copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(copy.dataset.email);
      copy.textContent = "Copied ✓";
    } catch {
      copy.textContent = copy.dataset.email;
    }
    setTimeout(() => (copy.textContent = "Copy email"), 2200);
  });
})();
