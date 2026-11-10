"""Preprocessing: ROI signals -> clean, uniformly sampled breathing signal.

Steps (spec 6.5): (0) FFC repair + reference cancellation, (1) resample to a
uniform grid, (2) detrend slow drift, (3) band-pass to the breathing band.
We never normalize amplitude: a collapsing amplitude is how apnea is found.

Units: degrees Celsius, seconds, Hz.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, sosfilt, sosfiltfilt

from thermal.config import PipelineConfig
from thermal.ffc import detect_ffc, reference_subtract, repair_invalid
from thermal.roi import ROI, reduce_roi


def resample_uniform(t: np.ndarray, s: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Linearly interpolate irregular samples (t, s) onto a uniform grid at ``fs`` Hz."""
    t_u = np.arange(t[0], t[-1], 1.0 / fs)
    return t_u, np.interp(t_u, t, s)


def detrend(s: np.ndarray, fs: float, method: str = "highpass",
            band_lo_hz: float = 0.10, window_s: float = 30.0, poly_order: int = 2) -> np.ndarray:
    """Remove slow drift.

    "highpass" (default): zero-phase 2nd-order Butterworth high-pass at half
    the breathing band's lower edge, so drift goes but breathing is untouched.
    "movmean": subtract a ``window_s`` moving average.
    "poly": subtract a least-squares polynomial of ``poly_order``.
    """
    if method == "highpass":
        sos = butter(2, 0.5 * band_lo_hz, btype="highpass", fs=fs, output="sos")
        return sosfiltfilt(sos, s - s.mean())
    if method == "movmean":
        n = max(3, int(window_s * fs))
        return s - uniform_filter1d(s, size=n, mode="nearest")
    if method == "poly":
        x = np.arange(s.size) / fs
        return s - np.polyval(np.polyfit(x, s, poly_order), x)
    raise ValueError(f"unknown detrend method {method!r}")


def bandpass(s: np.ndarray, fs: float, band_hz: tuple[float, float],
             order: int = 4, causal: bool = False) -> np.ndarray:
    """Butterworth band-pass.

    Offline (``causal=False``) uses zero-phase ``sosfiltfilt`` (no delay, but
    it looks at the future). Real time needs ``causal=True`` (``sosfilt``):
    it only uses the past but delays the signal slightly.
    """
    sos = butter(order, band_hz, btype="bandpass", fs=fs, output="sos")
    return sosfilt(sos, s) if causal else sosfiltfilt(sos, s)


@dataclass
class Phase2Result:
    t: np.ndarray  # (N,) uniform time grid, s
    s_raw: np.ndarray  # nostril ROI, resampled only, degC
    s_clean: np.ndarray  # after FFC repair + reference cancellation, degC
    s_filt: np.ndarray  # detrended + band-passed breathing signal
    ctrl_raw: np.ndarray
    ctrl_filt: np.ndarray  # control ROI through the same pipeline
    ffc_mask: np.ndarray  # (N,) bool: samples repaired because of FFC/glitch
    ffc_step_times: np.ndarray  # seconds at which level steps were detected


def process_frames(frames: np.ndarray, t: np.ndarray, nostril: ROI, control: ROI,
                   reference: ROI, cfg: PipelineConfig | None = None) -> Phase2Result:
    """Frames -> clean breathing signals for the nostril and control ROIs."""
    cfg = cfg or PipelineConfig()
    fs = cfg.fs_nominal
    s = reduce_roi(frames, nostril, cfg.reduction)
    c = reduce_roi(frames, control, cfg.reduction)
    ref = reduce_roi(frames, reference, "mean")

    invalid = np.zeros(t.size, dtype=bool)
    steps_t = np.array([])
    s_c, c_c = s.copy(), c.copy()
    if cfg.ffc_handling:
        ffc = detect_ffc(frames, cfg.frozen_tol_c, cfg.step_min_c, cfg.step_k)
        invalid = ffc.frozen_mask
        steps_t = t[ffc.step_indices]
        s_c = repair_invalid(t, s, invalid, cfg.max_gap_s)
        c_c = repair_invalid(t, c, invalid, cfg.max_gap_s)
        ref = repair_invalid(t, ref, invalid, cfg.max_gap_s)
        for arr in (s_c, c_c, ref):  # leftover NaN (gap too long): last-resort fill
            bad = np.isnan(arr)
            if bad.any():
                arr[bad] = np.interp(t[bad], t[~bad], arr[~bad])
                invalid = invalid | bad
    if cfg.ffc_handling and cfg.reference_subtract:
        s_c = reference_subtract(s_c, ref)
        c_c = reference_subtract(c_c, ref)

    t_u, s_raw_u = resample_uniform(t, s, fs)
    _, c_raw_u = resample_uniform(t, c, fs)
    _, s_cl_u = resample_uniform(t, s_c, fs)
    _, c_cl_u = resample_uniform(t, c_c, fs)
    mask_u = np.interp(t_u, t, invalid.astype(float)) > 0

    lo = cfg.profile.band_hz[0]

    def finish(x: np.ndarray) -> np.ndarray:
        return bandpass(detrend(x, fs, cfg.detrend, lo), fs, cfg.profile.band_hz, cfg.filter_order)

    return Phase2Result(t_u, s_raw_u, s_cl_u, finish(s_cl_u), c_raw_u, finish(c_cl_u),
                        mask_u, steps_t)
