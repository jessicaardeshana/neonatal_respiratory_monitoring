# Kinect V2 raw depth acquisition — first milestone

This separate project reads your existing libfreenect2-metal build. It does not
reconfigure, rebuild, install into, or edit that installation. Testing is for
non-patient objects or a simulated breathing setup.

## Run in VS Code's integrated Terminal

Close Protonect first: only one application should access the Kinect.

```sh
cd /Users/jessicaardeshana/Desktop/nicu_project
cmake -S . -B build
cmake --build build
./build/depth_capture recordings/test_01 15
python3 python/view_recording.py recordings/test_01
```

Use a **new output directory** each time. Existing directories are refused.
The preview shows closer valid depths brighter, using a fixed 500–4500 mm display
range; invalid pixels are black. That display scaling never changes saved data.
The program prints dimensions, delivered frame rate, valid-pixel count, mean
valid depth, and SDK status. Escape, closing the preview, or Ctrl+C stops cleanly.
The duration starts at the first received frame; startup takes additional time.
There is a 10-second frame timeout. A 15-second recording at 30 fps uses roughly
391 MB (373 MiB); NumPy export creates an additional copy on disk.

Python's NumPy and Matplotlib are already available in the inspected `python3`
environment (`/opt/anaconda3/bin/python3`), so no installation is needed. If VS
Code uses another interpreter, select that interpreter or invoke it explicitly.

```sh
python3 python/view_recording.py recordings/test_01 --frame 100
python3 python/view_recording.py recordings/test_01 --check-only
python3 python/view_recording.py recordings/test_01 --export-npy
```

The plot has a depth scale in millimeters. The check prints timestamp spacing,
measured device-time frame rate, possible sequence gaps, and SDK error counts.
Export refuses to overwrite an existing `depth.npy`.

## Files and numerical access

- `CMakeLists.txt`: links the existing dylib, source/generated headers, existing
  GLFW installation, and macOS OpenGL. Includes a local SDK-header workaround.
- `src/depth_capture.cpp`: depth-only capture and preview, writes samples before
  returning SDK frame ownership, and stops/closes the device during cleanup.
- `python/view_recording.py`: validates file sizes and timestamp counts, loads
  without copying the entire recording into RAM, and plots one frame.
- Each recording: `depth.f32`, `timestamps.csv`, and `metadata.json`.

`depth.f32` contains little-endian float32 frames in `(frame, row, column)` order,
without an image header. JSON gives its dimensions and units. This is a simple
lossless numerical format; the loader optionally exports standard NumPy `.npy`.
All SDK values, including invalid values, are preserved. This is **decoded SDK
depth**, not the sensor's encoded infrared/time-of-flight packet data.

```python
import sys
sys.path.insert(0, 'python')
from view_recording import load_recording
import numpy as np

depth, timestamps, metadata = load_recording('recordings/test_01')
print(depth.shape)                       # (number_of_frames, 424, 512)
print(depth[0, 212, 256])                 # one pixel's depth in millimeters
valid = np.isfinite(depth[0]) & (depth[0] > 0)
time_s = timestamps['device_elapsed_s']
# After --export-npy:
# depth = np.load('recordings/test_01/depth.npy', mmap_mode='r')
```

A positive finite value is SDK-valid; this does not establish accuracy. The
viewer masks invalid pixels for display without editing the stored samples.
Nonzero SDK status is recorded and reported; these frames are not silently
removed. This initial program does not interpolate samples or estimate breathing.

## Phase 1 findings from this installation

Inspected `/Users/jessicaardeshana/libfreenect2-metal`:

- `examples/Protonect.cpp`: enumerates devices, opens the default serial with the
  default pipeline (unless explicitly selected), attaches a
  `SyncMultiFrameListener`, starts streams, waits for frames, and releases them.
  Registration/RGB are unnecessary for native depth acquisition.
- `examples/KinectCapture.cpp` and recording helpers also exist. The small
  standalone program avoids their larger calibration/recording workflows. Its
  snapshot depth writer quantizes to uint16; our float32 writer avoids rounding.
- `include/libfreenect2/frame_listener.hpp`: depth is 512 × 424 float32 in mm;
  nonpositive, NaN, and infinity indicate invalid/missing depth. Timestamps are
  uint32 ticks of 0.125 ms, typically advancing by 266 at 30 Hz or 533 at 15 Hz.
  Actual delivered rate must be measured; it can be lower under load.
- The same header defines `arrival_timestamp_us` as monotonic host time of the
  first contributing USB transfer. The depth parser and processors propagate
  it to frames. It is neither wall-clock time nor precisely the exposure time.
- `build/libfreenect2/config.h` and the built dylib show CPU, OpenGL, and OpenCL
  support (also OpenCL KDE); **Metal is not compiled in**, despite the directory
  name and `ENABLE_METAL=ON` cache option. Generated feature definitions reflect
  the actual build more reliably than requested cache options.
- `src/libfreenect2.cpp`: default selection tries supported GPU pipelines and
  falls back to CPU. In this build OpenGL is the first compiled GPU choice;
  `LIBFREENECT2_PIPELINE` can override selection. The recorder logs and stores
  the actual pipeline name.
- `build/lib/libfreenect2.dylib` is present and can be linked separately. The
  build-tree `freenect2Config.cmake` expects an installed prefix, so this project's
  CMake links that dylib directly with `include/` and generated `build/` headers.
- Default depth configuration is 0.5–4.5 m clipping, bilateral and edge-aware
  filtering enabled. The recorder explicitly applies and records these defaults.
  The filters can affect small motion; these are acquisition settings, not a
  demonstrated displacement resolution or clinically suitable working distance.

## Timing and recording limits

CSV stores raw device ticks, unwrapped device elapsed seconds, raw USB-arrival
microseconds, host time at frame receipt (steady clock, relative to first frame),
sequence, SDK status, and valid count. Metadata includes host Unix start time,
serial, firmware, actual pipeline, library revision, and depth settings.

Device rollover is handled by unsigned tick differences (wrap period roughly
6.2 days). A device reset can look like a large forward jump: inspect timestamp
intervals and sequence gaps before analysis. Host receipt time includes decoding,
queueing, and program delays. Separate monotonic clocks have unrelated origins;
use differences within each column rather than subtracting them directly.

Preview and disk writes run in the acquisition loop for simplicity. This may
reduce delivered rate; sequence and timing diagnostics reveal missing frames.
This is not a guaranteed lossless real-time recorder. Files are flushed
periodically; force quitting, disconnects, or a full disk can leave partial data.
The loader rejects partial frames or mismatched timestamp counts rather than
silently aligning them. A future acquisition improvement could add a disk queue.

## Verification and current hardware blocker

On this machine the standalone build and dynamic linking succeeded. Synthetic
recording checks preserved every float32 bit, including fractional millimeters,
zero, negative values, NaN, and infinity, and NumPy export succeeded. The small
fixture in `checks/synthetic_recording` is **synthetic, not camera data**.

Live acquisition was attempted twice. The SDK detected Kinect serial
`014648533747` but failed during reset with `LIBUSB_ERROR_NO_DEVICE` before any
frames were delivered. No real recording was produced. Preview rendering and
end-to-end camera capture therefore remain unverified.

1. Close Protonect and other Kinect programs.
2. Disconnect and reconnect the Kinect USB connection and its power adapter;
   ensure a direct, working USB 3 connection.
3. Retry the capture command above with a new directory.
4. If the same failure occurs, run your known-working Protonect command to
   check the hardware connection, then close it before retrying the recorder.

If default pipeline initialization fails, try the built-in CPU pipeline for
comparison (this does not change the library's configuration):

```sh
LIBFREENECT2_PIPELINE=cpu ./build/depth_capture recordings/cpu_test_01 15
```

The CPU option will not fix a USB reset failure. Keep the terminal error output
for diagnosis; no library reinstall or rebuild is needed for this project.

Once a real recording loads and displays correctly, the next stage is a manual
ROI depth-versus-time signal. No respiratory estimation, full-image frequency
mapping, artifact correction, or chest/abdomen processing is implemented yet.
