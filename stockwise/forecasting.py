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


def forecast(
    history: Sequence[float], method: Method = "auto", *, window: int = 3, alpha: float = 0.4,
    stockout_flags: Sequence[bool] | None = None,
) -> Forecast:
    if stockout_flags is not None and len(stockout_flags) != len(history):
        raise ValueError("stockout_flags must match the history length")
    values = _valid(history)
    if not values:
        raise ValueError("at least one observed week is required")
    if window < 1:
        raise ValueError("window must be at least 1")
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    if method not in ("moving_average", "exponential_smoothing", "auto"):
        raise ValueError(f"unsupported method: {method}")
    lower_bound = max((v for v, censored in zip(values, stockout_flags or [False] * len(values)) if censored), default=0.0)
    if len(values) < 3:
        return Forecast(max(values[-1], lower_bound), "last_week", "low", tuple(values))
    if method == "moving_average":
        return Forecast(max(moving_average(values, window), lower_bound), method, "medium", tuple(values))
    if method == "exponential_smoothing":
        return Forecast(max(exponential_smoothing(values, alpha), lower_bound), method, "medium", tuple(values))
    scores = {name: sum(_one_step_errors(values, name, window, alpha)) / (len(values) - 1)
              for name in ("moving_average", "exponential_smoothing")}
    # Stable ordering makes exact ties deterministic.
    chosen = min(scores, key=lambda name: (scores[name], name))
    value = moving_average(values, window) if chosen == "moving_average" else exponential_smoothing(values, alpha)
    return Forecast(max(value, lower_bound), chosen, "high" if len(values) >= 6 else "medium", tuple(values), scores[chosen])
