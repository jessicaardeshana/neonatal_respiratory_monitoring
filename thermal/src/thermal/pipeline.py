"""Run the whole thermal pipeline on ANY FrameSource.

This is the point of the FrameSource interface: ``run_pipeline`` neither knows
nor cares whether frames come from the simulator, a replayed file or a real
camera. Convenience layer over the Phase 2-4 modules; not a new algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from thermal.apnea import ApneaConfig, ApneaResult, detect_apnea
from thermal.config import PipelineConfig
from thermal.preprocess import Phase2Result, process_frames
from thermal.rate import RateEstimate, estimate_rates
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
