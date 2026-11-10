"""Phase 2 before/after figure (SYNTHETIC data).  Run from thermal/: python scripts/plot_phase2.py"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from thermal.config import PipelineConfig  # noqa: E402
from thermal.preprocess import process_frames  # noqa: E402
from thermal.roi import ROI  # noqa: E402
from thermal.sources.synthetic import SyntheticConfig, generate  # noqa: E402
from thermal.viz import phase2_before_after  # noqa: E402


def run(res, **kw):
    tr = res.truth
    return process_frames(res.frames, res.timestamps, ROI.from_box(tr.nostril_box),
                          ROI.from_box(tr.control_box), ROI.from_box(tr.reference_box),
                          PipelineConfig(**kw))


common = dict(duration_s=420, seed=5, ffc_interval_s=(60.0, 90.0), ffc_step_c=(0.3, 0.3),
              head_jitter=False)
breathing = generate(SyntheticConfig(**common, rate_bpm=15.0, amplitude_c=0.7, drift_c_per_min=0.5))
silent = generate(SyntheticConfig(**common, amplitude_c=0.0))

out = Path(__file__).resolve().parents[1] / "figures" / "phase2_before_after.png"
phase2_before_after(breathing, silent, run(breathing, ffc_handling=False),
                    run(breathing, ffc_handling=True), run(silent, ffc_handling=False),
                    run(silent, ffc_handling=True), str(out))
print(f"wrote {out}")
