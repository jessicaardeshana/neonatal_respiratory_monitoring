"""Phase 3: rate estimators, quality, metrics (SYNTHETIC data)."""

import numpy as np

from thermal.config import ADULT, NEONATE, PipelineConfig
from thermal.metrics import coverage, mae, max_abs_error, step_lag, truth_on_grid, window_truth
from thermal.preprocess import process_frames
from thermal.quality import agreement_factor, quality_from_snr
from thermal.rate import estimate_rates
from thermal.roi import ROI
from thermal.sources.synthetic import SyntheticConfig, generate

FS = 8.7


def _sine(bpm, dur=120.0, noise=0.0, seed=0):
    t = np.arange(0, dur, 1 / FS)
    x = np.sin(2 * np.pi * bpm / 60 * t)
    return t, x + noise * np.random.default_rng(seed).standard_normal(t.size)


def _pipeline(res, profile=ADULT, reduction="mean"):
    tr = res.truth
    cfg = PipelineConfig(profile=profile, reduction=reduction)
    out = process_frames(res.frames, res.timestamps, ROI.from_box(tr.nostril_box),
                         ROI.from_box(tr.control_box), ROI.from_box(tr.reference_box), cfg)
    est = estimate_rates(out.t, out.s_filt, FS, profile)
    wt = window_truth(out.t, truth_on_grid(res.timestamps, tr.rate_bpm, out.t), est.t_end, est.window_s)
    steady = (est.t_end - est.window_s > 15) & (est.t_end < out.t[-1] - 15)  # skip filter edges
    return out, est, wt, steady


def test_estimators_recover_a_pure_sine():
    for bpm in (10, 20, 30):
        t, x = _sine(bpm)
        est = estimate_rates(t, x, FS, ADULT)
        assert np.nanmax(np.abs(est.spectral_bpm - bpm)) < 0.3, bpm
        assert np.nanmax(np.abs(est.time_bpm - bpm)) < 0.5, bpm
        assert coverage(est.spectral_bpm) == 1.0
        assert est.quality.min() > 0.9


def test_neonate_profile_on_a_pure_sine():
    t, x = _sine(60, dur=90)
    est = estimate_rates(t, x, FS, NEONATE)
    assert np.nanmax(np.abs(est.spectral_bpm - 60)) < 0.5


def test_first_estimate_waits_for_the_window_to_fill():
    t, x = _sine(20, dur=60)
    est = estimate_rates(t, x, FS, ADULT)
    assert est.t_end[0] >= ADULT.window_s - 1 / FS


def test_noise_gives_low_quality_and_nan_not_a_wrong_number():
    rng = np.random.default_rng(1)
    t = np.arange(0, 300, 1 / FS)
    from thermal.preprocess import bandpass
    x = bandpass(rng.standard_normal(t.size), FS, ADULT.band_hz)
    est = estimate_rates(t, x, FS, ADULT)
    assert coverage(est.spectral_bpm) < 0.15
    assert np.median(est.quality) < 0.3


def test_quality_mapping_and_agreement_factor():
    assert quality_from_snr(100.0) == 1.0
    assert quality_from_snr(0.1) == 0.0
    assert 0.0 < quality_from_snr(3.0) < 1.0
    assert agreement_factor(20.0, 21.0) == 1.0
    assert agreement_factor(20.0, 29.0) == 0.5
    assert agreement_factor(20.0, float("nan")) == 0.5


def test_acceptance_adult_rates_within_1_bpm_full_nuisance_model():
    """Spec Phase 3: 10/20/30 breaths/min, all nuisances ON, 5% rate wander."""
    for bpm in (10, 20, 30):
        for seed in (0, 1):
            res = generate(SyntheticConfig(duration_s=200, seed=seed, rate_bpm=bpm))
            _, est, wt, steady = _pipeline(res)
            assert mae(est.spectral_bpm, wt, steady) < 1.0, (bpm, seed)
            assert mae(est.time_bpm, wt, steady) < 1.0, (bpm, seed)
            within = np.abs(est.spectral_bpm - wt)[steady] <= 1.0
            # 5% simulated rate wander makes "the" rate of a window ambiguous: at
            # 30 bpm 82-100% of windows are within +/-1 depending on the seed.
            assert within.mean() >= 0.75, (bpm, seed, within.mean())


def test_estimators_are_near_exact_when_the_true_rate_does_not_wander():
    """The remaining error above is the rate wandering, not the estimator."""
    for bpm in (10, 20, 30):
        res = generate(SyntheticConfig(duration_s=200, seed=2, rate_bpm=bpm, rate_variability=0.0))
        _, est, wt, steady = _pipeline(res)
        assert max_abs_error(est.spectral_bpm, wt, steady) < 0.5, bpm
        assert max_abs_error(est.time_bpm, wt, steady) < 0.5, bpm


def test_neonate_rates_within_2_bpm_mae():
    for bpm in (40, 60, 80):
        res = generate(SyntheticConfig(duration_s=200, seed=0, rate_bpm=bpm))
        _, est, wt, steady = _pipeline(res, profile=NEONATE)
        assert mae(est.time_bpm, wt, steady) < 2.0, bpm
        assert mae(est.spectral_bpm, wt, steady) < 2.0, bpm


def test_rate_step_is_tracked_with_a_finite_lag():
    res = generate(SyntheticConfig(duration_s=300, seed=3, rate_bpm=10.0,
                                   rate_steps=((150.0, 25.0),), rate_variability=0.0))
    out, est, _, _ = _pipeline(res)
    lag = step_lag(est.t_end, est.spectral_bpm, 150.0, 25.0, tol_bpm=1.5)
    assert np.isfinite(lag)
    assert 0 < lag <= est.window_s + 4.0  # about one window length


def test_control_roi_has_no_breathing_peak_low_quality():
    res = generate(SyntheticConfig(duration_s=300, seed=4, rate_bpm=15.0))
    out, est, _, steady = _pipeline(res)
    ctrl = estimate_rates(out.t, out.ctrl_filt, FS, ADULT)
    assert coverage(est.spectral_bpm, steady) > 0.9
    # head jitter leaves slow bumps in the cheek signal: ~12% of control windows
    # pass the quality gate (a known motion artifact); still far below nostril.
    assert coverage(ctrl.spectral_bpm, steady) < 0.2
    assert np.median(ctrl.quality) < 0.3 < np.median(est.quality)


def test_control_roi_is_silent_when_head_does_not_move():
    res = generate(SyntheticConfig(duration_s=300, seed=4, rate_bpm=15.0, head_jitter=False))
    out, _, _, steady = _pipeline(res)
    ctrl = estimate_rates(out.t, out.ctrl_filt, FS, ADULT)
    assert coverage(ctrl.spectral_bpm, steady) == 0.0


def test_metric_helpers():
    est = np.array([10.0, np.nan, 12.0])
    truth = np.array([10.5, 99.0, 11.0])
    assert mae(est, truth) == 0.75
    assert max_abs_error(est, truth) == 1.0
    assert coverage(est) == 2 / 3
    t_end = np.arange(0, 100.0)
    e = np.where(t_end < 60, 10.0, 20.0)
    assert step_lag(t_end, e, 50.0, 20.0) == 10.0
    assert np.isnan(step_lag(t_end, np.full(100, 10.0), 50.0, 20.0))
