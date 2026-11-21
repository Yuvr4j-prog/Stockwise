# Linear programming notes by stage

## Stage 1: data model, migration, forecasting, and imports

Data model/migration: **No LPP involved.** This stage stores product costs/margins and sales history consumed by forecasting and optimization.

Forecasting: **No LPP involved.** The forecast produces the demand cap consumed by the optimizer.

CSV/XLSX imports: **No LPP involved.** The parser produces product costs/margins and dated weekly observations consumed by forecasting and optimization.

The original Stage 1 formulation treated every nonzero minimum quantity as mandatory. Stage 1.5 below supersedes that behavior with an optional MOQ activation variable.

## Stage 1.5: forecasting and import corrections

Forecasting/import validation: **No LPP involved.** Stockout-adjusted forecasts and validated sales rows produce inputs for the MILP.

## Stage 1.5: optimizer with optional MOQ

For each product `i`, let:

- `y_i` = integer number of packs ordered;
- `z_i ∈ {0,1}` = whether an MOQ/forced product is activated;
- `s_i` = units per pack, `c_i` = unit cost, `p_i` = unit profit;
- `f_i` = statistical forecast or seller override (both may be fractional);
- `r_i` = named risk multiplier (`0.80`, `1.00`, or `1.15`) and `q` = optional numeric scale;
- `D_i = floor(f_i × r_i × q + ε)` = whole-unit demand cap after risk scaling (`ε=10⁻⁹` only avoids binary floating-point underflow at an integer boundary);
- `u_i = floor(D_i / s_i)` = pack cap;
- `m_i = ceil(MOQ_i / s_i)` = minimum packs that satisfy MOQ;
- `B` = budget and `S` = optional storage capacity in units.

For an MOQ product or a forced inclusion, the formulation is:

\[
\max \sum_i p_i s_i y_i
\]
subject to
\[
\sum_i c_i s_i y_i \le B, \qquad
\sum_i s_i y_i \le S \quad (\text{when storage is set}),
\]
\[
m_i z_i \le y_i \le u_i z_i, \qquad
y_i \in \mathbb{Z}_{\ge 0},\quad z_i \in \{0,1\}.
\]

When there is no MOQ and no forced inclusion, `z_i` is unnecessary and `0 ≤ y_i ≤ u_i`. When `MOQ_i=0` but the seller forces inclusion, use `m_i=1`. Force exclusion sets the cap to zero. If an optional product's cap is below its MOQ, it is unavailable (`y_i=0`); if it is forced included, the plan is infeasible and the API reports that condition. The minimum is rounded upward to complete packs.

Plain language: maximize expected unit profit while respecting money, storage, whole packs, and forecast demand. An MOQ product is either not ordered or bought in enough complete packs to meet its supplier minimum. A forced inclusion fixes its activation to one.

This is a **MILP**. The objective and constraints are linear; pack quantities `y_i` are integers and activation variables `z_i` are binary. The binary is essential because it models the disjunction “zero or at least MOQ.” Relaxing integrality could produce fractional packs or a fractional activation that buys below MOQ.

### Risk and forecast inputs

- `stockwise/forecasting.py::forecast` first adjusts each flagged observation to `max(observed_sales, mean(unflagged_sales))`, then runs the selected method. If every observation is flagged it uses the recorded values and marks confidence low. A most-recent flagged sale remains a final one-week lower bound. No historical flagged maximum is carried forward as a permanent floor.
- `stockwise/api.py::_product_forecast` applies a seller's forecast override when set; otherwise it uses the statistical forecast.
- `stockwise/optimizer.py::solve_plan` accepts finite nonnegative fractional forecast demand and overrides, applies `forecast × demand_scale × risk_multiplier`, floors to the whole-unit cap `D_i`, then floors again to complete packs. Named multipliers are Safe `0.80`, Balanced `1.00`, Aggressive `1.15`; numeric `demand_scale` multiplies the named factor. The API continues to return the unrounded forecast for display while the allocation remains integer-valued.

### Mapping constraints to code

- `stockwise/optimizer.py::solve_plan` builds integer pack variables, optional binary activation variables, upper/lower linking rows, objective coefficients, and the SciPy `LinearConstraint`.
- The budget row coefficient is `cost_i × pack_size_i`; its upper bound is `budget`.
- Optional storage row coefficients are `pack_size_i`; its upper bound is `storage_limit`.
- MOQ and forced-inclusion links are `y_i - cap_packs_i*z_i ≤ 0` and `y_i - min_packs_i*z_i ≥ 0`. Forced inclusion sets the binary lower/upper bound to one. Forced exclusion sets the pack cap to zero.
- SciPy `Bounds` gives pack variables zero lower bounds and their adjusted demand upper bounds; binary linking rows allow optional MOQ products to remain at zero.
- The post-solve outputs and greedy comparison are reconstructed in whole units from pack counts.

### Edge cases and solver behavior

- Optional unreachable MOQ is set to zero units; a forced inclusion with an unreachable cap or nonpositive margin raises `InfeasiblePlan`.
- A forced-included allocation that exceeds budget/storage has no feasible MILP solution and raises `InfeasiblePlan`; no constraint is relaxed and no invalid fallback plan is returned.
- Negative-margin optional products are disabled; zero-demand products have no available packs. Zero-cost profitable products remain bounded by demand and storage.
- Monetary inputs, demand, risk scales, and overrides are checked for finiteness and nonnegativity; storage, MOQ, pack size, and flags are validated as whole-number/boolean inputs as appropriate. Fractional demand is valid; quantities and pack counts remain integral.
- Demand caps bound every variable, so the objective is not unbounded. Tied optima may be selected by HiGHS; greedy ties use SKU order.

### Worked example: an optional MOQ

Budget `B=₹12`, storage `S=4` units:

| SKU | Unit cost | Unit profit | Pack size | MOQ | Forecast | Possible positive orders |
|---|---:|---:|---:|---:|---:|---|
| A | ₹3 | ₹4 | 2 | 3 | 6 | 0, 4, or 6 units |
| B | ₹4 | ₹5 | 1 | 0 | 2 | 0, 1, or 2 units |

For A, `m_A=ceil(3/2)=2` packs. Buying 4 units costs ₹12 and earns ₹16; 6 units exceed budget and storage. Buying B's full cap costs ₹8 and earns ₹10. With A's 4 units, storage is full, so no B can be added. The exact solver chooses `A=4, B=0`, spends ₹12, and earns ₹16. The greedy ratio order is A (`4/3`) before B (`5/4`) and also selects A=4, matching the solver. The domain test `test_moq_is_optional_and_non_multiple_minimum_rounds_to_full_packs` verifies the pack-rounded minimum; the API suite verifies an affordable budget that still skips the optional MOQ.

### Greedy comparison and a suboptimal case

The greedy baseline sorts by unit profit/cost (zero-cost items first, then SKU) and adds each product while its MOQ threshold, budget, and storage allow. It is a quick comparison, not a substitute for the MILP.

With one-unit packs and one-unit demand caps, let A cost ₹10/profit ₹60, B cost ₹6/profit ₹33, C cost ₹6/profit ₹33, and budget ₹12. Greedy takes A first (ratio 6 versus 5.5), then cannot afford B/C, earning ₹60. The exact solver takes B+C and earns ₹66. `tests/test_optimizer.py::test_milp_matches_hand_solved_example_and_greedy_is_suboptimal` checks that output.

The seeded 300-case property-style test enumerates every feasible quantity for small random instances with MOQs, pack sizes, storage limits, risk modes, overrides, and forced include/exclude choices, then asserts the SciPy MILP profit is optimal or correctly infeasible.

### Fractional-demand correction and worked example

The optimizer previously rejected a fractional `ProductOption.demand` before reaching its existing scale-and-floor calculation. This caused `/api/v1/plans/optimize` to return a 500 for ordinary moving-average forecasts and fractional overrides. `stockwise/optimizer.py::solve_plan` now validates demand with the finite-number check, selects an override when present, applies risk/numeric scaling, and floors the result to whole units before deriving full-pack caps. Regression coverage is in `tests/test_optimizer.py::test_fractional_demand_is_scaled_then_floored_for_each_risk_mode`, `test_fractional_forecast_override_is_scaled_then_floored`, `test_fractional_demand_hand_example_with_three_products`, and the fractional cases in `test_milp_matches_brute_force_for_300_random_constrained_cases`; API coverage verifies the 38.33 moving average and a 37.5 override.

For a hand-solvable three-product case with Balanced risk (`r=1`), unit packs, no MOQ, no storage cap, and budget ₹10:

| SKU | Unit cost | Unit profit | Fractional forecast | Whole-unit cap |
|---|---:|---:|---:|---:|
| A | ₹3 | ₹5 | 2.4 | 2 |
| B | ₹4 | ₹7 | 1.8 | 1 |
| C | ₹5 | ₹8 | 1.1 | 1 |

The only cap-respecting combinations that spend at most ₹10 include `A=2,B=1,C=0` (spend ₹10, profit ₹17), `B=1,C=1` (₹9, ₹15), `A=1,C=1` (₹8, ₹13), and `A=2` (₹6, ₹10); therefore the exact optimum is `A=2,B=1,C=0`, with ₹10 spent and ₹17 expected profit. `tests/test_optimizer.py::test_fractional_demand_hand_example_with_three_products` asserts this exact solver result. Greedy orders B then A and happens to match here; the earlier A/B/C budget-₹12 example remains the case where greedy earns ₹60 while the exact solution earns ₹66.

## Stage 2: FastAPI, auth, and persistence endpoints

**No LPP involved.** The API scopes seller data, converts saved history/products into the Stage 1.5 forecasting and MILP inputs, and persists each recommendation and its inputs.

### Stage 2 bug fix: fractional forecasts

**No new LPP is involved.** The API consumes a continuous statistical forecast or override as demand input; the optimizer converts it to a whole-unit demand bound after risk scaling. The objective, integer variables, pack/MOQ links, budget, and storage constraints are unchanged. `stockwise/api.py::optimize` passes the forecast value through to `stockwise/optimizer.py::solve_plan`; `tests/test_api.py::test_optimize_accepts_fractional_moving_average_forecast` and `test_optimize_accepts_fractional_forecast_override` verify both API paths. The generic 500 handler now logs a traceback server-side; error reporting does not alter the LPP.

## Stage 3: frontend

**No LPP involved.** The frontend consumes product histories and forecast results, sends budget/risk/optional constraints to the Stage 2 optimizer endpoint, and displays the saved MILP allocation in both the full table and purchase slip. It does not construct or solve a separate optimization model.

## Stage 4: packaging, deployment readiness, and seed data

**No LPP involved.** Packaging, health checks, rate limits, and the seed command do not formulate or solve an allocation; the seeded weekly sales and product fields are ordinary seller inputs that the existing Stage 1.5 forecast and MILP can consume. The app's saved plans remain outputs of the unchanged Stage 1.5 formulation.

No objective, decision variable, or optimization constraint was added or changed in this stage. For the existing integer formulation, the fractional-demand three-product example above still yields `A=2, B=1, C=0`, spend ₹10, profit ₹17; the hand-solved greedy-suboptimal example above yields ₹60 greedy versus ₹66 MILP. Stage 4's seed data supplies inputs to the existing LPP. LPP-related unit tests passed in the available test run; PostgreSQL migrations and the API-to-solver path were not re-run because PostgreSQL could not bind to localhost and Docker was unavailable.
