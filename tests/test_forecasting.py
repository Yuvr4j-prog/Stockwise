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
    # The historical stockout no longer creates a permanent lower bound on forecasts.
    assert result.demand == pytest.approx(8)


def test_stockout_adjusted_to_unflagged_mean_and_all_stockout_is_low_confidence():
    adjusted = forecast([20, 20, 1], "moving_average", window=3, stockout_flags=[False, False, True])
    assert adjusted.demand == pytest.approx(20)
    all_flagged = forecast([2, 10, 3], "moving_average", stockout_flags=[True, True, True])
    assert all_flagged.confidence == "low"
    assert all_flagged.demand >= 3


def test_old_stockout_does_not_remain_a_forecast_floor():
    result = forecast([2, 15, 1, 1, 1], "moving_average", window=3,
                      stockout_flags=[False, True, False, False, False])
    assert result.demand == 1


@pytest.mark.parametrize("history,kwargs", [([], {}), ([1], {"window": 0}), ([1], {"alpha": 0}), ([1, -1], {})])
def test_invalid_forecasts_raise(history, kwargs):
    with pytest.raises(ValueError):
        forecast(history, **kwargs)
