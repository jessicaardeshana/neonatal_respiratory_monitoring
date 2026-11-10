"""Preprocessing + the Phase 2 acceptance test (SYNTHETIC data)."""

from dataclasses import replace

import numpy as np
from scipy.signal import find_peaks

from thermal.config import PipelineConfig
from thermal.preprocess import bandpass, detrend, process_frames, resample_uniform
from thermal.roi import ROI
from thermal.sources.synthetic import SyntheticConfig, generate

EDGE_S = 20.0  # ignore filter edge effects at both ends when counting


def _rois(res):
    tr = res.truth
    return ROI.from_box(tr.nostril_box), ROI.from_box(tr.control_box), ROI.from_box(tr.reference_box)


def _run(res, **cfgkw):
    n, c, r = _rois(res)
    return process_frames(res.frames, res.timestamps, n, c, r, PipelineConfig(**cfgkw))


def _inner(out, x):
    m = (out.t > out.t[0] + EDGE_S) & (out.t < out.t[-1] - EDGE_S)
    return x[m]


def test_resample_is_uniform_and_follows_signal():
    t = np.sort(np.random.default_rng(0).uniform(0, 60, 400))
    t_u, s_u = resample_uniform(t, np.sin(0.5 * t), 8.7)
    assert np.allclose(np.diff(t_u), 1 / 8.7)
    assert np.max(np.abs(s_u - np.sin(0.5 * t_u))) < 0.05


def test_detrend_removes_linear_drift_keeps_breathing():
    fs = 8.7
    t = np.arange(0, 180, 1 / fs)
    breath = 0.7 * np.sin(2 * np.pi * 0.25 * t)
    for method in ("highpass", "movmean", "poly"):
        out = detrend(breath + 0.5 * t / 60, fs, method)
        mid = slice(int(30 * fs), -int(30 * fs))
        assert abs(np.polyfit(t[mid], out[mid], 1)[0]) < 5e-3, method
        assert out[mid].std() > 0.4, method  # breathing survived


def test_bandpass_passes_in_band_blocks_out_of_band_and_causal_is_delayed():
    fs = 8.7
    t = np.arange(0, 120, 1 / fs)
    band = (0.10, 0.70)
    inb, low, high = (np.sin(2 * np.pi * f * t) for f in (0.3, 0.02, 2.5))
    assert bandpass(inb, fs, band).std() > 0.6
    assert bandpass(low, fs, band)[200:-200].std() < 0.05
    assert bandpass(high, fs, band)[200:-200].std() < 0.05
    zero_phase, causal = bandpass(inb, fs, band), bandpass(inb, fs, band, causal=True)
    lag = np.argmax(np.correlate(causal[300:-300], zero_phase[300:-300], "full")) - (len(causal[300:-300]) - 1)
    assert lag > 0  # causal output lags the zero-phase one


def test_amplitude_is_preserved_not_normalized():
    res = generate(SyntheticConfig(duration_s=180, seed=1, ffc=False, amplitude_c=0.7))
    out = _run(res)
    pp = np.ptp(_inner(out, out.s_filt))
    assert 0.8 < pp < 2.0  # about 2A = 1.4 degC peak-to-peak


def _spurious_peaks(res, **cfgkw):
    """Count breath-sized peaks in a NO-BREATHING recording."""
    out = _run(res, **cfgkw)
    x = _inner(out, out.s_filt)
    return find_peaks(np.abs(x), prominence=0.1)[0].size


def test_ffc_handling_off_creates_spurious_breaths_on_removes_them():
    """PHASE 2 ACCEPTANCE: no breathing at all, but FFC events present.

    Head jitter is switched off so this test isolates FFC. Jitter alone leaves
    a ~0.12 degC bump in the filtered signal (a motion artifact, future work).
    """
    res = generate(SyntheticConfig(duration_s=420, seed=5, amplitude_c=0.0, head_jitter=False,
                                   ffc_interval_s=(60.0, 90.0), ffc_step_c=(0.3, 0.3)))
    assert res.truth.ffc_step_indices.size >= 3
    off = _spurious_peaks(res, ffc_handling=False)
    on = _spurious_peaks(res, ffc_handling=True)
    assert off >= 3, f"expected spurious peaks with handling off, got {off}"
    assert on == 0, f"expected none with handling on, got {on}"


def test_handling_on_recovers_the_clean_breathing_signal():
    base = dict(duration_s=420, seed=5, amplitude_c=0.7, ffc_interval_s=(60.0, 90.0),
                ffc_step_c=(0.3, 0.3), drift_c_per_min=0.5)
    clean = _run(generate(SyntheticConfig(**base, ffc=False)), ffc_handling=False)
    dirty = generate(SyntheticConfig(**base, ffc=True))
    on, off = _run(dirty, ffc_handling=True), _run(dirty, ffc_handling=False)
    ref = _inner(clean, clean.s_filt)
    rms = lambda o: np.sqrt(np.mean((_inner(o, o.s_filt) - ref) ** 2))
    assert rms(on) < 0.08
    assert rms(off) > 2 * rms(on)


def test_control_roi_has_no_breathing_peak_in_spectrum():
    res = generate(SyntheticConfig(duration_s=300, seed=3, ffc=False, amplitude_c=0.7, rate_bpm=15))
    out = _run(res)
    fs = 8.7
    def power_at(x, f0):
        x = _inner(out, x)
        spec = np.abs(np.fft.rfft(x * np.hanning(x.size))) ** 2
        freqs = np.fft.rfftfreq(x.size, 1 / fs)
        return spec[np.abs(freqs - f0) < 0.03].sum()
    assert power_at(out.s_filt, 0.25) > 50 * power_at(out.ctrl_filt, 0.25)


def test_ffc_mask_marks_repaired_samples():
    res = generate(SyntheticConfig(duration_s=400, seed=2, ffc_interval_s=(100.0, 150.0)))
    out = _run(res)
    assert out.ffc_mask.any() and out.ffc_step_times.size == res.truth.ffc_step_indices.size
    assert not _run(res, ffc_handling=False).ffc_mask.any()
