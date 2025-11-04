"""Minimal models for superconducting-optical transduction.

Parameters in electro-optomechanical converters span wide ranges: vacuum
coupling rates ``g`` from kHz to MHz, optical linewidths ``kappa`` in the
MHz–GHz regime, and mechanical damping ``gamma`` down to Hz. The
docstrings below annotate typical operating points so validation errors
can be interpreted in a physical context.
"""

from __future__ import annotations

import math


def _ensure_non_negative(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0.0:
        raise ValueError(f"{name} must be non-negative")


def _ensure_positive(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value <= 0.0:
        raise ValueError(f"{name} must be positive")


def cooperativity(g: float, kappa: float, gamma: float) -> float:
    """Return the single-photon cooperativity of an electro-optomechanical interface.

    Notes
    -----
    * Cooperativities well below unity signal weak coupling; values above
      1e3 often indicate the rotating-wave approximation no longer holds
      and a more complete model is required.
    * ``kappa`` and ``gamma`` must both be positive linewidths. Entering a
      negative decay rate usually stems from confusion between ``kappa``
      and detuning parameters.
    """

    _ensure_non_negative(g, "g")
    _ensure_positive(kappa, "kappa")
    _ensure_positive(gamma, "gamma")
    return float(4.0 * g * g / (kappa * gamma))


def conversion_efficiency_linearized(
    g: float, kappa_e: float, kappa_o: float, gamma_m: float
) -> float:
    """Linearised on-resonance conversion efficiency with clamped bounds.

    Notes
    -----
    * ``g`` is commonly 10^3–10^6 Hz for membrane-in-the-middle devices.
    * ``kappa_e``/``kappa_o`` represent coupling-limited linewidths; MHz
      scales indicate overcoupled resonators, while Hz values should raise
      suspicion of a unit mix-up.
    * ``gamma_m`` for cryogenic mechanical resonators typically falls
      below 10^3 Hz, motivating the positivity guard here.
    """

    _ensure_non_negative(g, "g")
    _ensure_non_negative(kappa_e, "kappa_e")
    _ensure_non_negative(kappa_o, "kappa_o")
    _ensure_positive(gamma_m, "gamma_m")
    denominator = (kappa_e + kappa_o) * gamma_m
    if denominator == 0.0:
        return 0.0
    eta = 4.0 * g * g / denominator
    return max(0.0, min(1.0, float(eta)))
