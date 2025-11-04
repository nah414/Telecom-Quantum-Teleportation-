import math

import pytest

from qinterconnect import freespace


def test_rayleigh_range():
    zR = freespace.rayleigh_range(1e-3, 1.55e-6)
    assert zR > 1.0


def test_geometric_spreading_loss_monotonic():
    narrow_loss = freespace.geometric_spreading_loss_db(1e-3, 1.55e-6, 500.0, 0.25)
    wide_loss = freespace.geometric_spreading_loss_db(2e-3, 1.55e-6, 500.0, 0.25)
    assert wide_loss < narrow_loss


def test_hv5_cn2_rejects_negative_altitude():
    with pytest.raises(ValueError):
        freespace.hv5_cn2(-1.0)


def test_rayleigh_range_rejects_non_finite():
    with pytest.raises(ValueError):
        freespace.rayleigh_range(float("nan"), 1.55e-6)


def test_gaussian_beam_summary_matches_primitives():
    summary = freespace.gaussian_beam_summary(1e-3, 1.55e-6)
    assert summary["rayleigh_range_m"] == pytest.approx(
        freespace.rayleigh_range(1e-3, 1.55e-6)
    )
    assert summary["divergence_rad"] == pytest.approx(1.55e-6 / (math.pi * 1e-3))
