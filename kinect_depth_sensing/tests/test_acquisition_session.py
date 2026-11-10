"""Exercise continuous process control and preview reads without Kinect hardware."""
import json
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from acquisition_session import AcquisitionSession
from acquisition_platform import preview_ppm


class SessionTests(unittest.TestCase):
    def test_continuous_session_stop_and_saved_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = root / 'fake_recorder'
            fake.write_text(f'#!{sys.executable}\n' + '''
import json, pathlib, signal, sys, time
assert sys.argv[2] == '--continuous'
p = pathlib.Path(sys.argv[1]); p.mkdir()
running = True
def stop(*args):
    global running
    running = False
signal.signal(signal.SIGINT, stop)
streams = {}
for name in ('depth', 'ir', 'rgb'):
    color = name == 'rgb'
    file = name + ('.u8' if color else '.f32')
    import struct
    (p/file).write_bytes(bytes([10,20,30,255])*4 if color else struct.pack('<4f',1000.125,0,float('nan'),999.875))
    streams[name] = dict(file=file,width=2,height=2,channels=4 if color else 1,dtype='|u1' if color else '<f4')
(p/'metadata.json').write_text(json.dumps(dict(streams=streams)))
status=dict(state='recording',reason='',elapsed_s=1,free_bytes=10000000000,streams={name:dict(frames=1,bytes=16,queue_drops=0,format=4 if name=='rgb' else 2) for name in streams})
(p/'status.json').write_text(json.dumps(status))
print('fake acquisition running', flush=True)
deadline=time.monotonic()+10
while running and time.monotonic()<deadline:
    time.sleep(.02)
status.update(state='stopped',reason='user_stop')
(p/'status.tmp').write_text(json.dumps(status)); (p/'status.tmp').replace(p/'status.json')
''')
            fake.chmod(0o755)
            session = AcquisitionSession(fake)
            try:
                directory = session.start(root / 'recordings')
                deadline = time.monotonic()+5
                while session.status() is None and time.monotonic()<deadline:
                    time.sleep(.02)
                status = session.status()
                self.assertIsNotNone(status)
                self.assertTrue(session.running)
                with self.assertRaises(RuntimeError):
                    session.start(root)
                depth = session.latest_frame('depth', status)
                self.assertEqual(depth[0,0], 1000.125)
                self.assertTrue(np.isnan(depth[1,0]))
                np.testing.assert_array_equal(session.latest_frame('rgb', status)[0,0], [30,20,10])
                payload = preview_ppm(depth, 'depth')
                self.assertTrue(payload.startswith(b'P6\n2 2\n255\n'))
                self.assertEqual(len(payload.split(b'\n',3)[3]), 12)
                session.stop()
                session.process.wait(timeout=5)
                self.assertEqual(session.process.returncode, 0)
                self.assertEqual(session.status()['reason'], 'user_stop')
                self.assertIn('fake acquisition running', session.log_tail())
                session.close_log()
                # Start a separate recording, preserving the previous session.
                self.assertNotEqual(session.start(root / 'recordings'), directory)
                session.stop()
                session.process.wait(timeout=5)
                self.assertTrue(directory.exists())
            finally:
                if session.running:
                    session.stop()
                    session.process.wait(timeout=5)
                session.close_log()

    def test_missing_binary_reports_build_command(self):
        with tempfile.TemporaryDirectory() as temp:
            session = AcquisitionSession(Path(temp)/'missing')
            with self.assertRaisesRegex(FileNotFoundError, 'cmake'):
                session.start(temp)


if __name__ == '__main__':
    unittest.main()
