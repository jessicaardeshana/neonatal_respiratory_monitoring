# Phase 3 results (ALL SYNTHETIC: simulated, not measured)

5 seeds per row, 240 s, all nuisances on (noise, drift, head jitter, FFC, timestamp jitter, dropped frames, 5% rate wander). Windows overlapping the first/last 15 s (filter edges) are skipped. Truth = mean true rate over each window.

| profile | true bpm | reduction | spectral MAE | time-domain MAE | spectral within +/-1 | coverage |
|---|---|---|---|---|---|---|
| adult | 10 | mean | 0.14 | 0.09 | 100% | 100% |
| adult | 10 | max | 0.14 | 0.08 | 100% | 100% |
| adult | 20 | mean | 0.29 | 0.10 | 99% | 100% |
| adult | 20 | max | 0.29 | 0.09 | 99% | 100% |
| adult | 30 | mean | 0.44 | 0.09 | 92% | 100% |
| adult | 30 | max | 0.44 | 0.11 | 91% | 100% |
| neonate | 40 | mean | 0.54 | 0.15 | 87% | 100% |
| neonate | 40 | max | 0.54 | 0.17 | 87% | 100% |
| neonate | 60 | mean | 0.85 | 0.18 | 67% | 100% |
| neonate | 60 | max | 0.86 | 0.36 | 66% | 94% |
| neonate | 80 | mean | 1.09 | 0.20 | 50% | 94% |
| neonate | 80 | max | 1.17 | 0.40 | 48% | 87% |

Step 10 -> 25 bpm at 150 s: lag to settle within 1.5 bpm = spectral 42 s, time-domain 38 s (window length 30 s).
Control ROI passes the quality gate in 0% of steady windows (nostril: 95%).
