"""Run a scenario through the REAL pipeline and package every stage for the UI.

All data here is SIMULATED (``source.kind == "simulation"``). Results are cached
by parameter hash so the guided-tour story loads instantly and slider reruns of
a repeated setting are free.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from thermal.app.scenarios import ScenarioParams, choose_profile, to_apnea, to_synthetic
from thermal.config import PipelineConfig
from thermal.ffc import detect_ffc, repair_invalid
from thermal.metrics import mae, score_events, truth_on_grid, window_truth
from thermal.pipeline import PipelineOutput, run_pipeline
from thermal.quality import agreement_factor, quality_from_snr
from thermal.rate import estimate_rates, window_peaks, window_spectrum
from thermal.preprocess import resample_uniform
from thermal.roi import ROI, reduce_roi
from thermal.sources.synthetic import SyntheticSource

FRAME_ROWS, FRAME_COLS = 60, 80
EDGE_S = 15.0
CACHE_SIZE = 8
THERMAL_DIR = Path(__file__).resolve().parents[3]


def _list(a: np.ndarray, nd: int = 3) -> list:
    """JSON-safe list: rounded, NaN -> null."""
    return [None if not math.isfinite(x) else round(float(x), nd) for x in np.asarray(a, dtype=float).tolist()]


def _intervals(mask: np.ndarray, t: np.ndarray) -> list[list[float]]:
    edges = np.diff(np.concatenate(([0], mask.astype(int), [0])))
    return [[round(float(t[s]), 2), round(float(t[min(e, t.size) - 1]), 2)]
            for s, e in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))]


@dataclass
class Run:
    run_id: str
    params: ScenarioParams
    source: SyntheticSource
    output: PipelineOutput
    frames_i16: np.ndarray  # (T, 60, 80) centi-degC, little-endian int16
    payload: dict


class Service:
    """Builds and caches runs. Thread-safe (FastAPI runs sync endpoints in a thread pool)."""

    def __init__(self) -> None:
        self._runs: OrderedDict[str, Run] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                self._runs.move_to_end(run_id)
            return run

    def run(self, params: ScenarioParams) -> Run:
        run_id = hashlib.sha1(json.dumps(params.model_dump(), sort_keys=True).encode()).hexdigest()[:12]
        with self._lock:
            if run_id in self._runs:
                self._runs.move_to_end(run_id)
                return self._runs[run_id]
        run = self._build(run_id, params)
        with self._lock:
            self._runs[run_id] = run
            while len(self._runs) > CACHE_SIZE:
                self._runs.popitem(last=False)
        return run

    # ------------------------------------------------------------------ analysis for the Pipeline view
    def spectrum(self, run: Run, t0: float, t1: float) -> dict:
        """Amplitude spectrum (degC) of the signal before and after band-passing, over [t0, t1]."""
        sig, fs = run.output.signals, run.source.fs_nominal
        m = (sig.t >= t0) & (sig.t <= t1)
        if m.sum() < int(8 * fs):
            raise ValueError("Need at least 8 s of signal for a spectrum.")
        profile = choose_profile(run.params)[0]
        bpm = np.arange(0.0, 100.01, 0.25)
        out = {"bpm": bpm.tolist(), "band_bpm": [profile.band_hz[0] * 60, profile.band_hz[1] * 60], "window_s": round(t1 - t0, 1)}
        for name, x in (("clean", sig.s_clean[m]), ("filtered", sig.s_filt[m])):
            out[name] = _list(_amp_spectrum(x, fs, bpm), 4)
        return out

    def window(self, run: Run, t_end: float) -> dict:
        """What the rate estimator sees for the window ending at ``t_end``: signal, peaks, spectrum, rates, quality."""
        sig, est, fs = run.output.signals, run.output.rate, run.source.fs_nominal
        ws = est.window_s
        m = (sig.t > t_end - ws) & (sig.t <= t_end)
        if t_end < ws or m.sum() < int(0.9 * ws * fs):
            raise ValueError(f"The first reading needs a full {ws:.0f} s window.")
        profile = choose_profile(run.params)[0]
        seg, tt = sig.s_filt[m], sig.t[m]
        f, power, f_pk, snr = window_spectrum(seg, fs, profile.band_hz, ws)
        peaks, td = window_peaks(seg, fs, profile)
        sp = 60.0 * f_pk
        quality = quality_from_snr(snr) * agreement_factor(sp, td)
        bpm = np.arange(0.0, 100.01, 0.25)
        amp = np.interp(bpm, f * 60.0, 2.0 * np.sqrt(power) / np.hanning(seg.size).sum())
        ok = quality >= 0.5
        return {"t0": round(float(tt[0]), 2), "t1": round(float(tt[-1]), 2), "window_s": ws,
                "signal_t": _list(tt, 3), "signal": _list(seg, 3),
                "peaks_t": _list(tt[peaks], 2), "peaks_v": _list(seg[peaks], 3),
                "bpm": bpm.tolist(), "amp": _list(amp, 4), "band_bpm": [profile.band_hz[0] * 60, profile.band_hz[1] * 60],
                "peak_bpm": round(sp, 2), "snr_db": round(float(10 * np.log10(max(snr, 1e-12))), 1),
                "snr_halfwidth_bpm": round(max(0.03, 2.0 / ws) * 60, 2),
                "spectral_bpm": _num(sp), "time_bpm": _num(td), "quality": round(float(quality), 3),
                "shown_spectral": _num(sp) if ok else None, "shown_time": _num(td) if ok else None,
                "resolution_bpm": round(60.0 / ws, 2)}

    # ------------------------------------------------------------------ build
    def _build(self, run_id: str, p: ScenarioParams) -> Run:
        cfg = to_synthetic(p)
        profile, warning = choose_profile(p)
        src = SyntheticSource(cfg)
        tr = src.truth
        pcfg = PipelineConfig(profile=profile, fs_nominal=src.fs_nominal)
        acfg = to_apnea(p)
        out = run_pipeline(src, ROI.from_box(tr.nostril_box), ROI.from_box(tr.control_box),
                           ROI.from_box(tr.reference_box), pcfg, acfg)
        frames = np.round(src.result.frames.astype(np.float64) * 100.0).astype(np.int16)
        return Run(run_id, p, src, out, frames, self._payload(run_id, p, cfg, profile, warning, src, out, acfg))

    def _payload(self, run_id, p, cfg, profile, warning, src, out, acfg) -> dict:
        sig, est, ap, tr = out.signals, out.rate, out.apnea, src.truth
        ft = src.result.timestamps
        full = src.result.frames
        # colour ranges for the thermal view: whole scene, or zoomed to face temperatures
        face_lo, face_hi = cfg.nostril_baseline_c - 1.2, cfg.nostril_baseline_c + 1.2
        scene_lo, scene_hi = float(min(cfg.ambient_c, full.min())) - 0.3, float(cfg.skin_center_c) + 0.7
        ctrl = estimate_rates(sig.t, sig.ctrl_filt, cfg.fs_nominal, profile)
        steady = (est.t_end - est.window_s > EDGE_S) & (est.t_end < sig.t[-1] - EDGE_S)
        events = [{"start": round(e.start, 2), "end": round(e.end, 2), "kind": e.kind,
                   "declared_at": round(e.declared_at, 2)} for e in ap.events]
        pauses = [(s, s + d) for s, d in cfg.apnea_events]
        sc = score_events(pauses, [(e.start, e.end) for e in ap.events if e.kind == "apnea"])
        rate_wt = window_truth(sig.t, truth_on_grid(ft, tr.rate_bpm, sig.t), est.t_end, est.window_s)
        ok = steady.copy()
        for a, b in pauses:
            ok &= ~((est.t_end > a) & (est.t_end - est.window_s < b))
        for ts, _ in cfg.rate_steps:
            ok &= ~((est.t_end > ts) & (est.t_end - est.window_s < ts))
        sub = slice(None, None, 4)
        # extra stage data for the Pipeline view: reference ROI, the FFC-repaired signal (before background
        # subtraction), and which frames were frozen. Recomputed with the same functions the pipeline uses.
        pc = PipelineConfig(profile=profile, fs_nominal=cfg.fs_nominal)
        nos, ref = ROI.from_box(tr.nostril_box), ROI.from_box(tr.reference_box)
        det = detect_ffc(full, pc.frozen_tol_c, pc.step_min_c, pc.step_k)
        s_n, s_r = reduce_roi(full, nos, pc.reduction), reduce_roi(full, ref, "mean")
        rep_n, rep_r = (_fill(ft, repair_invalid(ft, x, det.frozen_mask, pc.max_gap_s)) for x in (s_n, s_r))
        _, ref_u = resample_uniform(ft, s_r, cfg.fs_nominal)
        _, rep_n_u = resample_uniform(ft, rep_n, cfg.fs_nominal)
        _, rep_r_u = resample_uniform(ft, rep_r, cfg.fs_nominal)
        return {
            "run_id": run_id,
            "source": {"kind": "simulation", "label": "SIMULATED DATA"},
            "params": p.model_dump(),
            "meta": {
                "fs": cfg.fs_nominal, "n_frames": int(ft.size), "duration_s": float(ft[-1]),
                "frame_shape": [FRAME_ROWS, FRAME_COLS], "profile": profile.name,
                "band_hz": list(profile.band_hz), "window_s": est.window_s, "profile_warning": warning,
                "temp_range": {"face": [round(face_lo, 2), round(face_hi, 2)],
                               "scene": [round(scene_lo, 2), round(scene_hi, 2)]},
                "min_quality": 0.5, "k": acfg.k, "min_pause_s": acfg.min_duration_s,
                "abs_floor_c": acfg.abs_floor_c, "envelope_window_s": acfg.envelope_window_s,
            },
            "frame_times": _list(ft, 3),
            "rois": {"nostril": list(tr.nostril_box), "control": list(tr.control_box),
                     "reference": list(tr.reference_box)},
            "grid_t": _list(sig.t, 3),
            "stages": {
                "raw": {"nostril": _list(sig.s_raw), "control": _list(sig.ctrl_raw), "reference": _list(ref_u)},
                "repaired": {"nostril": _list(rep_n_u), "reference": _list(rep_r_u)},
                "ffc": {"step_times": _list(sig.ffc_step_times, 2),  # detected by the pipeline
                        "step_sizes": _list(det.step_sizes, 3), "frozen_times": _list(ft[det.frozen_mask], 2),
                        "repaired": _intervals(sig.ffc_mask, sig.t)},  # samples it repaired
                "clean": _list(sig.s_clean),
                "filtered": {"nostril": _list(sig.s_filt), "control": _list(sig.ctrl_filt)},
                "rate": {"t_end": _list(est.t_end, 2), "spectral": _list(est.spectral_bpm, 2),
                         "time": _list(est.time_bpm, 2), "quality": _list(est.quality, 3),
                         "snr_db": _list(est.snr_db if est.snr_db is not None else np.full(est.t_end.size, np.nan), 1)},
                "apnea": {"envelope": _list(ap.envelope), "baseline": _list(ap.baseline),
                          "threshold": _list(acfg.k * ap.baseline), "events": events},
                "control_rate": {"coverage": _coverage(ctrl.spectral_bpm, steady),
                                 "quality_median": _median(ctrl.quality, steady),
                                 "nostril_coverage": _coverage(est.spectral_bpm, steady),
                                 "nostril_quality_median": _median(est.quality, steady),
                                 "t_end": _list(ctrl.t_end, 2), "quality": _list(ctrl.quality, 3)},
            },
            "truth": {"label": "simulation ground truth",
                      "rate": {"t": _list(ft[sub], 2), "bpm": _list(tr.rate_bpm[sub], 2)},
                      "pauses": [[round(a, 2), round(b, 2)] for a, b in pauses],
                      "ffc_step_times": _list(ft[tr.ffc_step_indices], 2),
                      "breath_swing_c": round(float(tr.amplitude_c), 3), "ambient_c": cfg.ambient_c},
            "summary": {
                "pauses_injected": len(pauses), "pauses_found": len(pauses) - sc["missed"],
                "false_events": score_events(pauses, [(e.start, e.end) for e in ap.events])["false_alarms"],
                "start_err_s": [round(x, 1) for x in sc["start_err"]], "end_err_s": [round(x, 1) for x in sc["end_err"]],
                "rate_mae_time": _num(mae(est.time_bpm, rate_wt, ok)), "rate_mae_spectral": _num(mae(est.spectral_bpm, rate_wt, ok)),
                "rate_answered": _coverage(est.time_bpm, ok), "signal_lost_fraction": round(float(ap.signal_lost.mean()), 3),
                "ffc_injected": int(tr.ffc_step_indices.size), "ffc_detected": int(sig.ffc_step_times.size),
            },
        }


def _fill(t: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Linear-fill any NaN left by a too-long gap (same last-resort fill the pipeline uses)."""
    bad = np.isnan(x)
    if bad.any() and not bad.all():
        x = x.copy(); x[bad] = np.interp(t[bad], t[~bad], x[~bad])
    return x


def _amp_spectrum(x: np.ndarray, fs: float, bpm: np.ndarray) -> np.ndarray:
    """Amplitude (degC) of the sinusoid at each rate in ``bpm``: Hann window, zero padded, mean removed."""
    w = np.hanning(x.size)
    nfft = int(2 ** np.ceil(np.log2(x.size * 8)))
    amp = 2.0 * np.abs(np.fft.rfft((x - x.mean()) * w, nfft)) / w.sum()
    return np.interp(bpm, np.fft.rfftfreq(nfft, 1.0 / fs) * 60.0, amp)


def _num(x: float) -> float | None:
    return None if not math.isfinite(x) else round(float(x), 3)


def _coverage(x: np.ndarray, mask: np.ndarray) -> float | None:
    return round(float(np.isfinite(x[mask]).mean()), 3) if mask.any() else None


def _median(x: np.ndarray, mask: np.ndarray) -> float | None:
    return _num(float(np.nanmedian(x[mask]))) if mask.any() else None
