# Optimization Validation Notebook Guide

## Purpose

This notebook exists to validate that the LP optimization layer works correctly from end to end and that its outputs are readable, explainable, and demo-ready.

Notebook:
- `analytics/analysis/optimization_validation.ipynb`

It is the optimization equivalent of:
- `analytics/analysis/plot_validation.ipynb`
- `analytics/analysis/score_validation.ipynb`

---

## What This Notebook Validates

The notebook is designed to confirm that the optimization layer can:

- connect to the current database
- identify products with positive procurement requirements
- run the LP using the current `optimization/run_lp_optimization.py` interface
- display the returned result cleanly
- validate different scenarios and user parameters
- confirm that returned business-facing outputs remain aligned with the optimization module

---

## Primary Dependency

The notebook calls:

- `optimization/run_lp_optimization.py`

This file is the canonical source of truth for:
- LP logic
- returned result schema
- formula description
- executive summary
- allocation and cost outputs

The notebook should validate those outputs, not redefine them.

---

## What the Notebook Covers

### 1. Imports and DB connection
Confirms:
- repo imports work
- environment variables load
- PostgreSQL connection succeeds

### 2. Product identification
Checks which products currently have positive net procurement requirements using:
- `vw_procurement_requirement`
- `dim_product` (for human-readable product names)

### 3. LP scenario runs
Runs representative scenarios such as:
- baseline run
- diversification-constrained run
- infeasible budget run
- service-level buffer run
- facility-filtered run
- urgency validation run

### 4. Result display
Formats and displays the result dict returned by the LP module, including:
- requirement summary
- facility breakdown
- supplier pool
- selected allocations
- MOQ notes
- cost summary
- excluded suppliers
- constraint diagnostics
- formula description
- executive summary

### 5. Cross-scenario comparison
Allows side-by-side comparison of how parameters affect:
- supplier choice
- cost
- diversification
- feasibility
- urgency behavior

---

## How to Use It

## Step 1 — Open notebook
Open:
- `analytics/analysis/optimization_validation.ipynb`

## Step 2 — Run top to bottom
Run the notebook from the first cell through the last cell.

Important:
- do not skip the DB connection cells
- do not manually patch scenario cells
- this notebook should now run top-to-bottom against the current optimization interface

## Step 3 — Check available products
Use the product identification section to see which products currently have:
- positive procurement requirement
- enough signal to test the LP meaningfully

## Step 4 — Run baseline scenario
This confirms:
- the LP solves
- the schema is correct
- the returned result can be displayed cleanly

## Step 5 — Run constraint / sensitivity scenarios
Use the provided cells to inspect:
- diversification effect
- budget infeasibility handling
- service-level buffer effect
- facility filtering
- urgency mode

---

## What to Look For

### Successful run indicators
- LP status is `Optimal` or expected `Infeasible`
- requirement totals make sense
- selected suppliers are plausible
- excluded suppliers are explained clearly
- cost summary is readable
- executive summary reads naturally

### Quality checks
- user-facing quantity outputs are integers
- cost outputs are based on landed cost
- MOQ notes are readable
- urgency behavior is explained in business language
- no stale field names or notebook-only workarounds appear

---

## Urgency Validation

The notebook now includes an urgency section.

What it demonstrates:
- urgency adds a lead-time penalty to the objective
- urgency does **not** impose a hard supplier cutoff
- urgency may or may not change allocations depending on whether other constraints are binding

Business interpretation:
- urgency makes slow suppliers less attractive
- but it cannot override constraints like diversification caps if those constraints already fix the solution structure

---

## What This Notebook Is NOT For

This notebook is **not** where we:
- redesign the LP
- edit SQL schemas
- create demo orchestration logic
- define session-level final summaries

Those belong elsewhere.

This notebook is only for:
- validation
- output inspection
- business-facing result review

---

## Best Practice

If the notebook breaks:
1. check whether `run_lp_optimization.py` changed
2. confirm the notebook still matches the current result schema
3. avoid adding notebook-only hacks unless absolutely necessary

The correct fix is usually:
- align the notebook to the optimization module
not
- create a parallel interface inside the notebook

---

## Bottom Line

This notebook is the team’s main checkpoint for confirming that the LP layer is:
- working
- explainable
- presentation-ready
- aligned with the current optimization pipeline