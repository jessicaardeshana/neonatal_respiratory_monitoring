"""Configuration: breathing profiles and pipeline parameters.

Hardware numbers here come from memory and are UNVERIFIED (spec Section 4);
check them against the Lepton datasheet before relying on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FRAME_SHAPE: tuple[int, int] = (60, 80)  # rows x cols, Lepton 2.5 (unverified)
FS_NOMINAL_HZ: float = 8.7  # Hz, Lepton 2.5 is < 9 Hz (unverified)


@dataclass(frozen=True)
class Profile:
    """Breathing profile: expected rate range and the matching filter band."""

    name: str
    rate_min_bpm: float  # breaths/min
    rate_max_bpm: float  # breaths/min
    band_hz: tuple[float, float]  # band-pass edges, Hz
    window_s: float  # rate-estimation window, seconds


ADULT = Profile("adult", 8.0, 30.0, (0.10, 0.70), 30.0)
NEONATE = Profile("neonate", 30.0, 90.0, (0.50, 1.50), 20.0)
PROFILES: dict[str, Profile] = {p.name: p for p in (ADULT, NEONATE)}


@dataclass
class PipelineConfig:
    """Pipeline parameters. Fields are added phase by phase."""

    profile: Profile = ADULT
    fs_nominal: float = FS_NOMINAL_HZ
    filter_order: int = 4  # Butterworth order
    extra: dict = field(default_factory=dict)
