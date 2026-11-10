"""Display native depth, IR intensity, and RGB with explicit timestamp offsets."""
import argparse
from pathlib import Path
import numpy as np
from recording import load_depth, load_streams, shared_times, nearest_index, rgb_image, report


# Retain the original depth-only loader interface for existing notebooks.
def load_recording(directory):
    s, meta = load_depth(directory)
    return s.frames, s.timestamps, meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--frame', type=int, default=0, help='Initial depth-frame index')
    parser.add_argument('--export-npy', action='store_true', help='Export each native stream without changing values')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    streams, meta = load_streams(args.directory)
    depth = streams['depth']
    if not 0 <= args.frame < len(depth.frames):
        parser.error(f'--frame must be between 0 and {len(depth.frames)-1}')
    print(f'Pipeline: {meta["pipeline"]}')
    for stream in streams.values():
        report(stream)
    times, clock = shared_times(streams)
    print(f'Nearest-frame display clock: {clock}. Nearby frames are not exposure-synchronized.')
    summary = args.directory / 'summary.json'
    if summary.exists():
        print(f'Recorder summary: {summary.read_text().strip()}')
    if args.export_npy:
        targets = {name: args.directory / f'{name}.npy' for name in streams}
        if any(p.exists() for p in targets.values()):
            raise FileExistsError('An export already exists; existing files will not be overwritten')
        for name, path in targets.items():
            with path.open('xb') as file:
                np.save(file, streams[name].frames, allow_pickle=False)
            print(f'Saved {path}; timestamps remain in CSV')
    if args.check_only:
        return
    import matplotlib.pyplot as plt
    from matplotlib.widgets import Slider
    fig, axes = plt.subplots(1, len(streams), figsize=(18, 5), squeeze=False)
    fig.subplots_adjust(bottom=.23, wspace=.6)
    images = {}
    for ax, (name, stream) in zip(axes[0], streams.items()):
        if name == 'rgb':
            image = ax.imshow(rgb_image(stream, 0))
        else:
            frame = stream.frames[0]
            mask = ~np.isfinite(frame) | ((frame <= 0) if name == 'depth' else False)
            image = ax.imshow(np.ma.masked_where(mask, frame), cmap='viridis' if name == 'depth' else 'gray')
            fig.colorbar(image, ax=ax, fraction=.046, label='Depth (mm)' if name == 'depth' else 'SDK IR intensity')
        images[name] = (ax, image)
        ax.set_xlabel('Native column')
        if name == 'depth':
            ax.set_ylabel('Native row')
    def update(index):
        index = int(index)
        target = times['depth'][index]
        for name, stream in streams.items():
            j = index if name == 'depth' else nearest_index(times[name], target)
            ax, image = images[name]
            frame = stream.frames[j]
            if name == 'rgb':
                image.set_data(rgb_image(stream, j))
            else:
                mask = ~np.isfinite(frame) | ((frame <= 0) if name == 'depth' else False)
                image.set_data(np.ma.masked_where(mask, frame))
                valid = frame[~mask]
                if valid.size:
                    lo, hi = np.percentile(valid, [2, 98])
                    image.set_clim(float(lo), float(hi) if hi > lo else float(lo)+1)
            delta = times[name][j] - target
            stale = ' | TIME GAP' if abs(delta) > .1 else ''
            ax.set_title(f'{name.upper()} #{j} | Δt={delta*1000:+.1f} ms{stale}\nSDK status={int(stream.timestamps["status"][j])}')
        fig.suptitle(f'Depth time {target:.3f} s | {clock}\nNative views are not spatially registered; IR is reflected intensity, not temperature')
        fig.canvas.draw_idle()
    update(args.frame)
    if len(depth.frames) > 1:
        slider = Slider(fig.add_axes([.2, .07, .6, .04]), 'Depth frame', 0,
                        len(depth.frames)-1, valinit=args.frame, valstep=1)
        slider.on_changed(update)
    plt.show()


if __name__ == '__main__':
    main()
