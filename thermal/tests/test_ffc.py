"""FFC detection and repair (SYNTHETIC data)."""

from dataclasses import replace

import numpy as np

from thermal.ffc import detect_ffc, reference_subtract, repair_invalid
from thermal.sources.synthetic import SyntheticConfig, generate


def _cfg(**kw):
    return replace(SyntheticConfig(duration_s=400, seed=2, ffc_interval_s=(100.0, 150.0),
                                   amplitude_c=0.7), **kw)


def test_detects_exactly_the_injected_frozen_frames_and_steps():
    res = generate(_cfg())
    out = detect_ffc(res.frames)
    assert np.array_equal(np.flatnonzero(out.frozen_mask), res.truth.ffc_indices)
    assert np.array_equal(out.step_indices, res.truth.ffc_step_indices)
    assert np.all(np.abs(out.step_sizes) >= 0.1 - 0.02)


def test_no_false_alarms_on_a_long_clean_run_with_breathing_jitter_apnea():
    res = generate(_cfg(ffc=False, duration_s=900, apnea_events=((300.0, 30.0),)))
    out = detect_ffc(res.frames)
    assert not out.frozen_mask.any()
    assert out.step_indices.size == 0


def test_telemetry_flag_overrides_frozen_heuristic():
    res = generate(_cfg(ffc=False, duration_s=60))
    flag = np.zeros(res.frames.shape[0], dtype=bool)
    flag[10:12] = True
    out = detect_ffc(res.frames, telemetry_ffc=flag)
    assert np.array_equal(out.frozen_mask, flag)


def test_repair_interpolates_short_gaps_and_nans_long_ones():
    t = np.arange(100) / 10.0
    s = np.sin(t)
    bad = np.zeros(100, dtype=bool)
    bad[10:12] = True   # 0.3 s gap: repaired
    bad[50:80] = True   # 3.1 s gap: left NaN
    s_bad = s.copy(); s_bad[bad] = 99.0
    out = repair_invalid(t, s_bad, bad, max_gap_s=2.0)
    assert np.allclose(out[10:12], s[10:12], atol=0.01)
    assert np.isnan(out[50:80]).all()
    assert not np.isnan(out[:50]).any()


def test_reference_subtract_cancels_shared_step():
    n = 200
    breath = np.sin(np.arange(n) / 5.0)
    step = np.where(np.arange(n) >= 100, 0.3, 0.0)
    out = reference_subtract(24.0 + breath + step, 24.0 + step)
    assert np.allclose(out - out.mean(), breath - breath.mean(), atol=1e-9)
