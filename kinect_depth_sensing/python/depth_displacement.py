"""Depth-only exploratory ROI median and relative camera-axis surface motion."""
import argparse
import csv
from pathlib import Path
import numpy as np
from recording import load_depth


def extract_depth_roi(stream, roi, min_valid_fraction=.7):
    x, y, w, h = roi
    height, width = stream.frames.shape[1:]
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x+w > width or y+h > height:
        raise ValueError('ROI must be a positive rectangle inside the depth image')
    if not 0 < min_valid_fraction <= 1:
        raise ValueError('min_valid_fraction must be in (0, 1]')
    median = np.full(len(stream.frames), np.nan)
    fraction = np.zeros(len(stream.frames))
    for i in range(len(stream.frames)):
        pixels = stream.frames[i, y:y+h, x:x+w]
        valid = np.isfinite(pixels) & (pixels > 0)
        fraction[i] = valid.mean()
        if stream.timestamps['status'][i] == 0 and fraction[i] >= min_valid_fraction:
            median[i] = np.median(pixels[valid])
    if not np.isfinite(median).any():
        raise ValueError('No ROI frames meet valid-depth and SDK-status requirements')
    baseline = float(np.nanmedian(median))
    return median, baseline - median, fraction, baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--roi', type=int, nargs=4, metavar=('X', 'Y', 'WIDTH', 'HEIGHT'))
    parser.add_argument('--min-valid-fraction', type=float, default=.7)
    parser.add_argument('--output', type=Path, help='Optional new CSV; refuses overwrite')
    parser.add_argument('--no-show', action='store_true')
    args = parser.parse_args()
    depth, _ = load_depth(args.directory)  # No IR/RGB data are opened.
    roi = args.roi
    if roi is None:
        if args.no_show:
            parser.error('--no-show requires --roi')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        frame = depth.frames[0]
        ax.imshow(np.ma.masked_where(~np.isfinite(frame) | (frame <= 0), frame))
        ax.set_title('Click two opposite ROI corners in the DEPTH image')
        points = plt.ginput(2, timeout=-1)
        plt.close(fig)
        if len(points) != 2:
            parser.error('ROI selection cancelled')
        (x0, y0), (x1, y1) = points
        x, y = max(0, int(min(x0, x1))), max(0, int(min(y0, y1)))
        right = min(frame.shape[1], int(np.ceil(max(x0, x1))))
        bottom = min(frame.shape[0], int(np.ceil(max(y0, y1))))
        roi = [x, y, right-x, bottom-y]
    t = depth.timestamps['device_elapsed_s']
    dt = np.diff(t)
    if not np.all(dt > 0):
        raise ValueError('Depth device timestamps must increase; inspect reset/duplicate timestamps first')
    median, relative, fraction, baseline = extract_depth_roi(depth, roi, args.min_valid_fraction)
    print(f'Depth ROI {roi}; baseline median {baseline:.4f} mm; usable frames {np.isfinite(median).sum()}/{len(median)}')
    print('Relative surface depth change: positive toward camera. Motion and sensor noise may also contribute; no respiratory rate is inferred.')
    if args.output:
        with args.output.open('x', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['device_elapsed_s', 'median_depth_mm', 'relative_toward_camera_mm', 'valid_fraction', 'sdk_status'])
            writer.writerows(zip(t, median, relative, fraction, depth.timestamps['status']))
    if not args.no_show:
        import matplotlib.pyplot as plt
        plot_relative = relative.copy()
        # Break plotted lines at large gaps; do not invent missing samples.
        if len(dt):
            plot_relative[1:][dt > 3*np.median(dt)] = np.nan
        fig, axes = plt.subplots(2, 1, sharex=True)
        axes[0].plot(t, plot_relative)
        axes[0].set_ylabel('Toward-camera change (mm)')
        axes[0].set_title(f'Depth only, ROI {roi}; temporal-median baseline removed')
        axes[1].plot(t, fraction)
        axes[1].set_ylabel('Valid ROI fraction'); axes[1].set_ylim(0, 1.05)
        axes[1].set_xlabel('Depth device elapsed time (s)')
        plt.show()


if __name__ == '__main__':
    main()
