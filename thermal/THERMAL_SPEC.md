# THERMAL_SPEC.md — Thermal Respiratory Sensing (Proof of Concept)

> Briefing for a Claude Code session. Read this whole file first, then work through the phases in order.
> **Work one phase at a time. Stop at the end of each phase, show the results (plots + test output), and wait for approval before starting the next phase.**
> Owner: Alan (thermal sensing lead). Rest of the team owns the ultrasonic, Kinect/depth, and fusion/CNN work. Keep all thermal code inside `thermal/` so we do not collide with their work.

---

## STATUS / SESSION LOG (read this first, update it with every commit/push and every break)

**Rules:** never push to `main` until Alan says so; push only to feature branches. Newest entry on top.

**Current state:** Phase 0 complete (awaiting review). Next: Phase 1, synthetic generator.

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

## 12. Instructions to Claude Code (how to behave in this session)
- Read this file fully before writing code. Restate the current phase and its "done when" criteria before starting it.
- One phase at a time. At the end of each phase: run the tests, generate the figures, summarize in a few sentences, and **stop for review**.
- Explain *why* each design choice was made in plain language (the user learns best from intuition and visuals, not just steps). Keep explanations to one or two concepts at a time; do not dump everything at once.
- Prefer fixed, deterministic procedures over guess-and-tune methods. Where a parameter must be chosen, expose it in config and say how it was chosen.
- Label synthetic results as synthetic everywhere. Never present simulated performance as measured performance.
- If a hardware detail is uncertain, say so, put it behind a config option, and add it to Section 11 rather than guessing silently.
- Keep changes inside `thermal/`. Ask before touching anything outside it.
