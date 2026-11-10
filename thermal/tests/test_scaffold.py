"""Phase 0 checks: package imports and config is sane."""

import numpy as np

import thermal
from thermal.config import ADULT, NEONATE, PROFILES, PipelineConfig
from thermal.sources import FrameSource


def test_package_imports():
    assert thermal.__version__


def test_profiles_bands_match_rates():
    for p in (ADULT, NEONATE):
        lo, hi = p.band_hz
        assert lo < hi
        # band must contain the profile's rate range (breaths/min / 60 = Hz)
        assert lo <= p.rate_min_bpm / 60 + 1e-9
        assert hi >= p.rate_max_bpm / 60 - 1e-9
    assert set(PROFILES) == {"adult", "neonate"}


def test_default_config_nyquist_covers_neonate_band():
    cfg = PipelineConfig()
    assert cfg.fs_nominal / 2 > NEONATE.band_hz[1]


def test_frame_source_protocol_is_checkable():
    class Dummy:
        fs_nominal = 8.7

        def frames(self):
            yield 0.0, np.zeros((60, 80), dtype=np.float32)

    assert isinstance(Dummy(), FrameSource)
