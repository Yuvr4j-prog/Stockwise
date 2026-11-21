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
- `d_i` = forecast after override and risk scaling, `u_i = floor(d_i / s_i)` = pack cap;
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
- `stockwise/optimizer.py::solve_plan` applies `d_i = forecast_i × demand_scale × risk_multiplier`, then floors the cap to whole units and to full packs. Named multipliers are Safe `0.80`, Balanced `1.00`, Aggressive `1.15`; numeric `demand_scale` multiplies the named factor.

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
- All monetary inputs, demand, risk scales, storage, MOQ, pack size, flags, and overrides are validated for finite/nonnegative or whole-number requirements as appropriate.
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

## Stage 2: FastAPI, auth, and persistence endpoints

**No LPP involved.** The API scopes seller data, converts saved history/products into the Stage 1.5 forecasting and MILP inputs, and persists each recommendation and its inputs.

## Stage 3: frontend (not built)

**No LPP involved.** The frontend will display product histories and call forecast/plan APIs; it does not construct a different optimization model.

## Stage 4: packaging and seed data (not built)

**No LPP involved.** Compose and demo data will provide the PostgreSQL environment and sample inputs for the same optimizer.
