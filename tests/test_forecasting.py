import pytest

from stockwise.forecasting import exponential_smoothing, forecast, moving_average


def test_moving_average_uses_last_window_and_keeps_zero():
    assert moving_average([2, 0, 4, 8], 2) == 6
    assert moving_average([2, 0], 3) == 1


def test_exponential_smoothing_recursion():
    assert exponential_smoothing([10, 0], 0.4) == pytest.approx(6)
    assert exponential_smoothing([1, 5], 1) == 5


def test_auto_backtests_and_is_deterministic_on_tie():
    result = forecast([4, 4, 4, 4], "auto")
    assert result.method == "exponential_smoothing"
    assert result.demand == pytest.approx(4)
    assert result.mae == pytest.approx(0)


def test_short_history_is_last_week_low_confidence():
    result = forecast([3, 0], "moving_average")
    assert (result.demand, result.method, result.confidence) == (0, "last_week", "low")


def test_stockout_observation_is_demand_lower_bound():
    result = forecast([2, 15, 1], "moving_average", window=2, stockout_flags=[False, True, False])
    assert result.demand == 15


@pytest.mark.parametrize("history,kwargs", [([], {}), ([1], {"window": 0}), ([1], {"alpha": 0}), ([1, -1], {})])
def test_invalid_forecasts_raise(history, kwargs):
    with pytest.raises(ValueError):
        forecast(history, **kwargs)
