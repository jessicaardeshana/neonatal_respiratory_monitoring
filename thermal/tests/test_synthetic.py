"""Phase 1 tests: synthetic generator and its ground truth (all SYNTHETIC)."""

from dataclasses import replace

import numpy as np

from thermal.sources import FrameSource
from thermal.sources.synthetic import SyntheticConfig, SyntheticSource, generate


def _clean(**kw) -> SyntheticConfig:
    """Config with every nuisance off, so only the breathing remains."""
    base = SyntheticConfig(
        noise=False, drift=False, head_jitter=False, ffc=False,
        timestamp_jitter=False, dropped_frames=False, rate_variability=0.0,
    )
    return replace(base, **kw)


def _box_mean(res, box):
    r0, r1, c0, c1 = box
    return res.frames[:, r0:r1, c0:c1].mean(axis=(1, 2))


def _count_rising_crossings(x):
    x = x - x.mean()
    return int(np.sum((x[:-1] < 0) & (x[1:] >= 0)))


def test_shapes_dtype_and_monotonic_timestamps():
    res = generate(SyntheticConfig(duration_s=60, seed=1))
    assert res.frames.shape[1:] == (60, 80)
    assert res.frames.dtype == np.float32
    assert res.frames.shape[0] == res.timestamps.size
    assert np.all(np.diff(res.timestamps) > 0)


def test_is_a_frame_source():
    src = SyntheticSource(SyntheticConfig(duration_s=10))
    assert isinstance(src, FrameSource)
    ts, frame = next(iter(src.frames()))
    assert frame.shape == (60, 80)


def test_same_seed_is_reproducible_and_different_seed_differs():
    a = generate(SyntheticConfig(duration_s=60, seed=7))
    b = generate(SyntheticConfig(duration_s=60, seed=7))
    c = generate(SyntheticConfig(duration_s=60, seed=8))
    assert np.array_equal(a.frames, b.frames)
    assert np.array_equal(a.timestamps, b.timestamps)
    assert not np.array_equal(a.frames, c.frames)


def test_toggling_one_nuisance_does_not_change_another():
    """Each nuisance has its own random stream."""
    a = generate(_clean(duration_s=30, seed=3, noise=True))
    b = generate(_clean(duration_s=30, seed=3, noise=True, drift=True))
    assert not np.array_equal(a.frames, b.frames)  # drift changed values
    # ...but the noise realization is identical: remove drift's smooth ramp
    diff = (b.frames - a.frames)[:, 0, 0]
    assert np.allclose(diff, diff[:, None].mean(axis=1), atol=1e-4)


def test_all_off_gives_uniform_timestamps_and_no_noise():
    res = generate(_clean(duration_s=20))
    assert np.allclose(np.diff(res.timestamps), 1 / res.config.fs_nominal)
    # background pixel far from the face is exactly ambient
    assert np.all(res.frames[:, 0, 40] == np.float32(res.config.ambient_c))


def test_ground_truth_rate_matches_injected_breath_count():
    """20 breaths/min for 120 s -> 40 breaths in the nostril signal."""
    res = generate(_clean(duration_s=120, rate_bpm=20.0))
    assert np.allclose(res.truth.rate_bpm, 20.0)
    assert abs(_count_rising_crossings(_box_mean(res, res.truth.nostril_box)) - 40) <= 1


def test_rate_step_is_in_truth_and_in_signal():
    res = generate(_clean(duration_s=240, rate_bpm=10.0, rate_steps=((120.0, 30.0),)))
    t, s = res.timestamps, _box_mean(res, res.truth.nostril_box)
    first, second = t < 120, t >= 120
    assert np.allclose(res.truth.rate_bpm[first], 10.0)
    assert np.allclose(res.truth.rate_bpm[second], 30.0)
    assert abs(_count_rising_crossings(s[first]) - 20) <= 1  # 10/min * 2 min
    assert abs(_count_rising_crossings(s[second]) - 60) <= 1  # 30/min * 2 min


def test_breath_waveform_is_asymmetric_exhale_rises_faster():
    res = generate(_clean(duration_s=120, rate_bpm=12.0, thermal_lag_s=0.0))
    s = _box_mean(res, res.truth.nostril_box)
    s = s - s.mean()
    rising = np.sum(np.diff(s) > 0)
    falling = np.sum(np.diff(s) < 0)
    assert falling > rising  # fast rise = fewer samples going up


def test_apnea_mask_matches_window_and_amplitude_collapses():
    res = generate(_clean(duration_s=180, rate_bpm=15.0, apnea_events=((60.0, 20.0),)))
    t, mask = res.timestamps, res.truth.apnea_mask
    assert t[mask].min() >= 60.0 and t[mask].max() < 80.0
    assert abs((mask.sum() / res.config.fs_nominal) - 20.0) < 0.5
    s = _box_mean(res, res.truth.nostril_box)
    s = s - s.mean()
    inside = s[(t >= 62.0) & (t < 80.0)]  # after the 1 s ramp (+ lag margin)
    outside = s[(t >= 10.0) & (t < 50.0)]
    assert np.ptp(inside) < 0.05 * np.ptp(outside)


def test_amplitude_scales_with_ambient_incubator_effect():
    cool = SyntheticConfig(ambient_c=22.0).breath_amplitude_c
    warm = SyntheticConfig(ambient_c=34.0).breath_amplitude_c
    hot = SyntheticConfig(ambient_c=36.0).breath_amplitude_c
    assert 0.3 <= cool <= 1.5
    assert warm < 0.1 * cool
    assert hot == 0.0


def test_nostril_box_carries_breathing_control_and_reference_do_not():
    res = generate(_clean(duration_s=120, rate_bpm=15.0))
    nostril = _box_mean(res, res.truth.nostril_box)
    control = _box_mean(res, res.truth.control_box)
    reference = _box_mean(res, res.truth.reference_box)
    assert np.ptp(nostril) > 1.0
    assert np.ptp(control) < 1e-3
    assert np.ptp(reference) < 1e-3


def test_ffc_frozen_frames_are_repeats_and_indices_match():
    res = generate(
        SyntheticConfig(duration_s=400, seed=2, dropped_frames=False,
                        ffc_interval_s=(100.0, 150.0))
    )
    idx = res.truth.ffc_indices
    assert idx.size >= 2
    for j in idx:
        assert np.array_equal(res.frames[j], res.frames[j - 1])
    # a non-FFC consecutive pair is not identical (noise is on)
    non = np.setdiff1d(np.arange(1, 50), idx)
    assert not np.array_equal(res.frames[non[0]], res.frames[non[0] - 1])


def test_ffc_step_changes_scene_level_by_configured_amount():
    res = generate(
        _clean(duration_s=400, ffc=True, ffc_interval_s=(100.0, 150.0),
               ffc_step_c=(0.2, 0.2))
    )
    bg = res.frames[:, 0, 40].astype(np.float64)  # untouched background pixel
    for k in res.truth.ffc_step_indices:
        assert abs(abs(bg[k] - bg[k - 3]) - 0.2) < 1e-3
    # persistent: level after the last event differs from the start
    assert abs(bg[-1] - bg[0]) >= 0.2 - 1e-3


def test_ffc_off_means_no_frozen_frames():
    res = generate(_clean(duration_s=400))
    assert res.truth.ffc_indices.size == 0
    assert res.truth.ffc_step_indices.size == 0


def test_timestamp_jitter_and_dropped_frames_are_applied():
    res = generate(SyntheticConfig(duration_s=300, seed=4, dropped_frame_prob=0.02))
    dt = np.diff(res.timestamps)
    period = 1 / res.config.fs_nominal
    assert dt.min() > 0
    assert np.any(dt > 1.5 * period)  # a dropped frame leaves a gap
    clean_dt = dt[dt < 1.5 * period]
    assert clean_dt.std() > 0  # not perfectly uniform
    assert np.all(np.abs(clean_dt - period) <= 0.21 * period + 1e-9)
