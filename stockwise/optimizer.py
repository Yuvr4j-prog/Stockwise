"""Whole-unit, optional-MOQ allocation using scipy.optimize.milp."""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from math import ceil, floor, isfinite
from numbers import Real
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

RISK_MULTIPLIERS = {"safe": 0.80, "balanced": 1.00, "aggressive": 1.15}


@dataclass(frozen=True)
class ProductOption:
    sku: str
    cost: float
    profit: float
    demand: float
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
    """Raised when requested mandatory orders cannot satisfy the constraints."""


def _whole_number(value: object) -> bool:
    try:
        return not isinstance(value, bool) and isinstance(value, (Real, Decimal)) and isfinite(value) and int(value) == value
    except (TypeError, ValueError, OverflowError):
        return False


def _finite_number(value: object) -> bool:
    try:
        return not isinstance(value, bool) and isinstance(value, (Real, Decimal)) and isfinite(value)
    except (TypeError, ValueError, OverflowError):
        return False


def solve_plan(
    products: Sequence[ProductOption], budget: float, *, storage_limit: int | None = None,
    demand_scale: float = 1.0, risk_mode: str | None = None,
    forecast_overrides: Mapping[str, float] | None = None,
) -> PlanResult:
    """Maximize profit with whole units/packs and optional-or-required MOQs.

    ``risk_mode`` multiplies ``demand_scale``; omit it to use only the numeric
    scale. A selected risk mode uses the explicit, user-facing multipliers.
    """
    if not _finite_number(budget) or budget < 0:
        raise ValueError("budget must be a finite non-negative amount")
    budget = float(budget)
    if not _finite_number(demand_scale) or demand_scale < 0:
        raise ValueError("demand_scale must be finite and non-negative")
    demand_scale = float(demand_scale)
    if storage_limit is not None and (not _whole_number(storage_limit) or storage_limit < 0):
        raise ValueError("storage_limit must be a finite non-negative whole number")
    risk_multiplier = 1.0
    if risk_mode is not None:
        if not isinstance(risk_mode, str):
            raise ValueError("risk_mode must be safe, balanced, or aggressive")
        normalized_mode = risk_mode.lower()
        if normalized_mode not in RISK_MULTIPLIERS:
            raise ValueError("risk_mode must be safe, balanced, or aggressive")
        risk_multiplier = RISK_MULTIPLIERS[normalized_mode]
    scale = demand_scale * risk_multiplier
    if not isfinite(scale):
        raise ValueError("combined demand scale must be finite")
    skus = [p.sku for p in products]
    if any(not isinstance(sku, str) or not sku.strip() for sku in skus):
        raise ValueError("product SKU must be a non-empty string")
    if len(set(skus)) != len(skus):
        raise ValueError("product SKUs must be unique")
    overrides = forecast_overrides or {}
    if any(not isinstance(key, str) for key in overrides):
        raise ValueError("forecast override keys must be product SKUs")
    unknown_overrides = set(overrides) - set(skus)
    if unknown_overrides:
        raise ValueError(f"forecast overrides contain unknown SKU(s): {', '.join(sorted(unknown_overrides))}")

    count = len(products)
    pack_caps: list[int] = []
    min_packs: list[int] = []
    binary_for: dict[int, int] = {}
    effective: list[ProductOption] = []
    for i, p in enumerate(products):
        if not _finite_number(p.cost) or not _finite_number(p.profit) or p.cost < 0:
            raise ValueError(f"invalid cost/profit for {p.sku!r}")
        if not _whole_number(p.demand) or p.demand < 0:
            raise ValueError(f"{p.sku}: demand must be a finite non-negative quantity")
        if not _whole_number(p.min_qty) or p.min_qty < 0:
            raise ValueError(f"{p.sku}: MOQ must be a non-negative whole number")
        if not _whole_number(p.pack_size) or p.pack_size < 1:
            raise ValueError(f"{p.sku}: pack size must be a positive whole number")
        if not isinstance(p.force_include, bool) or not isinstance(p.force_exclude, bool):
            raise ValueError(f"{p.sku}: force flags must be boolean")
        if p.force_include and p.force_exclude:
            raise InfeasiblePlan(f"{p.sku}: cannot force include and exclude")
        p = replace(p, cost=float(p.cost), profit=float(p.profit), demand=float(p.demand),
                    min_qty=int(p.min_qty), pack_size=int(p.pack_size))
        raw_demand = overrides.get(p.sku, p.demand)
        if not _finite_number(raw_demand) or raw_demand < 0:
            raise ValueError(f"{p.sku}: forecast override must be finite and non-negative")
        scaled_demand = float(raw_demand) * scale
        if not _finite_number(scaled_demand):
            raise ValueError(f"{p.sku}: adjusted demand cap must be finite")
        unit_cap = floor(scaled_demand + 1e-9)
        max_packs = unit_cap // p.pack_size
        needed_packs = ceil(p.min_qty / p.pack_size) if p.min_qty else (1 if p.force_include else 0)
        has_activation = p.min_qty > 0 or p.force_include
        if p.force_exclude:
            max_packs = 0
        if p.profit <= 0:
            if p.force_include:
                raise InfeasiblePlan(f"{p.sku}: forced inclusion has non-positive margin")
            max_packs = 0
        if has_activation and max_packs < needed_packs:
            if p.force_include:
                raise InfeasiblePlan(
                    f"{p.sku}: forced inclusion is infeasible because the adjusted demand cap "
                    f"({unit_cap} units) is below its MOQ/order multiple ({needed_packs * p.pack_size} units)"
                )
            # Optional MOQ cannot be reached, so this SKU is simply unavailable.
            max_packs = 0
        pack_caps.append(max_packs)
        min_packs.append(needed_packs if max_packs else 0)
        effective.append(p)

    if not count:
        return PlanResult((), 0, budget, 0, 0, 0, {})

    # y_i are pack counts. z_i switches products with an MOQ or forced include on/off.
    for i, p in enumerate(effective):
        if (p.min_qty > 0 or p.force_include) and pack_caps[i] > 0:
            binary_for[i] = count + len(binary_for)
    variable_count = count + len(binary_for)
    costs = np.zeros(variable_count)
    profits = np.zeros(variable_count)
    for i, p in enumerate(effective):
        costs[i] = p.cost * p.pack_size
        profits[i] = p.profit * p.pack_size
    if not np.isfinite(costs).all() or not np.isfinite(profits).all():
        raise ValueError("pack-adjusted cost/profit coefficients must be finite")

    # Base budget/storage rows plus two linking rows for each product activation binary.
    link_count = len(binary_for) * 2
    row_count = 1 + (storage_limit is not None) + link_count
    matrix = lil_matrix((row_count, variable_count), dtype=float)
    matrix[0, :count] = costs[:count]
    row_upper = [float(budget)]
    row_lower = [-np.inf]
    if storage_limit is not None:
        for i, p in enumerate(effective):
            matrix[1, i] = p.pack_size
        row_lower.append(-np.inf)
        row_upper.append(float(storage_limit))
    row = 1 + (storage_limit is not None)
    for i, z_idx in binary_for.items():
        matrix[row, i] = 1
        matrix[row, z_idx] = -pack_caps[i]
        row_lower.append(-np.inf)
        row_upper.append(0)
        row += 1
        matrix[row, i] = 1
        matrix[row, z_idx] = -min_packs[i]
        row_lower.append(0)
        row_upper.append(np.inf)
        row += 1

    lower_bounds = [0.0] * variable_count
    upper_bounds = [float(v) for v in pack_caps] + [1.0] * len(binary_for)
    for i, z_idx in binary_for.items():
        if effective[i].force_include:
            lower_bounds[z_idx] = upper_bounds[z_idx] = 1.0
    result = milp(
        -profits,
        integrality=np.ones(variable_count),
        bounds=Bounds(lower_bounds, upper_bounds),
        constraints=LinearConstraint(matrix.tocsr(), np.array(row_lower), np.array(row_upper)),
        options={"disp": False},
    )
    if result.status == 2:
        raise InfeasiblePlan("mandatory included products cannot fit within the budget and storage limit")
    if not result.success or result.x is None:
        raise RuntimeError(f"MILP solver did not return an optimum: {result.message}")

    quantities = {p.sku: int(round(result.x[i])) * p.pack_size for i, p in enumerate(effective)}
    greedy = _greedy(effective, pack_caps, min_packs, budget, storage_limit)
    items: list[ItemResult] = []
    for i, p in enumerate(effective):
        quantity = quantities[p.sku]
        cap = pack_caps[i] * p.pack_size
        if p.force_exclude:
            reason = "Excluded by seller"
        elif cap == 0:
            reason = "Below minimum order or no forecast demand"
        elif quantity == cap:
            reason = "Capped by forecast demand"
        elif budget - sum(quantities[x.sku] * x.cost for x in effective) < p.cost:
            reason = "Budget ran out"
        elif quantity == 0:
            reason = "Limited by budget or storage"
        elif p.min_qty and quantity == p.pack_size * min_packs[i]:
            reason = "Minimum order met"
        else:
            reason = "Best profit per rupee"
        items.append(ItemResult(p.sku, quantity, quantity * p.cost, quantity * p.profit, reason))
    spent = sum(item.spend for item in items)
    profit = sum(item.expected_profit for item in items)
    greedy_profit = sum(greedy[p.sku] * p.profit for p in effective)
    return PlanResult(tuple(items), spent, max(0, budget - spent), profit,
                      profit / spent if spent else 0, greedy_profit, greedy)


def _greedy(
    products: Sequence[ProductOption], pack_caps: Sequence[int], min_packs: Sequence[int],
    budget: float, storage_limit: int | None,
) -> dict[str, int]:
    quantities = [0] * len(products)
    for i, p in enumerate(products):
        if p.force_include:
            quantities[i] = min_packs[i]
    spent = sum(quantities[i] * products[i].pack_size * products[i].cost for i in range(len(products)))
    stored = sum(quantities[i] * products[i].pack_size for i in range(len(products)))
    if spent > budget + 1e-9 or (storage_limit is not None and stored > storage_limit):
        raise InfeasiblePlan("forced-included quantities exceed budget or storage")
    order = sorted(range(len(products)), key=lambda i: (
        -(products[i].profit / products[i].cost if products[i].cost else float("inf")), products[i].sku
    ))
    for i in order:
        p = products[i]
        if p.profit <= 0:
            continue
        if quantities[i] == 0 and (p.min_qty > 0 or p.force_include):
            first = min_packs[i]
            add_cost = first * p.pack_size * p.cost
            add_units = first * p.pack_size
            if spent + add_cost > budget + 1e-9 or (storage_limit is not None and stored + add_units > storage_limit):
                continue
            quantities[i] += first
            spent += add_cost
            stored += add_units
        while quantities[i] < pack_caps[i]:
            add_cost = p.pack_size * p.cost
            if spent + add_cost > budget + 1e-9 or (storage_limit is not None and stored + p.pack_size > storage_limit):
                break
            quantities[i] += 1
            spent += add_cost
            stored += p.pack_size
    return {p.sku: quantities[i] * p.pack_size for i, p in enumerate(products)}
