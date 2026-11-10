"""Five seconds of SYNTHETIC video as a frame strip plus the nostril signal.

Shows, frame by frame, the nostril patch cooling on inhale and warming on
exhale. Color scale is zoomed to the face (31.8-34 degC) so the ~1 degC swing
is visible. Run from the thermal/ folder:  python scripts/plot_five_seconds.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from thermal.sources.synthetic import SyntheticConfig, generate  # noqa: E402

cfg = SyntheticConfig(duration_s=30, seed=5, rate_bpm=15, head_jitter=False, ffc=False,
                      drift=False, dropped_frames=False, rate_variability=0.0)
res = generate(cfg)
t = res.timestamps
r0, r1, c0, c1 = res.truth.nostril_box
sig = res.frames[:, r0:r1, c0:c1].mean(axis=(1, 2))

t0 = 10.0
m = (t >= t0) & (t < t0 + 5)
shown = np.flatnonzero(m)[::4][:10]

fig = plt.figure(figsize=(14, 7))
gs = fig.add_gridspec(3, 5, height_ratios=[1, 1, 1.1])
for k, i in enumerate(shown):
    ax = fig.add_subplot(gs[k // 5, k % 5])
    ax.imshow(res.frames[i][22:52, 24:58], cmap="inferno", vmin=31.8, vmax=34.0,
              extent=(23.5, 57.5, 51.5, 21.5))
    ax.add_patch(Rectangle((c0 - .5, r0 - .5), c1 - c0, r1 - r0, fill=False, ec="cyan", lw=1.4))
    ax.set_title(f"t = {t[i] - t0:.1f} s   {sig[i]:.2f} °C", fontsize=10)
    ax.axis("off")
ax = fig.add_subplot(gs[2, :])
ax.plot(t[m] - t0, sig[m], lw=2)
ax.plot(t[shown] - t0, sig[shown], "ro")
for k, i in enumerate(shown):
    ax.annotate(str(k + 1), (t[i] - t0, sig[i]), textcoords="offset points", xytext=(0, 7), ha="center")
ax.set_xlabel("time (s)")
ax.set_ylabel("nostril box mean (°C)")
ax.set_title("Nostril box temperature over the same 5 s "
             "(red dots = frames above, left to right, top row then bottom row)")
fig.suptitle("SYNTHETIC: 5 seconds of video at 15 breaths/min "
             "(color scale zoomed to 31.8-34 °C, cropped to the face)", fontsize=13)
fig.tight_layout()
out = Path(__file__).resolve().parents[1] / "figures" / "synthetic_five_seconds.png"
fig.savefig(out, dpi=100)
print(f"wrote {out}")
