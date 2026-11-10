"""Run the whole thermal pipeline on ANY FrameSource.

This is the point of the FrameSource interface: ``run_pipeline`` neither knows
nor cares whether frames come from the simulator, a replayed file or a real
camera. Convenience layer over the Phase 2-4 modules; not a new algorithm.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from thermal.apnea import ApneaConfig, ApneaResult, detect_apnea
from thermal.config import PipelineConfig
from thermal.preprocess import Phase2Result, process_frames
from thermal.rate import RateEstimate, estimate_rates, hold_to_grid
from thermal.recorder import git_commit
from thermal.roi import ROI
from thermal.sources.base import FrameSource


@dataclass
class PipelineOutput:
    signals: Phase2Result  # cleaned nostril/control signals
    rate: RateEstimate  # spectral + time-domain rate, quality
    apnea: ApneaResult  # envelope, events


def collect_frames(source: FrameSource, max_frames: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Drain a source into (frames[T, 60, 80], timestamps[T])."""
    ts, fr = [], []
    for t, frame in source.frames():
        ts.append(t)
        fr.append(frame)
        if max_frames is not None and len(ts) >= max_frames:
            break
    if not ts:
        raise ValueError("source produced no frames")
    return np.stack(fr), np.array(ts)


def rois_from_meta(meta: dict) -> tuple[ROI, ROI, ROI]:
    """(nostril, control, reference) ROIs stored in a recording's meta (synthetic sources)."""
    try:
        r = meta["rois"]
        return ROI.from_box(tuple(r["nostril"])), ROI.from_box(tuple(r["control"])), ROI.from_box(tuple(r["reference"]))
    except KeyError:
        raise ValueError("This recording has no ROIs in its metadata. For real data, draw them with "
                         "thermal.roi.select_roi_interactive and pass them explicitly.") from None


def run_pipeline(source: FrameSource, nostril: ROI, control: ROI, reference: ROI,
                 cfg: PipelineConfig | None = None, apnea_cfg: ApneaConfig | None = None) -> PipelineOutput:
    """Frames -> clean signals -> rate + quality -> apnea events."""
    cfg = cfg or PipelineConfig(fs_nominal=source.fs_nominal)
    frames, t = collect_frames(source)
    sig = process_frames(frames, t, nostril, control, reference, cfg)
    rate = estimate_rates(sig.t, sig.s_filt, cfg.fs_nominal, cfg.profile)
    apnea = detect_apnea(sig.t, sig.s_filt, cfg.fs_nominal, cfg.profile, apnea_cfg)
    return PipelineOutput(sig, rate, apnea)


def processed_arrays(out: PipelineOutput, estimator: str = "time_domain") -> dict[str, np.ndarray]:
    """The Section 7 processed-output arrays, all on the same uniform time grid.

    ``rate_bpm`` and ``quality`` are window-level values held per sample
    causally (a sample sees only windows that had already finished; NaN before
    the first). ``rate_bpm`` is NaN wherever quality was too low. ``estimator``
    picks "time_domain" (default, most accurate in our study) or "spectral".
    ``signal_lost`` is an additive extra beyond the Section 7 table.
    """
    if estimator not in ("time_domain", "spectral"):
        raise ValueError("estimator must be 'time_domain' or 'spectral'")
    sig, est, ap = out.signals, out.rate, out.apnea
    rate = est.time_bpm if estimator == "time_domain" else est.spectral_bpm
    return {
        "t": sig.t, "s_raw": sig.s_raw, "s_ctrl": sig.ctrl_raw, "s_filt": sig.s_filt,
        "envelope": ap.envelope, "rate_bpm": hold_to_grid(sig.t, est.t_end, rate),
        "quality": hold_to_grid(sig.t, est.t_end, est.quality),
        "apnea": ap.apnea.copy(), "ffc_mask": sig.ffc_mask.copy(), "signal_lost": ap.signal_lost.copy(),
    }


def save_processed(path: str | Path, out: PipelineOutput, meta: dict, estimator: str = "time_domain") -> Path:
    """Write the Section 7 processed-output .npz (no pickle; ``meta`` is a JSON string)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    full = {"git_commit": git_commit(), "rate_estimator": estimator, **meta}
    np.savez_compressed(path, **processed_arrays(out, estimator), meta=np.array(json.dumps(full, default=str)))
    return path


def load_processed(path: str | Path) -> tuple[dict[str, np.ndarray], dict]:
    """Read a processed-output file: (arrays, meta). Safe: never unpickles."""
    with np.load(Path(path), allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files if k != "meta"}
        return arrays, json.loads(str(z["meta"]))
