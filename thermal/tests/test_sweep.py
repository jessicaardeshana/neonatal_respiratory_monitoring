"""Phase 4b: sweep helpers (MODEL PREDICTION code, SYNTHETIC data)."""

import importlib.util
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location(
    "sweep_ambient", Path(__file__).resolve().parents[1] / "scripts" / "sweep_ambient.py")
sw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sw)


def test_aggregate_averages_over_seeds_and_ignores_nan():
    rows = [{"ambient": 24.0, "seed": 0, "head_jitter": True, "x": 1.0},
            {"ambient": 24.0, "seed": 1, "head_jitter": True, "x": 3.0},
            {"ambient": 30.0, "seed": 0, "head_jitter": True, "x": float("nan")},
            {"ambient": 30.0, "seed": 1, "head_jitter": True, "x": 5.0}]
    agg = sw.aggregate(rows)
    assert agg[24.0]["x"] == 2.0 and agg[30.0]["x"] == 5.0


def test_usable_requires_all_three_criteria():
    good = {"coverage": 1.0, "mae_time": 0.1, "apnea_found": 1.0}
    assert sw.usable(good)
    assert not sw.usable({**good, "coverage": 0.5})
    assert not sw.usable({**good, "mae_time": 2.0})
    assert not sw.usable({**good, "mae_time": float("nan")})
    assert not sw.usable({**good, "apnea_found": 0.5})


def test_cool_room_works_and_signal_vanishes_at_exhale_temperature():
    cool = sw.run_one(24.0, 0, head_jitter=False)
    gone = sw.run_one(35.0, 0, head_jitter=False)
    assert cool["amp_design_c"] > 0.7 and gone["amp_design_c"] == 0.0
    assert cool["amp_rms_c"] > 10 * gone["amp_rms_c"]
    assert cool["apnea_found"] == 1.0 and gone["apnea_found"] == 0.0
    assert gone["lost_frac"] > 0.5  # reported as "cannot see breathing", not as apnea
