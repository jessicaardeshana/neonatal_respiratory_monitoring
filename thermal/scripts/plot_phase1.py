"""Generate the Phase 1 overview figure (SYNTHETIC data).

Run from the thermal/ folder:  python scripts/plot_phase1.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from thermal.sources.synthetic import SyntheticConfig, generate  # noqa: E402
from thermal.viz import phase1_overview  # noqa: E402

cfg = SyntheticConfig(
    duration_s=400.0,
    seed=11,
    rate_bpm=15.0,
    apnea_events=((100.0, 20.0),),
)
res = generate(cfg)
out = Path(__file__).resolve().parents[1] / "figures" / "phase1_synthetic_overview.png"
phase1_overview(res, str(out))
print(f"wrote {out}")
print(f"frames={res.frames.shape[0]}  FFC frozen idx={res.truth.ffc_indices.tolist()}  "
      f"step idx={res.truth.ffc_step_indices.tolist()}  A={res.truth.amplitude_c:.2f} degC")
