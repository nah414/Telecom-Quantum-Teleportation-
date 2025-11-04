import pytest

from qinterconnect import fiber


def test_fiber_loss_db():
    assert fiber.fiber_loss_db(10, 0.2) == 2.0


def test_qber_bb84():
    qber = fiber.qber_bb84(est_signal_counts=1000, dark_counts=10)
    assert 0.0 <= qber <= 0.5


def test_key_rate_saturates_when_qber_high():
    assert fiber.key_rate_bb84(signal_rate_hz=1e6, qber=0.9) == 0.0


def test_qber_rejects_negative_counts():
    import pytest

    with pytest.raises(ValueError):
        fiber.qber_bb84(est_signal_counts=-1, dark_counts=0)


def test_fiber_loss_rejects_non_finite():
    import math
    import pytest

    with pytest.raises(ValueError):
        fiber.fiber_loss_db(math.nan, 0.2)


def test_loss_transmission_round_trip():
    loss_db = fiber.transmission_to_loss_db(1e-3)
    transmission = fiber.loss_db_to_transmission(loss_db)
    assert transmission == pytest.approx(1e-3)


def test_transmission_rejects_invalid_bounds():
    with pytest.raises(ValueError):
        fiber.transmission_to_loss_db(0.0)
