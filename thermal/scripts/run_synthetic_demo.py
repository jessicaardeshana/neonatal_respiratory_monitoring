"""Phase 6: end-to-end SYNTHETIC demo. One command reproduces everything.

    python scripts/run_synthetic_demo.py            # from the thermal/ folder (about 2 minutes)
    python scripts/run_synthetic_demo.py --quick    # demo scenario only, skips the acceptance sweeps

Produces (all SYNTHETIC: simulated, not measured):
    figures/demo_summary.png     raw signal, filtered signal, estimated vs true rate,
                                 apnea flags vs truth, control ROI
    figures/demo_report.md       numbers behind the figure + Section 9 acceptance checklist
    data/demo_processed.npz      Section 7 processed-output file for teammates (gitignored)

Everything is seeded: running it twice gives identical numbers.
"""

from __future__ import annotations

import argparse
import gc
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from thermal.apnea import ApneaConfig  # noqa: E402
from thermal.config import ADULT, NEONATE, PipelineConfig, Profile  # noqa: E402
from thermal.metrics import (coverage, mae, score_events, step_lag,  # noqa: E402
                             truth_on_grid, window_truth)
from thermal.pipeline import PipelineOutput, run_pipeline, save_processed  # noqa: E402
from thermal.rate import estimate_rates  # noqa: E402
from thermal.roi import ROI  # noqa: E402
from thermal.sources.synthetic import SyntheticConfig, SyntheticSource  # noqa: E402

THERMAL = Path(__file__).resolve().parents[1]
EDGE_S = 15.0  # ignore filter-edge ringing at both ends of a recording

# The demo scenario: breathing speeds up from 12 to 22 breaths/min at 220 s, two 25 s pauses,
# every nuisance on (noise, drift, head jitter, FFC, timestamp jitter, dropped frames).
DEMO_CFG = SyntheticConfig(duration_s=420.0, seed=11, rate_bpm=12.0, rate_steps=((220.0, 22.0),),
                           apnea_events=((100.0, 25.0), (320.0, 25.0)))
STEP_T, STEP_BPM = 220.0, 22.0


def run_scenario(cfg: SyntheticConfig, profile: Profile = ADULT) -> tuple[SyntheticSource, PipelineOutput]:
    """Simulate, then run the full pipeline through the source-agnostic runner."""
    src = SyntheticSource(cfg)
    tr = src.truth
    pcfg = PipelineConfig(profile=profile, fs_nominal=src.fs_nominal)
    out = run_pipeline(src, ROI.from_box(tr.nostril_box), ROI.from_box(tr.control_box),
                       ROI.from_box(tr.reference_box), pcfg, ApneaConfig())
    return src, out


def rate_errors(src: SyntheticSource, out: PipelineOutput, avoid: list[tuple[float, float]]):
    """(window truth, steady-window mask) for rate scoring; windows overlapping ``avoid`` spans are skipped."""
    sig, est = out.signals, out.rate
    wt = window_truth(sig.t, truth_on_grid(src.result.timestamps, src.truth.rate_bpm, sig.t),
                      est.t_end, est.window_s)
    steady = (est.t_end - est.window_s > EDGE_S) & (est.t_end < sig.t[-1] - EDGE_S)
    for a, b in avoid:
        steady &= ~((est.t_end > a) & (est.t_end - est.window_s < b))
    return wt, steady


def pause_windows(cfg: SyntheticConfig) -> list[tuple[float, float]]:
    return [(s, s + d) for s, d in cfg.apnea_events]


# ---------------------------------------------------------------- demo scenario metrics
def demo_metrics(src: SyntheticSource, out: PipelineOutput) -> dict:
    cfg, est, sig = src.cfg, out.rate, out.signals
    pauses = pause_windows(cfg)
    wt, steady = rate_errors(src, out, pauses + [(STEP_T, STEP_T + est.window_s)])
    sc = score_events(pauses, [(e.start, e.end) for e in out.apnea.events if e.kind == "apnea"])
    any_ev = score_events(pauses, [(e.start, e.end) for e in out.apnea.events])
    ctrl = estimate_rates(sig.t, sig.ctrl_filt, cfg.fs_nominal, ADULT)
    steady_all = (est.t_end - est.window_s > EDGE_S) & (est.t_end < sig.t[-1] - EDGE_S)
    true_steps = src.result.timestamps[src.truth.ffc_step_indices]
    det_steps = sig.ffc_step_times
    matched = sum(bool(np.any(np.abs(det_steps - t) < 0.5)) for t in true_steps)
    return {
        "mae_spec": mae(est.spectral_bpm, wt, steady), "mae_time": mae(est.time_bpm, wt, steady),
        "lag_spec": step_lag(est.t_end, est.spectral_bpm, STEP_T, STEP_BPM),
        "lag_time": step_lag(est.t_end, est.time_bpm, STEP_T, STEP_BPM),
        "start_err": sc["start_err"], "end_err": sc["end_err"], "missed": sc["missed"],
        "false_alarms": any_ev["false_alarms"], "fragments": sc["fragments"],
        "ffc_true": len(true_steps), "ffc_found": matched, "ffc_extra": len(det_steps) - matched,
        "ctrl_cov": coverage(ctrl.spectral_bpm, steady_all), "nos_cov": coverage(est.spectral_bpm, steady_all),
        "ctrl_q": float(np.nanmedian(ctrl.quality[steady_all])), "nos_q": float(np.nanmedian(est.quality[steady_all])),
        "ctrl": ctrl,
    }


# ---------------------------------------------------------------- Section 9 acceptance sweeps
def acceptance() -> dict:
    """Quick re-check of the spec's Section 9 criteria on fresh synthetic recordings."""
    rate_rows, false_events = [], 0
    for prof, rates, tol in ((ADULT, (10, 20, 30), 1.0), (NEONATE, (40, 60, 80), 2.0)):
        for bpm in rates:
            sp, td, within = [], [], []
            for seed in range(3):
                src, out = run_scenario(SyntheticConfig(duration_s=200.0, seed=seed, rate_bpm=float(bpm)), prof)
                wt, st = rate_errors(src, out, [])
                sp.append(mae(out.rate.spectral_bpm, wt, st)); td.append(mae(out.rate.time_bpm, wt, st))
                ok = np.isfinite(out.rate.spectral_bpm) & st
                within.append(float((np.abs(out.rate.spectral_bpm - wt)[ok] <= tol).mean()))
                false_events += len(out.apnea.events)
                del src, out; gc.collect()
            rate_rows.append((prof.name, bpm, tol, float(np.mean(sp)), float(np.mean(td)), float(np.mean(within))))
    n = found = 0
    s_err, e_err = [], []
    for bpm in (10, 20, 30):
        for seed in range(5):
            ev = ((120.0, 20.0), (230.0, 20.0))
            cfg = SyntheticConfig(duration_s=330.0, seed=seed, rate_bpm=float(bpm), apnea_events=ev)
            src, out = run_scenario(cfg)
            sc = score_events(pause_windows(cfg), [(e.start, e.end) for e in out.apnea.events if e.kind == "apnea"])
            n += len(ev); found += len(ev) - sc["missed"]
            s_err += sc["start_err"]; e_err += sc["end_err"]
            false_events += score_events(pause_windows(cfg), [(e.start, e.end) for e in out.apnea.events])["false_alarms"]
            del src, out; gc.collect()
    return {"rate_rows": rate_rows, "pauses_n": n, "pauses_found": found,
            "start_worst": float(np.max(np.abs(s_err))), "end_worst": float(np.max(np.abs(e_err))),
            "false_events": false_events}


# ---------------------------------------------------------------- figure + report
def make_figure(src: SyntheticSource, out: PipelineOutput, m: dict, path: Path) -> None:
    cfg, sig, est, ap, tr = src.cfg, out.signals, out.rate, out.apnea, src.truth
    pauses = pause_windows(cfg)
    fig, ax = plt.subplots(5, 1, figsize=(13, 17), sharex=True)
    fig.suptitle("Phase 6: SYNTHETIC end-to-end demo (simulated, not measured)\n"
                 "12 -> 22 breaths/min at 220 s, two 25 s pauses, all nuisances on", fontsize=13)

    ax[0].plot(sig.t, sig.s_raw, lw=0.8)
    for k, ts in enumerate(sig.ffc_step_times):
        ax[0].axvline(ts, color="red", ls="--", alpha=0.6, label="detected FFC step" if k == 0 else None)
    ax[0].set_title("1. Raw nostril ROI signal (breathing + drift + FFC steps)")
    ax[0].set_ylabel("degC"); ax[0].legend(loc="upper right", fontsize=8)

    ax[1].plot(sig.t, sig.s_filt, lw=0.8)
    for k, (a, b) in enumerate(pauses):
        ax[1].axvspan(a, b, color="red", alpha=0.15, label="true pause" if k == 0 else None)
    ax[1].set_title("2. Filtered breathing signal (FFC repaired, drift removed, band-passed)")
    ax[1].set_ylabel("degC"); ax[1].legend(loc="upper right", fontsize=8)

    ax[2].plot(src.result.timestamps, tr.rate_bpm, "k", lw=2, label="true rate")
    ax[2].plot(est.t_end, est.spectral_bpm, "o-", ms=3, label="spectral estimate")
    ax[2].plot(est.t_end, est.time_bpm, "s-", ms=3, label="time-domain estimate")
    ax[2].axvline(STEP_T, color="gray", ls=":")
    ax[2].set_title(f"3. Estimated vs true rate (30 s windows; NaN where quality < 0.5). Step lag: spectral "
                    f"{m['lag_spec']:.0f} s, time-domain {m['lag_time']:.0f} s")
    ax[2].set_ylabel("breaths/min"); ax[2].legend(loc="upper left", fontsize=8)

    ax[3].plot(ap.t, ap.envelope, label="envelope (RMS)")
    ax[3].plot(ap.t, ap.baseline, label="baseline")
    ax[3].plot(ap.t, 0.25 * ap.baseline, ":", label="threshold = 0.25 x baseline")
    for k, (a, b) in enumerate(pauses):
        ax[3].axvspan(a, b, color="red", alpha=0.15, label="true pause" if k == 0 else None)
    for k, e in enumerate(ap.events):
        ax[3].axvspan(e.start, e.end, ymin=0, ymax=0.08, color="blue", alpha=0.8,
                      label=f"detected ({e.kind})" if k == 0 else None)
    ax[3].set_title("4. Apnea flags vs truth: detected pauses (blue bars) against injected pauses (red)")
    ax[3].set_ylabel("degC RMS"); ax[3].legend(loc="upper right", fontsize=8)

    ax[4].plot(sig.t, sig.s_filt, color="lightgray", lw=0.8, label="nostril ROI (filtered)")
    ax[4].plot(sig.t, sig.ctrl_filt, color="C1", lw=1, label="control ROI, cheek (filtered)")
    ax[4].set_title(f"5. Control ROI (artifact check): no breathing peak. Passes the rate-quality gate in "
                    f"{m['ctrl_cov'] * 100:.0f}% of windows vs {m['nos_cov'] * 100:.0f}% for the nostril ROI")
    ax[4].set_ylabel("degC"); ax[4].set_xlabel("time (s)"); ax[4].legend(loc="upper right", fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.96)); fig.savefig(path, dpi=80); plt.close(fig)


def _status(ok: bool) -> str:
    return "PASS" if ok else "NOT MET"


def write_report(src: SyntheticSource, m: dict, acc: dict | None, path: Path) -> None:
    pause_lines = "; ".join(f"pause {i + 1}: start {s:+.1f} s, end {e:+.1f} s"
                            for i, (s, e) in enumerate(zip(m["start_err"], m["end_err"])))
    L = ["# Phase 6 demo report (ALL SYNTHETIC: simulated, not measured)\n",
         "Reproduce: `python scripts/run_synthetic_demo.py` from `thermal/`. Everything is seeded, so "
         "re-running gives identical numbers. Figure: `figures/demo_summary.png`.\n",
         "## Scenario\n",
         "Adult profile, 420 s, seed 11. Breathing 12 breaths/min, stepping to 22 at 220 s. Two injected "
         "25 s pauses (100 s and 320 s). Every nuisance on: pixel noise, drift, head jitter, FFC events, "
         "timestamp jitter, dropped frames, 5% breath-to-breath rate wander.\n",
         "## Results on the demo recording\n",
         f"- **Rate error** (30 s windows, pauses and the step excluded): spectral MAE {m['mae_spec']:.2f}, "
         f"time-domain MAE {m['mae_time']:.2f} breaths/min.",
         f"- **Rate step lag** (time until the estimate holds within 1.5 breaths/min of 22): spectral "
         f"{m['lag_spec']:.0f} s, time-domain {m['lag_time']:.0f} s (window length 30 s).",
         f"- **Pauses:** {2 - m['missed']} of 2 detected as apnea ({pause_lines}). False alarms: "
         f"{m['false_alarms']}. Fragments: {m['fragments']}.",
         f"- **FFC:** {m['ffc_found']} of {m['ffc_true']} injected level steps detected, {m['ffc_extra']} extra.",
         f"- **Control ROI:** passes the quality gate in {m['ctrl_cov'] * 100:.0f}% of windows (nostril: "
         f"{m['nos_cov'] * 100:.0f}%); median quality {m['ctrl_q']:.2f} vs {m['nos_q']:.2f}.\n"]
    if acc is not None:
        L += ["## Section 9 acceptance checklist (fresh synthetic recordings)\n",
              "| criterion | result | status |", "|---|---|---|"]
        tol_ok = []
        for name, bpm, tol, sp, td, wi in acc["rate_rows"]:
            ok = sp <= tol and td <= tol
            tol_ok.append(ok)
            L.append(f"| {name} {bpm} breaths/min within +-{tol:.0f} (mean error, 3 seeds, 200 s) | spectral "
                     f"{sp:.2f}, time-domain {td:.2f}; {wi * 100:.0f}% of spectral windows within +-{tol:.0f} "
                     f"| {_status(ok)} |")
        n, f = acc["pauses_n"], acc["pauses_found"]
        L.append(f"| 20 s pauses detected, start/end within ~5 s (3 rates x 5 seeds) | {f} of {n} detected; "
                 f"worst start error {acc['start_worst']:.1f} s, worst end error {acc['end_worst']:.1f} s "
                 f"| {_status(f == n and max(acc['start_worst'], acc['end_worst']) <= 5.0)} |")
        L.append(f"| Control ROI shows no breathing peak | gate passed in {m['ctrl_cov'] * 100:.0f}% of windows "
                 f"(nostril {m['nos_cov'] * 100:.0f}%) | {_status(m['ctrl_cov'] < 0.2)} |")
        L.append(f"| FFC does not create false breaths or false apnea | {acc['false_events']} spurious apnea/"
                 f"signal_lost events over every acceptance run | {_status(acc['false_events'] == 0)} |")
        L.append("| All tests pass | run `python -m pytest` (not checked by this script) | n/a |")
        L += ["", "Reading the table: \"NOT MET\" means the strict spec wording is not satisfied, even when the "
              "numbers are close. See the Phase 3 and Phase 4 entries in `THERMAL_SPEC.md` for why (simulated "
              "5% rate wander makes a window's true rate ambiguous; a 20 s pause sits right on the "
              "detector's 20 s minimum, so a few are missed).\n"]
    L += ["## Files",
          "- `figures/demo_summary.png`: the five-panel figure.",
          "- `data/demo_processed.npz` (gitignored): Section 7 processed output on one uniform time grid: "
          "`t, s_raw, s_ctrl, s_filt, envelope, rate_bpm, quality, apnea, ffc_mask` plus `signal_lost` and a "
          "JSON `meta`. Read it with `thermal.pipeline.load_processed`. `rate_bpm` is the time-domain "
          "estimate held causally per sample (NaN when quality is low).\n",
          "## Not covered (honest limits)",
          "All numbers are from a model, not a camera. Head motion is modeled only as +-1 pixel shifts; "
          "the Lepton read path is untested on hardware; a warm incubator degrades apnea detection "
          "(Phase 4b)."]
    path.write_text("\n".join(L) + "\n")


def main(out_dir: Path | None = None, data_dir: Path | None = None, quick: bool = False) -> dict:
    out_dir = Path(out_dir) if out_dir else THERMAL / "figures"
    data_dir = Path(data_dir) if data_dir else THERMAL / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    src, out = run_scenario(DEMO_CFG)
    m = demo_metrics(src, out)
    tr = src.truth
    meta = {"profile": ADULT.name, "band_hz": list(ADULT.band_hz), "fs_nominal": src.fs_nominal,
            "source": "SyntheticSource", "synthetic": True,
            "rois": {"nostril": list(tr.nostril_box), "control": list(tr.control_box),
                     "reference": list(tr.reference_box)},
            "scenario": {"seed": DEMO_CFG.seed, "rate_bpm": DEMO_CFG.rate_bpm,
                         "rate_steps": DEMO_CFG.rate_steps, "apnea_events": DEMO_CFG.apnea_events}}
    npz = save_processed(data_dir / "demo_processed.npz", out, meta)
    make_figure(src, out, m, out_dir / "demo_summary.png")
    acc = None if quick else acceptance()
    write_report(src, m, acc, out_dir / "demo_report.md")
    print((out_dir / "demo_report.md").read_text())
    print(f"wrote {out_dir / 'demo_summary.png'}\nwrote {out_dir / 'demo_report.md'}\nwrote {npz}")
    return {"metrics": m, "acceptance": acc, "npz": npz}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="demo scenario only; skip the acceptance sweeps")
    main(quick=ap.parse_args().quick)
