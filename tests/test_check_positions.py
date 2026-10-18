import math

import pytest

from arrabida_dataset.check_positions import evaluate

TIDE = (0.8, 2.8)


def test_missing_lidar_is_no_bathymetry():
    assert evaluate(16, None, None, None, TIDE)["status"] == "no_lidar"
    assert evaluate(16, math.nan, None, None, TIDE)["status"] == "no_lidar"


def test_label_within_tolerance_passes():
    result = evaluate(16, 15.56, None, None, TIDE)
    assert result["status"] == "pass"
    assert result["low"] == pytest.approx(16 - 15.56 - 2.8)
    assert result["high"] == pytest.approx(16 - 15.56 - 0.8)
    assert result["neighbour"] == ""


def test_deep_label_over_shallow_lidar_is_flagged_and_neighbourhood_checked():
    assert evaluate(15, 6.0, 12.0, 16.0, TIDE) == {
        "low": pytest.approx(6.2),
        "high": pytest.approx(8.2),
        "status": "flag",
        "neighbour": "true",
    }
    assert evaluate(15, 6.0, 5.0, 7.0, TIDE)["neighbour"] == "false"
