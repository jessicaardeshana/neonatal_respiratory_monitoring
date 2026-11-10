# THERMAL_SPEC.md — Thermal Respiratory Sensing (Proof of Concept)

> Briefing for a Claude Code session. Read this whole file first, then work through the phases in order.
> **Work one phase at a time. Stop at the end of each phase, show the results (plots + test output), and wait for approval before starting the next phase.**
> Owner: Alan (thermal sensing lead). Rest of the team owns the ultrasonic, Kinect/depth, and fusion/CNN work. Keep all thermal code inside `thermal/` so we do not collide with their work.

---

## STATUS / SESSION LOG (read this first, update it with every commit/push and every break)

**Rules:** never push to `main` until Alan says so; push only to feature branches. Newest entry on top.

**Current state:** Phases 0-6 and 4b complete and pushed. Interactive demo app (`DEMO_APP_SPEC.md`): **steps A and B built, at Checkpoint 1 (awaiting Alan's review of the Monitor screen).** Next: step C (Pipeline view), D (Lab sliders), E (Results page + tour), F (Device screen), G (polish). Phase 7 (bring-up docs) follows the app.

### 2026-11-10 · branch `thermalexploration` · Monitor redesign (Alan's Checkpoint 1 feedback)
- **Feedback:** the thermal video took over the screen; Alan only needs to see the nose region changing; wants all the graphs visible together without scrolling to compare them; dislikes the neon look.
- **Done:** (1) Thermal view is now a small zoomed crop around the nose and cheek (rows 22-50, cols 26-54) with live nose/cheek temperatures; "Full" frame and "Face/Scene" color scale are one click away. (2) The Monitor is a fixed one-screen layout (no scrolling at 1280x720 and up): a fixed-height status bar (so alarms never shift the layout), a compact top row (thermal, rate, meters, event log), then THREE graphs stacked on ONE shared time axis (breathing signal, rate estimate vs simulation truth, breathing strength vs the pause threshold) with the pause, detected apnea and camera glitches aligned across them, then transport + a whole-recording scrubber. "Graphs show" switches between last 30 s, last 60 s and the whole recording. The rate graph autoscales to the visible window. (3) Neon removed: flat graphite panels, muted teal/amber/red used only for meaning, no glows, gradients or pulsing (the alarm is a flat tinted bar). Short-screen mode compacts the top row; below 1180 px wide it stacks and scrolls.
- **Verified in the browser at 1440x860 and 1280x720:** no page scroll, no clipped controls, graphs 79-114 px tall, alarm / pause-suspected / whole-recording views checked. 125 tests still pass.
- **Housekeeping:** the preview tool starts the server on 8766 if 8765 is busy (a stale server of mine was holding 8765; it is stopped).

### 2026-11-10 · branch `thermalexploration` · Demo app steps A + B (Checkpoint 1)
- **Done:** backend `thermal/app/` (`scenarios.py` slider parameters with validation and the default story; `service.py` runs the REAL pipeline via `run_pipeline` and packages every stage, cached by parameter hash; `results.py` reads the real report files plus the honest-limits list; `server.py` FastAPI on 127.0.0.1: `/api/health /schema /run /frames /results`; frames served as raw int16 centi-degC chunks). `scripts/run_app.py` starts it (`python scripts/run_app.py`, opens `http://127.0.0.1:8765`; `pip install -e ".[dev,app]"`). Frontend in `thermal/app/static/` is plain HTML/CSS/JS with no build step and no external libraries (own canvas charts, own inferno palette), so it works offline. **Monitor screen** built: thermal video player (play/pause, 1-8x, scrub, face-range vs full-scene color scale, ROI boxes, live nostril/cheek temperatures, color bar), big breathing rate with a 30 s "measuring" ring, signal-quality and breathing-strength meters (with the 25% pause threshold marked), status chip (Measuring / Breathing detected / Pause suspected with countdown / Apnea alarm / Signal lost), alarm banner, event log, 30 s scrolling signal strip with the true pause (labeled simulation-only) and detected apnea, and a whole-recording scrubber. Header has a permanent SIMULATED DATA badge. Other tabs are placeholders marked "soon".
- **Default story (seed 7, 180 s):** 14 breaths/min, first reading at 30 s, camera recalibration glitch repaired at 56.8 s, speed-up to 24 at 75 s, 25 s pause from 95 s (suspected, then alarm declared at 113.8 s, resumes at about 121 s), second glitch at 140.9 s. Pipeline result: 1 of 1 pause found (start +0.3 s, end +1.1 s), 0 false events, 2 of 2 glitches detected, rate MAE 0.08 breaths/min. Seed 7 was picked so the glitches land away from the pause; it is a demo choice, not a typical case.
- **Verified:** 125 tests pass (24 API tests incl. slider mapping, hot incubator -> signal_lost, frame chunks decode to plausible temperatures, `NaN` never leaks into JSON, static assets all exist). Visually checked in the browser at 1600x1000 and at narrow width at steady breathing, pause suspected and alarm; playback advances at the right speed; console clean. Not yet checked: Full-scene color mode visuals, 1920x1080 exactly.
- **Bugs found and fixed while reviewing:** a CSS class-name clash (`.alarm` on the banner hid the status chip and rate number in the alarm state); overlapping strip labels; empty event log wrapping.
- **Decisions:** the status chip's "pause suspected" countdown is computed from the envelope at the playhead (causal), and alarm timing uses the detector's `declared_at`, so the screen does not use future information to raise the alarm. The true pause is only drawn up to the playhead. `rate` default estimator is the time-domain one (toggle: "Counting" vs "Spectrum").
- **Open:** Pipeline/Lab/Results/Device/Tour not built; live camera path untested (no hardware); the slider rerun speed looks fine so far (default story runs in about 0.2 s).
- **Next step:** Alan reviews Checkpoint 1 (run `python scripts/run_app.py`). Then step C: Pipeline stepper (7 stages with before/after and plain-language what/why), then D: Lab sliders (Checkpoint 2).

### 2026-11-10 · branch `thermalexploration` · Plan: interactive demo + device app (no code yet)
- **Why:** Alan wants to screen-record a polished interactive demo for the team (thermal video playback, step-by-step pipeline, sliders, results and honest limits) that doubles as the product's software side, including a Device screen that detects a Lepton and shows the live feed.
- **Decisions (Alan, 2026-11-10):** local web app (Python/FastAPI backend running the real pipeline + browser UI); features = 30 s frame playback, step-by-step pipeline view, lab sliders, results and limits page; Device screen with safe detection (USB identity, never opens a camera until Connect); dark clinical look; guided tour + free explore; opening story = normal -> speed-up -> 25 s pause + alarm -> recovery with an FFC glitch handled; unbranded title. Full plan, architecture, honesty rules, build steps A-G and acceptance criteria are in `DEMO_APP_SPEC.md`.
- **Order change:** Phase 7 (bring-up docs) now comes after the app, because the Device screen and live path shape the hardware-day checklist.
- **Open risks:** USB IDs for the Lepton breakout and the whole live path are unverified; slider recompute speed; windowed (not causal) live processing.
- **Next step:** Alan approves or edits `DEMO_APP_SPEC.md`; then build step A (backend + API) and stop at Checkpoint 1 (Monitor screen playing the default story).

### 2026-11-10 · branch `thermalexploration` · Phase 6 end-to-end demo
- **Done:** `scripts/run_synthetic_demo.py`: ONE command (`python scripts/run_synthetic_demo.py` from `thermal/`, about 10 s; `--quick` skips the acceptance sweeps) runs the full pipeline through `run_pipeline` on a `SyntheticSource` and writes `figures/demo_summary.png` (raw signal, filtered signal, estimated vs true rate, apnea flags vs truth, control ROI), `figures/demo_report.md` (numbers + Section 9 checklist) and `data/demo_processed.npz` (the Section 7 output contract; see the new note under the Section 7 table). New helpers: `pipeline.processed_arrays / save_processed / load_processed`, `rate.hold_to_grid`, public `recorder.git_commit`. `thermal/README.md` now says how to run it. 99 tests pass.
- **Reproducible:** every seed is fixed; running the command twice gives byte-identical report, figure and arrays (tested, and checked by hash on the full run).
- **Demo scenario (seed 11):** 12 -> 22 breaths/min at 220 s, two 25 s pauses, every nuisance on. Result: rate MAE spectral 0.26 / time-domain 0.09 breaths/min; step settles in 23 s (spectral) and 27 s (time-domain); 2 of 2 pauses detected (start errors +0.7 and +0.5 s, end errors +1.3 and +0.5 s); 0 false alarms; 2 of 2 FFC steps detected, 0 extra; control ROI passes the quality gate in 4% of windows vs 86% for the nostril.
- **Section 9 acceptance checklist, re-checked on fresh recordings (see `figures/demo_report.md`):** PASS for rate at 10/20/30 (adult, +-1) and 40/60/80 (neonate, +-2) on mean error (adult 30: 89% and neonate 80: 85% of spectral windows within tolerance), PASS for control ROI (4% vs 86%), PASS for FFC (0 spurious events over every run). **NOT MET: "20 s pauses detected": 26 of 30 detected** (3 rates x 5 seeds, pauses at 120 s and 230 s; start/end errors are fine, worst 1.2 s and 2.2 s). The Phase 4 study found 28 of 30 at other pause timings, so the real rate is roughly 87-93%; the misses are pauses estimated 1-2 s short of the 20 s minimum. Raising `duration_tol_s` would catch them at the cost of flagging ~17 s pauses (Phase 4 notes). Decision left to Alan.
- **Honest limits:** all synthetic; head motion modeled only as 1 px shifts; Lepton read path untested; a warm incubator degrades apnea detection (Phase 4b); `rate_bpm` in the contract file is the time-domain estimate (chosen because it was more accurate at every rate; the spectral one is available via `estimator="spectral"`).
- **Next step:** Phase 7 (Section 8): write `scripts/bringup_lepton.md` (Section 10 hardware-day checklist and test protocol, referencing `TimestampLogger`, `raw_to_celsius`, `FileSource`, `record`, and the Section 11 unverified assumptions) and finish `thermal/README.md`. After that the spec's phases are done; remaining open items are in Section 11. Stop for review.

### 2026-11-10 · branch `thermalexploration` · Phase 5 hardware-ready adapters
- **Done:** `recorder.py` (`record`, `save_recording`: raw-frame `.npz` with frames, timestamps, JSON meta and optional ground truth, no pickle; refuses to write outside the gitignored `thermal/data/` unless told to; `TimestampLogger` for frame-rate, jitter and gap measurement with CSV output), `sources/file_source.py` (`FileSource`: strict validation with clear errors, unit conversion, `from_arrays` for clips from any other camera), `sources/lepton.py` (`LeptonSource`, `raw_to_celsius` as the single unit-conversion function with scale and offset, `normalize_raw_frame`, `DeviceNotFoundError` with a checklist), and `pipeline.py` (`run_pipeline(source, rois...)`: runs signals -> rate -> apnea on ANY FrameSource; small convenience module added beyond the Section 5 layout, still inside `thermal/`). 93 tests pass.
- **Acceptance (synthetic):** a recorded-then-replayed `.npz` gives bit-identical pipeline output to the live `SyntheticSource`: cleaned signals, rate estimates, quality, envelope, and the detected apnea event all compare equal (`test_pipeline_runs_identically_from_syntheticsource_and_a_replayed_npz`).
- **Safety decisions:** no test opens a real device: the Lepton is tested with a fake capture and with `cv2.VideoCapture` monkeypatched closed (on a Mac, index 0 would grab the webcam). `LeptonSource` opens nothing until `frames()` is iterated, always releases the camera (even if the consumer stops early), gives up after 30 failed reads in a row, and fails loudly on an unexpected frame format. Recordings are loaded with `allow_pickle=False`. `data/` is verified gitignored by a test.
- **NOT verified (needs hardware):** everything camera-specific in `lepton.py` (see the new bullet in Section 11). The code is a best-guess adapter, not a validated driver.
- **Not done yet:** the processed-output `.npz` contract for teammates (Section 7 table: `t, s_raw, s_ctrl, s_filt, envelope, rate_bpm, quality, apnea, ffc_mask, meta` on one uniform grid) is not written yet; it belongs with the Phase 6 demo, since it needs the per-sample hold of window-level rate/quality. ROIs for real data must be drawn with `roi.select_roi_interactive` (needs a display).
- **Next step:** Phase 6 (`scripts/run_synthetic_demo.py`): one command produces the summary figure set (raw, filtered, estimated vs true rate, apnea flags vs truth, control ROI) plus a short markdown report in `figures/`, and also write the Section 7 processed `.npz`. Stop for review.

### 2026-11-10 · branch `thermalexploration` · Phase 4b incubator sensitivity sweep (MODEL PREDICTION, not a measurement)
- **Done:** `scripts/sweep_ambient.py` sweeps ambient 22 -> 36 degC (13 points, 8 seeds each, two 25 s pauses per recording, 15 breaths/min, all nuisances on) and records breathing amplitude, spectral SNR, rate error and coverage, and apnea detection. Run it again with `python scripts/sweep_ambient.py` (about 5 min). Outputs: `figures/phase4b_ambient_sweep.png`, `figures/phase4b_report.md` (full tables). `RateEstimate` gained an `snr_db` field. 68 tests pass.
- **Key model assumption (UNVERIFIED on hardware):** breathing swing A = 0.07 x (34.5 degC exhaled air - ambient), so it reaches zero at 34.5 degC. The gain 0.07 was chosen to give A of about 0.74 degC at 24 degC; it is a modeling choice, not a measurement. Also fixed: pixel noise 0.05 degC, 18-pixel nostril ROI, 0.3 s thermal lag. Not modeled: canopy material blocking long-wave IR, humidity or condensation, distance.
- **Predictions (1 degC grid; "usable" = rate answered in >= 90% of windows AND time-domain MAE <= 1 bpm AND >= 90% of pauses labeled apnea):** with the head moving (1 px shifts, as simulated) usable up to about **28 degC**, broken from 29; with the head perfectly still usable up to about **33 degC**, broken from 34. Rate estimation by itself holds up to about 33 degC in both cases (answered in 92% of windows at 33, 54% at 34, with MAE under 0.2 bpm up to 33). At 34 degC the swing is only 0.04 degC; at 35-36 degC it is zero and the detector reports signal_lost (81% of the recording), never apnea.
- **Why apnea detection breaks earlier than rate estimation:** the apnea threshold is 0.25 x the breathing envelope, which shrinks as the incubator warms, while head-shift bumps (about 0.03 degC RMS in the envelope) stay the same size. At 29-33 degC the bumps start to exceed the threshold and chop a pause into pieces too short to flag (pauses found drop 100% -> 88% -> 81% -> 62%). Verified by switching nuisances off one at a time: head jitter off restores 100% at 30 and 32 degC; FFC, drift and timestamp jitter off change nothing. **Head stability (or motion tracking) matters more than any other factor for apnea detection in a warm incubator.**
- **Other findings:** (1) the quality gate leaks: at 35-36 degC with the head moving about 7% of windows still return a rate, wrong by about 6 bpm, so "rate answered" does not mean "rate correct". (2) Spectral SNR plateaus near 20 dB for swings above 0.15 degC; that ceiling is the breathing's own spectral spread (rate wander, harmonics), not noise. (3) Measured RMS of the filtered signal is only about 0.4 x the model swing A (a sine would give 0.71 x A) because of head shifts moving the patch off the ROI and the thermal lag.
- **What to measure on hardware (this sweep says what matters):** breathing swing vs ambient/incubator temperature at 20-30 cm (is the gain near 0.07, is it linear?); the real noise floor of the ROI mean; how many pixels and how much amplitude real head motion costs; whether the canopy and humidity attenuate the signal.
- **Caveats:** the usable criteria (90%, 1 bpm, 90%) and the 1 degC grid are documented choices; at 16 pauses per temperature the pause-detection percentages move in 6% steps. Rates other than 15 bpm and neonate profile not swept.
- **Next step:** Phase 5 (Section 8): `recorder.py` (save frames + timestamps to .npz, raw data gitignored), `file_source.py` (replay), `lepton.py` (FrameSource that fails gracefully with no device, with the unit-conversion function and a frame-rate/timestamp logger). Done when the pipeline runs identically from `SyntheticSource` and a recorded-then-replayed `.npz`. Stop for review.

### 2026-11-10 · branch `thermalexploration` · Phase 4 apnea detector
- **Done:** `apnea.py`: RMS (or Hilbert) amplitude envelope, causal rolling-median baseline that is frozen during pauses (it never learns them), flag when envelope < 0.25 x baseline for the minimum duration, `apnea` vs `signal_lost` labels, event list with `start`, `end`, `kind` and `declared_at` (earliest real-time alarm). `metrics.score_events` scores start/end errors, misses, false alarms, fragments. `scripts/phase4_report.py` writes `figures/phase4_apnea.png` and `figures/phase4_report.md`. 65 tests pass.
- **Results (synthetic, all nuisances on, 3 rates x 5 seeds x 2 pauses):** 20 s pauses (20 s rule): 28 of 30 detected (93%), start error +0.7 s mean / 2.2 s worst, end error +1.0 / 2.2 s, 0 false alarms, 0 fragments. 25 s pauses and 22 s pauses: 30 of 30. 10 s pauses (10 s rule): 29 of 30. **False alarms on clean data: 0 over 180 min** (12 runs x 15 min, 10/15/20/30 bpm). A 90 s pause is flagged for its whole length. `signal_lost` demonstrated: no visible breathing is flagged signal_lost (91% of samples after 120 s) and never apnea; a pause after good breathing is labeled apnea. The spec's targets (20 s pauses found, start/end within about 5 s) are met except for the 2 borderline misses.
- **Why 2 of 30 20 s pauses were missed:** the envelope reacts late and by an amount that depends on where in a breath the pause begins, so the estimated pause length varies by about +-2 s; the two misses were estimated at 18.3 and 18.4 s against a 18.5 s cutoff (20 s minus a 1.5 s tolerance). A 3 s tolerance catches all 30 but then also flags 17 s pauses 57% of the time. Kept the stricter default (`duration_tol_s = 1.5`). Alan can change it if missing is worse than over-calling.
- **Design decisions:** envelope delay is back-dated using the derived formula (1 - k^2) x window (centered windows: 0.5 x window less); envelope window 4 s; baseline = 180 s rolling median; warm-up 30 s; "very low envelope" floor 0.05 degC RMS (typical breathing RMS is about 0.25-0.4); "very low quality" = below 0.5, the same cutoff the rate estimator uses to reject a window; "good breathing before" = mean quality >= 0.7 over the previous 30 s. All are documented choices, not fitted.
- **Known issues / limits:** (1) no flags until about 34 s of history exist; a pause in the first minute pollutes the baseline. (2) Timing numbers use a trailing (causal) envelope on the zero-phase band-passed signal; a fully causal filter chain has not been evaluated. (3) Sudden loss of the face mid-recording looks like apnea (good breathing, then nothing). This is inherent; needs face tracking or another cue. (4) Head jitter changes the nostril signal's amplitude by up to about 30% (visible in the figure at about 70 s), harmless against the 0.25 threshold but a real motion artifact. (5) signal_lost at the start of a recording is delayed because filter-edge transients look like breathing for about 75 s in the no-breathing demo. (6) In a hot incubator (34 degC) the swing is about 0.04 degC and quality sits near the cutoff, so signal_lost comes and goes (32% of the demo recording flagged). That is a preview of Phase 4b. (7) All synthetic.
- **Next step:** Phase 4b (`scripts/sweep_ambient.py`): sweep ambient 22 -> 36 degC and plot signal SNR, rate error, apnea-detection success vs ambient; label as a model prediction, not a measurement. Stop for review.

### 2026-11-10 · branch `thermalexploration` · Phase 3 rate estimation + quality + metrics
- **Done:** `rate.py` (sliding-window spectral estimator with x8 zero-pad + parabolic peak interpolation, and time-domain peak-spacing estimator; both return NaN when quality < 0.5; time reported is window END so only past data is used), `quality.py` (spectral SNR near f and 2f vs rest of band, mapped to 0-1 with -3 dB..+15 dB endpoints, times an agreement factor between the two estimators), `metrics.py` (MAE, max error, coverage, window truth, step lag). `scripts/phase3_report.py` writes `figures/phase3_rate.png` and `figures/phase3_report.md` (full table). 46 tests pass.
- **Results (synthetic, all nuisances on, 5 seeds, mean-ROI):** adult 10/20/30 bpm spectral MAE 0.14/0.29/0.44, time-domain MAE 0.09/0.10/0.09; spectral windows within +-1 bpm: 100%/99%/92%. Neonate 40/60/80: time-domain MAE 0.15/0.18/0.20, spectral MAE 0.54/0.85/1.09 (both inside the +-2 target on average; only 87/67/50% of spectral windows are within +-1). Step 10 -> 25 bpm: settles in 42 s (spectral) / 38 s (time-domain) with a 30 s window; windows that straddle the step are mixed and correctly return NaN. Control ROI passes the quality gate in 0% of steady windows (nostril 95%).
- **Mean vs max reduction:** about the same for the spectral estimator; max is worse for the time-domain estimator at neonate rates (MAE 0.36/0.40 vs 0.18/0.20 at 60/80 bpm) and loses coverage at 80 bpm (87% vs 94%). Keep **mean** as the default.
- **Spectral vs time-domain:** time-domain is more accurate at every rate here. Spectral error grows with rate because of the simulated 5% breath-to-breath rate wander (a window has no single true rate) plus 60/W bpm resolution; with the wander turned off the worst spectral error is 0.04-0.11 bpm at 10/20/30, so the estimator itself is accurate. The strict "+-1 bpm" target is therefore only met on average (and in 92-100% of adult windows), not in every window, when the wander is on.
- **Decisions:** thresholds (min quality 0.5, SNR mapping, 3 bpm agreement tolerance, 3-window hold for step lag, 2 s hop) are documented choices, not fitted. Quality gate returns NaN instead of a wrong number.
- **Known issues:** with head jitter on, about 12% of control-ROI windows (seed 4) pass the quality gate (slow bumps from 1 px head shifts); 0% when jitter is off. Same motion artifact as Phase 2; auto-tracking is future work. First window needs 30 s (adult) / 20 s (neonate) before any estimate. All numbers synthetic.
- **Next step:** Phase 4 (Section 6.7): amplitude envelope, apnea flag with `signal_lost` distinction; report start/end errors for injected 20 s pauses, false alarms on a long clean run, and the signal_lost case. Stop for review.

### 2026-11-10 · branch `thermalexploration` · Phase 2 preprocessing + FFC handling
- **Done:** `roi.py` (ROI, mean/max reduction, interactive picker for real data), `ffc.py` (frozen-frame + whole-scene step detection, telemetry-flag hook, short-gap interpolation, reference-ROI cancellation), `preprocess.py` (resample to uniform grid, detrend: highpass/movmean/poly, Butterworth band-pass zero-phase and causal, `process_frames` end-to-end for nostril + control ROI). `PipelineConfig` gained the FFC/detrend parameters. `figures/phase2_before_after.png` (via `scripts/plot_phase2.py`). 34 tests pass.
- **Acceptance test (synthetic):** a recording with NO breathing but FFC events produces spurious peaks with handling off (one per FFC event, about 0.13 degC) and none with handling on. With breathing, handling on recovers the clean signal (RMS error < 0.08 degC) and off is more than 2x worse.
- **Decisions:** detector finds exactly the injected frozen frames and steps and has no false alarms over a 15 min clean run with apnea. Step threshold = max(0.05 degC, 8 x robust noise sigma): the scene mean barely moves for breathing (18-pixel patch) but jumps for FFC (all pixels). Reference-ROI subtraction removes both drift and FFC steps. Detrend default is a high-pass at half the band's lower edge so breathing is not touched. Amplitude is never normalized.
- **Known issues:** (1) head jitter alone leaves a ~0.12 degC bump in the filtered signal (the ROI slides across a temperature edge). It is a motion artifact, future work per Section 2; the FFC acceptance test turns jitter off to isolate FFC. (2) zero-phase filter edges ring in the first/last ~20 s (tests and later rate windows should ignore them). (3) frozen-frame detection needs sensor noise; a noise-free static scene would be misread. (4) all synthetic.
- **Added after review:** `figures/phase2_steps.png` (via `scripts/plot_phase2_steps.py`) shows the cleaning one step at a time on equal-height y axes: raw -> FFC repaired -> background subtracted (drift and jump gone, still ~33 degC) -> detrended + band-passed (centered on 0). Key idea: breathing temperature swings are the signal; slow drift and FFC jumps are what get removed (the background patch has no breathing, so it shows exactly what is not breathing). Read this figure first to understand Phase 2.
- **Next step:** Phase 3 (Sections 6.6, 6.8): spectral and time-domain rate estimators, quality index, `metrics.py`; check +-1 breath/min at 10/20/30 bpm, step-change lag, control ROI shows no peak, and report MAE spectral vs time-domain and mean vs max. Stop for review.

### 2026-11-10 · branch `thermalexploration` · Phase 1 synthetic generator
- **Done:** `sources/synthetic.py` implements Section 6.2: face blob + nostril patch, non-sinusoidal breath (sine + 2nd harmonic), thermal lag (tau 0.3 s), amplitude scaling with (exhale - ambient), constant/step/variable rate, apnea windows with 1 s ramps, and toggleable noise, drift, head jitter, FFC (frozen frames + persistent offset step), timestamp jitter, dropped frames. Returns frames, timestamps and a `GroundTruth` (rate, apnea mask, ROI boxes, FFC indices). `SyntheticSource` implements `FrameSource`. `viz.phase1_overview` + `scripts/plot_phase1.py` make `figures/phase1_synthetic_overview.png` (a: frame with ROIs, b: oscillating signal, c: apnea, d: FFC glitch). 19 tests pass.
- **Decisions:** each nuisance has its own random stream (toggling one does not change another; fixed seed is reproducible). Default amplitude gain 0.07 degC per degC gives A = 0.74 degC at 24 degC ambient, about 0.04 at 34 degC and 0 at 36 degC (the incubator effect). Ground truth also includes a control ROI (cheek) and reference ROI (background corner) for Phase 2. FFC freezes repeat the previous frame, and the offset step persists until the end of the recording.
- **Known quirk:** head jitter shifts the face by 1 px, and because the cheek control ROI sits on a temperature gradient, its mean shows small steps (about 0.1-0.4 degC). This is a motion artifact the pipeline must tolerate, not a breathing peak. Jitter rate is configurable (`head_jitter_prob`, default 0.01 per frame).
- **Open issues:** all numbers are simulated from unverified datasheet recall. The face gradient and jitter size are modeling guesses, not measurements.
- **Added after review:** `figures/synthetic_five_seconds.png` (made by `scripts/plot_five_seconds.py`) shows 10 frames over 5 s with a zoomed color scale: the nostril patch is darker than its surroundings on inhale and brighter on exhale. The first overview figure uses the full 24-34 degC scale, so a ~1 degC breath swing is nearly invisible there. Look at this one first to understand the signal.
- **Next step:** Phase 2 (Sections 6.3-6.5): FFC detection/repair, ROI reduction, resample/detrend/band-pass. Stop for review after it.

### 2026-11-10 · branch `thermalexploration` · Phase 0 scaffold
- **Done:** created the `thermal/` tree from Section 5 (package, `pyproject.toml`, config dataclasses with adult/neonate profiles, `FrameSource` protocol, placeholder modules and scripts). `thermal/.gitignore` keeps `thermal/data/` out of git. `pytest` runs: 4 tests pass.
- **Decisions:** `.gitignore` lives in `thermal/` (not repo root) so nothing outside `thermal/` is touched. Placeholder modules are one-line docstrings until their phase. Installed with `pip install -e ".[dev]"` (Python 3.11).
- **Open issues:** hardware specs in Section 4 are still unverified (they are flagged in `config.py`). No camera yet.
- **Next step:** Phase 1, synthetic generator (Section 6.2). Stop for review after it.

---

## 1. Project context (why this exists)

The team is building a **contactless respiratory monitor for premature NICU infants**. Today's NICU monitors use skin-contact electrodes/stickers, which damage fragile skin, fall off, and produce many false alarms. We want continuous breathing monitoring with nothing attached to the baby.

Chosen design (from the team's decision matrix):

| Modality | What it senses | Strength | Weakness |
|---|---|---|---|
| Ultrasonic / movement (teammates) | Chest/belly motion | Works through blankets | Cannot confirm air is actually moving, so it can miss **obstructive apnea** (chest keeps moving, no airflow) |
| **Thermal (this file)** | Temperature change at the nostrils from exhaled vs inhaled air | Tied directly to **airflow** | Needs a view of the nose/face; a warm incubator shrinks the temperature difference |

The two are complementary. The thermal signal will eventually be one input channel to a **1D CNN** (time-series model) alongside the ultrasonic signal. Hardware plan: FLIR Lepton 2.5 thermal module (and Xbox Kinect v2 depth, owned by teammates) feeding a Windows laptop.

## 2. Our job: thermal sensing only

**Goal (one sentence):** Show that a thermal camera pointed at a face can turn "air moving in and out of the nose" into a clean 1D time series whose frequency matches the breathing rate, and whose amplitude collapses when breathing stops.

**The physics in one paragraph:** exhaled air is roughly 34–35 °C; inhaled room air is roughly 22–25 °C. The skin and air just below the nostrils warm on each exhale and cool on each inhale. A thermal camera sees that as a small region of pixels rhythmically brightening and dimming. Everything in this project is extracting that rhythm reliably.

### Non-goals (do NOT build these now)
- No ultrasonic code, Kinect/depth code, sensor fusion, or CNN training. Only produce a clean output contract (Section 7) they can consume.
- No automatic face/nostril detection or head-motion tracking in the first pass (fixed, hand-drawn ROI is fine).
- No infant data of any kind. Test subjects are consenting adult teammates only.
- No cloud services, web UI, or heavy frameworks.

## 3. Current status and constraint: NO HARDWARE YET

We do **not** have a Lepton, a USB breakout, or any thermal camera yet. Therefore the strategy is **simulation-first, hardware-ready**:

1. Build a physics-based **synthetic thermal video generator** with known ground-truth breathing rate and known apnea events.
2. Build and validate the entire processing pipeline against that synthetic data.
3. Put all camera access behind a `FrameSource` interface so that swapping synthetic data for a real Lepton (or a replayed recording) requires **no changes** to the processing code.
4. Write the hardware bring-up and test protocol now so the first real session is fast.

This is also the honest framing for the end-of-week demo: "pipeline validated on realistic synthetic data and ready for hardware, plus real recordings the moment a camera is available."

## 4. Hardware reference (verify against datasheets before relying on any number)

FLIR Lepton 2.5 (from memory; **verify**):
- Resolution **80 × 60** pixels (stored as shape `(60, 80)` = rows × cols).
- Frame rate **< 9 Hz** (treat as ~8.7 Hz nominal; real timestamps jitter, so never assume uniform spacing).
- Horizontal FOV roughly **50°**; at 30 cm that is roughly 3–4 mm per pixel, so a nostril is only ~1–2 pixels wide. Keep the camera close (~20–30 cm) for the PoC.
- Radiometric: output can be temperature-linear. Typical convention is **centi-Kelvin** (value × 0.01 = Kelvin) in high-gain mode. **Verify** and make the conversion a single configurable function.
- Thermal sensitivity (NETD) about 50 mK → model pixel noise as Gaussian, σ ≈ 0.05 °C per pixel.
- **FFC (flat-field correction):** the camera periodically fires a shutter to recalibrate, which causes a frozen/glitched frame and a small step change in values. Unhandled, **FFC events look like breaths**. Handling them is a required feature, not an optional one.
- Likely USB path on Windows: a PureThermal-style UVC breakout presenting the Lepton as a webcam with a 16-bit (`Y16`) format. With OpenCV this usually means disabling RGB conversion (`CAP_PROP_CONVERT_RGB = 0`) and requesting the `Y16 ` FourCC. **Verify on real hardware**; keep it isolated in `LeptonSource`.

Breathing rates to support (make them configurable "profiles"):

| Profile | Rate | Frequency band used for filtering |
|---|---|---|
| `adult` (for our testing) | ~8–30 breaths/min | ~0.10–0.70 Hz |
| `neonate` (the real target) | ~30–90 breaths/min | ~0.50–1.50 Hz |

Nyquist at ~8.7 Hz is ~4.3 Hz, so frame rate is not a limit for either profile.

## 5. Repository layout (inside the team repo)

```
thermal/
  README.md                  # short: how to run the demo
  pyproject.toml             # or requirements.txt; Python 3.11+
  src/thermal/
    __init__.py
    config.py                # dataclasses: Profile (adult/neonate), pipeline params
    sources/
      base.py                # FrameSource protocol (Section 6.1)
      synthetic.py           # physics-based generator (Section 6.2)
      file_source.py         # replay recorded .npz / thermal video
      lepton.py              # real hardware adapter (stub until hardware exists)
    recorder.py              # save frames + timestamps to .npz (Section 7)
    ffc.py                   # FFC/glitch-frame detection and repair
    roi.py                   # ROI definition and per-frame reduction
    preprocess.py            # resample, detrend, band-pass
    rate.py                  # breathing-rate estimators
    apnea.py                 # amplitude envelope + apnea flagging
    quality.py               # signal quality index
    metrics.py               # error metrics vs ground truth
    viz.py                   # all plotting helpers
  scripts/
    run_synthetic_demo.py    # end-to-end demo → figures/ + report
    sweep_ambient.py         # incubator-temperature sensitivity study
    bringup_lepton.md        # hardware day checklist (Section 10)
  tests/
    test_synthetic.py  test_ffc.py  test_preprocess.py
    test_rate.py       test_apnea.py  test_pipeline_e2e.py
  figures/                   # generated plots (committed small PNGs only)
  data/                      # GITIGNORED: raw recordings never go to GitHub
```

Conventions: type hints, small pure functions, docstrings that state units (°C, seconds, Hz, breaths/min), `numpy`/`scipy`/`matplotlib`/`opencv-python`/`pytest` only. Fixed random seeds in tests. Work on a feature branch (e.g. `thermal/phase-N-...`), small commits, no direct pushes to `main`.

## 6. Components in detail

### 6.1 `FrameSource` interface
```python
class FrameSource(Protocol):
    fs_nominal: float                     # Hz, e.g. 8.7
    def frames(self) -> Iterator[tuple[float, np.ndarray]]:
        """Yield (timestamp_seconds, frame_celsius[60, 80]) in time order."""
```
All downstream code consumes only this. Frames are float32 **°C** after conversion. Timestamps are monotonic seconds and may be non-uniform.

### 6.2 Synthetic generator (`sources/synthetic.py`) — the most important early piece
Must produce a believable 80×60 thermal video with **known ground truth**:

- **Scene:** background at ambient temperature (default 24 °C), a warm head/face blob (~33–34 °C skin) with a cooler fringe, and a small **nostril region** (a few pixels) that carries the breathing modulation. Place it at a known pixel location so tests can find it.
- **Breath modulation:** nostril-region temperature = baseline + A · w(φ(t)), where φ is breathing phase (integrate the instantaneous rate), A ≈ 0.3–1.5 °C by default, and w is not a pure sine (exhale warms faster than inhale cools; use a sine plus a weaker second harmonic). Optional first-order thermal lag (τ ≈ 0.3 s).
- **Amplitude depends on the gradient:** A should scale with (T_exhale − T_ambient). This is how we model the **incubator problem**: at ambient 22 °C the swing is large; at 34 °C it nearly vanishes.
- **Rate:** configurable constant, step changes, or slow variability (breath-to-breath jitter ~5%). Ground truth rate-vs-time is returned alongside the frames.
- **Apnea events:** configurable (start, duration) windows where breath amplitude ramps to ~0 within ~1 s. Ground truth boolean mask returned.
- **Nuisances (each individually toggleable):** per-pixel Gaussian noise σ = 0.05 °C; slow global drift (~0.02–0.05 °C/min); small random head jitter (±1 pixel); **FFC events** every ~2–3 min that repeat the previous frame for 1–2 frames and then apply a small offset step (~0.1–0.3 °C); timestamp jitter (±10%); occasional dropped frame.
- Returns: frames, timestamps, and a `GroundTruth` object (rate(t) in breaths/min, apnea mask, nostril pixel box, FFC frame indices).

### 6.3 FFC / glitch detection (`ffc.py`)
- Detect repeated/frozen frames (frame-to-frame difference ≈ 0 across the whole image) and global step changes in mean scene temperature that exceed what breathing could cause.
- Repair: mark those samples invalid, then interpolate across short gaps in the 1D signal. Also remove a persistent post-FFC offset step (e.g., re-reference the ROI signal against a nearby static background reference ROI).
- Real Lepton note: if telemetry rows are enabled, the FFC-state flag is the authoritative signal; design `ffc.py` so a telemetry flag can be plugged in later, with image-based detection as the fallback.

### 6.4 ROI and reduction (`roi.py`)
- `ROI` = rectangle `(row0, row1, col0, col1)`. Provide helper to draw it interactively on a frame (OpenCV `selectROI`) for real data; in synthetic runs use the known location (and also test a slightly wrong ROI to see how robust we are).
- Reduce each frame to one scalar: **mean** temperature in ROI (default) or **max** (option). Compare both in the report.
- **Control ROI:** same size, placed on cheek/forehead (no airflow). The pipeline must report both signals; the control should show **no** breathing peak. This is our artifact check.
- **Reference ROI:** a static background patch used to cancel global drift/FFC offsets (subtract it from the nostril signal as an option).

### 6.5 Preprocessing (`preprocess.py`)
1. Resample the irregular (t, s) samples onto a uniform grid at `fs_nominal` (linear interpolation).
2. Detrend (remove slow drift): high-pass or polynomial/moving-average removal; keep the choice configurable.
3. Band-pass: 4th-order Butterworth, band from the active profile. Offline uses zero-phase (`sosfiltfilt`). Also provide a **causal** (`sosfilt`) version because the real-time version must not look into the future.
4. Normalize only where explicitly needed; never normalize away the amplitude, because amplitude collapse is how we detect apnea.

### 6.6 Rate estimation (`rate.py`)
Implement **both** and compare:
- **Spectral:** sliding-window Welch/FFT, zero-padded for finer peak interpolation. Default window 30 s (adult) / 20 s (neonate), hop 1–5 s. Restrict the peak search to the profile band. Report breaths/min = 60 × f_peak. State the frequency-resolution trade-off in the docstring (30 s window → ~2 breaths/min raw resolution before interpolation).
- **Time-domain:** peak/zero-crossing counting on the filtered signal with a minimum-distance constraint derived from the profile's max rate.
- Each estimate also returns a **confidence** value (see 6.8). If confidence is low, return `NaN` rather than a wrong number.

### 6.7 Apnea detection (`apnea.py`)
- Compute a breathing-band **amplitude envelope** (rolling RMS, or Hilbert envelope on the filtered signal).
- Baseline = robust running reference of the envelope during recent normal breathing (e.g., rolling median over several minutes, frozen while apnea is flagged so it does not "learn" the pause).
- Flag apnea when envelope < `k × baseline` (default k ≈ 0.25) continuously for ≥ `min_duration` seconds. Clinical apnea is conventionally a pause of **≥ 20 s**, so default `min_duration = 20`; make it configurable (demos may use ~10 s).
- Output: boolean per-sample flag plus event list `(start, end)`.
- A flat signal can also mean "sensor lost the face." Add a distinct `signal_lost` status (very low envelope AND very low SNR with no recent breathing) versus `apnea` only when there was good-quality breathing immediately before. Document this limitation honestly.

### 6.8 Signal quality (`quality.py`)
- Spectral SNR: power in a narrow band around the peak (and its first harmonic) divided by remaining in-band power.
- Peak prominence and, optionally, agreement between the spectral and time-domain estimates.
- Single scalar in [0, 1] per window. Used to gate rate output and to distinguish apnea from signal loss.

## 7. Output contract for teammates (fusion / CNN)

Recorded and processed data are stored as `.npz` with these keys:

| Key | Shape | Meaning |
|---|---|---|
| `t` | (N,) | seconds, uniform grid after resampling |
| `s_raw` | (N,) | nostril-ROI mean temperature, °C |
| `s_ctrl` | (N,) | control-ROI signal, °C |
| `s_filt` | (N,) | band-passed breathing signal |
| `envelope` | (N,) | breathing-band amplitude |
| `rate_bpm` | (N,) | rate estimate (NaN when low confidence) |
| `quality` | (N,) | 0–1 |
| `apnea` | (N,) bool | apnea flag |
| `ffc_mask` | (N,) bool | samples repaired due to FFC/glitch |
| `meta` | dict | profile, ROI, fs, source type, git commit |

**Implementation notes (Phase 6, `pipeline.save_processed` / `load_processed`):** `meta` is stored as a JSON string (so files load with `allow_pickle=False`), not a pickled dict. One additive key beyond the table: `signal_lost` (N,) bool, so a consumer can tell "cannot see breathing" from apnea. `rate_bpm` is the time-domain estimate held causally per sample (NaN before the first 30 s window and wherever quality < 0.5); `quality` is held the same way; `apnea` is the retroactive event flag. `envelope` is NaN until its window fills. Demo output lives at `data/demo_processed.npz` (gitignored); regenerate with `python scripts/run_synthetic_demo.py`.

Raw-frame recordings (`recorder.py`) use a separate `.npz`: `frames` (T, 60, 80) float32 °C, `timestamps` (T,), `meta`. Raw frame files live in `data/` which is **gitignored** (they are images of people's faces; never commit them).

## 8. Phases (execute in order; stop after each)

**Phase 0 — Scaffold.** Create the `thermal/` tree, packaging, config dataclasses, `FrameSource` protocol, pytest setup, `.gitignore` entry for `thermal/data/`. *Done when:* `pytest` runs (even with trivial tests) and the package imports.

**Phase 1 — Synthetic generator.** Implement 6.2. *Done when:* a figure shows (a) a sample frame with the nostril ROI marked, (b) the raw ROI signal visibly oscillating, (c) the signal during an apnea window, (d) visible FFC glitches. Tests confirm ground-truth rate matches the injected phase, apnea mask matches the injected window, and seeds are reproducible.

**Phase 2 — Preprocessing + FFC handling.** Implement 6.3–6.5. *Done when:* a before/after plot shows FFC artifacts and drift removed, and a test proves that with FFC events enabled and handling **off**, spurious breath peaks appear, while handling **on** removes them.

**Phase 3 — Rate estimation + quality.** Implement 6.6 and 6.8 and `metrics.py`. *Done when:* on synthetic data at 10, 20, 30 breaths/min (adult) the estimate is within ±1 breath/min after the first window fills; a rate step-change is tracked with a reported lag; the control ROI yields low quality/no peak. Report MAE for spectral vs time-domain, and mean vs max reduction.

**Phase 4 — Apnea detector.** Implement 6.7. *Done when:* injected 20 s pauses are detected with start/end errors reported; false alarm count over a long clean run is reported; the `signal_lost` case is demonstrated.

**Phase 4b — Incubator sensitivity study (high value for the team).** `scripts/sweep_ambient.py`: sweep ambient temperature 22 → 36 °C and plot signal SNR, rate error, and apnea-detection success versus ambient. Goal is to quantify, with the model, when a warm incubator breaks thermal sensing. Clearly label this as a model prediction, **not** a measurement; it tells us what to measure on real hardware.

**Phase 5 — Hardware-ready adapters.** `recorder.py`, `file_source.py`, and a `lepton.py` that implements `FrameSource` and fails gracefully (clear error message) when no device is present. Include the unit conversion function and a frame-rate/timestamp logger. *Done when:* the end-to-end pipeline runs identically from `SyntheticSource` and from a recorded-then-replayed `.npz`.

**Phase 6 — End-to-end demo script.** `scripts/run_synthetic_demo.py` produces one summary figure set and a short markdown report in `figures/`: raw signal, filtered signal, estimated vs true rate, apnea flags vs truth, control ROI. *Done when:* one command reproduces everything. This is the artifact for the end-of-week showing.

**Phase 7 — Bring-up docs.** Write `scripts/bringup_lepton.md` (Section 10) and a short `thermal/README.md`.

## 9. Acceptance criteria for the proof of concept

On **synthetic** data (declared as such in every figure title):
- Rate within ±1 breath/min at steady state for 10/20/30 breaths/min (adult profile) and within ±2 for 40/60/80 (neonate profile).
- 20 s apneas detected, with start/end within ~5 s.
- Control ROI shows no breathing peak.
- FFC events do not generate false breaths or false apnea.
- All tests pass; demo reproduces from one command.

On **real hardware** (when it arrives), the same four checks in Section 10 become the pass/fail demo.

## 10. Hardware day: bring-up and real-data test protocol (for `bringup_lepton.md`)

Bring-up checklist:
1. Confirm the device enumerates (UVC) on the Windows laptop and a live image displays.
2. Confirm frame format (16-bit), frame rate, and the °C conversion (point at a known warm object and ambient; sanity-check readings against a thermometer).
3. Log timestamps and measure real frame-interval jitter.
4. Trigger/observe an FFC event and verify `ffc.py` flags it.
5. Record a 60 s static-scene clip to measure the noise floor.

Test protocol (adult teammate, room temperature, camera ~20–30 cm from the face, head resting, nostrils in view):
1. **Raw signal check:** normal breathing 60 s. Does the nostril ROI visibly oscillate?
2. **Paced breathing:** metronome at 10, 20, 30 breaths/min, 60–90 s each. Does the estimate track?
3. **Breath-hold:** hold ~20 s, then resume. Does the envelope collapse and recover?
4. **Control ROI:** cheek/forehead ROI must show no breathing peak.
5. **Ground truth:** count breaths by hand with a stopwatch (or use a chest-band/phone reference if available). Record it in the file metadata.

Safety/privacy: adult volunteers only, informed and consenting; do not commit raw face recordings; no infant or clinical data at this stage.

## 11. Risks and open questions to keep visible
- **Resolution:** 80×60 gives ~1–2 pixels per nostril; ROI placement and distance will dominate real performance.
- **Head motion:** fixed ROI fails if the head moves; auto-tracking is future work.
- **Warm incubators** shrink the gradient (Phase 4b quantifies this); **humidity/condensation** and the **canopy material** (many plastics block long-wave IR) are real-world unknowns that need a real test. Do not claim through-canopy sensing without measuring it.
- **Swaddling/blankets** can hide the face; thermal needs a clear view, which is exactly why ultrasonic is its partner.
- **Obstructive vs central apnea:** thermal detects absence of airflow, which covers both, but only while the nose is visible.
- **No hardware yet:** open action for the human, not for Claude Code. Ask the course staff or a lab for a loan of any radiometric thermal camera, and in parallel order a Lepton 2.5 + USB breakout. Any thermal recording (even from a handheld thermal camera) can be converted to `.npz` and replayed through `FileSource` to get a real-data demo.
- **Unverified numbers:** every hardware spec in Section 4 is from memory and must be checked against the datasheet.
- **Unverified Lepton read path (added in Phase 5, all in `sources/lepton.py`, none tested on a device):** the breakout appears as a UVC webcam with `Y16 ` frames; OpenCV needs `CAP_PROP_CONVERT_RGB = 0` plus the Y16 FOURCC; raw values are centi-Kelvin (x 0.01 K); frames arrive as uint16 (60, 80) or as 8-bit byte pairs of width 160 (little-endian assumed); timestamps are host time at read (no hardware timestamps), so real jitter is unknown; FFC telemetry is not read (image-based detection only); Windows may need `backend=cv2.CAP_DSHOW`. First hardware day must confirm each one (`scripts/bringup_lepton.md`, Phase 7).

## 12. Instructions to Claude Code (how to behave in this session)
- Read this file fully before writing code. Restate the current phase and its "done when" criteria before starting it.
- One phase at a time. At the end of each phase: run the tests, generate the figures, summarize in a few sentences, and **stop for review**.
- Explain *why* each design choice was made in plain language (the user learns best from intuition and visuals, not just steps). Keep explanations to one or two concepts at a time; do not dump everything at once.
- Prefer fixed, deterministic procedures over guess-and-tune methods. Where a parameter must be chosen, expose it in config and say how it was chosen.
- Label synthetic results as synthetic everywhere. Never present simulated performance as measured performance.
- If a hardware detail is uncertain, say so, put it behind a config option, and add it to Section 11 rather than guessing silently.
- Keep changes inside `thermal/`. Ask before touching anything outside it.
