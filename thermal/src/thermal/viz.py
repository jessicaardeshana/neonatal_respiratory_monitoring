"""Plotting helpers. Every figure title says SYNTHETIC where data is simulated."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from thermal.sources.synthetic import Box, SyntheticResult


def _box_mean(frames: np.ndarray, box: Box) -> np.ndarray:
    r0, r1, c0, c1 = box
    return frames[:, r0:r1, c0:c1].mean(axis=(1, 2))


def _rect(box: Box, color: str, label: str) -> Rectangle:
    r0, r1, c0, c1 = box
    return Rectangle((c0 - 0.5, r0 - 0.5), c1 - c0, r1 - r0, fill=False,
                     edgecolor=color, linewidth=1.6, label=label)


def phase1_overview(res: SyntheticResult, path: str, frame_index: int = 100) -> None:
    """Four-panel Phase 1 figure: frame+ROIs, signal, apnea, FFC glitches."""
    t, tr = res.timestamps, res.truth
    nostril = _box_mean(res.frames, tr.nostril_box)
    control = _box_mean(res.frames, tr.control_box)
    scene = res.frames.mean(axis=(1, 2))

    fig, ax = plt.subplots(2, 2, figsize=(13, 8.5))
    fig.suptitle("Phase 1: SYNTHETIC thermal video (simulated, not measured)", fontsize=14)

    # (a) sample frame with ROIs marked
    a = ax[0, 0]
    im = a.imshow(res.frames[frame_index], cmap="inferno")
    a.add_patch(_rect(tr.nostril_box, "cyan", "nostril ROI"))
    a.add_patch(_rect(tr.control_box, "lime", "control ROI (cheek)"))
    a.add_patch(_rect(tr.reference_box, "white", "reference ROI"))
    a.legend(loc="lower right", fontsize=8)
    a.set_title("(a) SYNTHETIC frame (60x80) with ROIs")
    fig.colorbar(im, ax=a, label="degC", fraction=0.046)

    # (b) raw ROI signal, normal breathing
    b = ax[0, 1]
    m = (t >= 10) & (t < 70)
    b.plot(t[m], nostril[m], label="nostril ROI mean")
    b.plot(t[m], control[m], label="control ROI mean", alpha=0.8)
    b.set_title(f"(b) SYNTHETIC raw ROI signal, {tr.rate_bpm[m].mean():.0f} breaths/min")
    b.set_xlabel("time (s)"); b.set_ylabel("degC"); b.legend(fontsize=8)

    # (c) apnea window
    c = ax[1, 0]
    if tr.apnea_mask.any():
        ts = t[tr.apnea_mask]
        lo, hi = ts.min() - 25, ts.max() + 25
        mm = (t >= lo) & (t < hi)
        c.plot(t[mm], nostril[mm])
        c.axvspan(ts.min(), ts.max(), color="red", alpha=0.15, label="true apnea window")
        c.legend(fontsize=8)
    c.set_title("(c) SYNTHETIC apnea: breathing amplitude collapses")
    c.set_xlabel("time (s)"); c.set_ylabel("nostril ROI, degC")

    # (d) FFC glitches: whole-scene mean exposes the freeze and the step
    d = ax[1, 1]
    if tr.ffc_indices.size:
        k = int(tr.ffc_step_indices[0])
        mm = (t >= t[k] - 25) & (t < t[k] + 25)
        d.plot(t[mm], scene[mm], label="whole-scene mean")
        fz = tr.ffc_indices[(tr.ffc_indices >= np.flatnonzero(mm)[0])
                            & (tr.ffc_indices <= np.flatnonzero(mm)[-1])]
        d.plot(t[fz], scene[fz], "rv", label="frozen (repeated) frame")
        d.axvline(t[k], color="gray", ls="--", label="offset step")
        d.legend(fontsize=8)
    d.set_title("(d) SYNTHETIC FFC glitch: frozen frame + level step")
    d.set_xlabel("time (s)"); d.set_ylabel("degC")

    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def phase2_before_after(res: SyntheticResult, none_res: SyntheticResult, off, on, none_off,
                        none_on, path: str) -> None:
    """Phase 2 figure: raw vs cleaned signal, and the no-breathing FFC test."""
    tr = res.truth
    step_t = res.timestamps[tr.ffc_step_indices]
    fig, ax = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
    fig.suptitle("Phase 2: SYNTHETIC data, FFC + drift handling before vs after "
                 "(drift exaggerated to 0.5 degC/min for visibility)", fontsize=13)

    ax[0].plot(off.t, off.s_raw)
    ax[0].set_title("BEFORE: raw nostril signal (drifting upward, with FFC level steps)")
    ax[0].set_ylabel("degC")
    ax[1].plot(on.t, on.s_filt)
    ax[1].set_title("AFTER: FFC repaired, reference-cancelled, detrended, band-passed "
                    "(breathing at 15 breaths/min, steady amplitude)")
    ax[1].set_ylabel("degC")
    for a in ax[:2]:
        for k, ts in enumerate(step_t):
            a.axvline(ts, color="red", ls="--", alpha=0.6, label="FFC step" if k == 0 else None)
        a.legend(loc="upper right", fontsize=8)

    ax[2].plot(none_off.t, none_off.s_filt, label="FFC handling OFF: spurious 'breaths'", alpha=0.9)
    ax[2].plot(none_on.t, none_on.s_filt, label="FFC handling ON: flat (correct)", lw=1.5)
    ax[2].set_title("ACCEPTANCE TEST: recording with NO breathing at all but FFC events, "
                    "band-passed signal")
    ax[2].set_ylabel("degC"); ax[2].set_xlabel("time (s)"); ax[2].legend(loc="upper right", fontsize=8)
    for ts in none_res.timestamps[none_res.truth.ffc_step_indices]:
        ax[2].axvline(ts, color="red", ls="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
