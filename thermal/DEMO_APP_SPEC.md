# DEMO_APP_SPEC.md: Thermal Respiratory Sensing, Interactive Demo + Device App

> Plan for the interactive app. Companion to `THERMAL_SPEC.md` (the science, pipeline and session log).
> Status (2026-11-10, 18:36): **steps A-D built and pushed; E, F, G still to build.** See "Build status" and "Deviations from the plan" right below. Owner: Alan. Keep all code inside `thermal/`.
> Read `THERMAL_SPEC.md` first (especially Sections 6-7, 11 and the session log) so you know what the pipeline does.

---

## Build status (as of 2026-11-10, branch `thermalexploration`)

| step | what | status | commit |
|---|---|---|---|
| A | Backend: scenarios, service, API, `run_app.py`, `app` extras, API tests | DONE | 50b3975 |
| B | UI shell + Monitor + thermal player (Checkpoint 1) | DONE, redesigned after Alan's feedback | 50b3975, 6330053 |
| C | Pipeline view: 7 stages, before/after, plain-language text | DONE | d1b392e |
| D | Lab: sliders, presets, live rerun (Checkpoint 2) | DONE | f469f9d |
| E | Results & limits page + guided tour | NOT STARTED (data endpoint `GET /api/results` exists; the tab and the header "Guided tour" button are placeholders) | |
| F | Device screen: safe detection, Connect, live view, ROI picker, Record | NOT STARTED (`devices.py`, `live.py` do not exist yet) | |
| G | Polish: 1920x1080 check, Full-scene colors, README | NOT STARTED | |

Run it: `pip install -e ".[dev,app]"` then `python scripts/run_app.py` (port 8765). Tests: `tests/test_app_api.py` (about 65 of the 146 tests).

## Deviations from the plan (what changed while building, and why)

- **No external chart library.** The plan said "vendor uPlot". We wrote our own small canvas chart helper instead (`static/js/chart.js`): no download, no dependency, works offline. Same for the thermal color palette (own inferno lookup).
- **Monitor redesigned (Alan's feedback after Checkpoint 1):** the video took over the screen and he wanted to compare graphs without scrolling and disliked the neon look. Now: a small zoomed nose/cheek view (Full frame and Face/Scene colors one click away), a fixed-height status bar instead of a pop-in alarm banner (so alarms never shift the layout), and three graphs (signal, rate vs truth, breathing strength vs threshold) on ONE shared time axis with 30 s / 60 s / whole-recording windows; fits one screen from 1280x720. Palette is flat graphite with muted teal/amber/red used only for meaning; no glows or pulsing.
- **Extra endpoints** beyond the plan: `GET /api/spectrum` and `GET /api/window` (so the Pipeline view shows the real estimator's spectrum, peaks and numbers). `rate.py` exposes `window_spectrum` and `window_peaks` for this (no behavior change).
- **Lab additions:** seven one-click presets, a recording-length slider, and a server-generated verdict + plain-language notes (so wording is tested, and based on measured results). Slider limits clamp dependent values (the pause must end before the recording does).
- **Detector fix found through the Lab:** pause labeling apnea vs signal_lost now uses the best recent quality plus a strength floor (see `THERMAL_SPEC.md` log, step D). Phase 4 numbers unchanged; one Phase 4b cell changed (33 degC, head moving).
- **Pipeline/Lab views are built lazily** on first visit so they do not move the Monitor's playhead; `state.loadRun` swaps the run shown by Monitor and Pipeline ("Watch this in the Monitor").
- **Light theme dropped** (Alan chose dark; tokens are in `static/css/app.css` so a re-skin is small).

## Still to build (details unchanged in Sections 4-11)

- **E:** Results & limits UI (cards from `/api/results` + the honest-limits list in `app/results.py`) and the guided tour (12 steps, Section 5; Next/Back; panel highlights; free explore always one click away).
- **F:** `devices.py` (USB-identity detection, never opens a camera), `live.py` (rolling buffer, re-run the batch pipeline every 1-2 s, WebSocket, labeled "windowed, not causal"), Device screen, ROI picker (replaces OpenCV `selectROI`), Record to `data/`. Tests only with injected fakes. Lepton USB IDs and the whole read path are unverified (spec Section 11).
- **G:** visual check at exactly 1920x1080 and in Full-scene colors; README section; anything Alan asks for after the team sees the recording.

---

## 1. Why this exists

Alan wants to show his team, by screen recording with a voiceover, that thermal sensing of breathing works. A set of static figures is not convincing enough. The demo should let a viewer **see the thermal video, see exactly how each calculation turns it into a breathing rate and an apnea alarm, and play with the conditions that make it work or break.**

It is also the first draft of the **product's software side**: the screen a clinician or engineer would use with the real hardware. So the app has a **Device** screen that detects a FLIR Lepton when one is plugged in and, when connected, shows the real feed through the same pipeline.

**Hard honesty rule:** today every number comes from a physics-based simulation, not a camera. The UI must never let a viewer mistake simulated data for measured data (see Section 8).

## 2. Decisions made (from Alan, 2026-11-10)

| Question | Decision |
|---|---|
| App type | **Local web app**: Python backend running our real pipeline + polished browser UI at `localhost`. Not a shared web page, because it must be able to talk to a real camera. |
| Features in version 1 | **30 s frame playback**, **step-by-step pipeline view**, **sliders that change the simulation**, **Results and limits page**. |
| Product side today | **Demo + Device screen**: detect a Lepton by USB identity, show status, offer Connect, run live feed through the same pipeline when connected. Live path is built but **untested until hardware exists**, and the UI says so. |
| Look and feel | **Dark clinical monitor.** Dark background, bold numbers, thermal color palette. |
| Presenter help | **Guided tour + free explore.** A "Start tour" button walks through the story with captions and highlights; free explore is always one click away. |
| Opening story | **Normal breathing, speed-up, pause, alarm**: about 30 s of steady breathing, breathing speeds up, a 25 s pause raises an apnea alarm, then it recovers. A camera recalibration (FFC) glitch happens along the way and is handled. |
| Name | **Unbranded**: "Thermal Respiratory Sensing: Proof of Concept". |

## 3. Scope

**In version 1**
- Thermal video player (play, pause, scrub, speed) over a window of the recording, with ROI boxes and a temperature readout.
- Monitor view: big breathing rate, status, apnea alarm banner, live signal strip.
- Pipeline view: click through every stage of the processing with a plot and a plain-language "what and why" for each.
- Lab sliders: breathing rate, inject an apnea pause (length, time), incubator temperature, noise, head movement, FFC events. Pipeline reruns and every view updates.
- Results and limits page: accuracy numbers, incubator sweep, acceptance checklist, and an honest list of what is not met or not tested.
- Guided tour mode.
- Device screen: safe camera detection, Connect, live feed, ROI picking, optional recording to the gitignored `data/` folder.

**Not in version 1 (non-goals)**
- No clinical claims, no alarm thresholds presented as validated, no patient data of any kind. This is a proof of concept, not a medical device.
- No cloud, accounts, or sharing server. The app binds to `127.0.0.1` only.
- No ultrasonic, Kinect or fusion views (teammates' work).
- No auto face/nostril detection or head tracking (future work in the spec).
- No standalone shareable HTML copy. If wanted later, it is a separate project.

## 4. What the viewer sees (screens)

> As built, the Monitor layout differs from the first sketch below: see "Deviations from the plan" above. The Pipeline and Lab screens match the plan, with the additions listed there.

Top bar: title, a **persistent data-source badge**, the Tour button, and navigation tabs.

1. **Monitor** (opening screen). Left: thermal video player. Center: huge breathing rate (breaths/min) with quality indicator and a small "true rate" tag in demo mode. Right: status card (Normal / Rate high / APNEA / Signal lost), alarm banner that turns red during an apnea event, event list. Bottom: scrolling signal strip with the true pause shaded in demo mode and detected pauses marked.
2. **Pipeline.** A horizontal stepper with the stages below. Each stage shows its plot, the setting that controls it, and two short lines: *what this does* and *why we need it*. A split compare toggle shows before vs after for the current stage.
   1. Frames and ROI (nostril, control cheek, background reference)
   2. ROI average to one number per frame (raw signal)
   3. FFC repair (frozen frames and level steps found and fixed)
   4. Remove drift and background (reference subtraction)
   5. Resample and band-pass (breathing band only)
   6. Rate estimation (spectral and time-domain, side by side, plus quality)
   7. Amplitude envelope and apnea decision (baseline, 0.25x threshold, minimum duration)
3. **Lab.** Sliders and toggles (Section 6) beside live views of the monitor and signal. A "Reset to story" button.
4. **Results and limits.** Cards generated from the real report files, plus the honest-limits list (Section 9).
5. **Device.** Connection status, Scan, Connect, live view, ROI picker, Record, and a plain statement of what is and is not verified.

## 5. The guided tour (story script)

Each step highlights a panel, shows a one- or two-sentence caption, and waits for **Next**. Alan narrates over it. Free explore is one click away at any time.

1. What problem this solves: contactless breathing monitoring, no stickers (Monitor, no highlight, just the title card).
2. The thermal image: warm face, cooler room; point at the nostril box.
3. Breathing is a flicker: nostril temperature rises on exhale, falls on inhale (player + a zoomed 5 s strip).
4. From pictures to one line: average the box each frame (Pipeline stage 2).
5. The mess real cameras add: drift and the FFC glitch (Pipeline stage 3-4, show before/after).
6. Keep only breathing frequencies (stage 5).
7. Reading the rate: counting peaks and the spectrum agree (stage 6).
8. The speed-up: rate tracking follows it, with a lag of about one window.
9. The pause: amplitude collapses, the alarm fires, then recovery (stage 7 and Monitor).
10. Break it yourself: open the Lab, drag the incubator temperature up and watch the signal fade (Lab).
11. What we know and what we don't (Results and limits).
12. Next step: connect the real camera (Device).

## 6. Lab sliders

| Control | Range | Maps to |
|---|---|---|
| Breathing rate | 8-90 breaths/min (profile switches adult/neonate band automatically) | `SyntheticConfig.rate_bpm` |
| Rate change | add a step at a chosen time | `rate_steps` |
| Apnea pause | on/off, start time, length 5-60 s | `apnea_events` |
| Incubator / ambient temperature | 22-36 degC | `ambient_c` (swing shrinks to 0 at 34.5 degC) |
| Sensor noise | 0-3x the default 0.05 degC | `noise_sigma_c` |
| Head movement | off / small / large | `head_jitter`, `head_jitter_prob` |
| Camera recalibration (FFC) events | off / on, interval | `ffc`, `ffc_interval_s` |
| Detector strictness | minimum pause length (10 / 20 s), quality cutoff | `ApneaConfig`, `min_quality` |

Rerun target: under about 3 s for a 150 s recording; the default story (420 s) is cached. Show a spinner and keep the previous result visible while recomputing.

## 7. Architecture

```
thermal/
  src/thermal/app/
    scenarios.py     # slider schema, presets, parameter validation -> SyntheticConfig (BUILT)
    service.py       # runs run_pipeline, caches by parameter hash, builds payload + spectrum/window analysis + verdict/notes (BUILT)
    results.py       # report tables + honest-limits list (BUILT; UI not yet)
    server.py        # FastAPI, 127.0.0.1 only: /api/{health,schema,run,frames,spectrum,window,results} (BUILT)
    devices.py       # SAFE camera detection (no frame access)  (NOT BUILT: step F)
    live.py          # live session: windowed re-processing of a rolling buffer  (NOT BUILT: step F)
    static/          # index.html, css/app.css, js/{main,monitor,pipeline,lab,player,chart,util}.js (BUILT; no build step)
  scripts/run_app.py # one command: python scripts/run_app.py (BUILT)
  tests/test_app_api.py (BUILT)   # device/live tests come with step F
```

- **Backend:** FastAPI + uvicorn (new optional dependency group `app` in `pyproject.toml`). It calls the existing modules (`SyntheticSource`, `run_pipeline`, `ApneaConfig`, ...). No pipeline logic is duplicated in the UI.
- **Frontend:** plain HTML/CSS/JS with `<canvas>` for the thermal player and a small vendored chart library (uPlot, MIT) for signals. No Node or build step, so `pip install` + one command is all that is needed. Fonts: system stack, no CDN, so it works offline during a recording.
- **Data flow (demo):** UI sends scenario parameters -> `POST /api/run` -> server simulates + runs the pipeline -> returns the stage arrays (JSON, downsampled for display) plus a run id. Frames are served in chunks by `GET /api/frames?run=..&start=..&end=..` as quantized 16-bit binary (centi-degrees) so the 30 s player is smooth.
- **Per-stage payload** (one place the UI reads everything): ROI boxes, `s_raw`, `s_clean`, FFC marks, `s_filt`, rate estimates + quality, envelope + baseline + threshold, events, and (demo only) ground truth.
- **Live data flow:** `LeptonSource` -> rolling buffer (about 60-90 s) -> every 1-2 s re-run the batch pipeline on the buffer -> push results over a WebSocket. This is **not truly causal streaming** (the filters are zero-phase on the buffer); the UI labels it as such. A fully causal chain is future work.
- **Reuse, don't fork:** the app only imports from `thermal.*`. Any needed pipeline fix goes in the library with a test.

## 8. Honesty and safety rules (non-negotiable)

1. A **persistent badge** is always visible: `SIMULATED DATA` (demo) or `LIVE CAMERA, UNVERIFIED HARDWARE PATH` (live). Demo-only items like "true rate" and the shaded true pause are labeled as simulation ground truth and never shown in live mode.
2. Never present simulated accuracy as measured accuracy. Results page figures carry "model prediction" labels exactly as in the spec.
3. **Camera detection never opens a camera.** Detection lists USB devices and matches the PureThermal/Lepton vendor and product IDs; it does not touch any webcam. A camera is opened only after the user clicks **Connect**. (On a Mac, probing video device indexes would switch on the user's webcam.) The USB IDs are **unverified** and must be confirmed on hardware; the UI also offers a manual device-index field.
4. Server binds `127.0.0.1` only. No data leaves the machine.
5. Live frames are **never saved unless the user clicks Record**, and recordings go to the gitignored `thermal/data/` (existing `recorder.py` rule). Raw face images never go to GitHub.
6. No adult-subject or infant data is bundled. Adult volunteers only when hardware arrives, with consent (per the spec).
7. The app states it is a proof of concept, not a medical device.

## 9. Results and limits page: content

Generated from the existing report files where possible so the numbers cannot drift from the code:
- Accuracy: rate error by rate (Phase 3 report), apnea detection (Phase 4), incubator sweep (Phase 4b), demo acceptance checklist (Phase 6).
- **Honest limits list** (must be shown, not hidden):
  - All numbers are from a model; no camera data yet.
  - 20 s pause detection is borderline (26-28 of 30 caught); the rule can be loosened at a cost.
  - Warm incubators degrade apnea detection earlier than rate estimation (about 28 degC with head motion, about 33 degC with a still head); head motion is the biggest factor.
  - A face leaving the view looks like apnea.
  - Lepton read path, units and USB IDs unverified; live mode untested.
  - Canopy material, humidity and distance not modeled.
  - Pipeline uses a zero-phase filter, so timing is optimistic versus a fully real-time version.

## 10. Look and feel

- **Dark clinical monitor.** Near-black blue-gray background, one calm accent for normal, amber for warnings, red reserved for apnea alarm. Large tabular numerals for the rate. Thermal frames use an inferno-style palette with a labeled color bar in degC.
- Designed for a 1920x1080 screen recording: generous spacing, readable at 100% zoom, no tiny text, smooth 8.7 fps playback, animated but not flashy. A **Presenter** toggle hides dev chrome (run id, debug).
- Layout holds down to a laptop screen. Keyboard: space = play/pause, arrows = step, T = tour.
- Defined as color/spacing tokens in one CSS file so a re-skin (for example a light theme) is a small later change.

## 11. Build plan (checkpoints stop for Alan's review)

| Step | What | Done when |
|---|---|---|
| A | Backend: scenarios, service, API, `run_app.py`, `app` dependency group, API tests | `python scripts/run_app.py` serves; `/api/run` returns all stage payloads for the default story; frame chunks decode correctly; tests pass |
| B | UI shell + **Monitor** screen + thermal player | **Checkpoint 1:** Alan sees the default story playing with rate, alarm and signal strip |
| C | **Pipeline** stepper with all 7 stages and before/after compare | every stage plots real pipeline output and has its what/why text |
| D | **Lab** sliders with live rerun | **Checkpoint 2:** dragging incubator temperature visibly kills the signal and the status flips to Signal lost |
| E | **Results and limits** page + guided **tour** | tour runs end to end in about 5-8 min of narration; limits list complete |
| F | **Device** screen: safe detection, Connect, live view via `live.py`, ROI picker, Record; fully tested with a fake capture | detection reports "none" with no hardware; fake-camera live session runs through the pipeline; no test ever opens a real device |
| G | Polish pass, visual review in the browser at 1920x1080, README section, session log | **Final checkpoint:** screenshots reviewed, `pytest` green, one command starts everything |

Each step is committed on `thermalexploration` and the session log in `THERMAL_SPEC.md` is updated. Nothing is pushed to `main`.

## 12. Acceptance criteria

- One command (`python scripts/run_app.py`) starts the app and opens the browser; nothing else to install beyond `pip install -e ".[dev,app]"`.
- The default story shows steady breathing, a speed-up, a 25 s pause with an apnea alarm, a handled FFC glitch, and recovery, all from the real pipeline.
- Every pipeline stage is visible, with real data and a plain explanation.
- Each slider changes the simulation and every view updates; extreme settings degrade the result honestly (status becomes Signal lost, rate shows no answer) rather than faking success.
- With no hardware attached, the Device screen says so and the app stays in simulator mode. With a (fake) camera, the live path runs end to end.
- The simulated-data badge is always visible in demo mode. No test or code path opens a real camera without an explicit Connect click.
- All existing tests still pass; new tests cover the API, scenario mapping, device detection (with injected fakes) and the live session.

## 13. Risks and open questions

- **Slider rerun speed.** RESOLVED: a 180 s recording reruns in about 0.2-1 s (cached by parameter hash); the Lab debounces 300 ms and cancels stale requests.
- **USB IDs for the Lepton breakout are from memory.** Detection may miss the real device until confirmed; the manual index field is the fallback.
- **Live path is a best guess** (see `THERMAL_SPEC.md` Section 11). It will say "unverified" on screen until hardware day.
- **Windowed live processing is not real-time-causal.** Acceptable for a proof of concept; flagged in the UI.
- **Dependencies:** FastAPI, uvicorn (and optionally websockets) are new. uPlot is vendored (MIT).
- **Phase 7 (bring-up docs)** is deliberately moved **after** this app, because the Device screen and live path shape what the hardware-day checklist should say.
