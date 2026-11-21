"""Per-seller, request-time forecasting; no learned or persisted models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

Method = Literal["moving_average", "exponential_smoothing", "auto"]


@dataclass(frozen=True)
class Forecast:
    demand: float
    method: str
    confidence: str
    history: tuple[float, ...]
    mae: float | None = None


def _valid(values: Sequence[float]) -> list[float]:
    result = []
    for value in values:
        if value is None:
            continue
        v = float(value)
        if v < 0:
            raise ValueError("sales history cannot contain negative quantities")
        result.append(v)
    return result


def moving_average(history: Sequence[float], window: int = 3) -> float:
    values = _valid(history)
    if window < 1:
        raise ValueError("window must be at least 1")
    if not values:
        raise ValueError("at least one observed week is required")
    tail = values[-window:]
    return sum(tail) / len(tail)


def exponential_smoothing(history: Sequence[float], alpha: float = 0.4) -> float:
    values = _valid(history)
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    if not values:
        raise ValueError("at least one observed week is required")
    level = values[0]
    for value in values[1:]:
        level = alpha * value + (1 - alpha) * level
    return level


def _one_step_errors(values: list[float], method: str, window: int, alpha: float) -> list[float]:
    errors = []
    for i in range(1, len(values)):
        train = values[:i]
        prediction = moving_average(train, window) if method == "moving_average" else exponential_smoothing(train, alpha)
        errors.append(abs(values[i] - prediction))
    return errors


def _adjust_stockouts(values: list[float], flags: Sequence[bool]) -> list[float]:
    unflagged = [value for value, flagged in zip(values, flags) if not flagged]
    if not unflagged:
        return values.copy()
    baseline = sum(unflagged) / len(unflagged)
    return [max(value, baseline) if flagged else value for value, flagged in zip(values, flags)]


def forecast(
    history: Sequence[float], method: Method = "auto", *, window: int = 3, alpha: float = 0.4,
    stockout_flags: Sequence[bool] | None = None,
) -> Forecast:
    raw_history = list(history)
    if stockout_flags is not None and len(stockout_flags) != len(raw_history):
        raise ValueError("stockout_flags must match the history length")
    raw_flags = list(stockout_flags) if stockout_flags is not None else [False] * len(raw_history)
    if any(not isinstance(flag, bool) for flag in raw_flags):
        raise ValueError("stockout_flags must contain booleans")
    flags = [flag for value, flag in zip(raw_history, raw_flags) if value is not None]
    values = _valid(raw_history)
    if not values:
        raise ValueError("at least one observed week is required")
    if window < 1:
        raise ValueError("window must be at least 1")
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    if method not in ("moving_average", "exponential_smoothing", "auto"):
        raise ValueError(f"unsupported method: {method}")
    adjusted = _adjust_stockouts(values, flags)
    all_stockout = all(flags)
    if len(values) < 3:
        demand = adjusted[-1]
        if flags[-1]:
            demand = max(demand, values[-1])
        return Forecast(demand, "last_week", "low", tuple(values))
    if method == "moving_average":
        demand = moving_average(adjusted, window)
        if flags[-1]:
            demand = max(demand, values[-1])
        return Forecast(demand, method, "low" if all_stockout else "medium", tuple(values))
    if method == "exponential_smoothing":
        demand = exponential_smoothing(adjusted, alpha)
        if flags[-1]:
            demand = max(demand, values[-1])
        return Forecast(demand, method, "low" if all_stockout else "medium", tuple(values))
    methods = ("moving_average", "exponential_smoothing")
    scores: dict[str, float] = {}
    for name in methods:
        errors = []
        for i in range(1, len(values)):
            train = _adjust_stockouts(values[:i], flags[:i])
            prediction = moving_average(train, window) if name == "moving_average" else exponential_smoothing(train, alpha)
            target = values[i]
            prior_unflagged = [values[j] for j in range(i) if not flags[j]]
            if flags[i] and prior_unflagged:
                target = max(target, sum(prior_unflagged) / len(prior_unflagged))
            errors.append(abs(target - prediction))
        scores[name] = sum(errors) / (len(values) - 1)
    # Stable ordering makes exact ties deterministic.
    chosen = min(scores, key=lambda name: (scores[name], name))
    value = moving_average(adjusted, window) if chosen == "moving_average" else exponential_smoothing(adjusted, alpha)
    if flags[-1]:
        value = max(value, values[-1])
    confidence = "low" if all_stockout else ("high" if len(values) >= 6 else "medium")
    return Forecast(value, chosen, confidence, tuple(values), scores[chosen])
