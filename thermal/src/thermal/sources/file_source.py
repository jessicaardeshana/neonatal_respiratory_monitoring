"""Replay a recorded .npz as a FrameSource (spec Section 7 raw-frame format).

Lets the exact same pipeline run on a recording made earlier, on a real
session, or on a clip converted from any other thermal camera: build the
arrays, call ``save_recording``, then replay with ``FileSource``.

Validation is strict and loud: a malformed file raises ``ValueError`` saying
what is wrong, rather than producing garbage downstream. Files are loaded
with ``allow_pickle=False``, so a recording can never execute code.

If ``meta["units"]`` is "centikelvin" the frames are converted to degC on load
(via ``raw_to_celsius``); the default is "celsius".
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from thermal.config import FRAME_SHAPE
from thermal.sources.lepton import raw_to_celsius


class FileSource:
    """FrameSource that replays a recording. ``meta`` and ``truth`` are exposed as attributes."""

    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Recording not found: {path}")
        with np.load(path, allow_pickle=False) as z:
            missing = {"frames", "timestamps"} - set(z.files)
            if missing:
                raise ValueError(f"{path.name}: missing required array(s) {sorted(missing)}; "
                                 f"found {sorted(z.files)}")
            frames, ts = z["frames"], z["timestamps"]
            meta = json.loads(str(z["meta"])) if "meta" in z.files else {}
            self.truth = {k[len("truth_"):]: z[k] for k in z.files if k.startswith("truth_")}
        self._init_arrays(frames, ts, meta, path.name)

    def _init_arrays(self, frames: np.ndarray, ts: np.ndarray, meta: dict, name: str) -> None:
        if frames.ndim != 3 or frames.shape[1:] != FRAME_SHAPE:
            raise ValueError(f"{name}: frames must have shape (T, {FRAME_SHAPE[0]}, {FRAME_SHAPE[1]}), "
                             f"got {frames.shape}")
        if frames.shape[0] < 2:
            raise ValueError(f"{name}: need at least 2 frames, got {frames.shape[0]}")
        if ts.shape != (frames.shape[0],):
            raise ValueError(f"{name}: timestamps shape {ts.shape} does not match {frames.shape[0]} frames")
        ts = ts.astype(np.float64)
        if not np.all(np.isfinite(ts)):
            raise ValueError(f"{name}: timestamps contain NaN or infinity")
        if not np.all(np.diff(ts) > 0):
            raise ValueError(f"{name}: timestamps must be strictly increasing")
        units = meta.get("units", "celsius")
        if units == "celsius":
            frames_c = frames.astype(np.float32)
        elif units == "centikelvin":
            frames_c = raw_to_celsius(frames)
        else:
            raise ValueError(f"{name}: unknown units {units!r} (expected 'celsius' or 'centikelvin')")
        if not np.all(np.isfinite(frames_c)):
            raise ValueError(f"{name}: frames contain NaN or infinity")
        self.frames_c, self.timestamps, self.meta = frames_c, ts, meta
        self.fs_nominal = float(meta.get("fs_nominal") or 1.0 / np.median(np.diff(ts)))

    @classmethod
    def from_arrays(cls, frames: np.ndarray, timestamps: np.ndarray, fs_nominal: float | None = None,
                    units: str = "celsius", meta: dict | None = None) -> "FileSource":
        """Wrap in-memory arrays (e.g. converted from another camera) without a file."""
        self = cls.__new__(cls)
        self.truth = {}
        m = dict(meta or {})
        m["units"] = units
        if fs_nominal is not None:
            m["fs_nominal"] = fs_nominal
        self._init_arrays(np.asarray(frames), np.asarray(timestamps), m, "<arrays>")
        return self

    def frames(self) -> Iterator[tuple[float, np.ndarray]]:
        """Yield (timestamp_seconds, frame_celsius[60, 80]) in time order."""
        for t, f in zip(self.timestamps, self.frames_c):
            yield float(t), f
