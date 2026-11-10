"""Slider parameters -> synthetic scenario (SIMULATED data) and detector settings.

One place defines every demo control: its range, default and label. The server
sends this schema to the UI, so sliders can never drift from what the backend accepts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from thermal.apnea import ApneaConfig
from thermal.config import ADULT, NEONATE, Profile
from thermal.sources.synthetic import SyntheticConfig

NOISE_SIGMA_C = 0.05  # per-pixel sensor noise at "1x" (NETD about 50 mK, unverified)
HEAD_PROB = {"off": 0.0, "small": 0.01, "large": 0.04}  # chance per frame of a 1 px head shift
FFC_INTERVAL_S = (55.0, 85.0)  # real cameras calibrate every 2-3 min; sped up so the demo shows one


class ScenarioParams(BaseModel):
    """Everything the Lab sliders can change. Defaults are the guided-tour story."""

    rate_bpm: float = Field(14.0, ge=8, le=90, description="breathing rate, breaths/min")
    rate_change: bool = True
    rate_change_time_s: float = Field(75.0, ge=10, le=200)
    rate_after_bpm: float = Field(24.0, ge=8, le=90)
    apnea: bool = True
    apnea_start_s: float = Field(95.0, ge=20, le=220)
    apnea_len_s: float = Field(25.0, ge=5, le=60)
    ambient_c: float = Field(24.0, ge=22, le=36, description="room / incubator temperature, degC")
    noise_x: float = Field(1.0, ge=0, le=3, description="sensor noise as a multiple of the default")
    head: Literal["off", "small", "large"] = "small"
    ffc: bool = True
    min_pause_s: float = Field(20.0, ge=5, le=40, description="detector: shortest pause that counts, s")
    duration_s: float = Field(180.0, ge=60, le=240)
    seed: int = Field(7, ge=0, le=10_000)

    @model_validator(mode="after")
    def _check(self) -> "ScenarioParams":
        if self.rate_change and self.rate_change_time_s > self.duration_s - 20:
            raise ValueError("rate change must happen at least 20 s before the end")
        if self.apnea and self.apnea_start_s + self.apnea_len_s > self.duration_s - 10:
            raise ValueError("the pause must end at least 10 s before the recording ends")
        return self


# Slider schema for the UI: (key, label, kind, min, max, step, unit, help)
SCHEMA = [
    {"key": "rate_bpm", "label": "Breathing rate", "kind": "range", "min": 8, "max": 90, "step": 1, "unit": "breaths/min",
     "help": "Adults breathe about 8-30 times a minute, newborns about 30-90."},
    {"key": "rate_change", "label": "Change the rate partway", "kind": "toggle", "help": "Breathing speeds up or slows down."},
    {"key": "rate_after_bpm", "label": "Rate after the change", "kind": "range", "min": 8, "max": 90, "step": 1, "unit": "breaths/min"},
    {"key": "rate_change_time_s", "label": "Change happens at", "kind": "range", "min": 10, "max": 200, "step": 5, "unit": "s"},
    {"key": "apnea", "label": "Breathing pause (apnea)", "kind": "toggle", "help": "Airflow stops completely for a while."},
    {"key": "apnea_start_s", "label": "Pause starts at", "kind": "range", "min": 20, "max": 220, "step": 5, "unit": "s"},
    {"key": "apnea_len_s", "label": "Pause length", "kind": "range", "min": 5, "max": 60, "step": 1, "unit": "s"},
    {"key": "ambient_c", "label": "Incubator temperature", "kind": "range", "min": 22, "max": 36, "step": 0.5, "unit": "degC",
     "help": "Exhaled air is about 34.5 degC. The warmer the room, the smaller the temperature swing at the nose."},
    {"key": "noise_x", "label": "Sensor noise", "kind": "range", "min": 0, "max": 3, "step": 0.25, "unit": "x default"},
    {"key": "head", "label": "Head movement", "kind": "choice", "options": [["off", "Still"], ["small", "Occasional"], ["large", "Frequent"]],
     "help": "Each shift moves the picture by one pixel."},
    {"key": "ffc", "label": "Camera recalibration (FFC)", "kind": "toggle",
     "help": "The camera freezes for a moment and its level jumps. Sped up here so one shows within the demo."},
    {"key": "min_pause_s", "label": "Detector: shortest pause", "kind": "range", "min": 5, "max": 40, "step": 1, "unit": "s",
     "help": "Clinical apnea is a pause of 20 s or more."},
]


def choose_profile(p: ScenarioParams) -> tuple[Profile, str | None]:
    """Adult or newborn filter band from the rates in use, plus a warning if the rates span both."""
    rates = [p.rate_bpm] + ([p.rate_after_bpm] if p.rate_change else [])
    hi, lo = max(rates), min(rates)
    profile = NEONATE if hi > 40 else ADULT
    warn = None
    if lo < 28 and hi > 40:
        warn = ("These rates span both the adult and newborn ranges. The filter is tuned to one of them, "
                "so the other will read badly.")
    return profile, warn


def to_synthetic(p: ScenarioParams) -> SyntheticConfig:
    return SyntheticConfig(
        duration_s=p.duration_s, seed=p.seed, rate_bpm=p.rate_bpm,
        rate_steps=((p.rate_change_time_s, p.rate_after_bpm),) if p.rate_change else (),
        apnea_events=((p.apnea_start_s, p.apnea_len_s),) if p.apnea else (),
        ambient_c=p.ambient_c, noise=p.noise_x > 0, noise_sigma_c=NOISE_SIGMA_C * max(p.noise_x, 1e-9),
        head_jitter=p.head != "off", head_jitter_prob=HEAD_PROB[p.head],
        ffc=p.ffc, ffc_interval_s=FFC_INTERVAL_S,
    )


def to_apnea(p: ScenarioParams) -> ApneaConfig:
    return ApneaConfig(min_duration_s=p.min_pause_s)
