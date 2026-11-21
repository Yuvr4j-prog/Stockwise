from itertools import product
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
                    for quantities in product(*(range(p.demand + 1) if p.profit > 0 else range(1) for p in products))
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
    with pytest.raises(InfeasiblePlan, match="mandatory minimums"):
        solve_plan([ProductOption("x", 5, 2, 4, min_qty=2)], 5)
    with pytest.raises(InfeasiblePlan, match="demand cap"):
        solve_plan([ProductOption("x", 1, 2, 1, min_qty=2)], 10)


def test_duplicate_products_and_invalid_pack_rejected():
    with pytest.raises(ValueError, match="unique"):
        solve_plan([ProductOption("x", 1, 1, 1), ProductOption("x", 1, 1, 1)], 2)
    with pytest.raises(ValueError, match="pack size"):
        solve_plan([ProductOption("x", 1, 1, 1, pack_size=0)], 2)
