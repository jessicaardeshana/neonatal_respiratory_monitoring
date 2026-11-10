"""Synthetic checks only; these do not establish camera accuracy."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from recording import load_streams, load_depth, shared_times, nearest_index, rgb_image
from depth_displacement import extract_depth_roi


def fixture(path):
    depth = np.array([[[1000.125, 1000.125], [np.nan, 0]],
                      [[999.875, 999.875], [np.inf, -1]],
                      [[998., 998.], [998., 998.]]], dtype='<f4')
    ir = np.array([[[0, 65535], [3.125, np.nan]], [[1, 2], [3, 4]]], dtype='<f4')
    rgb = np.array([[[[10, 20, 30, 255]]], [[[40, 50, 60, 0]]]], dtype='u1')
    specs = {}
    for name, frames, unit in [('depth', depth, 'mm'), ('ir', ir, 'intensity'), ('rgb', rgb, 'color')]:
        file = name + ('.u8' if name == 'rgb' else '.f32')
        frames.tofile(path / file)
        specs[name] = dict(file=file, width=frames.shape[2], height=frames.shape[1],
                           channels=4 if name == 'rgb' else 1, dtype='|u1' if name == 'rgb' else '<f4', units=unit)
    (path / 'metadata.json').write_text(json.dumps(dict(schema_version=2, pipeline='synthetic', streams=specs)))
    header = 'frame,device_ticks,device_elapsed_s,arrival_timestamp_us,host_received_elapsed_s,sequence,status,format\n'
    (path / 'depth_timestamps.csv').write_text(header + '0,4294967200,0,1000000,0,10,0,2\n1,170,.03325,1033250,.034,11,0,2\n2,436,.0665,1066500,.067,12,1,2\n')
    (path / 'ir_timestamps.csv').write_text(header + '0,170,0,1033250,.034,11,0,2\n1,436,.03325,1066500,.067,12,0,2\n')
    (path / 'rgb_timestamps.csv').write_text(header + '0,800,0,1010000,.012,1,0,4\n1,1333,.066625,1076625,.079,2,0,5\n')
    return depth, ir, rgb


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.original = fixture(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_native_bits_and_channel_order(self):
        streams, _ = load_streams(self.path)
        for name, original in zip(('depth', 'ir', 'rgb'), self.original):
            self.assertEqual(original.tobytes(), streams[name].frames.tobytes())
        np.testing.assert_array_equal(rgb_image(streams['rgb'], 0)[0, 0], [30, 20, 10])
        np.testing.assert_array_equal(rgb_image(streams['rgb'], 1)[0, 0], [40, 50, 60])

    def test_nearest_frames_use_shared_clock_not_frame_index(self):
        streams, _ = load_streams(self.path)
        times, clock = shared_times(streams)
        self.assertEqual(clock, 'arrival_timestamp_us')
        self.assertEqual(nearest_index(times['ir'], times['depth'][1]), 0)
        self.assertAlmostEqual(times['ir'][0], .03325)
        self.assertEqual(nearest_index(times['rgb'], times['depth'][2]), 1)

    def test_depth_only_rejects_invalid_status_and_keeps_mm(self):
        (self.path / 'ir.f32').unlink()  # Depth analysis is independent.
        depth, _ = load_depth(self.path)
        median, displacement, fraction, baseline = extract_depth_roi(depth, [0, 0, 2, 2], .5)
        np.testing.assert_allclose(median[:2], [1000.125, 999.875])
        np.testing.assert_allclose(displacement[:2], [-.125, .125])
        self.assertTrue(np.isnan(median[2]))
        np.testing.assert_allclose(fraction, [.5, .5, 1.])
        self.assertEqual(baseline, 1000.)
        with self.assertRaises(ValueError):
            extract_depth_roi(depth, [1, 0, 2, 2])

    def test_partial_data_or_timestamp_mismatch_fails(self):
        with (self.path / 'ir.f32').open('ab') as f:
            f.write(b'x')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            load_streams(self.path)
        fixture(self.path)
        table = self.path / 'rgb_timestamps.csv'
        table.write_text('\n'.join(table.read_text().splitlines()[:-1])+'\n')
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            load_streams(self.path)

    def test_shared_clock_fallback(self):
        table = self.path / 'rgb_timestamps.csv'
        table.write_text(table.read_text().replace('1010000', '0'))
        streams, _ = load_streams(self.path)
        times, clock = shared_times(streams)
        self.assertEqual(clock, 'host_received_elapsed_s')
        self.assertAlmostEqual(times['rgb'][0], .012)


if __name__ == '__main__':
    unittest.main()
