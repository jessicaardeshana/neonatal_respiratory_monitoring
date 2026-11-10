"""Save and describe raw thermal recordings (spec Section 7, "raw-frame recordings").

File format (.npz, no pickle):
    frames      (T, 60, 80) float32, degrees Celsius
    timestamps  (T,) float64, seconds, monotonic (may be non-uniform)
    meta        JSON string (see below)
    truth_*     optional, only for synthetic sources (ground truth arrays)

``meta`` always has: source, synthetic, units, fs_nominal, frame_shape,
created_utc, git_commit. Synthetic sources also record their ROI boxes and
config. For real sessions pass ``extra_meta`` with the hand-counted breath
total, breathing protocol, etc. Do NOT put names or any personal details in meta.

PRIVACY: raw frames of a real person's face never go to GitHub. ``record``
refuses to write outside ``thermal/data/`` (which is gitignored) unless you
pass ``allow_outside_data=True``.

Also here: ``TimestampLogger`` for measuring real frame rate and jitter
(hardware bring-up step 3).

Units: degrees Celsius, seconds.
"""

from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from thermal.config import FRAME_SHAPE
from thermal.sources.base import FrameSource

DATA_DIR = Path(__file__).resolve().parents[2] / "data"  # thermal/data (gitignored)


def _json_default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.integer, np.floating)):
        return o.item()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serializable: {type(o)}")


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _check_destination(path: Path, allow_outside_data: bool) -> None:
    if allow_outside_data:
        return
    try:
        path.resolve().relative_to(DATA_DIR.resolve())
    except ValueError:
        raise ValueError(
            f"Refusing to write a raw recording to {path}: it is outside {DATA_DIR}, which is "
            "gitignored. Raw frames are images of people's faces and must never be committed. "
            "Write under thermal/data/, or pass allow_outside_data=True if you are sure "
            "(for example a temporary test folder).") from None


def save_recording(path: str | Path, frames: np.ndarray, timestamps: np.ndarray, meta: dict,
                   truth: dict[str, np.ndarray] | None = None,
                   allow_outside_data: bool = False) -> Path:
    """Write a raw-frame recording. Validates shapes; returns the written path."""
    path = Path(path)
    _check_destination(path, allow_outside_data)
    frames = np.asarray(frames, dtype=np.float32)
    timestamps = np.asarray(timestamps, dtype=np.float64)
    if frames.ndim != 3 or frames.shape[1:] != FRAME_SHAPE:
        raise ValueError(f"frames must have shape (T, {FRAME_SHAPE[0]}, {FRAME_SHAPE[1]}), got {frames.shape}")
    if timestamps.shape != (frames.shape[0],):
        raise ValueError(f"timestamps must have shape ({frames.shape[0]},), got {timestamps.shape}")
    if frames.shape[0] > 1 and not np.all(np.diff(timestamps) > 0):
        raise ValueError("timestamps must be strictly increasing")
    path.parent.mkdir(parents=True, exist_ok=True)
    extras = {f"truth_{k}": np.asarray(v) for k, v in (truth or {}).items()}
    np.savez_compressed(path, frames=frames, timestamps=timestamps,
                        meta=np.array(json.dumps(meta, default=_json_default)), **extras)
    return path if path.suffix == ".npz" else path.with_name(path.name + ".npz")


def record(source: FrameSource, path: str | Path, max_frames: int | None = None,
           extra_meta: dict | None = None, allow_outside_data: bool = False) -> Path:
    """Drain ``source`` (up to ``max_frames``) into a .npz recording.

    Works with any FrameSource. Synthetic sources also save their ground truth
    and ROI boxes so the recording can be scored after replay.
    """
    _check_destination(Path(path), allow_outside_data)  # fail before collecting anything
    ts, fr = [], []
    for t, frame in source.frames():
        ts.append(t)
        fr.append(frame)
        if max_frames is not None and len(ts) >= max_frames:
            break
    if not ts:
        raise ValueError("source produced no frames; nothing to record")
    meta: dict = {
        "source": type(source).__name__,
        "synthetic": False,
        "units": "celsius",
        "fs_nominal": float(source.fs_nominal),
        "frame_shape": list(FRAME_SHAPE),
        "n_frames": len(ts),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
    }
    truth = None
    tr = getattr(source, "truth", None)
    if tr is not None:  # synthetic source: keep ground truth + ROI boxes
        meta["synthetic"] = True
        meta["rois"] = {"nostril": list(tr.nostril_box), "control": list(tr.control_box),
                        "reference": list(tr.reference_box)}
        cfg = getattr(source, "cfg", None)
        if is_dataclass(cfg):
            meta["synthetic_config"] = asdict(cfg)
        truth = {"rate_bpm": tr.rate_bpm, "apnea_mask": tr.apnea_mask,
                 "ffc_indices": tr.ffc_indices}
    meta.update(extra_meta or {})
    return save_recording(path, np.stack(fr), np.array(ts), meta, truth, allow_outside_data)


class TimestampLogger:
    """Measure real frame intervals: frame rate, jitter and gaps (bring-up step 3).

    Feed it monotonic timestamps in seconds with ``add``. ``summary`` reports
    the median interval, jitter (std / median), the longest gap and the number
    of gaps longer than 1.5x the median (likely dropped frames).
    """

    def __init__(self, fs_nominal: float | None = None) -> None:
        self.fs_nominal = fs_nominal
        self.t: list[float] = []

    def add(self, t: float) -> None:
        self.t.append(float(t))

    def intervals(self) -> np.ndarray:
        return np.diff(np.asarray(self.t, dtype=np.float64))

    def summary(self) -> dict:
        dt = self.intervals()
        if dt.size == 0:
            return {"n_frames": len(self.t)}
        med = float(np.median(dt))
        return {
            "n_frames": len(self.t),
            "duration_s": float(self.t[-1] - self.t[0]),
            "fps_mean": float((len(self.t) - 1) / (self.t[-1] - self.t[0])),
            "fps_nominal": self.fs_nominal,
            "dt_median_s": med,
            "dt_std_s": float(dt.std()),
            "jitter_pct": float(100.0 * dt.std() / med),
            "dt_max_s": float(dt.max()),
            "n_gaps": int(np.sum(dt > 1.5 * med)),
        }

    def write_csv(self, path: str | Path) -> Path:
        """One row per frame: index, timestamp, interval since the previous frame."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        dt = np.concatenate(([np.nan], self.intervals()))
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["frame", "timestamp_s", "interval_s"])
            for i, (t, d) in enumerate(zip(self.t, dt)):
                w.writerow([i, f"{t:.6f}", "" if np.isnan(d) else f"{d:.6f}"])
        return path
