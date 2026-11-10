import numpy as np
import pytest

from thermal.roi import ROI, reduce_roi


def test_mean_and_max_reduction():
    f = np.zeros((3, 60, 80), dtype=np.float32)
    f[:, 10:12, 20:22] = [[1, 2], [3, 4]]
    roi = ROI(10, 12, 20, 22)
    assert np.allclose(reduce_roi(f, roi, "mean"), 2.5)
    assert np.allclose(reduce_roi(f, roi, "max"), 4.0)
    assert roi.n_pixels == 4 and ROI.from_box(roi.box) == roi


def test_bad_mode_raises():
    with pytest.raises(ValueError):
        reduce_roi(np.zeros((1, 60, 80)), ROI(0, 1, 0, 1), "median")
