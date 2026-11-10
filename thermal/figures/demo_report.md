# Phase 6 demo report (ALL SYNTHETIC: simulated, not measured)

Reproduce: `python scripts/run_synthetic_demo.py` from `thermal/`. Everything is seeded, so re-running gives identical numbers. Figure: `figures/demo_summary.png`.

## Scenario

Adult profile, 420 s, seed 11. Breathing 12 breaths/min, stepping to 22 at 220 s. Two injected 25 s pauses (100 s and 320 s). Every nuisance on: pixel noise, drift, head jitter, FFC events, timestamp jitter, dropped frames, 5% breath-to-breath rate wander.

## Results on the demo recording

- **Rate error** (30 s windows, pauses and the step excluded): spectral MAE 0.26, time-domain MAE 0.09 breaths/min.
- **Rate step lag** (time until the estimate holds within 1.5 breaths/min of 22): spectral 23 s, time-domain 27 s (window length 30 s).
- **Pauses:** 2 of 2 detected as apnea (pause 1: start +0.7 s, end +1.3 s; pause 2: start +0.5 s, end +0.5 s). False alarms: 0. Fragments: 0.
- **FFC:** 2 of 2 injected level steps detected, 0 extra.
- **Control ROI:** passes the quality gate in 4% of windows (nostril: 86%); median quality 0.29 vs 1.00.

## Section 9 acceptance checklist (fresh synthetic recordings)

| criterion | result | status |
|---|---|---|
| adult 10 breaths/min within +-1 (mean error, 3 seeds, 200 s) | spectral 0.14, time-domain 0.09; 100% of spectral windows within +-1 | PASS |
| adult 20 breaths/min within +-1 (mean error, 3 seeds, 200 s) | spectral 0.31, time-domain 0.10; 99% of spectral windows within +-1 | PASS |
| adult 30 breaths/min within +-1 (mean error, 3 seeds, 200 s) | spectral 0.48, time-domain 0.10; 89% of spectral windows within +-1 | PASS |
| neonate 40 breaths/min within +-2 (mean error, 3 seeds, 200 s) | spectral 0.57, time-domain 0.16; 99% of spectral windows within +-2 | PASS |
| neonate 60 breaths/min within +-2 (mean error, 3 seeds, 200 s) | spectral 0.92, time-domain 0.17; 91% of spectral windows within +-2 | PASS |
| neonate 80 breaths/min within +-2 (mean error, 3 seeds, 200 s) | spectral 1.13, time-domain 0.20; 85% of spectral windows within +-2 | PASS |
| 20 s pauses detected, start/end within ~5 s (3 rates x 5 seeds) | 26 of 30 detected; worst start error 1.2 s, worst end error 2.2 s | NOT MET |
| Control ROI shows no breathing peak | gate passed in 4% of windows (nostril 86%) | PASS |
| FFC does not create false breaths or false apnea | 0 spurious apnea/signal_lost events over every acceptance run | PASS |
| All tests pass | run `python -m pytest` (not checked by this script) | n/a |

Reading the table: "NOT MET" means the strict spec wording is not satisfied, even when the numbers are close. See the Phase 3 and Phase 4 entries in `THERMAL_SPEC.md` for why (simulated 5% rate wander makes a window's true rate ambiguous; a 20 s pause sits right on the detector's 20 s minimum, so a few are missed).

## Files
- `figures/demo_summary.png`: the five-panel figure.
- `data/demo_processed.npz` (gitignored): Section 7 processed output on one uniform time grid: `t, s_raw, s_ctrl, s_filt, envelope, rate_bpm, quality, apnea, ffc_mask` plus `signal_lost` and a JSON `meta`. Read it with `thermal.pipeline.load_processed`. `rate_bpm` is the time-domain estimate held causally per sample (NaN when quality is low).

## Not covered (honest limits)
All numbers are from a model, not a camera. Head motion is modeled only as +-1 pixel shifts; the Lepton read path is untested on hardware; a warm incubator degrades apnea detection (Phase 4b).
