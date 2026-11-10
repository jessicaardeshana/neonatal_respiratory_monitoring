"""Phase 4: apnea detector (SYNTHETIC data)."""

import numpy as np
import pytest

from thermal.apnea import ApneaConfig, amplitude_envelope, detect_apnea, running_baseline
from thermal.config import ADULT, PipelineConfig
from thermal.metrics import score_events
from thermal.preprocess import process_frames
from thermal.roi import ROI
from thermal.sources.synthetic import SyntheticConfig, generate

FS = 8.7


def _detect(res, acfg=None):
    tr = res.truth
    out = process_frames(res.frames, res.timestamps, ROI.from_box(tr.nostril_box),
                         ROI.from_box(tr.control_box), ROI.from_box(tr.reference_box), PipelineConfig())
    return detect_apnea(out.t, out.s_filt, FS, ADULT, acfg)


def _score(res, r, kind="apnea"):
    truth = [(s, s + d) for s, d in res.config.apnea_events]
    return score_events(truth, [(e.start, e.end) for e in r.events if e.kind == kind])


# ---- envelope ------------------------------------------------------------
def test_rms_envelope_of_a_sine_is_amplitude_over_sqrt2():
    t = np.arange(0, 60, 1 / FS)
    x = 0.8 * np.sin(2 * np.pi * 0.25 * t)
    env = amplitude_envelope(x, FS, window_s=8.0)  # whole number of cycles
    assert np.isnan(env[:10]).all()
    assert np.allclose(env[int(10 * FS):], 0.8 / np.sqrt(2), rtol=0.02)
    hil = amplitude_envelope(x, FS, window_s=8.0, method="hilbert")
    assert np.allclose(hil[int(10 * FS):-int(10 * FS)], 0.8 / np.sqrt(2), rtol=0.05)


def test_causal_envelope_reacts_later_than_centered():
    t = np.arange(0, 60, 1 / FS)
    x = np.where(t < 30, np.sin(2 * np.pi * 0.25 * t), 0.0)
    drop = lambda e: t[np.flatnonzero(np.nan_to_num(e, nan=1.0) < 0.1)[0]]
    assert drop(amplitude_envelope(x, FS, 4.0, causal=True)) > drop(amplitude_envelope(x, FS, 4.0, causal=False))


def test_bad_envelope_method_raises():
    with pytest.raises(ValueError):
        amplitude_envelope(np.zeros(100), FS, method="peak")


def test_baseline_is_nan_until_warmup_and_ignores_dips():
    env = np.concatenate((np.full(600, 1.0), np.full(300, 0.05), np.full(300, 1.0)))
    base = running_baseline(env, FS, k=0.25, baseline_s=180, warmup_s=30)
    assert np.isnan(base[:200]).all()
    assert np.allclose(base[700:], 1.0)  # frozen through the dip, never learned it


# ---- acceptance: injected pauses ----------------------------------------
@pytest.mark.parametrize("bpm", [10, 20, 30])
@pytest.mark.parametrize("causal", [True, False])
def test_20s_pauses_detected_with_small_start_end_errors(bpm, causal):
    ev = ((120.0, 20.0), (260.0, 20.0))
    res = generate(SyntheticConfig(duration_s=400, seed=bpm, rate_bpm=bpm, apnea_events=ev))
    r = _detect(res, ApneaConfig(causal=causal))
    sc = _score(res, r)
    assert sc["missed"] == 0 and sc["false_alarms"] == 0 and sc["fragments"] == 0
    assert all(e.kind == "apnea" for e in r.events)
    assert max(abs(np.array(sc["start_err"]))) <= 3.0  # spec target: within ~5 s
    assert max(abs(np.array(sc["end_err"]))) <= 3.0
    for e in r.events:  # earliest real-time alarm comes well after the pause begins
        assert e.declared_at >= e.start + 15.0


def test_flag_masks_match_events():
    res = generate(SyntheticConfig(duration_s=300, seed=0, rate_bpm=15.0, apnea_events=((120.0, 20.0),)))
    r = _detect(res)
    assert r.apnea.any() and not r.signal_lost.any()
    assert abs(r.apnea.sum() / FS - 20.0) < 3.0
    assert (r.t[r.apnea].min() >= 118.0) and (r.t[r.apnea].max() <= 144.0)


def test_pause_shorter_than_min_duration_is_not_flagged_but_is_with_10s_rule():
    res = generate(SyntheticConfig(duration_s=300, seed=0, rate_bpm=20.0, apnea_events=((120.0, 10.0),)))
    assert _detect(res).events == []
    r = _detect(res, ApneaConfig(min_duration_s=10.0))
    assert len(r.events) == 1 and r.events[0].kind == "apnea"


def test_long_pause_is_flagged_for_its_full_length():
    res = generate(SyntheticConfig(duration_s=400, seed=0, rate_bpm=20.0, apnea_events=((120.0, 90.0),)))
    r = _detect(res)
    sc = _score(res, r)
    assert len(r.events) == 1 and sc["missed"] == 0
    assert abs(sc["end_err"][0]) <= 3.0  # baseline did not learn the pause


# ---- false alarms ----------------------------------------------------------
@pytest.mark.parametrize("bpm,seed", [(10, 0), (30, 1)])
def test_no_false_alarms_on_a_long_clean_run_with_all_nuisances(bpm, seed):
    res = generate(SyntheticConfig(duration_s=600, seed=seed, rate_bpm=bpm))  # FFC, jitter, drift on
    assert _detect(res).events == []


def test_no_false_alarm_when_the_rate_changes():
    res = generate(SyntheticConfig(duration_s=500, seed=0, rate_bpm=10.0, rate_steps=((250.0, 30.0),)))
    assert _detect(res).events == []


# ---- signal_lost -----------------------------------------------------------
def test_no_visible_breathing_is_signal_lost_not_apnea():
    res = generate(SyntheticConfig(duration_s=250, seed=1, amplitude_c=0.0))
    r = _detect(res)
    assert r.events and all(e.kind == "signal_lost" for e in r.events)
    assert not r.apnea.any()
    assert r.signal_lost[r.t > 120].mean() > 0.9


def test_pause_after_good_breathing_is_apnea_not_signal_lost():
    res = generate(SyntheticConfig(duration_s=300, seed=2, rate_bpm=15.0, apnea_events=((150.0, 25.0),)))
    r = _detect(res)
    assert [e.kind for e in r.events] == ["apnea"]


# ---- scoring helper ----------------------------------------------------------
def test_score_events_counts_missed_false_alarms_and_fragments():
    truth = [(100.0, 120.0), (200.0, 220.0)]
    det = [(101.0, 122.0), (300.0, 320.0), (110.0, 115.0)]
    sc = score_events(truth, det)
    assert sc["start_err"] == [1.0] and sc["end_err"] == [2.0]
    assert sc["missed"] == 1 and sc["false_alarms"] == 1 and sc["fragments"] == 1


# ---- regression: a rate change shortly before a pause must not turn apnea into "signal_lost" ----------
@pytest.mark.parametrize("seed", [2, 5, 7])
@pytest.mark.parametrize("head", [True, False])
def test_pause_20_s_after_a_speed_up_is_still_labeled_apnea(seed, head):
    """Windows straddling a rate change score low on quality, but breathing was clearly there just before."""
    res = generate(SyntheticConfig(duration_s=180, seed=seed, rate_bpm=14.0, rate_steps=((75.0, 24.0),),
                                   apnea_events=((95.0, 25.0),), head_jitter=head, ffc_interval_s=(55.0, 85.0)))
    r = _detect(res)
    assert [e.kind for e in r.events] == ["apnea"]


def test_marginal_signal_in_a_hot_incubator_is_signal_lost_never_apnea():
    """Swing about 0.04 degC: the 'normal' level is below the very-low floor, so a pause cannot be called apnea."""
    res = generate(SyntheticConfig(duration_s=240, seed=3, ambient_c=34.0, apnea_events=((100.0, 30.0),)))
    r = _detect(res)
    assert not any(e.kind == "apnea" for e in r.events)
