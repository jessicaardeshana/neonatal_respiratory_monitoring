# Kinect V2 depth, infrared, and RGB acquisition

This separate project reuses `/Users/jessicaardeshana/libfreenect2-metal/build/lib/`.
No files or configuration in that installation were changed. The earlier
depth-only implementation is preserved in `backups/depth_only_v1/`.

## Continuous acquisition platform

Open the desktop control panel from VS Code's integrated Terminal:

```sh
cd /Users/jessicaardeshana/Desktop/nicu_project
cmake --build build
python3 python/acquisition_platform.py
```

1. Close Protonect and other camera programs.
2. Choose a save folder (an external disk is supported).
3. Click **Start recording**. Depth, IR and RGB are saved continuously, with
   successive frames and per-frame timestamps. There is no preset end time.
4. Watch live previews, frame counts, recent saved-frame rates, queue drops,
   session elapsed time, saved size and free disk space.
5. Click **Stop recording**. Wait for file flushing and camera cleanup before
   starting another session. Closing the panel also requests a graceful stop.
6. Click **Review recording** to browse the saved sequence with the frame slider.

The previous recorder already stored a time sequence; its capture duration was
fixed. This platform adds Start/Stop control and indefinite recording. Each Start
creates a unique session folder; each stream is appended to disk throughout the
session. Working memory stays bounded rather than growing with the recording.
The live previews update about once per second using the latest flushed frames;
recording continues at the sensor's delivered rate independently of that preview
refresh. Previews are not synchronized triplets. Depth uses a fixed display range;
IR display contrast adapts per preview. Saved measurements are unchanged.

The panel uses Python's Tkinter (available in the inspected interpreter) and
NumPy. `python/acquisition_session.py` manages the C++ child process and sends a
Stop signal; `python/acquisition_platform.py` supplies controls and previews. No
camera SDK bindings, web server, or library reconfiguration are needed.

You can also record continuously directly in Terminal:

```sh
./build/depth_capture recordings/continuous_01 --continuous
# Equivalent: ./build/depth_capture recordings/continuous_01
# Stop with Ctrl+C, Escape in the depth preview, or closing that preview.
```

Timed capture still works: append a number of seconds instead of `--continuous`.
Continuous-session metadata sets `continuous: true` and `requested_seconds: null`.
`status.json` is atomically refreshed after all streams have been flushed; it
reports readable saved-frame counts, queue drops, formats, elapsed time and free
space. The panel reads only complete frames covered by that status. Process logs
are saved beside the session folder as `<session_name>.log`, including startup
errors even if no recording directory could be created. The final summary and
status record the stop reason and any reported SDK error.

At full rate, uncompressed capture can use about **18 GB per minute**. There is
no duration limit, but free disk space and sustained write speed still limit a
session. The recorder refuses to start with less than 2 GiB available and checks
space about once per second, stopping automatically below that reserve. A queue
full of incoming frames causes counted drops; uninterrupted operation does not
guarantee every camera frame is retained. Disconnects or stalled streams stop
with an error rather than silently continuing or reconnecting.

Continuous-mode verification captured **118 depth, 118 IR and 121 RGB frames**
until an explicit Stop signal. All loaded successfully, with zero recorder queue
drops and zero saved SDK frame-error statuses; upstream sequence gaps occurred.
The SDK still reported its existing USB interface-release failure on close, so
this session is explicitly marked `sdk_close_error` although the files validate.
The platform shows that error in its status/log. No driver or library was changed.
The desktop panel and all three live-preview rendering paths were checked using
those saved frames. The Stop/process-control checks also pass with a fake capture
process. This verifies a short continuous run, not long-duration stability.

## What Protonect's four panels show

Confirmed from the installed source: `examples/Protonect.cpp` lines 420–493
and `examples/viewer.cpp` (rendering and grayscale shader).

| Panel label | SDK output | Native dimensions / values | Derived? |
| --- | --- | --- | --- |
| RGB | `Frame::Color` | 1920 × 1080, decoded 8-bit BGRX or RGBX | Native color output, no depth registration |
| ir | `Frame::Ir` | 512 × 424 float32, SDK intensity nominally 0–65535 | Native IR intensity output |
| depth | `Frame::Depth` | 512 × 424 float32, millimeters | SDK-computed depth from time-of-flight data, no color registration |
| registered | `Registration::apply(rgb, depth, &undistorted, &registered)` | 512 × 424 color samples mapped into the undistorted depth view | Derived from RGB, depth, and calibration |

The fourth panel is registered **color**, not another depth stream. Protonect
also computes an undistorted depth buffer internally; it does not add that as a
fifth panel. The viewer converts float IR/depth to grayscale by dividing by 4500;
those display brightnesses are not the numerical samples we save.

The three native outputs are separate data products, but IR and depth originate
from the same infrared time-of-flight sensor. RGB comes from the color camera.
Here “raw” means the unregistered SDK-decoded outputs, **not** encoded USB packets
or Bayer/JPEG sensor data. The active TurboJPEG decoder produces BGRX; the recorder
accepts and records either supported BGRX/RGBX format without channel conversion.

IR intensity measures reflected infrared signal. It is not temperature or
millimeters of displacement. Reflectance, angle, illumination, exposure and
processing can affect its values. Any IR-based motion method needs separate
validation. No IR displacement inference or multimodal fusion is implemented.

## Build and capture in VS Code's integrated Terminal

Close Protonect and any other Kinect program first.

```sh
cd /Users/jessicaardeshana/Desktop/nicu_project
cmake -S . -B build
cmake --build build
./build/depth_capture recordings/multistream_01 15
```

The executable retains its previous name, `depth_capture`, but now records all
three streams. Use a **new directory** each time; existing directories are refused.
The live window previews depth (500–4500 mm display range). Terminal counters show
saved frames and queue drops separately for all streams. Escape, closing the
window, or Ctrl+C stops; duration starts at the first incoming frame. A missing
stream triggers a 10-second timeout.

Uncompressed RGB is large: at 30 fps, all three streams together need about
301 MB/s and 4.5 GB for 15 seconds. Ensure enough space. NumPy exports use roughly
another recording's worth of disk. No extra packages are needed in the inspected
`/opt/anaconda3/bin/python3` environment (NumPy and Matplotlib are available).

## Three-stream Python viewer

```sh
python3 python/view_recording.py recordings/multistream_01
python3 python/view_recording.py recordings/multistream_01 --frame 40
python3 python/view_recording.py recordings/multistream_01 --check-only
python3 python/view_recording.py recordings/multistream_01 --export-npy
```

Use the depth-frame slider to browse. Depth, IR, and RGB appear side by side with
individual frame indices, SDK status and timestamp offsets. IR/depth display
contrast uses per-frame percentiles, which do not modify saved values. Do not
compare the apparent brightness across frames as if display scaling were fixed.
RGB conversion respects each frame's BGRX/RGBX flag. Native views have different
resolutions, optics and viewpoints: pixel coordinates are not interchangeable.

The viewer chooses nearest frames using the **shared host USB-arrival clock**.
If any arrival timestamps are unavailable, it uses the common host callback
clock for all streams and prints the clock selection. It does not use separately
zeroed device elapsed times for alignment. Time offsets over 100 ms are marked
`TIME GAP`. Nearest frames are not guaranteed exposure-synchronized; this is
visual browsing, not synchronization calibration or fusion.

## Files and module boundaries

- `src/depth_capture.cpp`: bounded ownership queue and per-stream writers.
  SDK callbacks enqueue; the main loop writes files and previews depth. The
  24-frame queue drops incoming frames when full and counts them by stream.
- `python/recording.py`: memory-mapped loading, validation, channel conversion,
  shared-clock selection and nearest-frame lookup. Supports legacy depth files.
- `python/view_recording.py`: visualization and optional NumPy export.
- `python/depth_displacement.py`: depth-only ROI surface motion analysis.
  It opens only the depth file, even if IR/RGB are absent or damaged.
- `tests/test_recording.py`: synthetic numerical/timing/ROI checks.
- `tests/test_acquisition_session.py`: continuous Start/Stop and complete-frame preview checks.

Each schema-2 recording contains:

| File | Contents |
| --- | --- |
| `depth.f32` | Little-endian float32 `(N_depth, 424, 512)` in mm |
| `ir.f32` | Little-endian float32 `(N_ir, 424, 512)` SDK intensity |
| `rgb.u8` | uint8 `(N_rgb, 1080, 1920, 4)`, native BGRX/RGBX; X unused |
| `depth_timestamps.csv`, `ir_timestamps.csv`, `rgb_timestamps.csv` | Separate per-stream timing and frame metadata |
| `metadata.json` | Schema, dimensions, dtypes, units, device, SDK revision, pipeline, depth settings |
| `summary.json` | Final saved counts, queue drops, frames pending at stop, exit code |

CSV fields: frame index, raw device ticks, per-stream unwrapped device elapsed
seconds, host USB-arrival microseconds, common host callback elapsed seconds,
sequence, SDK status, pixel format, exposure, gain and gamma. Exposure/gain/gamma
are preserved SDK fields; they are not assumed to be calibrated IR metadata.

Device ticks are uint32 in 0.125 ms units (typical increments 266 at 30 Hz or
533 at 15 Hz). Rollover is unwrapped; resets may produce a large jump. Host
arrival and callback clocks have different origins: compare differences within
a clock, not values across clocks. Device elapsed origins differ by stream.
The viewer reports actual delivered rate, sequence gaps and SDK errors.

Float values and invalid values are unchanged. Depth validity is finite and
positive. Nonzero-status frames are preserved and flagged. IR is saved without
applying depth validity rules. Data and CSV sizes must agree; the loader rejects
partial writes rather than silently aligning mismatched files. Periodic flushing
cannot guarantee recovery from force quitting or a full disk. Pending frames at
stop are explicitly discarded and counted before SDK resources are destroyed.

```python
import sys
sys.path.insert(0, 'python')
from recording import load_streams
streams, metadata = load_streams('recordings/multistream_01')
depth = streams['depth'].frames        # mm, memory mapped
ir = streams['ir'].frames              # SDK intensity, memory mapped
rgb_native = streams['rgb'].frames     # native 4-channel bytes
depth_times = streams['depth'].timestamps
# After --export-npy: np.load('.../depth.npy', mmap_mode='r')
```

## First depth-only displacement analysis

```sh
python3 python/depth_displacement.py recordings/multistream_01
```

Click two opposite corners in the depth image to choose an ROI. The script takes
the median of finite, positive depths in that rectangle per frame. It rejects
frames with SDK errors or less than 70% valid ROI pixels, leaving gaps as NaN.
The recording's temporal median is the baseline; positive relative change means
the surface moved toward the camera. It plots that change in millimeters and
valid-pixel fraction against actual depth timestamps. This is a camera-axis
surface-motion proxy; body/camera motion, changing visible pixels and depth noise
can also produce it. It does not identify breathing or estimate respiratory rate.

For repeatable selection and optional CSV export (refuses overwrite):

```sh
python3 python/depth_displacement.py recordings/multistream_01 \
  --roi 180 20 40 40 --output recordings/multistream_01/depth_roi.csv
```

`--roi` means X Y WIDTH HEIGHT in native depth pixels; the example is not an
anatomical recommendation. Use `--min-valid-fraction 0.7` to set the quality
threshold or `--no-show` with an explicit ROI for terminal-only analysis. No
interpolation, frequency filtering, slow-drift fitting, respiratory-rate
estimation, IR tracking, RGB region transfer, or fusion is applied.

## Inspection and verification

The existing generated `build/libfreenect2/config.h` and dylib enable CPU,
OpenGL and OpenCL (including KDE); **Metal is not compiled in**, despite the
folder name and requested cache option. The default selection uses the existing
SDK fallback chain; the tested actual pipeline is `opengl`. CMake links the
existing dylib directly with source and generated headers because its build-tree
package config expects an installed layout. A project-local SDK include-path
workaround handles the installed Apple compiler's missing libc++ search path.

Depth clipping/filter defaults remain 0.5–4.5 m, bilateral and edge-aware
filtering enabled; they are explicitly applied and saved. These settings do not
establish small-motion precision or neonatal suitability.

A live 3-second test in `recordings/three_stream_check_01` saved **87 depth,
87 IR, 77 RGB** frames. Python loaded and rendered all three, with a sample
RGB/depth offset of +11.3 ms. Actual delivered rates were 28.667 fps for depth/IR
and 28.500 fps for RGB. All saved SDK frame statuses were zero, but sequence gaps
occurred (two transitions per stream); queue drops were zero. A static depth ROI
also passed the analysis smoke check. These are acquisition checks, not a
controlled breathing or precision experiment.

The SDK reported a USB interface-release error during that test's shutdown.
The recorder's GLFW destruction order was subsequently corrected and SDK
stop/close failures now set a nonzero exit status. A second live attempt was
blocked by the SDK reporting a kernel driver owning control/RGB interface 0;
the updated cleanup path is therefore not yet verified on a successful capture.
No driver was detached and no system/library configuration was changed.
Close other camera programs and reconnect Kinect USB/power before the next run.
If it persists, check the known-working Protonect, then close it before retrying.

Synthetic checks pass for exact float/byte preservation, BGRX/RGBX conversion,
asynchronous nearest-frame matching, shared-clock fallback, invalid/status
rejection, partial files, timestamp mismatch, and signed depth changes:

```sh
python3 -m unittest discover -s tests -v
```

Use non-patient objects or a simulated breathing setup for controlled tests.
