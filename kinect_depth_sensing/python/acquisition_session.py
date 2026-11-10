"""Manage one continuous C++ capture process and read flushed preview frames."""
import json
from pathlib import Path
import signal
import subprocess
from datetime import datetime
from uuid import uuid4
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]


class AcquisitionSession:
    def __init__(self, recorder=None):
        self.recorder = Path(recorder) if recorder else PROJECT / 'build' / 'depth_capture'
        self.process = None
        self.directory = None
        self.stopping = False
        self._log = None
        self._metadata = None

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def start(self, parent):
        if self.running:
            raise RuntimeError('A recording is already running')
        if not self.recorder.is_file():
            raise FileNotFoundError('Build the recorder first: cmake -S . -B build && cmake --build build')
        parent = Path(parent).expanduser().resolve()
        parent.mkdir(parents=True, exist_ok=True)
        # The recorder creates this directory exclusively. Keep the process log
        # next to it so startup errors remain available even if device open fails.
        name = datetime.now().astimezone().strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:8]
        self.directory = parent / name
        self._metadata = None
        self.stopping = False
        if self._log:
            self._log.close()
        self._log = self.directory.with_suffix('.log').open('x')
        try:
            self.process = subprocess.Popen(
                [str(self.recorder), str(self.directory), '--continuous'],
                stdout=self._log, stderr=subprocess.STDOUT,
                cwd=PROJECT, start_new_session=True)
        except Exception:
            self._log.close()
            raise
        return self.directory

    def stop(self):
        if self.running and not self.stopping:
            self.stopping = True
            try:
                self.process.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass  # Process exited between poll and signal.

    def status(self):
        if self.directory is None:
            return None
        try:
            return json.loads((self.directory / 'status.json').read_text())
        except FileNotFoundError:
            return None

    def latest_frame(self, name, status):
        info = status['streams'][name]
        n = info['frames']
        if n == 0:
            return None
        if self._metadata is None:
            self._metadata = json.loads((self.directory / 'metadata.json').read_text())
        spec = self._metadata['streams'][name]
        shape = (spec['height'], spec['width'])
        if spec['channels'] > 1:
            shape += (spec['channels'],)
        dtype = np.dtype(spec['dtype'])
        count = int(np.prod(shape))
        with (self.directory / spec['file']).open('rb') as file:
            file.seek((n-1) * count * dtype.itemsize)
            pixels = np.fromfile(file, dtype=dtype, count=count)
        if pixels.size != count:
            return None  # Incomplete files are never displayed as complete frames.
        pixels = pixels.reshape(shape)
        if name == 'rgb':
            if info['format'] not in (4, 5):
                raise ValueError('Unknown native RGB format')
            pixels = pixels[..., :3]
            if info['format'] == 4:
                pixels = pixels[..., ::-1]
        return pixels

    def log_tail(self, limit=6000):
        if self.directory is None:
            return ''
        path = self.directory.with_suffix('.log')
        if not path.exists():
            return ''
        with path.open('rb') as file:
            file.seek(max(0, path.stat().st_size - limit))
            return file.read().decode('utf-8', errors='replace')

    def close_log(self):
        if self.running:
            raise RuntimeError('Stop the recording and wait for cleanup before closing')
        if self._log:
            self._log.close()
            self._log = None
