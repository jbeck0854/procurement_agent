# optimization/README.md

## Overview

This folder contains the LP-based procurement allocation layer.

Its purpose is to take the **procurement requirement** generated upstream and decide:

- **which suppliers to use**
- **how much to buy from each supplier**
- while respecting business constraints such as:
  - budget
  - compliance
  - risk tolerance
  - diversification limits
  - optional facility scope
  - optional service-level buffer

In simple terms, this layer answers:

> “Now that we know what we need to buy, who should we buy it from, and in what quantity?”

---

## File Contents

### `run_lp_optimization.py`
Main optimization module.

This file:
1. loads the procurement requirement for a selected product
2. loads the eligible suppliers for that product
3. scores / evaluates those suppliers using the existing scoring layer
4. builds and solves a linear program (LP)
5. returns a structured, business-facing result for the demo / agent

### `__init__.py`
Package file so the optimization layer can be imported cleanly.

---

## What This Layer Depends On

### `run_lp_optimization.py`
Main optimization module.

This file:
1. loads the procurement requirement for a selected product
2. loads the eligible suppliers for that product
3. scores / evaluates those suppliers using the existing scoring layer
4. builds and solves a linear program (LP)
5. returns a structured, business-facing result for the demo / agent

### `__init__.py`
Package file so the optimization layer can be imported cleanly.

---

This module does **not** create demand forecasts, BOM mappings, or inventory policy logic itself.

It relies on upstream layers that are already completed:

### 1. Forecasting layer
Provides forward finished-goods demand.

### 2. BOM layer
Translates finished-goods demand into procurement-side component demand.

### 3. Inventory / procurement requirement layer
Provides:
- how much of each product/component is actually needed
- after considering inventory, receipts, and safety stock

### 4. Supplier scoring layer
Provides supplier-level cost / risk information used by the LP.

---

## Main Input

The LP primarily consumes:

### Procurement requirement
From:

- `vw_procurement_requirement`

This view tells the LP:
- which product / component needs procurement
- how much is needed
- which facilities are involved
- how much net requirement remains after inventory coverage

### Supplier universe
From:
- supplier profile / scoring views
- existing scoring logic in `analytics/scoring.py`

This tells the LP:
- landed cost
- risk
- compliance status
- supplier tier
- MOQ / bulk-unit threshold
- lead time
- other supplier characteristics

---

## Core Idea

The LP solves a sourcing allocation problem.

It determines the quantity to purchase from each eligible supplier for a selected product.

### Objective
Minimize total procurement cost adjusted for risk.

### Subject to
- meeting required demand
- staying within budget (if provided)
- excluding non-compliant suppliers
- limiting supplier concentration (if provided)
- optionally adding extra procurement buffer via service level target

---

## Typical Flow of `run_lp_optimization.py`

## Step 1 — Load procurement requirement

The script reads procurement need for the selected product from:

- `vw_procurement_requirement`

By default:
- it aggregates across all facilities with `net_requirement > 0`

Optional:
- if `facility_id` is provided, it filters to that facility only

This produces total procurement demand for the LP run.

---

## Step 2 — Load and score suppliers

The script loads supplier candidates for the selected product.

It then uses the existing scoring layer to compute or retrieve:
- landed unit cost
- risk penalty
- compliance eligibility
- supplier decision tier
- MOQ / bulk units
- lead time information

Important:
- this layer **uses** the scoring system
- it does **not** redesign or replace it

---

## Step 3 — Build the LP

The script creates one decision variable per eligible supplier:

- quantity to procure from supplier `j`

These quantities are continuous and non-negative.

### The LP then applies:

#### Demand fulfillment constraint
Total allocated quantity must cover required procurement demand.

#### Budget constraint (optional)
Total spend must remain below the user’s budget cap.

#### Diversification / share cap constraint (optional)
No supplier can exceed a specified share of total procurement.

#### Service level target (optional user parameter)
Used as an additive procurement buffer multiplier on top of the already-computed procurement requirement.

Important:
- this does **not** rebuild safety stock
- it simply scales the procurement target above the requirement if requested

---

## Step 4 — Solve the LP

The model is solved using a linear programming solver.

Current intended solver:
- **PuLP + CBC**

This was chosen because it is:
- easy to read
- easy to debug
- suitable for demo use
- easier to explain than lower-level solver interfaces

---

## Step 5 — Format the results

After solving, the script returns a structured result that is easy for the demo agent or a notebook to consume.

This includes:

### Parameter recap
- selected product
- selected facility scope
- budget cap
- lambda risk
- max supplier share
- service level target
- urgency toggle
- order quantity assumption

### Requirement summary
- total procurement requirement
- adjusted requirement after service-level multiplier
- facilities included
- facility demand shares

### Supplier pool summary
- number of total suppliers for product
- number excluded by compliance
- number selected by LP

### Allocation output
For each selected supplier:
- supplier ID
- country
- quantity allocated
- share of total
- landed unit cost
- risk measure
- total cost contribution
- risk-adjusted cost contribution
- supplier tier
- MOQ / bulk-unit threshold
- whether MOQ was met
- whether bulk discount would be active

### Excluded supplier output
For suppliers not used:
- supplier ID
- country
- compliance status
- exclusion reason

### Constraint diagnostics
- LP solve status
- whether demand constraint was binding
- whether budget constraint was binding
- whether diversification constraints were binding
- infeasibility reason if applicable

### Formula description
A business-readable explanation of how the optimization was solved.

### Executive summary
A short procurement-facing explanation of the result.

---

## Important Design Choices

## 1. Product-level optimization first
The LP currently solves at the selected **product** level.

That means:
- it determines the best total allocation across suppliers for one product
- then optionally provides facility-level breakdown in post-processing

This keeps the first version:
- cleaner
- faster
- easier to explain

---

## 2. Facility is an optional user parameter
The user may:
- run the LP across all facilities with positive requirement
- or isolate a single facility

This makes the model more flexible for the demo without overcomplicating the base formulation.

---

## 3. MOQ is explainability-only in v1
Minimum order quantity / bulk-unit threshold is currently:
- surfaced in the output
- checked after solving

But it is **not yet** a hard optimization constraint.

That means the result tells us:
- whether MOQ was met
- whether bulk pricing would activate

without forcing a more complex mixed-integer optimization in version 1.

This keeps the LP simpler and safer for demo use.

---

## 4. Service level is treated as a user-facing buffer
The inventory layer already includes safety stock and policy logic.

So the LP does **not** re-solve inventory policy.

Instead:
- `service_level_target` acts as an additional multiplier on procurement quantity
- example:
  - `1.00` = satisfy the exact procurement requirement
  - `1.10` = procure 10% above requirement

This makes service level easy to explain and demo.

---

## Example User Parameters

The LP is designed to support parameters such as:

- `product`
- `facility_id` (optional)
- `planning_horizon`
- `budget_cap`
- `compliance_threshold`
- `lambda_risk`
- `max_supplier_share`
- `service_level_target`
- `urgency`
- `exclude_supplier_ids` (for disruption / what-if scenarios)
- `order_quantity`

---

## Example Business Question This Module Answers

> “For integrated circuit components over the next planning window, under a moderate risk preference and a $50,000 budget, what supplier mix should we use to satisfy procurement need while avoiding overconcentration?”

---

## What This Module Does NOT Do

This module does **not**:
- forecast demand
- build the BOM
- compute safety stock formulas
- modify supplier scoring logic
- modify procurement requirement logic
- manage agent orchestration directly

Its job is only:

> **take procurement need + supplier options → return an optimal supplier allocation**

---

## How This Fits into the Full System

The full pipeline now works like this:

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
LP Supplier Allocation
```

This optimization layer is the final step that turns analysis into a recommendation.

---

## Why This Matters

Without this layer, the system can tell us:

- what demand is coming
- what components are needed
- whether inventory is sufficient

But it cannot answer:

- who should we buy from?
- how much should we buy from each supplier?
- how do we trade off cost, risk, budget, and diversification?

This module is what makes the system a true procurement decision tool rather than just an analytics tool.