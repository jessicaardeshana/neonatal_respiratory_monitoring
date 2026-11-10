"""Phase 6: the one-command demo, the Section 7 output contract, and reproducibility (SYNTHETIC)."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from thermal.pipeline import load_processed, processed_arrays
from thermal.rate import hold_to_grid

_spec = importlib.util.spec_from_file_location(
    "run_synthetic_demo", Path(__file__).resolve().parents[1] / "scripts" / "run_synthetic_demo.py")
demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo)

CONTRACT = {"t", "s_raw", "s_ctrl", "s_filt", "envelope", "rate_bpm", "quality", "apnea", "ffc_mask"}


@pytest.fixture(scope="module")
def run1(tmp_path_factory):
    d = tmp_path_factory.mktemp("demo1")
    return d, demo.main(out_dir=d, data_dir=d, quick=True)


def test_one_command_produces_figure_report_and_processed_file(run1):
    d, res = run1
    assert (d / "demo_summary.png").stat().st_size > 50_000
    report = (d / "demo_report.md").read_text()
    assert "SYNTHETIC" in report and "demo_summary.png" in report
    assert (d / "demo_processed.npz").exists()


def test_demo_scenario_results_are_sensible(run1):
    m = run1[1]["metrics"]
    assert m["mae_time"] < 1.0 and m["mae_spec"] < 1.0
    assert m["missed"] == 0 and m["false_alarms"] == 0 and m["fragments"] == 0
    assert max(abs(x) for x in m["start_err"] + m["end_err"]) <= 5.0
    assert m["ffc_found"] == m["ffc_true"] and m["ffc_extra"] == 0
    assert m["ctrl_cov"] < 0.2 < m["nos_cov"]
    assert np.isfinite(m["lag_spec"]) and np.isfinite(m["lag_time"])


def test_processed_file_follows_section_7_contract(run1):
    arrays, meta = load_processed(run1[1]["npz"])
    assert CONTRACT <= set(arrays) and set(arrays) - CONTRACT == {"signal_lost"}
    n = arrays["t"].size
    assert all(a.shape == (n,) for a in arrays.values())
    for k in ("apnea", "ffc_mask", "signal_lost"):
        assert arrays[k].dtype == bool
    for k in ("t", "s_raw", "s_ctrl", "s_filt", "envelope", "rate_bpm", "quality"):
        assert np.issubdtype(arrays[k].dtype, np.floating)
    assert np.allclose(np.diff(arrays["t"]), np.diff(arrays["t"])[0])  # uniform grid
    ok = np.isfinite(arrays["rate_bpm"])  # a rate is only ever given when quality was good enough
    assert ok.any() and np.all(arrays["quality"][ok] >= 0.5)
    t = arrays["t"]
    inside = np.zeros(n, dtype=bool)
    for a, b in demo.pause_windows(demo.DEMO_CFG):
        inside |= (t >= a) & (t < b)
    assert arrays["apnea"][inside].mean() > 0.8 and arrays["apnea"][~inside].mean() < 0.05
    assert arrays["ffc_mask"].any()
    assert meta["synthetic"] and meta["profile"] == "adult" and meta["rate_estimator"] == "time_domain"
    assert {"nostril", "control", "reference"} == set(meta["rois"]) and "git_commit" in meta


def test_demo_is_reproducible_bit_for_bit(run1, tmp_path):
    d1, res1 = run1
    res2 = demo.main(out_dir=tmp_path, data_dir=tmp_path, quick=True)
    a1, m1 = load_processed(res1["npz"])
    a2, m2 = load_processed(res2["npz"])
    assert a1.keys() == a2.keys()
    for k in a1:
        assert np.array_equal(a1[k], a2[k], equal_nan=True), k
    assert m1 == m2
    assert (d1 / "demo_report.md").read_text() == (tmp_path / "demo_report.md").read_text()
    assert (d1 / "demo_summary.png").read_bytes() == (tmp_path / "demo_summary.png").read_bytes()


def test_processed_arrays_estimator_choice_and_validation():
    src, out = demo.run_scenario(demo.SyntheticConfig(duration_s=120.0, seed=2))
    td = processed_arrays(out, "time_domain")["rate_bpm"]
    sp = processed_arrays(out, "spectral")["rate_bpm"]
    assert td.shape == sp.shape and not np.array_equal(td, sp, equal_nan=True)
    with pytest.raises(ValueError, match="estimator"):
        processed_arrays(out, "magic")


def test_hold_to_grid_is_causal_and_nan_before_first_window():
    t = np.arange(0.0, 10.0, 1.0)
    out = hold_to_grid(t, np.array([3.0, 6.0]), np.array([10.0, 20.0]))
    assert np.isnan(out[:3]).all()
    assert out[3] == 10.0 and out[5] == 10.0 and out[6] == 20.0 and out[9] == 20.0
