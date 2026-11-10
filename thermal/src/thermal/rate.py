"""Breathing-rate estimators (spec 6.6): spectral and time-domain.

Both run on the band-passed, uniformly sampled signal from ``preprocess``.
Each window yields a rate in breaths/min and a quality in [0, 1]; windows with
quality below ``min_quality`` return NaN rather than a wrong number.

Frequency-resolution trade-off: a window of W seconds resolves frequencies
only to 1/W Hz, i.e. 60/W breaths/min (W = 30 s -> 2 breaths/min). We
zero-pad (x8) and interpolate the peak to do better than that for a clean
signal, but a short window can never separate two rates closer than 60/W, and
a long window reacts slowly to a rate change (lag is roughly W/2 or more).

Reported time is the END of each window, so estimates only use the past.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks

from thermal.config import Profile
from thermal.quality import agreement_factor, quality_from_snr, spectral_snr


@dataclass
class RateEstimate:
    t_end: np.ndarray  # (K,) window end times, s
    spectral_bpm: np.ndarray  # (K,) NaN when quality is low
    time_bpm: np.ndarray  # (K,) NaN when quality is low
    quality: np.ndarray  # (K,) in [0, 1]
    f_peak_hz: np.ndarray  # (K,) spectral peak frequency (not gated)
    window_s: float
    snr_db: np.ndarray | None = None  # (K,) spectral SNR in dB (not gated)


def _spectral_window(seg: np.ndarray, fs: float, band_hz: tuple[float, float],
                     window_s: float, zero_pad: int = 8) -> tuple[float, float]:
    """(peak frequency in Hz, linear SNR) for one window."""
    n = seg.size
    nfft = int(2 ** np.ceil(np.log2(n * zero_pad)))
    x = (seg - seg.mean()) * np.hanning(n)
    power = np.abs(np.fft.rfft(x, nfft)) ** 2
    f = np.fft.rfftfreq(nfft, 1.0 / fs)
    idx = np.flatnonzero((f >= band_hz[0]) & (f <= band_hz[1]))
    k = idx[np.argmax(power[idx])]
    f_pk = f[k]
    if 0 < k < power.size - 1 and min(power[k - 1], power[k], power[k + 1]) > 0:
        a, b, c = np.log(power[k - 1]), np.log(power[k]), np.log(power[k + 1])
        denom = a - 2 * b + c
        if denom != 0:  # parabolic interpolation of the log-power peak
            f_pk = f[k] + 0.5 * (a - c) / denom * (f[1] - f[0])
    snr = spectral_snr(f, power, band_hz, f_pk, half_width_hz=max(0.03, 2.0 / window_s))
    return float(f_pk), snr


def _time_window(seg: np.ndarray, fs: float, profile: Profile) -> float:
    """Breaths/min from the spacing of peaks in one window (NaN if < 3 peaks)."""
    min_dist = max(1, int(0.8 * fs * 60.0 / profile.rate_max_bpm))
    prom = 0.3 * (np.percentile(seg, 95) - np.percentile(seg, 5))
    peaks, _ = find_peaks(seg, distance=min_dist, prominence=max(prom, 1e-9))
    if peaks.size < 3:
        return float("nan")
    return 60.0 * (peaks.size - 1) / ((peaks[-1] - peaks[0]) / fs)


def estimate_rates(t: np.ndarray, x: np.ndarray, fs: float, profile: Profile,
                   hop_s: float = 2.0, min_quality: float = 0.5,
                   window_s: float | None = None) -> RateEstimate:
    """Sliding-window rate estimates from a band-passed signal ``x`` on uniform grid ``t``."""
    window_s = profile.window_s if window_s is None else window_s
    n_win, hop = int(round(window_s * fs)), max(1, int(round(hop_s * fs)))
    starts = np.arange(0, x.size - n_win + 1, hop)
    k = starts.size
    out = {name: np.full(k, np.nan) for name in ("sp", "td", "q", "f", "snr")}
    for i, s0 in enumerate(starts):
        seg = x[s0 : s0 + n_win]
        f_pk, snr = _spectral_window(seg, fs, profile.band_hz, window_s)
        sp, td = 60.0 * f_pk, _time_window(seg, fs, profile)
        q = quality_from_snr(snr) * agreement_factor(sp, td)
        out["q"][i], out["f"][i] = q, f_pk
        out["snr"][i] = 10.0 * np.log10(max(snr, 1e-12))
        if q >= min_quality:
            out["sp"][i], out["td"][i] = sp, td
    return RateEstimate(t[starts + n_win - 1], out["sp"], out["td"], out["q"], out["f"], window_s,
                        out["snr"])


def hold_to_grid(t: np.ndarray, t_end: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Per-sample, causal version of window-level values.

    Each sample time gets the value of the latest window that had already
    finished (``t_end <= t``); NaN before the first window completes.
    """
    idx = np.searchsorted(t_end, t, side="right") - 1
    return np.where(idx >= 0, values[np.clip(idx, 0, None)], np.nan)
