"""Phase 4b: incubator sensitivity sweep. MODEL PREDICTION, NOT A MEASUREMENT.

Sweeps the ambient (incubator) temperature in the synthetic model and records
how breathing amplitude, signal SNR, rate error and apnea detection respond.
The key model assumption (untested on hardware): the breathing swing scales
with (exhaled-air temperature - ambient), A = 0.07 * (34.5 - ambient) degC,
so it vanishes as the incubator approaches exhaled-air temperature.

Run from thermal/:  python scripts/sweep_ambient.py        (about 15 minutes)
"""

from __future__ import annotations

import gc
from pathlib import Path

import numpy as np

from thermal.apnea import ApneaConfig, detect_apnea
from thermal.config import ADULT, PipelineConfig
from thermal.metrics import mae, score_events, truth_on_grid, window_truth
from thermal.preprocess import process_frames
from thermal.rate import estimate_rates
from thermal.roi import ROI
from thermal.sources.synthetic import SyntheticConfig, generate

FS = 8.7
AMBIENTS = (22.0, 24.0, 26.0) + tuple(float(a) for a in range(27, 37))  # degC, 1 degC steps where it matters
SEEDS = tuple(range(8))
PAUSES = ((120.0, 25.0), (260.0, 25.0))  # 25 s: well above the 20 s rule (see Phase 4 notes)
RATE_BPM = 15.0
EDGE_S = 15.0
HERE = Path(__file__).resolve().parents[1] / "figures"

# "Usable" = every criterion below holds (averaged over seeds). Documented choices.
MIN_COVERAGE = 0.90  # fraction of windows that return a rate
MAX_RATE_MAE = 1.0  # breaths/min, time-domain estimator
MIN_APNEA_FOUND = 0.90  # fraction of pauses labeled apnea


def run_one(ambient_c: float, seed: int, head_jitter: bool = True) -> dict:
    """One synthetic recording at a given ambient temperature -> metrics dict."""
    res = generate(SyntheticConfig(duration_s=400, seed=seed, rate_bpm=RATE_BPM,
                                   ambient_c=ambient_c, apnea_events=PAUSES, head_jitter=head_jitter))
    tr = res.truth
    out = process_frames(res.frames, res.timestamps, ROI.from_box(tr.nostril_box),
                         ROI.from_box(tr.control_box), ROI.from_box(tr.reference_box),
                         PipelineConfig())
    est = estimate_rates(out.t, out.s_filt, FS, ADULT)
    ap = detect_apnea(out.t, out.s_filt, FS, ADULT, ApneaConfig())

    # steady windows that contain no injected pause (rate error is about breathing, not pauses)
    wt = window_truth(out.t, truth_on_grid(res.timestamps, tr.rate_bpm, out.t), est.t_end, est.window_s)
    in_pause = np.zeros(est.t_end.size, dtype=bool)
    for s, d in PAUSES:
        in_pause |= (est.t_end > s) & (est.t_end - est.window_s < s + d)
    steady = (est.t_end - est.window_s > EDGE_S) & (est.t_end < out.t[-1] - EDGE_S) & ~in_pause

    # breathing amplitude (RMS of the filtered signal) outside pauses
    m = np.ones(out.t.size, dtype=bool)
    for s, d in PAUSES:
        m &= ~((out.t > s - 5) & (out.t < s + d + 5))
    m &= (out.t > 30) & (out.t < out.t[-1] - 15)

    truth = [(s, s + d) for s, d in PAUSES]
    as_apnea = score_events(truth, [(e.start, e.end) for e in ap.events if e.kind == "apnea"])
    outside = [(e.start, e.end) for e in ap.events]
    any_ev = score_events(truth, outside)
    return {
        "ambient": ambient_c, "seed": seed, "head_jitter": head_jitter,
        "amp_design_c": tr.amplitude_c,
        "amp_rms_c": float(np.sqrt(np.mean(out.s_filt[m] ** 2))),
        "snr_db": float(np.nanmedian(est.snr_db[steady])),
        "quality": float(np.nanmedian(est.quality[steady])),
        "coverage": float(np.isfinite(est.spectral_bpm[steady]).mean()),
        "mae_spec": mae(est.spectral_bpm, wt, steady),
        "mae_time": mae(est.time_bpm, wt, steady),
        "apnea_found": 1.0 - as_apnea["missed"] / len(PAUSES) if len(PAUSES) else np.nan,
        "pauses_seen_any": 1.0 - any_ev["missed"] / len(PAUSES),
        "lost_frac": float(ap.signal_lost.mean()),
        "stray_events": any_ev["false_alarms"],
    }


def aggregate(rows: list[dict]) -> dict[float, dict]:
    """Average each metric over seeds, per ambient temperature (NaN-aware)."""
    out = {}
    for a in sorted({r["ambient"] for r in rows}):
        sel = [r for r in rows if r["ambient"] == a]
        out[a] = {k: float(np.nanmean([r[k] for r in sel])) if any(np.isfinite(r[k]) for r in sel)
                  else float("nan") for k in sel[0] if k not in ("ambient", "seed", "head_jitter")}
    return out


def usable(m: dict) -> bool:
    """All three criteria hold (NaN rate error counts as failing)."""
    return bool(m["coverage"] >= MIN_COVERAGE and np.isfinite(m["mae_time"])
                and m["mae_time"] <= MAX_RATE_MAE and m["apnea_found"] >= MIN_APNEA_FOUND)


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    aggs = {}
    for hj in (True, False):
        rows = []
        for a in AMBIENTS:
            for sd in SEEDS:
                rows.append(run_one(a, sd, head_jitter=hj))
                gc.collect()
            print(f"head_jitter={hj} ambient {a:.0f} done", flush=True)
        aggs[hj] = aggregate(rows)
    agg = aggs[True]
    amb = np.array(sorted(agg))
    col = lambda k, hj=True: np.array([aggs[hj][a][k] for a in amb])

    def limits(hj):
        ok_ = np.array([usable(aggs[hj][a]) for a in amb])
        bad = amb[~ok_]
        first_bad_ = bad.min() if bad.size else float("nan")
        good = amb[ok_ & (amb < first_bad_)] if bad.size else amb[ok_]
        return ok_, (good.max() if good.size else float("nan")), first_bad_

    ok, last_ok, first_bad = limits(True)
    ok_still, last_ok_still, first_bad_still = limits(False)

    fig, ax = plt.subplots(4, 1, figsize=(12, 13), sharex=True)
    fig.suptitle("Phase 4b: MODEL PREDICTION (synthetic, not measured): warm incubator vs thermal sensing\n"
                 "assumes breathing swing = 0.07 x (34.5 degC exhaled air - ambient); 8 seeds per point",
                 fontsize=12)
    ax[0].plot(amb, col("amp_design_c"), "k--", label="model swing A (semi-amplitude)")
    ax[0].plot(amb, col("amp_rms_c"), "o-", label="measured RMS of filtered signal")
    ax[0].axhline(0.05, color="gray", ls=":", label="'very low' floor (apnea detector)")
    ax[0].set_ylabel("degC"); ax[0].set_title("Breathing signal size shrinks linearly to zero at 34.5 degC")
    ax[1].plot(amb, col("snr_db"), "o-")
    ax[1].axhline(-3, color="gray", ls=":", label="quality 0 (noise level)")
    ax[1].axhline(15, color="green", ls=":", label="quality 1")
    ax[1].set_ylabel("dB"); ax[1].set_title("Spectral SNR of the breathing signal (median over windows)")
    ax[2].plot(amb, col("mae_time"), "s-", label="time-domain MAE (breaths/min)")
    ax[2].plot(amb, col("mae_spec"), "o-", label="spectral MAE (breaths/min)")
    ax2 = ax[2].twinx()
    ax2.plot(amb, col("coverage") * 100, "g^--", alpha=0.7, label="windows returning a rate (%)")
    ax2.set_ylabel("% of windows"); ax2.set_ylim(-5, 105)
    ax[2].set_ylabel("breaths/min"); ax[2].set_title("Rate estimation: error where it answers, and how often it answers")
    h1, l1 = ax[2].get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax[2].legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
    ax[3].plot(amb, col("apnea_found") * 100, "o-", label="25 s pauses labeled apnea (%), head moving")
    ax[3].plot(amb, col("apnea_found", False) * 100, "o--", color="C0", alpha=0.7,
               label="same, head perfectly still (head jitter off)")
    ax[3].plot(amb, col("lost_frac") * 100, "s-", color="C1", label="recording flagged signal_lost (%), head moving")
    ax[3].set_ylabel("%"); ax[3].set_xlabel("ambient / incubator temperature (degC)")
    ax[3].set_title("Apnea detection: pauses found vs 'cannot see breathing' flags")
    for a_ in ax:
        a_.axvline(34.5, color="red", ls="--", alpha=0.4)
        a_.grid(alpha=0.25)
        if not np.isnan(first_bad):
            a_.axvspan(first_bad - 0.5, amb.max() + 0.5, color="red", alpha=0.06)
    for a_ in (ax[0], ax[1], ax[3]):
        a_.legend(loc="best", fontsize=8)
    fig.tight_layout(); fig.savefig(HERE / "phase4b_ambient_sweep.png", dpi=105)

    L = ["# Phase 4b: incubator sensitivity sweep (MODEL PREDICTION, not a measurement)\n",
         "Synthetic recordings, 15 breaths/min, 400 s, two 25 s pauses, every nuisance on, 8 seeds per "
         "temperature. **Model assumption (unverified on hardware):** the breathing swing scales with "
         "(34.5 degC exhaled air - ambient), semi-amplitude A = 0.07 x (34.5 - ambient) degC. Pixel noise "
         "sigma = 0.05 degC, nostril ROI of 18 pixels.\n",
         f"Usable = rate answered in >= {MIN_COVERAGE:.0%} of windows AND time-domain MAE <= "
         f"{MAX_RATE_MAE} breaths/min AND >= {MIN_APNEA_FOUND:.0%} of pauses labeled apnea.\n",
         "| ambient degC | swing A | RMS | SNR dB | quality | rate answered | MAE time | MAE spectral | pauses labeled apnea | flagged signal_lost | usable |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a, k in zip(amb, ok):
        m = agg[a]
        L.append(f"| {a:.0f} | {m['amp_design_c']:.2f} | {m['amp_rms_c']:.2f} | {m['snr_db']:.1f} | "
                 f"{m['quality']:.2f} | {m['coverage'] * 100:.0f}% | {m['mae_time']:.2f} | {m['mae_spec']:.2f} | "
                 f"{m['apnea_found'] * 100:.0f}% | {m['lost_frac'] * 100:.0f}% | {'yes' if k else 'NO'} |")
    L += ["",
          "**Head perfectly still (head jitter off), same sweep:** pauses labeled apnea / usable:",
          "", "| ambient degC | pauses labeled apnea | rate answered | MAE time | usable |", "|---|---|---|---|---|"]
    for a, k in zip(amb, ok_still):
        m = aggs[False][a]
        L.append(f"| {a:.0f} | {m['apnea_found'] * 100:.0f}% | {m['coverage'] * 100:.0f}% | "
                 f"{m['mae_time']:.2f} | {'yes' if k else 'NO'} |")
    L += ["", "**Model predictions (1 degC grid, treat as what to measure on hardware, not as results):**",
          f"- Head moving (about 1 pixel shifts, as simulated): usable up to about {last_ok:.0f} degC, "
          f"broken from about {first_bad:.0f} degC.",
          f"- Head perfectly still: usable up to about {last_ok_still:.0f} degC, "
          f"broken from about {first_bad_still:.0f} degC.",
          "- Why head motion matters: each head shift leaves a bump of roughly 0.03 degC RMS in the "
          "envelope. The pause threshold is 0.25 x the breathing envelope, which falls from about 0.07 degC "
          "at 24 degC to about 0.017 at 32 degC, so the motion bumps eventually exceed it and chop pauses "
          "into pieces too short to flag. (Switching off FFC, drift or timestamp jitter changes nothing; "
          "switching off head jitter restores 100% at 30 and 32 degC.)",
          "- At 35-36 degC the swing is zero. With the head moving, about 7% of windows still return a rate "
          "(the quality gate leaks some noise windows) and those rates are wrong by about 6 breaths/min; with "
          "the head still, none do. 'Rate answered' must not be read as 'rate correct' when the signal is gone."]
    (HERE / "phase4b_report.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
