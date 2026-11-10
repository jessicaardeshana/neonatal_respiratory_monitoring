"""Storage and timing utilities; no modality inference or fusion."""
import json
from dataclasses import dataclass
from pathlib import Path
import numpy as np


@dataclass
class Stream:
    name: str
    frames: np.ndarray
    timestamps: np.ndarray
    spec: dict


def load_stream(directory, name, spec, timestamps_file):
    directory = Path(directory)
    dtype = np.dtype(spec['dtype'])
    shape = (spec['height'], spec['width'])
    if spec.get('channels', 1) > 1:
        shape += (spec['channels'],)
    frame_bytes = int(np.prod(shape)) * dtype.itemsize
    path = directory / spec['file']
    size = path.stat().st_size
    if size == 0 or size % frame_bytes:
        raise ValueError(f'{name}: empty data or incomplete frame')
    n = size // frame_bytes
    ts = np.atleast_1d(np.genfromtxt(directory / timestamps_file, delimiter=',', names=True))
    required = {'frame', 'device_ticks', 'device_elapsed_s', 'arrival_timestamp_us',
                'host_received_elapsed_s', 'sequence', 'status'}
    if not required.issubset(ts.dtype.names or ()):
        raise ValueError(f'{name}: missing timestamp fields')
    if len(ts) != n or not np.array_equal(ts['frame'], np.arange(n)):
        raise ValueError(f'{name}: frame/timestamp count or indices mismatch')
    if any(not np.isfinite(ts[field]).all() for field in required):
        raise ValueError(f'{name}: nonfinite timestamp/metadata fields')
    if name == 'rgb' and ('format' not in ts.dtype.names or not np.isin(ts['format'], [4, 5]).all()):
        raise ValueError('RGB requires per-frame format 4=BGRX or 5=RGBX')
    frames = np.memmap(path, mode='r', dtype=dtype, shape=(n,) + shape)
    return Stream(name, frames, ts, spec)


def load_streams(directory):
    directory = Path(directory)
    meta = json.loads((directory / 'metadata.json').read_text())
    version = meta.get('schema_version', 1)
    if version == 1:
        if meta['dtype'] != '<f4' or meta['units'] != 'mm':
            raise ValueError('Unsupported legacy depth format')
        spec = dict(file='depth.f32', width=meta['width'], height=meta['height'],
                    dtype='<f4', units='mm')
        return {'depth': load_stream(directory, 'depth', spec, 'timestamps.csv')}, meta
    if version != 2:
        raise ValueError(f'Unsupported schema {version}')
    streams = {}
    for name in ('depth', 'ir', 'rgb'):
        spec = meta['streams'][name]
        expected = ('|u1', 4) if name == 'rgb' else ('<f4', 1)
        if (spec['dtype'], spec.get('channels', 1)) != expected:
            raise ValueError(f'Unsupported {name} format')
        streams[name] = load_stream(directory, name, spec, f'{name}_timestamps.csv')
    return streams, meta


def load_depth(directory):
    """Load only depth, so independent IR/RGB failures do not block depth work."""
    directory = Path(directory)
    meta = json.loads((directory / 'metadata.json').read_text())
    if meta.get('schema_version', 1) == 1:
        streams, meta = load_streams(directory)
        return streams['depth'], meta
    if meta['schema_version'] != 2:
        raise ValueError('Unsupported recording schema')
    spec = meta['streams']['depth']
    if spec['dtype'] != '<f4' or spec['units'] != 'mm' or spec.get('channels', 1) != 1:
        raise ValueError('Unsupported depth format')
    return load_stream(directory, 'depth', spec, 'depth_timestamps.csv'), meta


def rgb_image(stream, index):
    """Interpret native BGRX/RGBX bytes for display; saved bytes are unchanged."""
    pixels = stream.frames[index, ..., :3]
    return pixels[..., ::-1] if stream.timestamps['format'][index] == 4 else pixels


def shared_times(streams):
    """Use one shared clock; never align independently zeroed device elapsed times."""
    use_arrival = all(np.all(s.timestamps['arrival_timestamp_us'] > 0) for s in streams.values())
    field, scale = ('arrival_timestamp_us', 1e-6) if use_arrival else ('host_received_elapsed_s', 1.)
    times = {name: s.timestamps[field] * scale for name, s in streams.items()}
    for name, t in times.items():
        if np.any(np.diff(t) < 0):
            raise ValueError(f'{name}: {field} goes backward; inspect recording before alignment')
    origin = times['depth'][0]
    return {name: t - origin for name, t in times.items()}, field


def nearest_index(times, target):
    # Sorted timestamp vectors, no interpolation of images.
    right = int(np.searchsorted(times, target))
    candidates = [max(0, min(len(times)-1, right + offset)) for offset in (-1, 0)]
    return min(candidates, key=lambda i: abs(times[i] - target))


def report(stream):
    ts = stream.timestamps
    dt = np.diff(ts['device_elapsed_s'])
    print(f'{stream.name}: {stream.frames.shape}, {stream.frames.dtype}; {stream.spec["units"]}')
    if len(dt) and np.all(dt > 0):
        print(f'  delivered rate {len(dt)/dt.sum():.3f} fps; interval min/median/max '
              f'{dt.min():.6f}/{np.median(dt):.6f}/{dt.max():.6f} s')
    elif len(dt):
        print('  WARNING: device timestamps repeat or go backward')
    jumps = np.diff(ts['sequence'].astype(np.uint32))
    print(f'  sequence transitions other than +1: {np.count_nonzero(jumps != 1)}; '
          f'SDK error frames: {np.count_nonzero(ts["status"])}')
    if np.any(ts['arrival_timestamp_us'] == 0):
        print('  WARNING: some USB arrival timestamps are unavailable')
