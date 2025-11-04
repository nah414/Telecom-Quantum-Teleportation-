"""Utility functions for modelling optical-fibre quantum channels.

Typical telecom fibre spans exhibit attenuation coefficients of
approximately 0.15–0.25 dB/km around the 1550 nm low-loss window and are
deployed over tens of kilometres in metro networks. Launch powers are
usually quoted in dBm, and link budgets frequently mix linear and dB
representations; helper converters below keep those interactions
consistent with the validation guards used throughout the module.
"""

from __future__ import annotations

import math


def _ensure_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _ensure_non_negative(value: float, name: str) -> None:
    _ensure_finite(value, name)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def fiber_loss_db(distance_km: float, alpha_db_per_km: float) -> float:
    """Return total channel loss in dB for a fibre span.

    Parameters
    ----------
    distance_km:
        Propagation distance in kilometres. Must be non-negative.
    alpha_db_per_km:
        Attenuation coefficient of the fibre in dB/km. Must be non-negative.
    Notes
    -----
    * ``distance_km`` for metropolitan deployments typically ranges from
      a few kilometres up to ~80 km before amplification is required.
    * ``alpha_db_per_km`` in modern SMF-28 fibre is usually 0.17–0.22 dB/km.
    """

    _ensure_non_negative(distance_km, "distance_km")
    _ensure_non_negative(alpha_db_per_km, "alpha_db_per_km")
    return float(distance_km * alpha_db_per_km)


def power_out_dbm(power_in_dbm: float, loss_db: float) -> float:
    """Return the launched optical power after attenuation has been applied.

    Notes
    -----
    * ``power_in_dbm`` is commonly constrained between -30 dBm (few nW)
      and +10 dBm (10 mW) for quantum-limited receivers to avoid damage.
    * ``loss_db`` is the cumulative span loss; values above 40–50 dB
      normally require trusted relays or quantum repeaters.
    """

    _ensure_finite(power_in_dbm, "power_in_dbm")
    _ensure_finite(loss_db, "loss_db")
    return float(power_in_dbm - loss_db)


def dispersion_broadening(
    ps_nm_km: float, spectral_width_nm: float, distance_km: float
) -> float:
    """Approximate pulse broadening from chromatic dispersion.

    The model assumes a constant dispersion parameter ``ps_nm_km`` (in ps/nm/km),
    a source spectral width ``spectral_width_nm`` (in nm) and a propagation
    distance ``distance_km`` (in km).

    Notes
    -----
    * Standard C-band transmitters typically exhibit spectral widths of
      0.1–0.4 nm for distributed-feedback lasers.
    * ``ps_nm_km`` for dispersion-unshifted fibre is approximately
      16–18 ps/nm/km at 1550 nm.
    """

    _ensure_non_negative(ps_nm_km, "ps_nm_km")
    _ensure_non_negative(spectral_width_nm, "spectral_width_nm")
    _ensure_non_negative(distance_km, "distance_km")
    return float(ps_nm_km * spectral_width_nm * distance_km)


def qber_bb84(est_signal_counts: float, dark_counts: float) -> float:
    """Estimate a BB84 quantum-bit error rate from signal/dark counts.

    Half of the dark counts are assumed to contribute errors. When no signal is
    detected the QBER saturates to 0.5, representing a random key.
    """

    _ensure_non_negative(est_signal_counts, "est_signal_counts")
    _ensure_non_negative(dark_counts, "dark_counts")
    if est_signal_counts == 0 and dark_counts == 0:
        return 0.0
    if est_signal_counts <= 0:
        return 0.5
    return float(0.5 * dark_counts / (est_signal_counts + dark_counts))


def _binary_entropy(probability: float) -> float:
    """Shannon binary entropy with guards for extreme probabilities."""

    _ensure_finite(probability, "probability")
    if probability <= 0.0 or probability >= 1.0:
        return 0.0
    return -probability * math.log2(probability) - (1.0 - probability) * math.log2(1.0 - probability)


def key_rate_bb84(signal_rate_hz: float, qber: float, sifting_factor: float = 0.5) -> float:
    """Asymptotic secret key rate for BB84 with simple binary-entropy penalty."""

    _ensure_non_negative(signal_rate_hz, "signal_rate_hz")
    _ensure_finite(qber, "qber")
    _ensure_finite(sifting_factor, "sifting_factor")
    if not 0.0 <= sifting_factor <= 1.0:
        raise ValueError("sifting_factor must lie in [0, 1]")
    q = max(0.0, min(0.5, float(qber)))
    rate = sifting_factor * signal_rate_hz * (1.0 - 2.0 * _binary_entropy(q))
    return max(0.0, float(rate))


def loss_db_to_transmission(loss_db: float) -> float:
    """Convert attenuation in dB to a linear power transmission factor.

    Notes
    -----
    * Typical spans yield transmissions of 10^-2 to 10^-5 (20–50 dB loss).
    * Negative ``loss_db`` values correspond to inline amplification and
      are permitted.
    """

    _ensure_finite(loss_db, "loss_db")
    return float(10.0 ** (-loss_db / 10.0))


def transmission_to_loss_db(transmission: float) -> float:
    """Convert a linear power transmission factor to dB attenuation.

    Parameters
    ----------
    transmission:
        Fractional power transmission (0, 1]. Zero is rejected to prevent
        ``log10`` singularities.

    Notes
    -----
    * Low-earth-orbit optical downlinks routinely operate around 1e-4
      transmission (40 dB loss) after accounting for pointing and weather.
    """

    if not math.isfinite(transmission):
        raise ValueError("transmission must be finite")
    if not 0.0 < transmission <= 1.0:
        raise ValueError("transmission must lie in (0, 1]")
    return float(-10.0 * math.log10(transmission))
