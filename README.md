# Procurement Agent – Business Analytics Capstone

An AI-powered Procurement Decision Intelligence Agent for semiconductor and electronics supply chains. The system translates natural language queries into end-to-end procurement recommendations — from demand forecasting through LP-optimized supplier allocation — with structured outputs designed for procurement and supply chain decision-makers.

> **Example query:** "From our available suppliers, provide a procurement plan to ensure we meet demand under moderate risk aversion."

---

## Key Capabilities

- **Supplier scoring** — Risk-adjusted landed cost ranking across a global supplier universe, with compliance filtering, MOQ checks, and tiered supplier classification
- **Demand forecasting** — Facility × product × week forward demand, grounded in historical commodity and production data
- **BOM-based component demand** — Finished-good forecasts exploded into procurement-level component demand via bill-of-materials translation
- **Inventory planning** — Base-stock policy with stochastic lead times; rolling depletion model with weekly trigger signals and safety stock utilization tracking
- **Procurement requirement calculation** — Net procurement need after inventory offset, computed at horizon level for LP input and at weekly level for timing explainability
- **LP optimization** — Cost-vs-risk tradeoff allocation across eligible suppliers; supports supplier share caps, country diversification (MIP), urgency mode, and what-if exclusion scenarios
- **Executive summaries and recommendations** — Session-level procurement plan with baseline cost comparison, risk premium quantification, and targeted sourcing guidance

---

## System Architecture

The pipeline runs in six stages:

```
1. Forecast demand
        Facility × product × week forward demand from historical series

2. BOM translation
        Finished-good demand × component qty-per-unit → gross component demand

3. Inventory policy
        Safety stock + base-stock target per facility × component
        Rolling depletion: available inventory consumed week by week until procurement is triggered

4. Net procurement requirement
        Horizon-level: max(0, gross demand + SS − on_hand − SR + BO)
        Weekly trigger view: which weeks and facilities cross the SS floor

5. LP optimization
        Allocate requirement across eligible suppliers
        Objective: minimize risk-adjusted cost (λ_risk-weighted)
        Constraints: demand fulfillment, budget cap, compliance, diversification

6. Recommendations + executive summary
        Per-run allocation detail, baseline comparison, session-level plan summary
```

---

## Repository Structure

```
procurement_agent/
│
├── forecasting/         # Demand forecasting models and outputs
├── inventory/           # Inventory policy, procurement requirement, and trigger logic
├── optimization/        # LP-based supplier allocation (run_lp_optimization.py)
├── analytics/           # Supplier scoring and risk/compliance analytics
├── demo/                # Streamlit app, agent tools, and UI rendering layers
│   ├── streamlit_app.py # Main app entry point
│   ├── tools/           # Query helpers and pipeline connectors
│   └── ui/              # View rendering for inventory, LP, and executive summary
├── sql/                 # PostgreSQL DDL, views, and load scripts
│   ├── load/            # Load scripts (must run in order)
│   ├── views.sql        # Analytical views (procurement requirement, LP demand floor)
│   ├── dimensions.sql   # Dimension table DDL
│   ├── facts.sql        # Fact table DDL
│   └── README.md        # Database setup instructions
├── cleaned_data/        # Cleaned CSV source files used for staging
└── README.md            # Project overview (this file)
```

---

## Demo / Usage

The agent is delivered as a Streamlit application. To run it:

```bash
cd demo
streamlit run streamlit_app.py
```

The interface is query-driven. Users submit natural language questions or requests; the agent routes them through the appropriate pipeline stage and returns structured tables, charts, and procurement recommendations.

Primary interaction modes:

- **Inventory queries** — horizon-level procurement summary, weekly trigger view, safety stock policy explanation
- **LP optimization** — supplier allocation runs with configurable risk weight, diversification mode, and budget constraints
- **Complete Procurement Plan** — aggregates all approved LP runs into a session-level executive summary with baseline cost comparison

The system is designed for speed: forecasts and inventory layers are precomputed, and the demo pipeline runs LP optimization live against the precomputed inputs.

---

## Database Setup

All instructions for loading and running the PostgreSQL database are in `sql/README.md`.

Follow that document step-by-step to:

1. Create the database
2. Run staging scripts and DDL for dimension and fact tables
3. Load dimensions
4. Load facts
5. Run view definitions (`views.sql`)

---

## Important Notes

- SQL scripts must be run **in the correct order** — out-of-order execution will cause foreign key errors. See `sql/README.md` for exact commands.
- The demo assumes precomputed forecasts (`fact_semiconductor_demand`) and a populated inventory layer (`fact_component_inventory_history`, `fact_inventory_policy`). Run `forecasting/` and `inventory/run_inventory.py` before launching the demo against a new dataset.
- The pipeline is fully reproducible: re-running any upstream layer regenerates all downstream inputs deterministically.
