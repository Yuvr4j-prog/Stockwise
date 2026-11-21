from itertools import product as cartesian_product
from math import ceil, floor
import random

import pytest

from stockwise.optimizer import InfeasiblePlan, ProductOption, solve_plan


def test_milp_matches_hand_solved_example_and_greedy_is_suboptimal():
    products = [ProductOption("A", 10, 60, 1), ProductOption("B", 6, 33, 1), ProductOption("C", 6, 33, 1)]
    result = solve_plan(products, 12)
    assert {i.sku: i.quantity for i in result.items} == {"A": 0, "B": 1, "C": 1}
    assert result.total_spent == 12
    assert result.total_profit == 66
    assert result.greedy_profit == 60


def test_random_small_integer_programs_match_brute_force():
    rng = random.Random(2026)
    for _ in range(30):
        products = [ProductOption(str(i), rng.randint(1, 9), rng.randint(-2, 16), rng.randint(0, 4)) for i in range(4)]
        budget = rng.randint(0, 25)
        result = solve_plan(products, budget)
        best = max((sum(p.profit * q for p, q in zip(products, quantities))
                    for quantities in cartesian_product(*(range(p.demand + 1) if p.profit > 0 else range(1) for p in products))
                    if sum(p.cost * q for p, q in zip(products, quantities)) <= budget), default=0)
        assert result.total_profit == best
        assert result.total_spent <= budget


def test_risk_override_pack_storage_minimum_and_force_rules():
    p = ProductOption("rice", 10, 4, 8, min_qty=2, pack_size=2)
    plan = solve_plan([p], 25, demand_scale=0.8, storage_limit=4, forecast_overrides={"rice": 10})
    assert plan.items[0].quantity == 2  # mandatory minimum; the next pack costs more than the remaining budget
    assert plan.total_spent == 20

    forced = solve_plan([ProductOption("oil", 2, 1, 5, pack_size=2, force_include=True)], 4)
    assert forced.items[0].quantity == 2
    excluded = solve_plan([ProductOption("tea", 1, 10, 5, force_exclude=True)], 10)
    assert excluded.items[0].quantity == 0


def test_zero_budget_negative_margin_and_empty_case():
    result = solve_plan([ProductOption("loss", 2, -1, 5), ProductOption("free", 0, 3, 2)], 0)
    assert {i.sku: i.quantity for i in result.items} == {"loss": 0, "free": 2}
    assert result.total_profit == 6
    assert solve_plan([], 50).unspent_budget == 50


def test_infeasible_mandatory_bounds_are_explained():
    # An unreachable optional MOQ makes the product unavailable, not infeasible.
    assert solve_plan([ProductOption("x", 5, 2, 1, min_qty=2)], 5).items[0].quantity == 0
    with pytest.raises(InfeasiblePlan, match="mandatory included"):
        solve_plan([ProductOption("x", 5, 2, 4, min_qty=2, force_include=True)], 5)
    assert solve_plan([ProductOption("x", 1, 2, 1, min_qty=2)], 10).items[0].quantity == 0


def test_duplicate_products_and_invalid_pack_rejected():
    with pytest.raises(ValueError, match="unique"):
        solve_plan([ProductOption("x", 1, 1, 1), ProductOption("x", 1, 1, 1)], 2)
    with pytest.raises(ValueError, match="pack size"):
        solve_plan([ProductOption("x", 1, 1, 1, pack_size=0)], 2)


def test_named_risk_multipliers_are_applied_on_top_of_numeric_scale():
    product = [ProductOption("x", 1, 1, 10)]
    assert solve_plan(product, 100, risk_mode="safe").items[0].quantity == 8
    assert solve_plan(product, 100, risk_mode="balanced").items[0].quantity == 10
    assert solve_plan(product, 100, risk_mode="aggressive").items[0].quantity == 11
    assert solve_plan(product, 100, risk_mode="aggressive", demand_scale=0.5).items[0].quantity == 5


def test_moq_is_optional_and_non_multiple_minimum_rounds_to_full_packs():
    optional = solve_plan([ProductOption("x", 2, 4, 8, min_qty=5, pack_size=3)], 4)
    assert optional.items[0].quantity == 0
    buy_minimum = solve_plan([ProductOption("x", 2, 4, 8, min_qty=5, pack_size=3)], 12)
    assert buy_minimum.items[0].quantity == 6


def test_force_include_fails_clearly_when_budget_or_margin_makes_it_impossible():
    with pytest.raises(InfeasiblePlan, match="budget and storage"):
        solve_plan([ProductOption("x", 10, 4, 4, force_include=True)], 9)
    with pytest.raises(InfeasiblePlan, match="non-positive margin"):
        solve_plan([ProductOption("x", 1, -1, 4, force_include=True)], 9)


@pytest.mark.parametrize("budget", [float("nan"), float("inf"), -1, None])
def test_invalid_budgets_are_rejected(budget):
    with pytest.raises(ValueError, match="budget"):
        solve_plan([], budget)


@pytest.mark.parametrize("scale", [float("nan"), float("inf"), -1, None])
def test_invalid_numeric_demand_scales_are_rejected(scale):
    with pytest.raises(ValueError, match="demand_scale"):
        solve_plan([], 10, demand_scale=scale)


@pytest.mark.parametrize("option", [
    ProductOption("x", float("nan"), 1, 1),
    ProductOption("x", float("inf"), 1, 1),
    ProductOption("x", -1, 1, 1),
    ProductOption("x", 1, float("nan"), 1),
    ProductOption("x", 1, float("inf"), 1),
    ProductOption("x", 1, 1, float("nan")),
    ProductOption("x", 1, 1, float("inf")),
    ProductOption("x", 1, 1, -1),
    ProductOption("x", 1, 1, 2, min_qty=-1),
    ProductOption("x", 1, 1, 2, pack_size=1.5),
    ProductOption("x", 1, 1, 2, force_include=1),
])
def test_invalid_product_inputs_are_rejected(option):
    with pytest.raises(ValueError):
        solve_plan([option], 10)


@pytest.mark.parametrize("storage", [-1, float("inf"), float("nan"), 1.5])
def test_invalid_storage_limits_are_rejected(storage):
    with pytest.raises(ValueError, match="storage_limit"):
        solve_plan([], 10, storage_limit=storage)


@pytest.mark.parametrize("overrides", [{"x": -1}, {"x": float("nan")}, {"x": float("inf")}, {"other": 2}])
def test_invalid_forecast_overrides_are_rejected(overrides):
    with pytest.raises(ValueError):
        solve_plan([ProductOption("x", 1, 1, 2)], 10, forecast_overrides=overrides)


def test_milp_matches_brute_force_for_300_random_constrained_cases():
    rng = random.Random(21051)
    risk_values = {"safe": 0.8, "balanced": 1.0, "aggressive": 1.15}
    for _ in range(300):
        risk_mode = rng.choice(list(risk_values))
        demand_scale = rng.choice([0.75, 1.0, 1.2])
        products = []
        for index in range(rng.randint(1, 4)):
            force_include = rng.random() < 0.10
            force_exclude = not force_include and rng.random() < 0.12
            products.append(ProductOption(
                sku=f"{index}", cost=rng.randint(0, 9), profit=rng.randint(-2, 15),
                demand=rng.randint(0, 6), min_qty=rng.randint(0, 6), pack_size=rng.randint(1, 3),
                force_include=force_include, force_exclude=force_exclude,
            ))
        budget = rng.randint(0, 24)
        storage = rng.randint(0, 12)
        overrides = {p.sku: rng.randint(0, 7) for p in products if rng.random() < 0.15}
        all_choices = []
        for p in products:
            cap_units = floor(overrides.get(p.sku, p.demand) * demand_scale * risk_values[risk_mode] + 1e-9)
            cap_packs = cap_units // p.pack_size
            min_packs = ceil(p.min_qty / p.pack_size) if p.min_qty else (1 if p.force_include else 0)
            if p.force_exclude or p.profit <= 0:
                choices = [] if p.force_include else [0]
            elif min_packs > cap_packs:
                choices = [] if p.force_include else [0]
            else:
                choices = list(range(min_packs, cap_packs + 1))
                if min_packs > 0:
                    choices = ([] if p.force_include else [0]) + list(range(min_packs, cap_packs + 1))
            all_choices.append([packs * p.pack_size for packs in choices])
        feasible = [units for units in cartesian_product(*all_choices)
                    if sum(q * p.cost for q, p in zip(units, products)) <= budget
                    and sum(units) <= storage]
        if not feasible:
            with pytest.raises(InfeasiblePlan):
                solve_plan(products, budget, storage_limit=storage, demand_scale=demand_scale,
                           risk_mode=risk_mode, forecast_overrides=overrides)
            continue
        expected_profit = max(sum(q * p.profit for q, p in zip(units, products)) for units in feasible)
        result = solve_plan(products, budget, storage_limit=storage, demand_scale=demand_scale,
                            risk_mode=risk_mode, forecast_overrides=overrides)
        assert result.total_profit == expected_profit
        assert result.total_spent <= budget + 1e-8
        assert sum(item.quantity for item in result.items) <= storage
        for p, item in zip(products, result.items):
            assert item.quantity % p.pack_size == 0
            assert item.quantity <= floor(overrides.get(p.sku, p.demand) * demand_scale * risk_values[risk_mode] + 1e-9)
            if p.force_include:
                assert item.quantity >= max(p.min_qty, p.pack_size)
            elif item.quantity:
                assert item.quantity >= p.min_qty
