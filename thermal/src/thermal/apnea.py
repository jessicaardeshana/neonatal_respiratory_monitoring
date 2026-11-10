"""Apnea detection (spec 6.7): amplitude envelope, baseline, apnea vs signal_lost.

Idea: breathing makes the band-passed signal oscillate with some amplitude.
When airflow stops, that amplitude collapses. We track the amplitude envelope,
compare it with a robust recent baseline, and flag a pause when it stays below
``k`` x baseline for at least ``min_duration_s`` (clinical apnea: >= 20 s).

Two different things look like "no breathing", so we label them separately:
  * ``apnea``: the envelope collapses AFTER good-quality breathing;
  * ``signal_lost``: the envelope is tiny and the quality index is low with no
    recent good breathing (face out of view, or a warm incubator that erased
    the temperature swing).
Limitation (honest): a face that suddenly leaves the view mid-recording looks
exactly like apnea (good breathing, then nothing). Only extra information
(for example face tracking) can tell them apart.

Timing: the envelope reacts late. For a trailing window W it drops below
k x baseline only once a fraction 1 - k^2 of the window is silent, i.e.
(1 - k^2) x W after the pause began, and recovers k^2 x W after it ended. We
back-date the start (and end) by those amounts (centered windows: 0.5 W less),
so reported ``start``/``end`` estimate the true pause. ``declared_at`` is the
earliest time a real-time system could raise the alarm. A pause is accepted if
its estimated length >= min_duration - duration_tol_s (the tolerance absorbs
envelope blur and the 1 s amplitude ramps).

Units: degrees Celsius (RMS amplitude of the band-passed signal), seconds.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
from scipy.signal import hilbert

from thermal.config import Profile
from thermal.rate import RateEstimate, estimate_rates, hold_to_grid


@dataclass
class ApneaConfig:
    """Detector parameters. Defaults are documented choices, not fitted values."""

    envelope_window_s: float = 4.0  # long enough to span most of a breath
    envelope_method: str = "rms"  # "rms" (default) or "hilbert"
    causal: bool = True  # trailing window (real time) vs centered (offline)
    k: float = 0.25  # flag when envelope < k * baseline
    min_duration_s: float = 20.0  # clinical apnea: pause >= 20 s
    baseline_s: float = 180.0  # baseline = median envelope over this span
    warmup_s: float = 30.0  # envelope history needed before any flag
    abs_floor_c: float = 0.05  # "very low" envelope for signal_lost (degC RMS)
    q_good: float = 0.7  # best recent window quality needed for a pause to count as apnea
    q_low: float = 0.5  # quality below this = "very low SNR" (the rate estimator's reject level)
    duration_tol_s: float = 1.5  # slack on min_duration for envelope-window blur
    lookback_s: float = 30.0  # window "immediately before" a pause
    hop_s: float = 2.0  # quality-estimator hop


@dataclass
class ApneaEvent:
    start: float  # s, first sample of the low-envelope run
    end: float  # s, first sample after the envelope recovered
    kind: str  # "apnea" or "signal_lost"
    declared_at: float  # s, start + min_duration (earliest real-time alarm)


@dataclass
class ApneaResult:
    t: np.ndarray
    envelope: np.ndarray  # RMS amplitude, degC (NaN until the window fills)
    baseline: np.ndarray  # degC, causal robust reference
    quality: np.ndarray  # 0-1, held from the latest rate-estimator window
    apnea: np.ndarray  # (N,) bool, retroactive flag for apnea events
    signal_lost: np.ndarray  # (N,) bool, retroactive flag for signal_lost events
    events: list[ApneaEvent] = field(default_factory=list)


def amplitude_envelope(x: np.ndarray, fs: float, window_s: float = 4.0,
                       method: str = "rms", causal: bool = True) -> np.ndarray:
    """Breathing-band amplitude, expressed as RMS (a sine of amplitude A gives A/sqrt(2)).

    ``causal=True`` averages over the trailing window (uses only the past; the
    envelope reacts about one window late). ``causal=False`` centers the window
    (offline; no delay). The first ~window samples are NaN.
    """
    n = max(2, int(round(window_s * fs)))
    if method == "rms":
        sq = np.concatenate(([0.0], np.cumsum(x.astype(np.float64) ** 2)))
        trailing = np.full(x.size, np.nan)
        trailing[n - 1 :] = np.sqrt((sq[n:] - sq[:-n]) / n)
    elif method == "hilbert":
        amp = np.abs(hilbert(x)) / np.sqrt(2.0)
        cs = np.concatenate(([0.0], np.cumsum(amp)))
        trailing = np.full(x.size, np.nan)
        trailing[n - 1 :] = (cs[n:] - cs[:-n]) / n
    else:
        raise ValueError(f"unknown envelope method {method!r}")
    if causal:
        return trailing
    shift = n // 2
    return np.concatenate((trailing[shift:], np.full(shift, np.nan)))


def running_baseline(env: np.ndarray, fs: float, k: float, baseline_s: float,
                     warmup_s: float) -> np.ndarray:
    """Causal robust baseline: rolling median of "normal" envelope values.

    Samples below ``k`` x the current baseline are NOT added to the history, so
    the baseline is frozen during a pause and never learns it. Until
    ``warmup_s`` of history exists the baseline is NaN (no flags possible). If
    the history empties (very long pause) the last baseline is held.
    """
    n = env.size
    base = np.full(n, np.nan)
    hist: deque[tuple[int, float]] = deque()
    span, min_n, step = int(baseline_s * fs), int(warmup_s * fs), max(1, int(fs))
    cur = np.nan
    for i in range(n):
        base[i] = cur  # decision at i uses only the past
        e = env[i]
        if not np.isfinite(e):
            continue
        if not np.isfinite(cur) or e >= k * cur:
            hist.append((i, e))
        while hist and hist[0][0] < i - span:
            hist.popleft()
        if len(hist) >= min_n and i % step == 0:
            cur = float(np.median([v for _, v in hist]))
    return base


def quality_on_grid(t: np.ndarray, est: RateEstimate) -> np.ndarray:
    """Hold the latest completed estimator window's quality (NaN before the first)."""
    return hold_to_grid(t, est.t_end, est.quality)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) index pairs of consecutive True values."""
    edges = np.diff(np.concatenate(([0], mask.astype(int), [0])))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def detect_apnea(t: np.ndarray, x: np.ndarray, fs: float, profile: Profile,
                 cfg: ApneaConfig | None = None) -> ApneaResult:
    """Run the full detector on a band-passed signal ``x`` on uniform grid ``t``."""
    cfg = cfg or ApneaConfig()
    dt = 1.0 / fs
    env = amplitude_envelope(x, fs, cfg.envelope_window_s, cfg.envelope_method, cfg.causal)
    base = running_baseline(env, fs, cfg.k, cfg.baseline_s, cfg.warmup_s)
    qual = quality_on_grid(t, estimate_rates(t, x, fs, profile, hop_s=cfg.hop_s))

    def t_after(i: int) -> float:
        return float(t[i]) if i < t.size else float(t[-1] + dt)

    events: list[ApneaEvent] = []
    covered = np.zeros(t.size, dtype=bool)
    half = 0.0 if cfg.causal else 0.5 * cfg.envelope_window_s
    lag_start = (1.0 - cfg.k**2) * cfg.envelope_window_s - half  # envelope reacts late
    lag_end = cfg.k**2 * cfg.envelope_window_s - half
    need = cfg.min_duration_s - cfg.duration_tol_s

    # Path A: envelope collapsed relative to the recent baseline
    low_a = np.isfinite(base) & (env < cfg.k * base)
    for s, e in _runs(low_a):
        start, end = max(float(t[0]), float(t[s]) - lag_start), t_after(e) - lag_end
        if end - start < need:
            continue
        past = qual[max(0, s - int(cfg.lookback_s * fs)) : s]
        past = past[np.isfinite(past)]
        # "good breathing immediately before": at least one recent window had clean breathing (best quality,
        # not the average: windows straddling a rate change score low but the breathing was still there) AND the
        # normal strength before the pause was above the "very low" floor (a marginal signal is not a real baseline).
        good = past.size > 0 and past.max() >= cfg.q_good and bool(np.isfinite(base[s]) and base[s] >= cfg.abs_floor_c)
        declared = max(float(t[s]), float(t[s]) + need - lag_start)
        events.append(ApneaEvent(start, end, "apnea" if good else "signal_lost", declared))
        covered[s:e] = True

    # Path B: tiny envelope AND very low quality, with no apnea already explaining it
    low_b = (env < cfg.abs_floor_c) & (qual < cfg.q_low) & ~covered
    for s, e in _runs(low_b):
        if (e - s) * dt >= need:
            events.append(ApneaEvent(float(t[s]), t_after(e), "signal_lost",
                                     float(t[s]) + need))

    events.sort(key=lambda ev: ev.start)
    apnea = np.zeros(t.size, dtype=bool)
    lost = np.zeros(t.size, dtype=bool)
    for ev in events:
        m = (t >= ev.start) & (t < ev.end)
        (apnea if ev.kind == "apnea" else lost)[m] = True
    return ApneaResult(t, env, base, qual, apnea, lost, events)
