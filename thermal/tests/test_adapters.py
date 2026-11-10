"""Phase 5: recorder, FileSource, LeptonSource, pipeline replay (SYNTHETIC data; no camera is ever opened)."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from thermal.apnea import ApneaConfig
from thermal.pipeline import collect_frames, rois_from_meta, run_pipeline
from thermal.recorder import DATA_DIR, TimestampLogger, record, save_recording
from thermal.sources import FrameSource
from thermal.sources.file_source import FileSource
from thermal.sources.lepton import (DeviceNotFoundError, LeptonConfig, LeptonSource,
                                    normalize_raw_frame, raw_to_celsius)
from thermal.sources.synthetic import SyntheticConfig, SyntheticSource

SHAPE = (60, 80)


def _arrays(n=30, fs=8.7):
    t = np.arange(n) / fs
    f = np.random.default_rng(0).normal(30, 1, (n, *SHAPE)).astype(np.float32)
    return f, t


# ---- unit conversion ---------------------------------------------------------
def test_raw_to_celsius_centikelvin_and_offset():
    out = raw_to_celsius(np.array([29315, 30015], dtype=np.uint16))
    assert out.dtype == np.float32 and np.allclose(out, [20.0, 27.0], atol=1e-3)
    assert np.allclose(raw_to_celsius(np.array([29315]), offset_c=-0.5), [19.5], atol=1e-3)
    assert np.allclose(raw_to_celsius(np.array([2931]), scale_k_per_count=0.1), [20.0 - 0.05], atol=0.1)


def test_normalize_raw_frame_formats_and_loud_failure():
    a16 = (np.arange(4800, dtype=np.uint16)).reshape(SHAPE)
    assert np.array_equal(normalize_raw_frame(a16), a16)
    assert np.array_equal(normalize_raw_frame(a16.reshape(1, -1)), a16)
    as8 = a16.astype("<u2").view(np.uint8).reshape(60, 160)  # 8-bit byte pairs
    assert np.array_equal(normalize_raw_frame(as8), a16)
    with pytest.raises(ValueError, match="Unexpected frame format"):
        normalize_raw_frame(np.zeros((10, 10), dtype=np.float32))


# ---- recorder ----------------------------------------------------------------
def test_recorder_round_trip_no_pickle_and_meta(tmp_path):
    src = SyntheticSource(SyntheticConfig(duration_s=20, seed=1, apnea_events=((8.0, 5.0),)))
    p = record(src, tmp_path / "r.npz", extra_meta={"manual_breath_count": 5}, allow_outside_data=True)
    with np.load(p, allow_pickle=False) as z:  # would raise if anything needed pickle
        meta = json.loads(str(z["meta"]))
        assert z["frames"].dtype == np.float32 and z["frames"].shape[1:] == SHAPE
        assert {"truth_rate_bpm", "truth_apnea_mask", "truth_ffc_indices"} <= set(z.files)
    assert meta["synthetic"] and meta["units"] == "celsius" and meta["manual_breath_count"] == 5
    assert {"nostril", "control", "reference"} == set(meta["rois"])
    assert "git_commit" in meta and "created_utc" in meta
    ref_f, ref_t = collect_frames(src)
    got = FileSource(p)
    assert np.array_equal(got.frames_c, ref_f) and np.array_equal(got.timestamps, ref_t)


def test_recorder_refuses_to_write_raw_frames_outside_the_gitignored_data_dir(tmp_path):
    src = SyntheticSource(SyntheticConfig(duration_s=5))
    with pytest.raises(ValueError, match="outside"):
        record(src, tmp_path / "x.npz")
    assert not (tmp_path / "x.npz").exists()


def test_data_dir_is_actually_gitignored():
    r = subprocess.run(["git", "check-ignore", "-q", str(DATA_DIR / "anything.npz")],
                       cwd=Path(__file__).parent, capture_output=True)
    assert r.returncode == 0


def test_save_recording_validates_inputs(tmp_path):
    f, t = _arrays()
    with pytest.raises(ValueError, match="shape"):
        save_recording(tmp_path / "a.npz", f[:, :10], t, {}, allow_outside_data=True)
    with pytest.raises(ValueError, match="timestamps"):
        save_recording(tmp_path / "a.npz", f, t[:-1], {}, allow_outside_data=True)
    with pytest.raises(ValueError, match="increasing"):
        save_recording(tmp_path / "a.npz", f, np.zeros(len(t)), {}, allow_outside_data=True)


def test_record_max_frames_and_empty_source(tmp_path):
    src = SyntheticSource(SyntheticConfig(duration_s=30))
    p = record(src, tmp_path / "m.npz", max_frames=10, allow_outside_data=True)
    assert FileSource(p).frames_c.shape[0] == 10

    class Empty:
        fs_nominal = 8.7

        def frames(self):
            return iter(())

    with pytest.raises(ValueError, match="no frames"):
        record(Empty(), tmp_path / "e.npz", allow_outside_data=True)


# ---- FileSource ----------------------------------------------------------------
def test_filesource_is_a_framesource_and_estimates_rate_without_meta(tmp_path):
    f, t = _arrays()
    save_recording(tmp_path / "n.npz", f, t, {}, allow_outside_data=True)
    fs = FileSource(tmp_path / "n.npz")
    assert isinstance(fs, FrameSource) and abs(fs.fs_nominal - 8.7) < 1e-6
    ts, frame = next(iter(fs.frames()))
    assert frame.shape == SHAPE and ts == 0.0


def test_filesource_from_arrays_converts_units():
    f, t = _arrays()
    raw = (f + 273.15) * 100  # centi-Kelvin
    fs = FileSource.from_arrays(raw.astype(np.float64), t, units="centikelvin")
    assert np.allclose(fs.frames_c, f, atol=0.02)


@pytest.mark.parametrize("bad,msg", [
    ("missing", "missing required"), ("shape", "frames must have shape"), ("len", "does not match"),
    ("order", "strictly increasing"), ("nan", "NaN"), ("units", "unknown units"), ("short", "at least 2"),
])
def test_filesource_rejects_malformed_files(tmp_path, bad, msg):
    f, t = _arrays()
    meta = {}
    if bad == "missing":
        np.savez(tmp_path / "b.npz", frames=f)
    else:
        if bad == "shape": f = f[:, :10]
        if bad == "len": t = t[:-1]
        if bad == "order": t = t[::-1].copy()
        if bad == "nan": t = t.copy(); t[3] = np.nan
        if bad == "units": meta = {"units": "fahrenheit"}
        if bad == "short": f, t = f[:1], t[:1]
        np.savez(tmp_path / "b.npz", frames=f, timestamps=t, meta=np.array(json.dumps(meta)))
    with pytest.raises(ValueError, match=msg):
        FileSource(tmp_path / "b.npz")


def test_filesource_missing_file_and_pickled_file_are_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        FileSource(tmp_path / "nope.npz")
    f, t = _arrays()
    np.savez(tmp_path / "p.npz", frames=f, timestamps=t, meta=np.array({"x": 1}, dtype=object))
    with pytest.raises(ValueError):  # object arrays need pickle: never loaded
        FileSource(tmp_path / "p.npz")


# ---- LeptonSource (fake capture only: no real device is ever opened) ----------------
class FakeCapture:
    def __init__(self, frames, opened=True, fail_after=None):
        self.frames, self.opened, self.fail_after = list(frames), opened, fail_after
        self.props, self.released, self.reads = {}, False, 0

    def isOpened(self): return self.opened
    def set(self, prop, value): self.props[prop] = value; return True
    def release(self): self.released = True

    def read(self):
        self.reads += 1
        if self.fail_after is not None and self.reads > self.fail_after:
            return False, None
        return (True, self.frames[(self.reads - 1) % len(self.frames)]) if self.frames else (False, None)


def _raw_frames(n=5, centik=30015):
    return [np.full(SHAPE, centik + i, dtype=np.uint16) for i in range(n)]


def test_lepton_streams_celsius_with_monotonic_timestamps_and_logs_them():
    cap = FakeCapture(_raw_frames(5))
    src = LeptonSource(max_frames=5, capture_factory=lambda i, b: cap)
    assert isinstance(src, FrameSource)
    out = list(src.frames())
    assert len(out) == 5 and out[0][0] == 0.0
    assert np.all(np.diff([t for t, _ in out]) >= 0)
    assert np.allclose(out[0][1], 27.0, atol=1e-3) and out[0][1].dtype == np.float32
    assert cap.props[16] == 0 and cap.props[6] == 0x20363159  # raw 16-bit, 'Y16 ' fourcc
    assert cap.released and src.logger.summary()["n_frames"] == 5


def test_lepton_releases_the_device_even_if_the_consumer_stops_early():
    cap = FakeCapture(_raw_frames(5))
    gen = LeptonSource(capture_factory=lambda i, b: cap).frames()
    next(gen); gen.close()
    assert cap.released


def test_lepton_without_a_device_fails_with_a_clear_checklist():
    src = LeptonSource(LeptonConfig(device_index=7), capture_factory=lambda i, b: FakeCapture([], opened=False))
    with pytest.raises(DeviceNotFoundError, match="device index 7") as e:
        next(src.frames())
    assert "SyntheticSource" in str(e.value) and "CAP_DSHOW" in str(e.value)


def test_lepton_default_path_without_camera_is_graceful(monkeypatch):
    """The real cv2 path, with VideoCapture replaced so no device is touched."""
    import cv2

    class Closed:
        def __init__(self, *a): pass
        def isOpened(self): return False

    monkeypatch.setattr(cv2, "VideoCapture", Closed)
    with pytest.raises(DeviceNotFoundError):
        next(LeptonSource().frames())


def test_lepton_gives_up_after_too_many_failed_reads_and_flags_bad_format():
    cap = FakeCapture(_raw_frames(2), fail_after=2)
    src = LeptonSource(LeptonConfig(max_consecutive_failures=3), capture_factory=lambda i, b: cap)
    with pytest.raises(DeviceNotFoundError, match="stopped delivering"):
        list(src.frames())
    assert cap.released
    bad = FakeCapture([np.zeros((10, 10), dtype=np.uint16)])
    with pytest.raises(ValueError, match="Unexpected frame format"):
        next(LeptonSource(capture_factory=lambda i, b: bad).frames())


# ---- TimestampLogger -------------------------------------------------------------
def test_timestamp_logger_reports_rate_jitter_and_gaps(tmp_path):
    log = TimestampLogger(8.7)
    t = np.cumsum(np.r_[0.0, np.full(100, 0.1)])
    t[60:] += 0.25  # one long gap
    for x in t: log.add(x)
    s = log.summary()
    assert s["n_frames"] == 101 and s["n_gaps"] == 1 and abs(s["dt_median_s"] - 0.1) < 1e-9
    assert s["dt_max_s"] == pytest.approx(0.35) and s["fps_mean"] < 10
    csv = log.write_csv(tmp_path / "ts.csv")
    assert len(csv.read_text().splitlines()) == 102
    assert TimestampLogger().summary() == {"n_frames": 0}


# ---- PHASE 5 ACCEPTANCE: identical pipeline from live source and replay ---------------------
def test_pipeline_runs_identically_from_syntheticsource_and_a_replayed_npz(tmp_path):
    cfg = SyntheticConfig(duration_s=220, seed=7, rate_bpm=18.0, apnea_events=((100.0, 25.0),))
    live = SyntheticSource(cfg)
    p = record(live, tmp_path / "session.npz", allow_outside_data=True)
    replay = FileSource(p)
    rois = rois_from_meta(replay.meta)
    a = run_pipeline(live, *rois, apnea_cfg=ApneaConfig())
    b = run_pipeline(replay, *rois, apnea_cfg=ApneaConfig())

    assert np.array_equal(a.signals.t, b.signals.t)
    for name in ("s_raw", "s_clean", "s_filt", "ctrl_filt", "ffc_mask"):
        assert np.array_equal(getattr(a.signals, name), getattr(b.signals, name)), name
    for name in ("spectral_bpm", "time_bpm", "quality", "t_end", "snr_db"):
        assert np.array_equal(getattr(a.rate, name), getattr(b.rate, name), equal_nan=True), name
    assert np.array_equal(a.apnea.envelope, b.apnea.envelope, equal_nan=True)
    assert [(e.start, e.end, e.kind) for e in a.apnea.events] == [(e.start, e.end, e.kind) for e in b.apnea.events]
    assert len(a.apnea.events) == 1 and a.apnea.events[0].kind == "apnea"  # and it is a meaningful result


def test_rois_from_meta_explains_how_to_get_rois_for_real_data():
    with pytest.raises(ValueError, match="select_roi_interactive"):
        rois_from_meta({})
