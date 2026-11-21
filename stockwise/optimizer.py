"""Whole-unit budget allocation using scipy.optimize.milp and a greedy baseline."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import floor, isfinite
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix


@dataclass(frozen=True)
class ProductOption:
    sku: str
    cost: float
    profit: float
    demand: int
    min_qty: int = 0
    pack_size: int = 1
    force_include: bool = False
    force_exclude: bool = False


@dataclass(frozen=True)
class ItemResult:
    sku: str
    quantity: int
    spend: float
    expected_profit: float
    reason: str


@dataclass(frozen=True)
class PlanResult:
    items: tuple[ItemResult, ...]
    total_spent: float
    unspent_budget: float
    total_profit: float
    roi: float
    greedy_profit: float
    greedy_quantities: Mapping[str, int]
    status: str = "optimal"
    solver_message: str = ""


class InfeasiblePlan(ValueError):
    pass


def solve_plan(
    products: Sequence[ProductOption], budget: float, *, storage_limit: int | None = None,
    demand_scale: float = 1.0, forecast_overrides: Mapping[str, float] | None = None,
) -> PlanResult:
    """Solve capped integer allocation; demand bounds are floored to whole units."""
    if not isfinite(budget) or budget < 0:
        raise ValueError("budget must be a finite non-negative amount")
    if not isfinite(demand_scale) or demand_scale < 0:
        raise ValueError("demand_scale must be finite and non-negative")
    if storage_limit is not None and storage_limit < 0:
        raise ValueError("storage_limit must be non-negative")
    skus = [p.sku for p in products]
    if len(set(skus)) != len(skus):
        raise ValueError("product SKUs must be unique")
    bounds_hi: list[int] = []
    bounds_lo: list[int] = []
    effective: list[ProductOption] = []
    overrides = forecast_overrides or {}
    for p in products:
        if not p.sku or not all(isfinite(x) for x in (p.cost, p.profit)) or p.cost < 0:
            raise ValueError(f"invalid cost/profit for {p.sku!r}")
        if p.pack_size < 1:
            raise ValueError(f"{p.sku}: pack size must be at least 1")
        if p.demand < 0 or p.min_qty < 0:
            raise ValueError(f"invalid quantity bounds for {p.sku!r}")
        if p.force_include and p.force_exclude:
            raise ValueError(f"{p.sku}: cannot force include and exclude")
        raw_demand = overrides.get(p.sku, p.demand)
        if not isfinite(raw_demand) or raw_demand < 0:
            raise ValueError(f"invalid forecast override for {p.sku!r}")
        hi = floor(raw_demand * demand_scale + 1e-9)
        lo = max(p.min_qty, p.pack_size if p.force_include else 0)
        if p.force_exclude:
            if lo:
                raise InfeasiblePlan(f"{p.sku}: forced exclusion conflicts with minimum quantity")
            hi = 0
        if p.profit <= 0:
            if lo:
                raise InfeasiblePlan(f"{p.sku}: mandatory minimum has non-positive margin")
            hi = 0
        if p.cost == 0 and p.profit > 0 and hi > 0:
            # Zero cost is valid; all profitable available units remain desirable.
            pass
        if hi < lo:
            raise InfeasiblePlan(f"{p.sku}: minimum quantity {lo} exceeds adjusted demand cap {hi}")
        if lo and lo % p.pack_size:
            raise InfeasiblePlan(f"{p.sku}: minimum quantity must be a pack-size multiple")
        # Integer units are expressed as pack counts; quantities are reconstructed below.
        bounds_lo.append(lo // p.pack_size)
        bounds_hi.append(hi // p.pack_size)
        effective.append(p)
    n = len(effective)
    if n == 0:
        return PlanResult((), 0, budget, 0, 0, 0, {})
    costs = np.array([p.cost * p.pack_size for p in effective], dtype=float)
    profits = np.array([p.profit * p.pack_size for p in effective], dtype=float)
    constraints = []
    matrix = lil_matrix((1 + (storage_limit is not None), n), dtype=float)
    matrix[0, :] = costs
    upper = [budget]
    lower = [-np.inf]
    if storage_limit is not None:
        matrix[1, :] = np.array([p.pack_size for p in effective], dtype=float)
        upper.append(storage_limit)
        lower.append(-np.inf)
    constraints.append(LinearConstraint(matrix.tocsr(), np.array(lower), np.array(upper)))
    # Exclude neutral/negative margin quantities unless required by minimum bounds.
    c = -profits
    result = milp(c, integrality=np.ones(n), bounds=Bounds(bounds_lo, bounds_hi), constraints=constraints,
                  options={"disp": False})
    if result.status == 2:
        raise InfeasiblePlan("budget, storage, and mandatory minimums have no feasible allocation")
    if not result.success or result.x is None:
        raise RuntimeError(f"MILP solver did not return an optimum: {result.message}")
    quantities = {p.sku: int(round(result.x[i])) * p.pack_size for i, p in enumerate(effective)}
    greedy = _greedy(effective, bounds_lo, bounds_hi, costs, budget, storage_limit)
    items = []
    for p in effective:
        q = quantities[p.sku]
        cap = bounds_hi[skus.index(p.sku)] * p.pack_size
        if p.force_exclude:
            reason = "Excluded by seller"
        elif cap == 0:
            reason = "No forecast demand"
        elif p.profit <= 0:
            reason = "No positive margin"
        elif q == cap:
            reason = "Capped by forecast demand"
        elif budget - sum(quantities[x.sku] * x.cost for x in effective) < p.cost:
            reason = "Budget ran out"
        elif q == 0:
            reason = "Limited by budget or storage"
        else:
            reason = "Best profit per rupee"
        items.append(ItemResult(p.sku, q, q * p.cost, q * p.profit, reason))
    spent = sum(i.spend for i in items)
    profit = sum(i.expected_profit for i in items)
    return PlanResult(tuple(items), spent, max(0, budget - spent), profit,
                      profit / spent if spent else 0, sum(greedy[p.sku] * p.profit for p in effective), greedy)


def _greedy(products: Sequence[ProductOption], lo: Sequence[int], hi: Sequence[int], costs: np.ndarray,
            budget: float, storage_limit: int | None) -> dict[str, int]:
    n = len(products)
    counts = list(lo)
    spent = sum(counts[i] * costs[i] for i in range(n))
    stored = sum(counts[i] * products[i].pack_size for i in range(n))
    if spent > budget + 1e-9 or (storage_limit is not None and stored > storage_limit):
        raise InfeasiblePlan("mandatory minimums exceed budget or storage")
    order = sorted(range(n), key=lambda i: (-(products[i].profit / products[i].cost if products[i].cost else float("inf")), products[i].sku))
    for i in order:
        p = products[i]
        while counts[i] < hi[i] and spent + costs[i] <= budget + 1e-9 and (storage_limit is None or stored + p.pack_size <= storage_limit):
            counts[i] += 1
            spent += costs[i]
            stored += p.pack_size
    return {p.sku: counts[i] * p.pack_size for i, p in enumerate(products)}
