"""Load lossless SDK depth samples, check timestamps, and display one frame."""
import argparse
import json
from pathlib import Path
import numpy as np


def load_recording(directory):
    directory = Path(directory)
    meta = json.loads((directory / "metadata.json").read_text())
    if meta["dtype"] != "<f4" or meta["units"] != "mm":
        raise ValueError("Unsupported recording format")
    h, w = meta["height"], meta["width"]
    frame_bytes = h * w * 4
    size = (directory / "depth.f32").stat().st_size
    if size % frame_bytes:
        raise ValueError("Incomplete depth frame: recording may have been interrupted during a write")
    n = size // frame_bytes
    if not n:
        raise ValueError("Recording has no frames")
    timestamps = np.atleast_1d(np.genfromtxt(directory / "timestamps.csv", delimiter=",", names=True))
    if len(timestamps) != n:
        raise ValueError(f"Depth/timestamp count mismatch: {n} vs {len(timestamps)}")
    if not np.array_equal(timestamps["frame"], np.arange(n)):
        raise ValueError("Frame indices are inconsistent")
    depth = np.memmap(directory / "depth.f32", mode="r", dtype="<f4", shape=(n, h, w))
    return depth, timestamps, meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--frame", type=int, default=0)
    parser.add_argument("--export-npy", action="store_true")
    parser.add_argument("--check-only", action="store_true", help="Validate without opening a plot")
    args = parser.parse_args()
    depth, ts, meta = load_recording(args.directory)
    if not 0 <= args.frame < len(depth):
        parser.error(f"--frame must be between 0 and {len(depth)-1}")
    print(f"{depth.shape}: (frames, rows, columns), {depth.dtype}, millimeters; pipeline={meta['pipeline']}")
    dt = np.diff(ts["device_elapsed_s"])
    if len(dt):
        if np.any(dt <= 0):
            print("WARNING: device timestamps repeat or go backward; investigate before signal analysis")
        else:
            print(f"Device duration: {np.sum(dt):.3f} s; delivered rate: {len(dt)/np.sum(dt):.3f} fps")
            print(f"Frame interval min/median/max: {dt.min():.6f}/{np.median(dt):.6f}/{dt.max():.6f} s")
        jumps = np.diff(ts["sequence"].astype(np.uint32))
        print(f"Sequence transitions other than +1: {np.count_nonzero(jumps != 1)} (possible missing frames/reset)")
    print(f"Frames with SDK error status: {np.count_nonzero(ts['status'])}")
    if np.any(ts["arrival_timestamp_us"] == 0):
        print("WARNING: some USB-arrival timestamps are unavailable (zero)")
    frame = depth[args.frame]
    valid = np.isfinite(frame) & (frame > 0)
    print(f"Selected frame valid pixels: {valid.sum()}/{valid.size}")
    if valid.any():
        print(f"Depth min/median/max: {np.min(frame[valid]):.3f}/{np.median(frame[valid]):.3f}/{np.max(frame[valid]):.3f} mm")
    if args.export_npy:
        target = args.directory / "depth.npy"
        # Exclusive creation protects an existing export; float values unchanged.
        with target.open("xb") as file:
            np.save(file, depth, allow_pickle=False)
        print(f"Saved {target}; timestamps remain in timestamps.csv")
    if not args.check_only:
        import matplotlib.pyplot as plt
        plt.imshow(np.ma.masked_where(~valid, frame), cmap="viridis")
        plt.colorbar(label="Depth (mm)")
        plt.title(f"Frame {args.frame}, device time {ts['device_elapsed_s'][args.frame]:.3f} s")
        plt.xlabel("Column (pixel)")
        plt.ylabel("Row (pixel)")
        plt.show()


if __name__ == "__main__":
    main()
