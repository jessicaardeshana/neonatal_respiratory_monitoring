"""Real hardware adapter: FLIR Lepton 2.5 behind a PureThermal-style UVC breakout.

STATUS: written WITHOUT hardware. Every camera-specific detail below is an
unverified assumption from memory (listed in THERMAL_SPEC.md Section 11) and
must be checked on the first hardware day (``scripts/bringup_lepton.md``):

  * the breakout appears as a UVC webcam delivering 16-bit "Y16 " frames;
  * OpenCV needs CAP_PROP_CONVERT_RGB = 0 and the Y16 FOURCC to give raw data;
  * raw values are centi-Kelvin (value x 0.01 K) in radiometric high-gain mode;
  * frames arrive as uint16 (60, 80), or as 8-bit pairs of width 160;
  * timestamps are host time at read (the camera sends none this way), so
    real frame-interval jitter is a measurement to make, not an assumption;
  * FFC state is not read here (no telemetry rows); ``ffc.py`` falls back to
    image-based detection.

With no camera present, ``LeptonSource`` raises ``DeviceNotFoundError`` with a
checklist instead of failing mysteriously. Never open a device implicitly:
nothing is opened until ``frames()`` is iterated.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np

from thermal.config import FRAME_SHAPE, FS_NOMINAL_HZ
from thermal.recorder import TimestampLogger

KELVIN_TO_CELSIUS = 273.15
_CAP_PROP_FOURCC, _CAP_PROP_CONVERT_RGB = 6, 16  # OpenCV property ids (fallback if cv2 is absent)


class DeviceNotFoundError(RuntimeError):
    """No usable thermal camera could be opened."""


@dataclass
class LeptonConfig:
    device_index: int = 0
    backend: int | None = None  # e.g. cv2.CAP_DSHOW on Windows if the default backend fails
    fourcc: str = "Y16 "  # UNVERIFIED
    scale_k_per_count: float = 0.01  # UNVERIFIED: centi-Kelvin
    offset_c: float = 0.0  # calibration correction after checking against a thermometer
    fs_nominal: float = FS_NOMINAL_HZ  # Hz, UNVERIFIED (< 9 Hz)
    shape: tuple[int, int] = FRAME_SHAPE
    max_consecutive_failures: int = 30  # failed reads in a row before giving up


def raw_to_celsius(raw: np.ndarray, scale_k_per_count: float = 0.01, offset_c: float = 0.0) -> np.ndarray:
    """Convert raw radiometric counts to degrees Celsius (float32).

    The single place that knows the camera's unit convention. Default assumes
    centi-Kelvin (UNVERIFIED). ``offset_c`` lets you correct a constant bias
    after comparing against a reference thermometer.
    """
    celsius = np.asarray(raw, dtype=np.float64) * scale_k_per_count - KELVIN_TO_CELSIUS + offset_c
    return celsius.astype(np.float32)


def normalize_raw_frame(frame: np.ndarray, shape: tuple[int, int] = FRAME_SHAPE) -> np.ndarray:
    """Coerce a captured frame to uint16 with ``shape``.

    Accepts uint16 of the right size (any layout), or uint8 holding the 16-bit
    values as little-endian byte pairs (UNVERIFIED byte order). Anything else
    raises, so a wrong assumption is loud instead of silently garbage.
    """
    a = np.ascontiguousarray(frame)
    n = shape[0] * shape[1]
    if a.dtype == np.uint16 and a.size == n:
        return a.reshape(shape)
    if a.dtype == np.uint8 and a.size == 2 * n:
        return a.reshape(-1).view("<u2").reshape(shape)
    raise ValueError(f"Unexpected frame format: dtype={a.dtype}, shape={a.shape}. Expected 16-bit data "
                     f"with {n} values (shape {shape}). Check the capture format on real hardware.")


def _no_device_message(index: int) -> str:
    return (f"Could not open a thermal camera at device index {index}. Checklist: (1) is the Lepton / "
            "PureThermal breakout plugged in and enumerated as a UVC device? (2) try another device_index "
            "(a laptop webcam is often index 0); (3) on Windows try backend=cv2.CAP_DSHOW; (4) close other "
            "apps that hold the camera. Until a camera is available, use SyntheticSource or FileSource.")


class LeptonSource:
    """FrameSource backed by a real Lepton. Nothing is opened until ``frames()`` runs.

    ``capture_factory`` (index, backend) -> object with isOpened/set/read/release lets tests
    and other capture libraries plug in without touching a device. ``max_frames`` stops the
    stream early; ``logger`` collects frame timestamps for jitter measurement.
    """

    def __init__(self, cfg: LeptonConfig | None = None, max_frames: int | None = None,
                 capture_factory: Callable | None = None) -> None:
        self.cfg = cfg or LeptonConfig()
        self.fs_nominal = self.cfg.fs_nominal
        self.max_frames = max_frames
        self._factory = capture_factory
        self.logger = TimestampLogger(self.cfg.fs_nominal)

    def _open(self):
        if self._factory is not None:
            cap = self._factory(self.cfg.device_index, self.cfg.backend)
        else:
            import cv2  # lazy: only needed with real hardware

            args = (self.cfg.device_index,) if self.cfg.backend is None else (self.cfg.device_index, self.cfg.backend)
            cap = cv2.VideoCapture(*args)
        if cap is None or not cap.isOpened():
            raise DeviceNotFoundError(_no_device_message(self.cfg.device_index))
        fourcc = sum(ord(c) << (8 * i) for i, c in enumerate(self.cfg.fourcc[:4].ljust(4)))
        cap.set(_CAP_PROP_CONVERT_RGB, 0)  # raw 16-bit, no color conversion
        cap.set(_CAP_PROP_FOURCC, fourcc)
        return cap

    def frames(self) -> Iterator[tuple[float, np.ndarray]]:
        """Yield (seconds since the first frame, frame in degC) until stopped."""
        cap = self._open()
        t0, failures, n = None, 0, 0
        try:
            while self.max_frames is None or n < self.max_frames:
                ok, raw = cap.read()
                now = time.monotonic()
                if not ok or raw is None:
                    failures += 1
                    if failures >= self.cfg.max_consecutive_failures:
                        raise DeviceNotFoundError(
                            f"Camera stopped delivering frames ({failures} failed reads in a row).")
                    continue
                failures = 0
                t0 = now if t0 is None else t0
                self.logger.add(now - t0)
                frame = raw_to_celsius(normalize_raw_frame(raw, self.cfg.shape),
                                       self.cfg.scale_k_per_count, self.cfg.offset_c)
                n += 1
                yield now - t0, frame
        finally:
            cap.release()
