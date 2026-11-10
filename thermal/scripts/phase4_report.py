"""Phase 4 apnea-detector study + figure + markdown report (ALL SYNTHETIC).

Run from thermal/:  python scripts/phase4_report.py   (takes about 2 minutes)
"""

import gc
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from thermal.apnea import ApneaConfig, detect_apnea  # noqa: E402
from thermal.config import ADULT, PipelineConfig  # noqa: E402
from thermal.metrics import score_events  # noqa: E402
from thermal.preprocess import process_frames  # noqa: E402
from thermal.roi import ROI  # noqa: E402
from thermal.sources.synthetic import SyntheticConfig, generate  # noqa: E402

FS = 8.7
HERE = Path(__file__).resolve().parents[1] / "figures"


def run(res, acfg=None):
    tr = res.truth
    out = process_frames(res.frames, res.timestamps, ROI.from_box(tr.nostril_box),
                         ROI.from_box(tr.control_box), ROI.from_box(tr.reference_box), PipelineConfig())
    return out, detect_apnea(out.t, out.s_filt, FS, ADULT, acfg)


def pause_study(dur_s, min_dur, causal):
    se, ee, missed, fa, frag, n = [], [], 0, 0, 0, 0
    for bpm in (10, 20, 30):
        for seed in range(5):
            ev = ((120.0, dur_s), (260.0, dur_s))
            res = generate(SyntheticConfig(duration_s=400, seed=seed, rate_bpm=bpm, apnea_events=ev))
            _, r = run(res, ApneaConfig(min_duration_s=min_dur, causal=causal))
            sc = score_events([(s, s + d) for s, d in ev], [(e.start, e.end) for e in r.events])
            se += sc["start_err"]; ee += sc["end_err"]
            missed += sc["missed"]; fa += sc["false_alarms"]; frag += sc["fragments"]; n += len(ev)
            del res, r; gc.collect()
    se, ee = np.array(se), np.array(ee)
    return (f"| {dur_s:.0f} s pauses, min {min_dur:.0f} s, {'causal' if causal else 'centered'} | {n} | "
            f"{n - missed} | {se.mean():+.1f} / {np.abs(se).max():.1f} | {ee.mean():+.1f} / {np.abs(ee).max():.1f} | "
            f"{fa} | {frag} |")


rows = [pause_study(20, 20, True), pause_study(20, 20, False), pause_study(25, 20, True),
        pause_study(10, 10, True)]

# false alarms: long clean runs with every nuisance on
fa_total, minutes, fa_lines = 0, 0, []
for bpm in (10, 15, 20, 30):
    for seed in range(3):
        res = generate(SyntheticConfig(duration_s=900, seed=seed, rate_bpm=bpm))
        _, r = run(res)
        fa_total += len(r.events); minutes += 15
        fa_lines += [f"rate {bpm} seed {seed}: {e.kind} {e.start:.0f}-{e.end:.0f} s" for e in r.events]
        del res, r; gc.collect()

# demo recordings for the figure
ev = ((120.0, 20.0), (260.0, 20.0))
d_res = generate(SyntheticConfig(duration_s=400, seed=1, rate_bpm=15.0, apnea_events=ev))
d_out, d_r = run(d_res)
l_res = generate(SyntheticConfig(duration_s=250, seed=1, amplitude_c=0.0))
l_out, l_r = run(l_res)
h_res = generate(SyntheticConfig(duration_s=250, seed=1, ambient_c=34.0))
h_out, h_r = run(h_res)
cfg = ApneaConfig()

fig, ax = plt.subplots(4, 1, figsize=(13, 13))
fig.suptitle("Phase 4: SYNTHETIC apnea detection (simulated, not measured)", fontsize=13)
ax[0].plot(d_out.t, d_out.s_filt, lw=0.8)
for s, d in ev:
    ax[0].axvspan(s, s + d, color="red", alpha=0.15, label="true pause" if s == ev[0][0] else None)
for i, e in enumerate(d_r.events):
    ax[0].axvspan(e.start, e.end, ymin=0, ymax=0.12, color="blue", alpha=0.7, label="detected" if i == 0 else None)
    ax[0].axvline(e.declared_at, color="green", ls="--", label="earliest alarm" if i == 0 else None)
ax[0].set_title("(a) 20 s pauses at 15 breaths/min: breathing signal, true pauses (red), detections (blue bars)")
ax[0].set_ylabel("degC"); ax[0].legend(loc="upper right", fontsize=8)
ax[1].plot(d_r.t, d_r.envelope, label="envelope (RMS, causal 4 s)")
ax[1].plot(d_r.t, d_r.baseline, label="baseline (rolling median, frozen in pauses)")
ax[1].plot(d_r.t, cfg.k * d_r.baseline, ":", label="threshold = 0.25 x baseline")
for s, d in ev:
    ax[1].axvspan(s, s + d, color="red", alpha=0.15)
ax[1].set_title("(b) Why it works: the envelope falls below the threshold during each pause")
ax[1].set_ylabel("degC RMS"); ax[1].legend(loc="upper right", fontsize=8)
ax[2].plot(l_r.t, l_r.envelope, label="envelope")
ax[2].axhline(cfg.abs_floor_c, color="gray", ls=":", label="'very low' floor 0.05 degC")
for i, e in enumerate(l_r.events):
    ax[2].axvspan(e.start, e.end, color="orange", alpha=0.3, label="signal_lost" if i == 0 else None)
ax[2].set_title("(c) NO visible breathing at all (face out of view / signal erased): labeled signal_lost, not apnea")
ax[2].set_ylabel("degC RMS"); ax[2].legend(loc="upper right", fontsize=8)
ax[3].plot(h_r.t, h_r.envelope, label="envelope")
ax[3].plot(h_r.t, h_r.quality * 0.1, label="quality (x0.1 for scale)", alpha=0.6)
ax[3].axhline(cfg.abs_floor_c, color="gray", ls=":")
for i, e in enumerate(h_r.events):
    ax[3].axvspan(e.start, e.end, color="orange", alpha=0.3, label="signal_lost" if i == 0 else None)
ax[3].set_title("(d) Hot incubator (ambient 34 degC): breathing swing nearly gone, quality marginal, "
                "signal_lost comes and goes")
ax[3].set_xlabel("time (s)"); ax[3].set_ylabel("degC RMS"); ax[3].legend(loc="upper right", fontsize=8)
fig.tight_layout(); fig.savefig(HERE / "phase4_apnea.png", dpi=105)

lines = ["# Phase 4 results (ALL SYNTHETIC: simulated, not measured)\n",
         "Rates 10/20/30 breaths/min x 5 seeds, 400 s, two pauses each, every nuisance on (noise, drift, "
         "head jitter, FFC, timestamp jitter, dropped frames, 5% rate wander). Errors are detected minus "
         "true, in seconds: mean / worst |error|. `causal` uses only the past; `centered` is offline.\n",
         "| scenario | injected | detected | start error | end error | false alarms | fragments |",
         "|---|---|---|---|---|---|---|", *rows, "",
         f"**False alarms on clean recordings:** {fa_total} events over {minutes} minutes "
         f"(12 runs of 15 min, rates 10/15/20/30, 3 seeds, all nuisances on, no pauses injected).",
         *[f"- {x}" for x in fa_lines], "",
         "**signal_lost demos (single runs, seed 1):**",
         f"- No visible breathing (amplitude 0): {len(l_r.events)} event(s), kinds "
         f"{sorted({e.kind for e in l_r.events})}, "
         f"{l_r.signal_lost[l_r.t > 120].mean() * 100:.0f}% of samples after 120 s flagged signal_lost, "
         f"{l_r.apnea.sum()} samples flagged apnea.",
         f"- Hot incubator, ambient 34 degC (swing about 0.04 degC): {len(h_r.events)} signal_lost "
         f"event(s), {h_r.signal_lost.mean() * 100:.0f}% of the recording flagged. Intermittent because quality "
         "hovers near the 0.5 cutoff: a marginal signal, not a clean loss."]
(HERE / "phase4_report.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
