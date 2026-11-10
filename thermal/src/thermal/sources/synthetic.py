"""Physics-based synthetic thermal video with known ground truth.

EVERYTHING produced here is SIMULATED. It is a model of what a Lepton-class
camera should see, built from datasheet numbers recalled from memory (see
THERMAL_SPEC.md Section 4). It validates pipeline logic; it does not measure
real-world performance.

Model in one paragraph: the scene is room-temperature background plus a warm
face blob. A small nostril patch carries the breathing: its temperature is
``baseline + A * w(phase)`` where the swing ``A`` scales with how much warmer
exhaled air is than the room (so a warm incubator shrinks it). Optional
nuisances (noise, drift, head jitter, FFC events, timestamp jitter, dropped
frames) are layered on top, each independently switchable.

Units: temperatures in degrees Celsius, time in seconds, rates in
breaths/min, frequencies in Hz. Frames have shape (rows, cols) = (60, 80).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import lfilter

from thermal.config import FRAME_SHAPE, FS_NOMINAL_HZ

Box = tuple[int, int, int, int]  # (row0, row1, col0, col1), end-exclusive

FINE_FS_HZ = 50.0  # internal grid for phase integration and thermal lag
APNEA_RAMP_S = 1.0  # breath amplitude ramps to ~0 within this many seconds


@dataclass
class SyntheticConfig:
    """All generator parameters. Defaults give a realistic adult test scene."""

    # --- timing -----------------------------------------------------------
    duration_s: float = 180.0
    fs_nominal: float = FS_NOMINAL_HZ  # Hz
    seed: int = 0

    # --- scene (degrees C) -------------------------------------------------
    ambient_c: float = 24.0
    skin_center_c: float = 33.5
    skin_edge_c: float = 30.0  # cooler fringe of the face blob
    nostril_baseline_c: float = 33.0
    exhale_c: float = 34.5  # temperature of exhaled air

    # --- layout (rows, cols, end-exclusive) --------------------------------
    nostril_box: Box = (38, 41, 37, 43)
    control_box: Box = (33, 36, 29, 35)  # cheek: no airflow, artifact check
    reference_box: Box = (2, 6, 2, 10)  # static background patch

    # --- breathing ---------------------------------------------------------
    rate_bpm: float = 15.0  # breaths/min
    # (time_s, new_rate_bpm) step changes, applied in time order
    rate_steps: tuple[tuple[float, float], ...] = ()
    rate_variability: float = 0.05  # fractional breath-to-breath jitter (std)
    amplitude_gain: float = 0.07  # degC of swing per degC of (exhale - ambient)
    amplitude_c: float | None = None  # overrides the gain model if set
    harmonic: float = 0.25  # relative size of 2nd harmonic (asymmetry)
    thermal_lag_s: float = 0.3  # first-order lag time constant (0 = off)

    # --- apnea: (start_s, duration_s) windows ------------------------------
    apnea_events: tuple[tuple[float, float], ...] = ()

    # --- nuisance toggles --------------------------------------------------
    noise: bool = True
    drift: bool = True
    head_jitter: bool = True
    ffc: bool = True
    timestamp_jitter: bool = True
    dropped_frames: bool = True

    # --- nuisance parameters -----------------------------------------------
    noise_sigma_c: float = 0.05  # per-pixel Gaussian (NETD ~50 mK)
    drift_c_per_min: float = 0.03  # slow global drift, random sign
    head_jitter_prob: float = 0.01  # per-frame chance the head shifts by 1 px
    ffc_interval_s: tuple[float, float] = (120.0, 180.0)
    ffc_freeze_frames: tuple[int, int] = (1, 2)  # repeated frames per event
    ffc_step_c: tuple[float, float] = (0.1, 0.3)  # offset magnitude, random sign
    timestamp_jitter_frac: float = 0.10  # +/- fraction of the frame period
    dropped_frame_prob: float = 0.005

    @property
    def breath_amplitude_c(self) -> float:
        """Semi-amplitude A of the breath swing in degC.

        Scales with (exhale - ambient): large in a cool room, ~0 when the
        ambient temperature approaches the exhaled-air temperature.
        """
        if self.amplitude_c is not None:
            return float(self.amplitude_c)
        return max(0.0, self.amplitude_gain * (self.exhale_c - self.ambient_c))


@dataclass
class GroundTruth:
    """What the generator injected, aligned to the OUTPUT frames."""

    rate_bpm: np.ndarray  # (T,) true instantaneous rate, breaths/min
    apnea_mask: np.ndarray  # (T,) bool, True inside an injected apnea window
    nostril_box: Box
    control_box: Box
    reference_box: Box
    ffc_indices: np.ndarray  # frame indices that are frozen (repeated) frames
    ffc_step_indices: np.ndarray  # first frame index carrying each new offset
    amplitude_c: float  # breath semi-amplitude A used, degC
    ambient_c: float
    is_synthetic: bool = True


@dataclass
class SyntheticResult:
    frames: np.ndarray  # (T, 60, 80) float32 degC
    timestamps: np.ndarray  # (T,) seconds, monotonic, possibly non-uniform
    truth: GroundTruth
    config: SyntheticConfig = field(repr=False)


def _face_template(cfg: SyntheticConfig) -> np.ndarray:
    """Static scene: ambient background, warm face ellipse, nostril patch."""
    rows, cols = FRAME_SHAPE
    rr, cc = np.mgrid[0:rows, 0:cols]
    r2 = ((rr - 30) / 22.0) ** 2 + ((cc - 40) / 17.0) ** 2
    face = cfg.skin_center_c - (cfg.skin_center_c - cfg.skin_edge_c) * r2
    img = np.where(r2 < 1.0, face, cfg.ambient_c).astype(np.float64)
    r0, r1, c0, c1 = cfg.nostril_box
    img[r0:r1, c0:c1] = cfg.nostril_baseline_c
    return img


def _rate_curve(cfg: SyntheticConfig, t: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """True instantaneous rate (breaths/min) on time grid ``t``."""
    rate = np.full_like(t, cfg.rate_bpm, dtype=np.float64)
    for t_step, bpm in sorted(cfg.rate_steps):
        rate[t >= t_step] = bpm
    if cfg.rate_variability > 0:
        z = gaussian_filter1d(rng.standard_normal(t.size), sigma=4.0 * FINE_FS_HZ)
        z /= z.std() if z.std() > 0 else 1.0
        rate = rate * (1.0 + cfg.rate_variability * z)
    return rate


def _waveform(phase: np.ndarray, harmonic: float) -> np.ndarray:
    """Non-sinusoidal breath shape, scaled to peak amplitude 1.

    sin(phi) + h*sin(2*phi) rises faster than it falls: exhale warms the
    patch quickly, inhale cools it more slowly.
    """
    w = np.sin(phase) + harmonic * np.sin(2 * phase)
    return w / np.abs(w).max() if np.abs(w).max() > 0 else w


def _apnea_amplitude(t: np.ndarray, events: tuple[tuple[float, float], ...]) -> np.ndarray:
    """Multiplier in [0, 1]: 1 = normal breathing, 0 = apnea (1 s ramps)."""
    m = np.ones_like(t)
    for start, dur in events:
        down = np.clip((t - start) / APNEA_RAMP_S, 0.0, 1.0)
        up = 1.0 - np.clip((t - (start + dur)) / APNEA_RAMP_S, 0.0, 1.0)
        m *= 1.0 - down * up
    return m


def generate(cfg: SyntheticConfig) -> SyntheticResult:
    """Generate a synthetic thermal video plus ground truth.

    Each nuisance draws from its own child random stream, so toggling one
    nuisance never changes the random numbers used by another. Same config +
    seed always yields identical output.
    """
    ss = np.random.SeedSequence(cfg.seed)
    (s_rate, s_ts, s_drop, s_jit, s_noise, s_drift, s_ffc) = ss.spawn(7)

    # --- timestamps: nominal grid, jitter, then dropped frames --------------
    period = 1.0 / cfg.fs_nominal
    n_nom = int(np.floor(cfg.duration_s * cfg.fs_nominal))
    t_all = np.arange(n_nom) * period
    if cfg.timestamp_jitter:
        rng = np.random.default_rng(s_ts)
        t_all = t_all + rng.uniform(-1, 1, n_nom) * cfg.timestamp_jitter_frac * period
        t_all[0] = 0.0
        t_all = np.maximum.accumulate(t_all)
    keep = np.ones(n_nom, dtype=bool)
    if cfg.dropped_frames:
        rng = np.random.default_rng(s_drop)
        keep = rng.random(n_nom) >= cfg.dropped_frame_prob
        keep[0] = True
    t = t_all[keep]
    n = t.size

    # --- breathing signal on a fine grid, then sampled at frame times -------
    t_fine = np.arange(0.0, cfg.duration_s + 1.0, 1.0 / FINE_FS_HZ)
    rate_fine = _rate_curve(cfg, t_fine, np.random.default_rng(s_rate))
    phase_fine = 2 * np.pi * np.cumsum(rate_fine / 60.0) / FINE_FS_HZ
    amp = cfg.breath_amplitude_c
    mod_fine = (
        amp
        * _waveform(phase_fine, cfg.harmonic)
        * _apnea_amplitude(t_fine, cfg.apnea_events)
    )
    if cfg.thermal_lag_s > 0:
        alpha = (1.0 / FINE_FS_HZ) / (cfg.thermal_lag_s + 1.0 / FINE_FS_HZ)
        mod_fine = lfilter([alpha], [1.0, alpha - 1.0], mod_fine)
    mod = np.interp(t, t_fine, mod_fine)
    rate_true = np.interp(t, t_fine, rate_fine)

    # --- build frames --------------------------------------------------------
    template = _face_template(cfg)
    frames = np.tile(template, (n, 1, 1))
    r0, r1, c0, c1 = cfg.nostril_box
    frames[:, r0:r1, c0:c1] = cfg.nostril_baseline_c + mod[:, None, None]

    if cfg.head_jitter:  # whole scene shifts by at most +/-1 pixel
        rng = np.random.default_rng(s_jit)
        dr = dc = 0
        for i in range(n):
            if rng.random() < cfg.head_jitter_prob:
                dr = int(np.clip(dr + rng.integers(-1, 2), -1, 1))
                dc = int(np.clip(dc + rng.integers(-1, 2), -1, 1))
            if dr or dc:
                frames[i] = np.roll(frames[i], (dr, dc), axis=(0, 1))

    if cfg.drift:  # slow global drift, random sign, linear in time
        rng = np.random.default_rng(s_drift)
        sign = rng.choice([-1.0, 1.0])
        frames += (sign * cfg.drift_c_per_min * t / 60.0)[:, None, None]

    if cfg.noise:
        rng = np.random.default_rng(s_noise)
        frames += rng.normal(0.0, cfg.noise_sigma_c, frames.shape)

    # --- FFC: persistent offset step, then repeated (frozen) frames ----------
    frozen: list[int] = []
    step_idx: list[int] = []
    if cfg.ffc:
        rng = np.random.default_rng(s_ffc)
        events: list[tuple[int, int, float]] = []
        t_ev = rng.uniform(*cfg.ffc_interval_s)
        while t_ev < t[-1]:
            k = int(np.searchsorted(t, t_ev))
            n_frz = int(rng.integers(cfg.ffc_freeze_frames[0], cfg.ffc_freeze_frames[1] + 1))
            step = rng.uniform(*cfg.ffc_step_c) * rng.choice([-1.0, 1.0])
            if 1 <= k and k + n_frz < n:
                events.append((k, n_frz, step))
            t_ev += rng.uniform(*cfg.ffc_interval_s)
        for k, n_frz, step in events:  # offsets first (persist to the end)
            frames[k + n_frz :] += step
            step_idx.append(k + n_frz)
        for k, n_frz, _ in events:  # then freeze: repeat the previous frame
            for j in range(k, k + n_frz):
                frames[j] = frames[k - 1]
                frozen.append(j)

    # --- ground truth --------------------------------------------------------
    apnea_mask = np.zeros(n, dtype=bool)
    for start, dur in cfg.apnea_events:
        apnea_mask |= (t >= start) & (t < start + dur)

    truth = GroundTruth(
        rate_bpm=rate_true,
        apnea_mask=apnea_mask,
        nostril_box=cfg.nostril_box,
        control_box=cfg.control_box,
        reference_box=cfg.reference_box,
        ffc_indices=np.array(sorted(frozen), dtype=int),
        ffc_step_indices=np.array(sorted(step_idx), dtype=int),
        amplitude_c=amp,
        ambient_c=cfg.ambient_c,
    )
    return SyntheticResult(frames.astype(np.float32), t, truth, cfg)


class SyntheticSource:
    """FrameSource backed by the synthetic generator (see ``FrameSource``)."""

    def __init__(self, cfg: SyntheticConfig | None = None) -> None:
        self.cfg = cfg or SyntheticConfig()
        self.fs_nominal = self.cfg.fs_nominal
        self.result = generate(self.cfg)
        self.truth = self.result.truth

    def frames(self) -> Iterator[tuple[float, np.ndarray]]:
        """Yield (timestamp_seconds, frame_celsius[60, 80]) in time order."""
        for ts, frame in zip(self.result.timestamps, self.result.frames):
            yield float(ts), frame
