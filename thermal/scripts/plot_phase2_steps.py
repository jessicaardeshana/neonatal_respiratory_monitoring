"""Phase 2 cleaning shown one step at a time, same y-axis height (SYNTHETIC).

Run from thermal/:  python scripts/plot_phase2_steps.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from thermal.config import PipelineConfig  # noqa: E402
from thermal.ffc import detect_ffc, repair_invalid  # noqa: E402
from thermal.preprocess import process_frames  # noqa: E402
from thermal.roi import ROI, reduce_roi  # noqa: E402
from thermal.sources.synthetic import SyntheticConfig, generate  # noqa: E402

res = generate(SyntheticConfig(duration_s=420, seed=5, rate_bpm=15.0, amplitude_c=0.7,
                               drift_c_per_min=0.5, ffc_interval_s=(60.0, 90.0),
                               ffc_step_c=(0.3, 0.3), head_jitter=False))
tr, t = res.truth, res.timestamps
nos, ctl, ref = (ROI.from_box(b) for b in (tr.nostril_box, tr.control_box, tr.reference_box))
cfg = PipelineConfig()
out = process_frames(res.frames, t, nos, ctl, ref, cfg)

raw = reduce_roi(res.frames, nos)
refsig = reduce_roi(res.frames, ref)
ffc = detect_ffc(res.frames)
repaired = repair_invalid(t, raw, ffc.frozen_mask, cfg.max_gap_s)
step_t = t[ffc.step_indices]

T0, T1, SPAN = 100.0, 190.0, 2.6  # zoom window (s) around an FFC step; same y height per panel
w = (t >= T0) & (t < T1)
wu = (out.t >= T0) & (out.t < T1)


def style(a, title, y, xs):
    mid = (np.nanmax(y[xs]) + np.nanmin(y[xs])) / 2
    a.set_ylim(mid - SPAN / 2, mid + SPAN / 2)
    a.set_title(title, fontsize=10, loc="left")
    a.set_ylabel("degC")
    for k, s in enumerate(step_t[(step_t >= T0) & (step_t < T1)]):
        a.axvline(s, color="red", ls="--", alpha=0.5, label="FFC step" if k == 0 else None)


fig, ax = plt.subplots(4, 1, figsize=(13, 11), sharex=True)
fig.suptitle("Phase 2, one step at a time (SYNTHETIC, drift exaggerated to 0.5 degC/min). "
             f"Every panel is {SPAN} degC tall", fontsize=12)

ax[0].plot(t[w], raw[w], label="nostril ROI (raw)")
ax[0].plot(t[w], refsig[w] - refsig[w][0] + raw[w][0], color="gray", lw=2, alpha=0.8,
           label="background ROI (no breathing), shifted to line up: shows the drift + step")
style(ax[0], "1. RAW: breathing wiggle + slow warming + FFC jump. "
             "The gray line is a patch with NO breathing: it shows what is NOT breathing", raw, w)
ax[0].legend(loc="upper left", fontsize=8)

ax[1].plot(t[w], repaired[w])
style(ax[1], "2. FFC glitch frames repaired (only 1-2 frozen frames, so little change; "
             "the jump is still there)", repaired, w)

ax[2].plot(out.t[wu], out.s_clean[wu])
style(ax[2], "3. Background subtracted: drift and FFC jump are GONE, "
             "temperature stays near the real ~33 degC", out.s_clean, wu)

ax[3].plot(out.t[wu], out.s_filt[wu])
style(ax[3], "4. Detrended + band-passed: just the breathing wiggle, centered on 0 "
             "(change from the average, not absolute temperature)", out.s_filt, wu)
ax[3].set_xlabel("time (s)")
for a in ax:
    a.grid(alpha=0.25)
fig.tight_layout()
path = Path(__file__).resolve().parents[1] / "figures" / "phase2_steps.png"
fig.savefig(path, dpi=105)
print(f"wrote {path}")
