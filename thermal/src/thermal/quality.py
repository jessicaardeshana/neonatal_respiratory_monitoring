"""Signal quality index (spec 6.8): how much does this window look like breathing?

A clean breathing window has most of its in-band power concentrated at one
frequency (and maybe its first harmonic). A window with no breathing (noise,
a lost face, a control ROI) spreads power across the band.

    SNR = power near f_peak and 2*f_peak  /  all other power in the band

Quality in [0, 1] = clip((SNR_dB + 3) / 18, 0, 1): 0 at or below -3 dB (noise
level for a peak picked from noise), 1 at or above +15 dB. These endpoints are
a documented choice, not a fitted value.
"""

from __future__ import annotations

import numpy as np

SNR_DB_FLOOR = -3.0
SNR_DB_CEIL = 15.0


def spectral_snr(f: np.ndarray, power: np.ndarray, band_hz: tuple[float, float],
                 f_peak: float, half_width_hz: float) -> float:
    """Linear SNR: power within +/-half_width of f_peak and 2*f_peak vs rest of band.

    ``half_width_hz`` should cover the window's main lobe (about 2/window_s for
    a Hann window), otherwise a clean peak leaks into the "noise".
    """
    in_band = (f >= band_hz[0]) & (f <= band_hz[1])
    sig = np.zeros_like(in_band)
    for harmonic in (1, 2):
        sig |= np.abs(f - harmonic * f_peak) <= half_width_hz
    sig &= in_band
    return float(power[sig].sum() / (power[in_band & ~sig].sum() + 1e-30))


def quality_from_snr(snr: float) -> float:
    """Map linear SNR to a quality score in [0, 1]."""
    if not np.isfinite(snr) or snr <= 0:
        return 0.0
    snr_db = 10.0 * np.log10(snr)
    return float(np.clip((snr_db - SNR_DB_FLOOR) / (SNR_DB_CEIL - SNR_DB_FLOOR), 0.0, 1.0))


def agreement_factor(spectral_bpm: float, time_bpm: float, tol_bpm: float = 3.0) -> float:
    """1.0 if the two estimators agree within ``tol_bpm``, else 0.5 (also if time-domain failed)."""
    if np.isfinite(spectral_bpm) and np.isfinite(time_bpm) and abs(spectral_bpm - time_bpm) <= tol_bpm:
        return 1.0
    return 0.5
