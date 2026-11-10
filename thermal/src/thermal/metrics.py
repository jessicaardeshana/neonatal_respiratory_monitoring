"""Error metrics against synthetic ground truth. Units: breaths/min, seconds."""

from __future__ import annotations

import numpy as np


def truth_on_grid(t_frames: np.ndarray, rate_frames: np.ndarray, t_grid: np.ndarray) -> np.ndarray:
    """Interpolate per-frame true rate onto the uniform processing grid."""
    return np.interp(t_grid, t_frames, rate_frames)


def window_truth(t_grid: np.ndarray, rate_grid: np.ndarray, t_end: np.ndarray,
                 window_s: float) -> np.ndarray:
    """Mean true rate over each estimator window (t_end - window_s, t_end]."""
    out = np.empty(t_end.size)
    for i, te in enumerate(t_end):
        m = (t_grid > te - window_s) & (t_grid <= te)
        out[i] = rate_grid[m].mean()
    return out


def mae(est: np.ndarray, truth: np.ndarray, mask: np.ndarray | None = None) -> float:
    """Mean absolute error over windows where the estimate is not NaN (and mask is True)."""
    ok = np.isfinite(est) if mask is None else (np.isfinite(est) & mask)
    return float(np.mean(np.abs(est[ok] - truth[ok]))) if ok.any() else float("nan")


def max_abs_error(est: np.ndarray, truth: np.ndarray, mask: np.ndarray | None = None) -> float:
    ok = np.isfinite(est) if mask is None else (np.isfinite(est) & mask)
    return float(np.max(np.abs(est[ok] - truth[ok]))) if ok.any() else float("nan")


def coverage(est: np.ndarray, mask: np.ndarray | None = None) -> float:
    """Fraction of windows (in mask) that returned a number instead of NaN."""
    sel = np.ones(est.size, dtype=bool) if mask is None else mask
    return float(np.isfinite(est[sel]).mean()) if sel.any() else float("nan")


def step_lag(t_end: np.ndarray, est: np.ndarray, t_step: float, new_bpm: float,
             tol_bpm: float = 1.5, hold: int = 3) -> float:
    """Seconds from a rate step until the estimate first holds within ``tol_bpm`` of the new rate.

    "Holds" means ``hold`` consecutive windows (default 3), so one lucky window
    does not count and later wobble from the simulated rate wander does not
    reset it. Windows that straddle the step are mixed, so lag is naturally
    about one window length. Returns NaN if it never settles.
    """
    ok = np.isfinite(est) & (np.abs(est - new_bpm) <= tol_bpm)
    for i in np.flatnonzero(t_end > t_step):
        if i + hold <= ok.size and ok[i : i + hold].all():
            return float(t_end[i] - t_step)
    return float("nan")


def score_events(true_windows: list[tuple[float, float]], detected: list[tuple[float, float]]) -> dict:
    """Compare detected (start, end) events with true (start, end) windows, in seconds.

    Each true window is matched to the detected event that overlaps it most.
    Errors are detected minus true (positive start error = detected late,
    positive end error = detected late). ``false_alarms`` are detections that
    overlap no true window; ``fragments`` are extra detections splitting one
    true window.
    """
    start_err, end_err, used = [], [], set()
    missed = 0
    for ts, te in true_windows:
        best, best_ov = None, 0.0
        for j, (ds, de) in enumerate(detected):
            ov = min(te, de) - max(ts, ds)
            if ov > best_ov:
                best, best_ov = j, ov
        if best is None:
            missed += 1
            continue
        used.add(best)
        start_err.append(detected[best][0] - ts)
        end_err.append(detected[best][1] - te)
    false_alarms = fragments = 0
    for j, (ds, de) in enumerate(detected):
        if j in used:
            continue
        if any(min(te, de) - max(ts, ds) > 0 for ts, te in true_windows):
            fragments += 1
        else:
            false_alarms += 1
    return {"start_err": start_err, "end_err": end_err, "missed": missed,
            "false_alarms": false_alarms, "fragments": fragments}
