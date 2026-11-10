# Phase 4 results (ALL SYNTHETIC: simulated, not measured)

Rates 10/20/30 breaths/min x 5 seeds, 400 s, two pauses each, every nuisance on (noise, drift, head jitter, FFC, timestamp jitter, dropped frames, 5% rate wander). Errors are detected minus true, in seconds: mean / worst |error|. `causal` uses only the past; `centered` is offline.

| scenario | injected | detected | start error | end error | false alarms | fragments |
|---|---|---|---|---|---|---|
| 20 s pauses, min 20 s, causal | 30 | 28 | +0.7 / 2.2 | +1.0 / 2.2 | 0 | 0 |
| 20 s pauses, min 20 s, centered | 30 | 28 | +0.8 / 2.3 | +1.0 / 2.2 | 0 | 0 |
| 25 s pauses, min 20 s, causal | 30 | 30 | +0.8 / 2.2 | +0.9 / 1.9 | 0 | 0 |
| 10 s pauses, min 10 s, causal | 30 | 29 | +0.7 / 1.7 | +0.9 / 1.6 | 0 | 0 |

**False alarms on clean recordings:** 0 events over 180 minutes (12 runs of 15 min, rates 10/15/20/30, 3 seeds, all nuisances on, no pauses injected).

**signal_lost demos (single runs, seed 1):**
- No visible breathing (amplitude 0): 1 event(s), kinds ['signal_lost'], 91% of samples after 120 s flagged signal_lost, 0 samples flagged apnea.
- Hot incubator, ambient 34 degC (swing about 0.04 degC): 3 signal_lost event(s), 32% of the recording flagged. Intermittent because quality hovers near the 0.5 cutoff: a marginal signal, not a clean loss.
