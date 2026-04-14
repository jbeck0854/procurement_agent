# optimization/

## Overview

This folder contains the LP-based procurement allocation layer.

Its job is singular and decisive:

> **Given what we need to buy, who should we buy it from, and in what quantity?**

The layer takes the upstream procurement requirement and produces an optimized supplier allocation that respects business constraints — budget, compliance, risk tolerance, concentration limits, and optionally, country diversification.

---

## File Contents

| File | Purpose |
|---|---|
| `run_lp_optimization.py` | Main optimization module — loads requirement, scores suppliers, builds and solves LP, returns structured result |
| `__init__.py` | Package init for clean imports |

---

## What This Layer Depends On

This module does **not** forecast demand, build BOMs, or compute safety stock.
It consumes the outputs of upstream layers that are already complete:

| Layer | What it provides |
|---|---|
| Forecasting | Forward finished-goods demand |
| BOM | Component demand derived from finished-goods forecast |
| Inventory / procurement requirement | Net procurement need after inventory offset |
| Supplier scoring (`analytics/scoring.py`) | Landed cost, risk penalty, compliance status, supplier tier |

---

## Main Inputs

### Procurement Requirement

The LP computes a **horizon-level** net requirement by aggregating full-horizon gross demand and applying the inventory offset **once per facility**:

```
facility_net_req = max(0,
    SUM(gross_requirement across all forecast weeks)
    + backorder_qty
    + safety_stock_qty
    - on_hand_qty
    - scheduled_receipts_qty
)
```

This is **not** the weekly procurement trigger view. That view applies the inventory offset once per forecast week (for explainability/drill-down). Summing it would apply the offset N times, producing a demand floor 40–1000× too small.

The LP demand floor is aggregated across all facilities with positive net requirement unless `facility_id` is specified.

To inspect the demand floor in plain language before running the LP, use `get_aggregated_procurement_need_tool()` from the inventory planning layer.

> **Data currency note.** Inventory state (on-hand, safety stock) is sourced from the most recent run of `run_inventory.py`. Re-run it after regenerating a forecast to keep the LP demand floor aligned.

### Supplier Universe

Loaded from `vw_supplier_complete_profile` and scored via `SupplierScorer.score()`. Provides:
- Landed unit cost
- Risk penalty (normalized 0–1)
- Compliance eligibility
- Supplier decision tier (Preferred / Acceptable / Avoid)
- MOQ / bulk-unit threshold
- Lead time (mean, used for urgency normalization)

---

## Objective Function

Minimize total risk-adjusted procurement cost:

```
minimize  Σ_j  c_j × (1 + λ_risk × r_j + λ_urgency × lt_norm_j) × x_j
```

| Symbol | Definition |
|---|---|
| `c_j` | Landed unit cost (USD/unit) |
| `r_j` | Risk penalty, normalized 0–1 |
| `lt_norm_j` | Lead-time mean, normalized 0–1 within eligible pool (0 = fastest, 1 = slowest) |
| `λ_risk` | User-controlled risk weight (default 0.50) |
| `λ_urgency` | `URGENCY_LEAD_TIME_WEIGHT` (0.25) when `urgency=True`, else 0 |
| `x_j` | Quantity allocated to supplier `j` (continuous, ≥ 0) |

**Interpreting λ_risk:**

| λ_risk value | Business intent |
|---|---|
| 0.0 | Cost only — risk profile ignored |
| 0.25 | Cost-focused, low risk weight |
| 0.50 | Balanced cost/risk tradeoff (default) |
| 1.0 | Risk-averse — risk carries equal weight to cost |
| 1.5 | Risk-priority — risk penalty dominates |

**Urgency mode** adds a lead-time cost premium using the same multiplicative structure as `λ_risk`. The slowest eligible supplier carries a 25% effective cost markup; the fastest carries none. No suppliers are excluded — feasibility is preserved.

---

## Constraints

| Constraint | When active | What it enforces |
|---|---|---|
| Demand fulfillment | Always | `Σ x_j ≥ D` (adjusted requirement) |
| Budget cap | If `budget_cap` is set | `Σ c_j × x_j ≤ budget_cap` |
| Compliance filter | Always | Suppliers below `compliance_threshold` are excluded before building the LP |
| Supplier share cap | If `diversification_mode = "supplier_share_only"` | `x_j ≤ max_supplier_share × D` for each supplier |
| Country diversification (MIP) | If `diversification_mode = "country_diversified"` | Exactly 3 suppliers, each from a different country, each ~30–35% of volume |
| Service level buffer | If `service_level_target > 1.0` | `D_adjusted = D × service_level_target` (additive buffer above requirement) |

### Diversification Modes

Three modes are supported. **The objective function never changes** — only constraints are added.

- **`none`** — No concentration constraint. LP concentrates on lowest adjusted-cost supplier(s).
- **`supplier_share_only`** — Enforces `max_supplier_share` cap per supplier. Spreads volume across multiple suppliers.
- **`country_diversified`** — Mixed Integer Program (MIP) extension:
  - Binary variables `y_j ∈ {0,1}` added
  - `Σ y_j = 3` (exactly 3 suppliers selected)
  - `Σ_{j ∈ country_c} y_j ≤ 1` (at most one per country)
  - `0.30·D ≤ x_j ≤ 0.35·D` for selected suppliers
  - Requires ≥ 3 countries in the eligible pool; falls back gracefully with a `diversification_fallback_note` if infeasible

### Service Level

`service_level_target` is an additive procurement buffer — it scales the demand target above the requirement the inventory layer already computed. It does **not** rebuild safety stock.

- `1.00` = procure exactly to requirement
- `1.10` = procure 10% above requirement

---

## Baseline Comparison

Every LP run silently computes a **baseline plan** alongside the optimized plan.

The baseline is the cheapest feasible compliant plan for the same product and demand, with:
- `lambda_risk = 0` (cost-only objective)
- `diversification_mode = "none"` (no concentration or country constraints)
- `max_supplier_share = 1.0` (single-supplier concentration allowed)
- Same compliance filter applied

The baseline record is stored in `result["baseline"]` and contains:

| Key | Description |
|---|---|
| `baseline_total_cost` | Total cost of the unconstrained cost-only plan |
| `baseline_selected_suppliers` | Number of suppliers used |
| `baseline_lead_supplier_share` | Share held by the largest supplier (0–1) |
| `baseline_country_count` | Number of distinct sourcing countries |

**The baseline is not shown in standard per-run output.** It is reserved for the Final Executive Summary, where it quantifies the cost of risk management and diversification in plain dollar terms.

---

## Final Executive Summary Integration

When the user approves one or more LP runs and triggers **"Complete Procurement Plan"**, the demo assembles a Final Executive Summary that spans all approved runs in the session.

This summary:
- Lists every approved product, total allocated quantity, selected suppliers, countries, and total spend
- Shows a baseline comparison table for each approved run:
  - Optimized plan cost vs. baseline cost-only plan
  - Cost delta (absolute USD and percentage premium)
  - Supplier count delta and country count delta vs. baseline
  - Interpretation label: Negligible (≤1%), Modest (≤10%), or Material (>10%)
- Summarizes diversification posture across all runs
- Characterizes the session-level risk premium as a strategic investment in supply-chain resilience

The baseline comparison makes it straightforward to justify a risk-adjusted or diversified plan to stakeholders — showing precisely how much extra spend the constraints added and what was gained.

**The baseline comparison appears only in the final session summary, not in individual run output.**

### Sourcing Recommendation Logic

The Final Executive Summary includes targeted sourcing recommendations when inventory pressure is elevated. Two behaviors are worth noting:

**Emergency sourcing weeks.** "Contact sales/sourcing immediately" guidance cites only the weeks where Safety Stock Utilization reaches **Moderate or higher (≥50%)**. Low-urgency triggered weeks — where cumulative procurement pressure is below 50% of the SS reserve — are not included. The threshold corresponds to urgency bands `Moderate` (≥50%), `High` (≥75%), and `Critical` (≥100%) in the weekly trigger view.

**Carryover demand.** The allocations approved in a session cover only the current planning horizon. If component demand continues beyond that window — which is likely for multi-quarter production programs — a new optimization must be run against an updated or extended forecast. Current supplier allocations do **not** roll forward automatically. Rerun with refreshed net requirements before the next procurement cycle begins.

---

## Session Behavior

Within a single agent session, a user may run the LP multiple times — for different products, different risk profiles, what-if exclusion scenarios, or diversification variants. Each run is independent.

Runs accumulate in session state as **approved scenarios**. The session summary aggregates across all approved runs, enabling cross-product and cross-scenario comparisons that are not visible in individual run output.

Common session patterns:

| Pattern | How it works |
|---|---|
| **Multi-product** | One LP run per component (transistors, power devices, etc.) — summary covers all |
| **What-if / disruption** | Same product with `exclude_supplier_ids` — appears as a separate scenario in session |
| **Urgency rerun** | Same product with `urgency=True` — compared to the original approved run |
| **Diversification variant** | Same product with `country_diversified` — baseline comparison shows the diversification premium |

---

## Step-by-Step Pipeline (`run_lp_optimization.py`)

### Step 1 — Load procurement requirement
Query `vw_component_requirement_lp` + `fact_component_inventory_history` + `fact_inventory_policy`.
Apply the horizon-level inventory offset formula (see above). Produce total demand `D`.

### Step 2 — Load and score suppliers
Query `vw_supplier_complete_profile`. Run `SupplierScorer.score()` with `lambda_risk` from params.
Normalize: `risk_penalty_norm = risk_penalty / 100`. Apply compliance filter.

### Step 3 — Build the LP
Create one continuous decision variable `x_j ≥ 0` per eligible supplier.
Apply objective + constraints as described above.
If `country_diversified`, extend to MIP with binary variables `y_j`.

### Step 4 — Solve
Solve with **PuLP + CBC**. Chosen for transparency, debuggability, and demo explainability.

### Step 5 — Compute baseline
Run a silent second solve with `lambda_risk=0`, `diversification_mode="none"`, `max_supplier_share=1.0`.
Store result in `result["baseline"]` for use in the Final Executive Summary.

### Step 6 — Format and return
Assemble the structured result dict (see Output Structure below).

---

## Output Structure

The `run()` function returns a dict with the following keys:

| Key | Contents |
|---|---|
| `params_recap` | All input parameters as confirmed for this run |
| `requirement` | Total `D`, adjusted `D`, facilities included, facility demand shares |
| `supplier_pool` | Total suppliers, excluded by compliance, selected by LP |
| `allocation` | Per-supplier allocation detail (see below) |
| `cost_summary` | Total cost, risk-adjusted cost, per-supplier cost breakdown |
| `excluded_suppliers` | Suppliers not used and why (compliance, exclusion, not selected) |
| `constraint_diagnostics` | LP status, binding constraints, infeasibility reason if applicable |
| `formula_description` | Plain-language explanation of objective + active constraints |
| `executive_summary` | Short procurement-facing narrative for the current run |
| `baseline` | Baseline comparison record (see Baseline Comparison section) |
| `avoid_tier_warning` | Warning if Avoid-tier suppliers were included due to pool constraints |
| `compliance_unlocked_note` | Note if compliance threshold was relaxed to restore feasibility |
| `compliance_exclusion_note` | Summary of suppliers excluded by compliance filter |
| `diversification_fallback_note` | Note if `country_diversified` fell back to a relaxed mode |
| `urgency_feasibility` | Feasibility status when urgency mode is active |

### Allocation detail (per selected supplier)

| Field | Description |
|---|---|
| Supplier ID | Internal supplier identifier |
| Country | Sourcing country |
| Quantity allocated | Units to procure from this supplier |
| Share of total | Fraction of total volume (0–1) |
| Landed unit cost | USD/unit |
| Risk penalty | Normalized 0–1 |
| Total cost | `quantity × landed_cost` |
| Risk-adjusted cost | `quantity × effective_cost_with_risk_weight` |
| Supplier tier | Preferred / Acceptable / Avoid |
| MOQ | Minimum order quantity |
| Bulk-unit threshold | Volume above which bulk pricing activates |
| MOQ met | Whether allocated quantity meets MOQ |
| Bulk discount active | Whether bulk threshold is reached |

---

## Parameters Reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `product` | str | required | Component to optimize (e.g. `"transistors"`) |
| `facility_id` | str or null | null | Restrict to one facility; null = aggregate all |
| `lambda_risk` | float | 0.50 | Risk weight in objective (0 = cost only, 1.5 = risk priority) |
| `max_supplier_share` | float | 1.0 | Max share per supplier (used by `supplier_share_only` mode) |
| `budget_cap` | float or null | null | Hard spend ceiling (USD) |
| `compliance_threshold` | float | 0.50 | Minimum compliance score; below = excluded |
| `service_level_target` | float | 1.0 | Procurement buffer multiplier (1.10 = 10% buffer) |
| `urgency` | bool | false | Adds lead-time cost premium to fast-delivery selection |
| `exclude_supplier_ids` | list[str] | [] | Manually exclude suppliers (disruption / what-if scenarios) |
| `forecast_run_id` | int | 0 | Pin to specific forecast run; 0 = latest |
| `diversification_mode` | str | `"none"` | `"none"` / `"supplier_share_only"` / `"country_diversified"` |

---

## Design Decisions

### Product-level first
The LP solves at the product level and optionally narrows to a facility. This keeps the formulation clean, explainable, and fast for demo use.

### MOQ is explainability-only (v1)
MOQ and bulk thresholds are surfaced in the output and checked post-solve, but are not hard LP constraints. The result tells the user whether MOQ would be met without introducing mixed-integer complexity for every run.

### Service level is a buffer, not a re-solve
The inventory layer already handles safety stock. `service_level_target` is a simple additive multiplier on the procurement target — easy to explain and safe to demo without touching inventory logic.

### Baseline is silent
The baseline plan is computed on every run but never displayed in individual run output. Showing it every time would create confusion between the optimized plan and the hypothetical unconstrained plan. It surfaces once — in the final session summary — where the comparison has clear business purpose.

---

## How This Fits into the Full System

```text
Historical Demand
    ↓
Demand Forecast
    ↓
BOM Translation
    ↓
Inventory / Safety Stock Check
    ↓
Net Procurement Requirement
    ↓
LP Supplier Allocation         ← this module
    ↓
Final Executive Summary        ← session-level aggregation across all approved runs
```

---

## Why This Matters

Every upstream layer — forecasting, BOM translation, inventory planning — produces **analysis**. It tells the team what demand is coming, what components are needed, and whether inventory is sufficient.

This layer is what converts that analysis into a **decision**: who to buy from, how much, at what cost, and under what risk posture.

Without it, the system can answer every preparatory question but cannot close the loop. With it, a procurement manager can move from "we need 47,000 transistors" to a specific, defensible supplier allocation — with the cost of risk management quantified in dollars, the diversification posture documented, and the baseline comparison ready for stakeholder review.

That is the difference between a supply-chain analytics tool and a procurement decision engine.
