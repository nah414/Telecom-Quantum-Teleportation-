import pytest

from qinterconnect import transduction


def test_cooperativity_monotonic():
    assert transduction.cooperativity(1.0, 1.0, 1.0) == 4.0


def test_conversion_efficiency_bounds():
    eta = transduction.conversion_efficiency_linearized(0.1, 1.0, 1.0, 0.5)
    assert 0.0 <= eta <= 1.0


def test_cooperativity_rejects_negative_coupling():
    with pytest.raises(ValueError):
        transduction.cooperativity(-1.0, 1.0, 1.0)


def test_conversion_efficiency_rejects_non_finite():
    import math
    import pytest

    with pytest.raises(ValueError):
        transduction.conversion_efficiency_linearized(math.nan, 1.0, 1.0, 0.5)
