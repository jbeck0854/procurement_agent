# Agent-Side Handoff — Optimization Integration

## Overview

The LP optimization layer is complete and validated.

The optimization module now returns a structured, business-facing result directly from:

- `optimization/run_lp_optimization.py`

This means the demo/agent side should treat the optimization module as the canonical source of:
- optimization outputs
- explainability fields
- executive summary text

No extra SQL views are required at this time.

---

## What Is Already Done

### Upstream pipeline
Already implemented:

- forecasting layer
- forecast storage
- BOM translation layer
- inventory policy layer
- procurement requirement layer
- LP optimization layer

The end-to-end workflow is now:

historical demand  
→ forecast  
→ BOM translation  
→ inventory / safety stock check  
→ procurement requirement  
→ supplier optimization

---

## Canonical Optimization Entry Point

### Python module
- `optimization/run_lp_optimization.py`

### Main callable
- `run(LPParams(...))`

### Canonical return
The returned result dict is the source of truth for:
- requirement summary
- supplier pool summary
- allocation
- excluded suppliers
- cost summary
- constraint diagnostics
- formula description
- executive summary

---

## Important Scope Rule

## LP-level executive summary
The current `executive_summary` is scoped to exactly **one LP run**:
- one product
- one planning horizon
- one set of parameters

This is correct and should remain unchanged.

It should summarize:
- what is being procured
- quantity target
- service-level target
- number of selected suppliers
- lead supplier
- total cost
- urgency flag
- compliance exclusions

## Session-level final summary
A broader “final procurement summary” across multiple LP runs should be built at the agent/session layer, not inside the LP module.

---

## Recommended Demo/Agent Modifications

## 1. New LP tool
### File
- `demo/tools/optimization.py` (new)

### Role
Wrap:
- `run(LPParams(...))`

### Should accept user-facing parameters such as:
- product
- facility_id (optional)
- budget_cap
- lambda_risk
- compliance_threshold
- max_supplier_share
- service_level_target
- urgency
- exclude_supplier_ids (optional disruption scenario)

### Should return
- the raw LP result dict from `run()`

Do not re-compute or reformat business logic inside the tool.

---

## 2. Orchestrator changes
### File
- `demo/graph/orchestrator.py`

### Role
- decide when LP optimization should be called
- register the LP agent/tool
- create one LP task per product requiring action if the workflow needs multiple procurement runs

This file should decide:
- which products need optimization
- whether to optimize one product or several

---

## 3. Builder changes
### File
- `demo/graph/builder.py`

### Role
- add `lp_agent` node
- route LP tasks through the graph
- ensure synthesizer runs only after LP tasks are complete

---

## 4. Synthesizer changes
### File
- `demo/graph/synthesizer.py`

### Role
Primary place for:
- reading LP outputs from `agent_results`
- surfacing each run’s `executive_summary`
- building a final session-level procurement summary after all LP runs are complete

This is the correct place for session-level aggregation because it already sees all agent results and already generates the final natural-language response.

---

## 5. State handling
### File
- `demo/graph/state.py`

### Recommendation
No structural change required.

Use consistent keys in `agent_results`, for example:
- `lp_transistors`
- `lp_power_devices`
- `lp_integrated_circuit_components`

This gives the synthesizer a predictable way to iterate across LP results.

---

## What Does NOT Need to Change

Likely no change needed for:
- SQL layer
- forecasting pipeline
- scoring logic
- BOM layer
- inventory layer

Also, no new SQL views are currently recommended:
- existing objects are sufficient
- LP already has what it needs from current views/tables

---

## Objects the LP Already Depends On

The optimization layer already depends on:
- `vw_procurement_requirement`
- `vw_supplier_complete_profile`
- `dim_product`
- `dim_supplier`

These are sufficient for current demo and agent needs.

---

## Recommended Session-Level Final Summary

After multiple LP runs are complete, the agent should build a final procurement summary containing:

- planning horizon
- products requiring action
- products successfully covered
- per-product LP status
- per-product total cost
- total procurement cost across the session
- total units to procure across the session
- any infeasible products
- compliance posture
- diversification note
- final session narrative

This summary should be built outside the LP module, by the agent/session layer.

---

## Recommended Next Step to Integrate Optimization Based on Forecasts and Procurement Needs

1. create `demo/tools/optimization.py`
2. register LP tool in orchestrator
3. add LP node and routing in builder
4. have synthesizer consume:
   - each LP run’s `executive_summary`
   - all LP result dicts for final session aggregation

---

## Bottom Line

The optimization layer is ready.

The main remaining work on the demo side is not mathematical — it is orchestration:
- call the LP correctly
- store results cleanly
- surface each run’s summary
- combine multiple runs into one final procurement narrative