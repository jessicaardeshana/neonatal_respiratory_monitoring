"""FFC (flat-field correction) and glitch detection and repair.

The Lepton periodically closes a shutter to recalibrate. Around that moment
the image freezes (frames repeat) and the scene level jumps by a small step.
A step looks exactly like the start of a breath, so it MUST be handled.

Image-based detection (used here) has two parts:
  * frozen frames: the whole image is identical to the previous frame;
  * level steps: the whole-scene mean jumps by more than breathing could
    cause (breathing changes only a ~18-pixel patch, so the scene mean barely
    moves; an FFC step moves every pixel at once).

If the camera's telemetry rows are enabled, pass its FFC-state flag as
``telemetry_ffc``: it is authoritative and replaces the frozen-frame
heuristic. Image-based step detection still runs.

Limitation: frozen-frame detection relies on sensor noise making real
consecutive frames differ. A perfectly noise-free static scene would be
misread as frozen.

Units: degrees Celsius, seconds.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FFCResult:
    frozen_mask: np.ndarray  # (T,) bool: repeated/frozen frames (invalid samples)
    step_indices: np.ndarray  # frame indices where the scene level jumps
    step_sizes: np.ndarray  # degC jump at each step index


def detect_ffc(
    frames: np.ndarray,
    frozen_tol_c: float = 1e-4,
    step_min_c: float = 0.05,
    step_k: float = 8.0,
    telemetry_ffc: np.ndarray | None = None,
) -> FFCResult:
    """Find frozen frames and whole-scene level steps.

    ``frozen_tol_c``: max absolute pixel difference (degC) below which a frame
    counts as a repeat of the previous one.
    ``step_min_c`` and ``step_k``: a step is a frame-to-frame jump in the
    scene mean larger than max(step_min_c, step_k * robust noise sigma).
    Choice: step_min_c = 0.05 degC sits well above scene-mean noise (~1 mK)
    and below the smallest FFC step we model (0.1 degC).
    """
    n = frames.shape[0]
    frozen = np.zeros(n, dtype=bool)
    if n > 1:
        diff = np.abs(np.diff(frames.astype(np.float64), axis=0)).max(axis=(1, 2))
        frozen[1:] = diff < frozen_tol_c
    if telemetry_ffc is not None:
        frozen = np.asarray(telemetry_ffc, dtype=bool).copy()

    scene = frames.astype(np.float64).mean(axis=(1, 2))
    d = np.diff(scene)
    sigma = 1.4826 * np.median(np.abs(d - np.median(d)))
    thr = max(step_min_c, step_k * sigma)
    idx = np.flatnonzero(np.abs(d) > thr) + 1  # step appears at frame i vs i-1
    return FFCResult(frozen, idx.astype(int), d[idx - 1])


def repair_invalid(
    t: np.ndarray, s: np.ndarray, invalid: np.ndarray, max_gap_s: float = 2.0
) -> np.ndarray:
    """Replace invalid samples by linear interpolation across short gaps.

    Gaps whose duration (previous valid sample to next valid sample) exceeds
    ``max_gap_s`` are left as NaN rather than inventing data.
    """
    out = s.astype(np.float64).copy()
    if not invalid.any():
        return out
    valid = ~invalid
    out[invalid] = np.interp(t[invalid], t[valid], s[valid])
    # find runs of invalid samples and NaN out the ones that are too long
    edges = np.diff(np.concatenate(([0], invalid.astype(int), [0])))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)  # [start, end)
    for a, b in zip(starts, ends):
        t_lo = t[a - 1] if a > 0 else t[a]
        t_hi = t[b] if b < t.size else t[b - 1]
        if t_hi - t_lo > max_gap_s:
            out[a:b] = np.nan
    return out


def reference_subtract(s: np.ndarray, s_ref: np.ndarray) -> np.ndarray:
    """Cancel anything the ROI and a static background patch share.

    The reference patch sees no breathing, but it sees the same slow drift
    and the same FFC level steps as the nostril ROI. Subtracting its
    deviation from its own starting level removes those, leaving breathing.
    """
    return s - (s_ref - np.nanmedian(s_ref[: max(1, min(20, s_ref.size))]))
