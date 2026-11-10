"""Regions of interest (ROI) and per-frame reduction to one number.

A thermal video is 60x80 numbers per frame. Breathing lives in a tiny patch
under the nose, so we pick a rectangle there (the ROI) and reduce each frame
to a single temperature. Stacking those numbers over time gives the 1D
breathing signal. A *control* ROI (cheek, no airflow) and a *reference* ROI
(static background) are reduced the same way.

Units: degrees Celsius. Boxes are (row0, row1, col0, col1), end-exclusive.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class ROI:
    """Rectangle in (row, col) pixel coordinates, end-exclusive."""

    row0: int
    row1: int
    col0: int
    col1: int

    @classmethod
    def from_box(cls, box: Box) -> "ROI":
        return cls(*box)

    @property
    def box(self) -> Box:
        return (self.row0, self.row1, self.col0, self.col1)

    @property
    def n_pixels(self) -> int:
        return (self.row1 - self.row0) * (self.col1 - self.col0)


def reduce_roi(frames: np.ndarray, roi: ROI, mode: str = "mean") -> np.ndarray:
    """Reduce each frame to one scalar inside ``roi``.

    ``mode="mean"`` (default) averages the ROI: robust to single-pixel noise.
    ``mode="max"`` takes the hottest pixel: more sensitive but noisier.
    Returns shape (T,) float64 in degC.
    """
    patch = frames[:, roi.row0 : roi.row1, roi.col0 : roi.col1].astype(np.float64)
    if mode == "mean":
        return patch.mean(axis=(1, 2))
    if mode == "max":
        return patch.max(axis=(1, 2))
    raise ValueError(f"mode must be 'mean' or 'max', got {mode!r}")


def select_roi_interactive(frame: np.ndarray, scale: int = 8) -> ROI:
    """Let a person draw the ROI on a real frame (needs a display + OpenCV).

    The frame is stretched to 8-bit and enlarged ``scale`` times so an 80x60
    image is usable. Drag a rectangle, then press ENTER/SPACE.
    """
    import cv2  # imported lazily: only needed for real-data sessions

    lo, hi = float(frame.min()), float(frame.max())
    img = ((frame - lo) / max(hi - lo, 1e-9) * 255).astype(np.uint8)
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    x, y, w, h = cv2.selectROI("Select ROI (ENTER to accept)", img, showCrosshair=True)
    cv2.destroyAllWindows()
    if w == 0 or h == 0:
        raise RuntimeError("No ROI selected")
    return ROI(y // scale, (y + h) // scale + 1, x // scale, (x + w) // scale + 1)
