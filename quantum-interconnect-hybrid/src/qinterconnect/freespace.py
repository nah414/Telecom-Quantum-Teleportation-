"""Simple free-space optical channel approximations.

Ground-to-space optical links usually operate with beam waists on the
order of millimetres, wavelengths at 850 nm or 1550 nm, and path lengths
from a few hundred metres (test ranges) to thousands of kilometres
(satellite uplinks). The helpers below document those operating regions
so validation errors can be traced back to implausible scenarios rather
than numerical edge cases.
"""

from __future__ import annotations

import math


def _ensure_positive(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value <= 0.0:
        raise ValueError(f"{name} must be positive")


def _ensure_non_negative(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0.0:
        raise ValueError(f"{name} must be non-negative")


def rayleigh_range(w0_m: float, wavelength_m: float) -> float:
    """Return the Rayleigh range for a Gaussian beam."""

    _ensure_positive(w0_m, "w0_m")
    _ensure_positive(wavelength_m, "wavelength_m")
    return float(math.pi * w0_m**2 / wavelength_m)


def beam_radius(w0_m: float, wavelength_m: float, z_m: float) -> float:
    """Beam radius at propagation distance ``z_m`` for a diffraction-limited beam.

    Notes
    -----
    * ``z_m`` can legitimately be negative when analysing symmetric two-way
      propagation about the beam waist.
    * ``w0_m`` typically lies between 0.5 mm (tight launch telescopes) and
      50 mm (large-aperture ground stations).
    """

    _ensure_positive(w0_m, "w0_m")
    _ensure_positive(wavelength_m, "wavelength_m")
    if not math.isfinite(z_m):
        raise ValueError("z_m must be finite")
    zR = rayleigh_range(w0_m, wavelength_m)
    return float(w0_m * math.sqrt(1.0 + (z_m / zR) ** 2))


def geometric_spreading_loss_db(
    w0_m: float, wavelength_m: float, z_m: float, aperture_radius_m: float
) -> float:
    """Diffraction-limited geometric loss captured by a circular receiver aperture."""

    _ensure_positive(aperture_radius_m, "aperture_radius_m")
    if not math.isfinite(z_m):
        raise ValueError("z_m must be finite")
    w = beam_radius(w0_m, wavelength_m, z_m)
    capture = 1.0 - math.exp(-(aperture_radius_m**2) / (2.0 * w**2))
    capture = min(1.0, max(1e-12, capture))
    return float(-10.0 * math.log10(capture))


def hv5_cn2(h_m: float, v_ms: float = 21.0, A: float = 1.7e-14) -> float:
    """Hufnagel–Valley boundary-layer profile for the index structure constant."""

    _ensure_non_negative(h_m, "h_m")
    _ensure_positive(v_ms, "v_ms")
    _ensure_positive(A, "A")
    boundary_layer = A * math.exp(-h_m / 100.0)
    turbulence = 0.00594 * (v_ms / 27.0) ** 2 * (10.0 ** (-5.0 * h_m)) * math.exp(-h_m / 1000.0)
    mid_altitude = 2.7e-16 * math.exp(-h_m / 1500.0)
    return float(boundary_layer + turbulence + mid_altitude)


def scintillation_index_weak(cn2: float, k: float, z_m: float) -> float:
    """Weak-turbulence plane-wave scintillation index (Rytov variance)."""

    _ensure_non_negative(cn2, "cn2")
    _ensure_positive(k, "k")
    _ensure_positive(z_m, "z_m")
    return float(1.23 * cn2 * (k ** (7.0 / 6.0)) * (z_m ** (11.0 / 6.0)))


def gaussian_beam_summary(w0_m: float, wavelength_m: float) -> dict[str, float]:
    """Return Rayleigh range and far-field divergence for a Gaussian beam.

    The summary bundles the most common derived parameters when sizing
    launch or receive optics. The far-field half-angle divergence is
    defined as ``theta = wavelength_m / (math.pi * w0_m)``.

    Notes
    -----
    * ``w0_m`` of 1–5 mm corresponds to modest telescope diameters suited
      to terrestrial free-space QKD testbeds.
    * ``wavelength_m`` near 1.55e-6 m falls within the eye-safe telecom
      C-band frequently chosen for field trials.
    """

    zR = rayleigh_range(w0_m, wavelength_m)
    divergence = wavelength_m / (math.pi * w0_m)
    return {"rayleigh_range_m": zR, "divergence_rad": float(divergence)}
