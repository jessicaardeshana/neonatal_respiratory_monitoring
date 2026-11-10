# thermal/ : contactless breathing monitor for NICU infants (proof of concept)

A thermal camera sees the nostrils warm on each exhale and cool on each inhale. This folder turns that
into a breathing rate and an apnea (breathing pause) alarm, with nothing attached to the baby.

**Status: simulation only.** No thermal camera exists yet, so every number and picture comes from a
physics-based simulator and is labeled SIMULATED. The pipeline is hardware-ready: swapping the simulator
for a recorded file or a real FLIR Lepton changes nothing downstream. Nothing here is a medical device.

**Read first:** [`THERMAL_SPEC.md`](THERMAL_SPEC.md) (the science, and the living session log with a
"START HERE" block, commit history and decisions) and [`DEMO_APP_SPEC.md`](DEMO_APP_SPEC.md) (the interactive app: plan and build status).

## Quick start (Python 3.11+)

```bash
cd thermal
pip install -e ".[dev,app]"
python -m pytest                      # 146 tests, about 22 seconds
python scripts/run_app.py             # interactive app: http://127.0.0.1:8765
python scripts/run_synthetic_demo.py  # one-command report + figures, about 10 seconds
```

## The interactive app (`python scripts/run_app.py`)

A dark, one-screen monitor UI that runs the **real pipeline** on simulated data (always badged SIMULATED).

| tab | what it shows |
|---|---|
| **Monitor** | Small zoomed nose view with live temperatures, breathing rate, status/alarm, and three graphs on one shared time axis (breathing signal, rate vs simulation truth, breathing strength vs the pause threshold). Press play for a 3-minute story: steady breathing, a camera-calibration glitch, a speed-up, a 25 s pause that raises an apnea alarm, recovery. |
| **Pipeline** | The seven processing stages one by one, with before/after plots and plain-language "what / why / how / look for": frames and regions, averaging, glitch repair, background subtraction, band-pass filter, rate estimation, apnea decision. |
| **Lab** | Sliders and one-click setups (breathing rate, pause, incubator temperature, noise, head movement, camera glitches, detector strictness). Reruns the pipeline live and gives a plain-language verdict. "Watch this in the Monitor" plays the scenario. |
| Results & limits, Device | Not built yet (placeholders). See `DEMO_APP_SPEC.md`. |

The server listens on 127.0.0.1 only. It never opens a camera unless you click Connect on the (future) Device screen.
If port 8765 is busy: `lsof -nP -iTCP:8765 -sTCP:LISTEN` and stop the old process, or use `--port`.

## One-command report (`python scripts/run_synthetic_demo.py`)

Produces `figures/demo_summary.png` (raw signal, filtered signal, estimated vs true rate, apnea flags vs truth,
control ROI), `figures/demo_report.md` (numbers plus the spec's acceptance checklist; one item is honestly
"NOT MET": 20 s pauses are detected 26-28 of 30 times) and `data/demo_processed.npz` (gitignored), the processed-output
file for the fusion/CNN teammates (contract in `THERMAL_SPEC.md` Section 7; read it with `thermal.pipeline.load_processed`).
Everything is seeded: running it twice gives identical results.

## Layout

```
src/thermal/
  sources/   FrameSource interface; synthetic generator; file replay (.npz); Lepton adapter (UNTESTED on hardware)
  roi.py ffc.py preprocess.py     regions -> glitch repair -> background subtraction -> band-pass
  rate.py quality.py metrics.py   spectral + counting rate estimators, quality score, error metrics
  apnea.py                        envelope, baseline, apnea vs signal_lost
  pipeline.py recorder.py         run everything on any source; save/load recordings and processed output
  app/                            FastAPI server + plain HTML/CSS/JS UI (no build step, works offline)
scripts/   run_app.py, run_synthetic_demo.py, sweep_ambient.py (incubator study), phase3/4 reports, figure scripts
tests/     146 tests         figures/   committed PNGs and *_report.md          data/   gitignored raw recordings
```

## Rules for working here

- Work on a feature branch (currently `thermalexploration`); do not push to `main` until the project lead says so.
- Keep thermal code inside `thermal/` so it does not collide with the ultrasonic, depth and fusion work.
- **Privacy:** raw frames of real people never go to GitHub. `recorder.py` refuses to write outside `data/` (gitignored).
- Label simulated results as simulated everywhere; never present a simulation as a measurement.
- Update the session log in `THERMAL_SPEC.md` with every commit/push and every break.

## Not done yet

Results & limits page and guided tour; Device screen with camera detection and live mode; polish; the hardware
bring-up checklist (`scripts/bringup_lepton.md` is a placeholder); every Lepton detail (frame format, units, USB
identity, timing) is unverified until a camera is available. Full list: START HERE in `THERMAL_SPEC.md`.
