# Phase 4b: incubator sensitivity sweep (MODEL PREDICTION, not a measurement)

Synthetic recordings, 15 breaths/min, 400 s, two 25 s pauses, every nuisance on, 8 seeds per temperature. **Model assumption (unverified on hardware):** the breathing swing scales with (34.5 degC exhaled air - ambient), semi-amplitude A = 0.07 x (34.5 - ambient) degC. Pixel noise sigma = 0.05 degC, nostril ROI of 18 pixels.

Usable = rate answered in >= 90% of windows AND time-domain MAE <= 1.0 breaths/min AND >= 90% of pauses labeled apnea.

| ambient degC | swing A | RMS | SNR dB | quality | rate answered | MAE time | MAE spectral | pauses labeled apnea | flagged signal_lost | usable |
|---|---|---|---|---|---|---|---|---|---|---|
| 22 | 0.88 | 0.35 | 21.1 | 1.00 | 100% | 0.09 | 0.21 | 100% | 0% | yes |
| 24 | 0.74 | 0.30 | 20.9 | 1.00 | 100% | 0.09 | 0.21 | 100% | 0% | yes |
| 26 | 0.60 | 0.24 | 20.7 | 1.00 | 100% | 0.09 | 0.21 | 100% | 0% | yes |
| 27 | 0.53 | 0.21 | 20.5 | 1.00 | 100% | 0.09 | 0.21 | 100% | 0% | yes |
| 28 | 0.46 | 0.18 | 20.2 | 1.00 | 100% | 0.10 | 0.21 | 100% | 0% | yes |
| 29 | 0.39 | 0.16 | 19.9 | 1.00 | 100% | 0.10 | 0.21 | 88% | 0% | NO |
| 30 | 0.32 | 0.13 | 19.5 | 1.00 | 100% | 0.10 | 0.21 | 81% | 0% | NO |
| 31 | 0.25 | 0.10 | 18.6 | 1.00 | 100% | 0.11 | 0.22 | 81% | 0% | NO |
| 32 | 0.18 | 0.07 | 17.2 | 1.00 | 99% | 0.12 | 0.22 | 81% | 0% | NO |
| 33 | 0.11 | 0.05 | 14.4 | 0.96 | 92% | 0.17 | 0.22 | 0% | 9% | NO |
| 34 | 0.04 | 0.02 | 7.0 | 0.54 | 54% | 0.61 | 0.44 | 0% | 33% | NO |
| 35 | 0.00 | 0.02 | 3.1 | 0.19 | 7% | 6.15 | 6.18 | 0% | 81% | NO |
| 36 | 0.00 | 0.02 | 3.1 | 0.19 | 7% | 6.15 | 6.18 | 0% | 81% | NO |

**Head perfectly still (head jitter off), same sweep:** pauses labeled apnea / usable:

| ambient degC | pauses labeled apnea | rate answered | MAE time | usable |
|---|---|---|---|---|
| 22 | 100% | 100% | 0.08 | yes |
| 24 | 100% | 100% | 0.08 | yes |
| 26 | 100% | 100% | 0.08 | yes |
| 27 | 100% | 100% | 0.08 | yes |
| 28 | 100% | 100% | 0.09 | yes |
| 29 | 100% | 100% | 0.09 | yes |
| 30 | 100% | 100% | 0.09 | yes |
| 31 | 100% | 100% | 0.09 | yes |
| 32 | 100% | 100% | 0.09 | yes |
| 33 | 100% | 100% | 0.09 | yes |
| 34 | 0% | 100% | 0.14 | NO |
| 35 | 0% | 0% | nan | NO |
| 36 | 0% | 0% | nan | NO |

**Model predictions (1 degC grid, treat as what to measure on hardware, not as results):**
- Head moving (about 1 pixel shifts, as simulated): usable up to about 28 degC, broken from about 29 degC.
- Head perfectly still: usable up to about 33 degC, broken from about 34 degC.
- Why head motion matters: each head shift leaves a bump of roughly 0.03 degC RMS in the envelope. The pause threshold is 0.25 x the breathing envelope, which falls from about 0.07 degC at 24 degC to about 0.017 at 32 degC, so the motion bumps eventually exceed it and chop pauses into pieces too short to flag. (Switching off FFC, drift or timestamp jitter changes nothing; switching off head jitter restores 100% at 30 and 32 degC.)
- At 35-36 degC the swing is zero. With the head moving, about 7% of windows still return a rate (the quality gate leaks some noise windows) and those rates are wrong by about 6 breaths/min; with the head still, none do. 'Rate answered' must not be read as 'rate correct' when the signal is gone.
