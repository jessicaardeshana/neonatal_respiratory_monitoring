"""Phase 3 accuracy study + figure + markdown report (ALL SYNTHETIC).

Run from thermal/:  python scripts/phase3_report.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from thermal.config import ADULT, NEONATE, PipelineConfig  # noqa: E402
from thermal.metrics import (coverage, mae, step_lag, truth_on_grid,  # noqa: E402
                             window_truth)
from thermal.preprocess import process_frames  # noqa: E402
from thermal.rate import estimate_rates  # noqa: E402
from thermal.roi import ROI  # noqa: E402
from thermal.sources.synthetic import SyntheticConfig, generate  # noqa: E402

FS, SEEDS, EDGE = 8.7, range(5), 15.0
HERE = Path(__file__).resolve().parents[1] / "figures"


def run(res, profile, reduction="mean"):
    tr = res.truth
    cfg = PipelineConfig(profile=profile, reduction=reduction)
    out = process_frames(res.frames, res.timestamps, ROI.from_box(tr.nostril_box),
                         ROI.from_box(tr.control_box), ROI.from_box(tr.reference_box), cfg)
    est = estimate_rates(out.t, out.s_filt, FS, profile)
    ctl = estimate_rates(out.t, out.ctrl_filt, FS, profile)
    wt = window_truth(out.t, truth_on_grid(res.timestamps, tr.rate_bpm, out.t), est.t_end, est.window_s)
    steady = (est.t_end - est.window_s > EDGE) & (est.t_end < out.t[-1] - EDGE)
    return out, est, ctl, wt, steady


rows = []
for prof, rates in ((ADULT, (10, 20, 30)), (NEONATE, (40, 60, 80))):
    for bpm in rates:
        for red in ("mean", "max"):
            sp, td, w1, cov = [], [], [], []
            for seed in SEEDS:
                res = generate(SyntheticConfig(duration_s=240, seed=seed, rate_bpm=bpm))
                _, est, _, wt, st = run(res, prof, red)
                sp.append(mae(est.spectral_bpm, wt, st))
                td.append(mae(est.time_bpm, wt, st))
                ok = np.isfinite(est.spectral_bpm) & st
                w1.append((np.abs(est.spectral_bpm - wt)[ok] <= 1.0).mean() if ok.any() else np.nan)
                cov.append(coverage(est.spectral_bpm, st))
            rows.append((prof.name, bpm, red, np.nanmean(sp), np.nanmean(td), np.nanmean(w1), np.nanmean(cov)))

# step-change scenario (adult, 10 -> 25 breaths/min at 150 s)
step_res = generate(SyntheticConfig(duration_s=300, seed=3, rate_bpm=10.0, rate_steps=((150.0, 25.0),)))
out, est, ctl, wt, st = run(step_res, ADULT)
lag_sp = step_lag(est.t_end, est.spectral_bpm, 150.0, 25.0)
lag_td = step_lag(est.t_end, est.time_bpm, 150.0, 25.0)
ctl_cov = coverage(ctl.spectral_bpm, st)

fig, ax = plt.subplots(3, 1, figsize=(12, 10))
fig.suptitle("Phase 3: SYNTHETIC rate estimation (simulated, not measured)", fontsize=13)
tt = step_res.timestamps
ax[0].plot(tt, step_res.truth.rate_bpm, "k", lw=2, label="true rate")
ax[0].plot(est.t_end, est.spectral_bpm, "o-", ms=3, label="spectral")
ax[0].plot(est.t_end, est.time_bpm, "s-", ms=3, label="time-domain")
ax[0].axvline(150, color="red", ls="--", alpha=0.5)
ax[0].set_title(f"Step 10 -> 25 breaths/min at 150 s (red). Lag to settle within 1.5: "
                f"spectral {lag_sp:.0f} s, time-domain {lag_td:.0f} s (window = 30 s)")
ax[0].set_ylabel("breaths/min"); ax[0].legend()
ax[1].plot(est.t_end, est.quality, label="nostril ROI")
ax[1].plot(ctl.t_end, ctl.quality, label="control ROI (cheek)")
ax[1].axhline(0.5, color="gray", ls=":", label="min quality 0.5")
ax[1].set_title(f"Signal quality: control ROI passes the gate in {ctl_cov * 100:.0f}% of steady windows")
ax[1].set_ylabel("quality 0-1"); ax[1].set_xlabel("time (s)"); ax[1].legend()
mean_rows = [r for r in rows if r[2] == "mean"]
x = np.arange(len(mean_rows)); w = 0.38
ax[2].bar(x - w / 2, [r[3] for r in mean_rows], w, label="spectral")
ax[2].bar(x + w / 2, [r[4] for r in mean_rows], w, label="time-domain")
ax[2].set_xticks(x, [f"{r[0]} {r[1]}" for r in mean_rows])
ax[2].set_ylabel("MAE (breaths/min)")
ax[2].set_title("Mean absolute error by true rate (mean-ROI, 5 seeds, all nuisances on)")
ax[2].legend()
fig.tight_layout(); fig.savefig(HERE / "phase3_rate.png", dpi=105)

lines = ["# Phase 3 results (ALL SYNTHETIC: simulated, not measured)\n",
         "5 seeds per row, 240 s, all nuisances on (noise, drift, head jitter, FFC, timestamp "
         "jitter, dropped frames, 5% rate wander). Windows overlapping the first/last 15 s "
         "(filter edges) are skipped. Truth = mean true rate over each window.\n",
         "| profile | true bpm | reduction | spectral MAE | time-domain MAE | spectral within +/-1 | coverage |",
         "|---|---|---|---|---|---|---|"]
lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]:.2f} | {r[4]:.2f} | {r[5] * 100:.0f}% | {r[6] * 100:.0f}% |"
          for r in rows]
lines += ["", f"Step 10 -> 25 bpm at 150 s: lag to settle within 1.5 bpm = spectral {lag_sp:.0f} s, "
          f"time-domain {lag_td:.0f} s (window length 30 s).",
          f"Control ROI passes the quality gate in {ctl_cov * 100:.0f}% of steady windows (nostril: "
          f"{coverage(est.spectral_bpm, st) * 100:.0f}%)."]
(HERE / "phase3_report.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
