"""FrameSource protocol: the only thing downstream code is allowed to consume."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class FrameSource(Protocol):
    """A stream of thermal frames.

    Frames are float32 degrees Celsius with shape (60, 80) = (rows, cols).
    Timestamps are monotonic seconds and may be non-uniformly spaced.
    """

    fs_nominal: float  # Hz, nominal frame rate (e.g. 8.7 for Lepton 2.5)

    def frames(self) -> Iterator[tuple[float, np.ndarray]]:
        """Yield (timestamp_seconds, frame_celsius[60, 80]) in time order."""
        ...
