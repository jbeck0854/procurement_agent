-- Synthetic/composite demand, inventory, and supplier metrics (monthly)
-- future, but preparing for schema ready

-- Monthly demand, by product
-- Purpose: forecast/plan demand, detect spikes/drops, stockout risk drivers
CREATE TABLE fact_demand_monthly (
    demand_key SERIAL PRIMARY KEY,

    -- grain keys
    date_key INT NOT NULL REFERENCES dim_date (date_key),
    product_key INT NOT NULL REFERENCES dim_product(product_key),

    -- measures
    demand_units NUMERIC NOT NULL CHECK (demand_units >= 0),
    demand_value_usd NUMERIC NULL CHECK (demand_value_usd IS NULL OR demand_vaue_usd >= 0),

    -- optional model/debug fields
    forecast_units NUMERIC NULL CHECK (forecast_units IS NULL nOR forecast_units >= 0),
    forecast_methd TEXT NULL, -- e.g., 'naive', 'moving average', 'elasticity'

    created_at TIMESTAMP DEFAULT NOW(),

    -- prevent duplidate rows at the declared grain
    CONSTRAINT uq_fact_demand_monthly UNIQUE (date_key, product_key)

);

CREATE INDEX IF NOT EXISTS idx_fact_demand_monthly_date ON fact_demand_monthly(date_key);

CREATE INDEX IF NOT EXISTS idx_fact_demand_monthly_product ON fact_demand_monthly(product_key);

-- Inventory snapshot (monthly, by supplier x product)
-- Purpose: on-hand levels, on-order pipeline, service level and stockout analysis
CREATE TABLE fact_inventory_snapshot_monthly (
    inventory_snapshot_key SERIAL PRIMARY KEY,

    -- grain keys
    date_key INT NOT NULL REFERENCES dim_date(date_key),
    supplier_key INT NOT NULL REFERENCES dim_supplier(supplier_key),
    product_key INT NOT NULL REFERENCES dim_product(product_key),

    -- measures (snapshot quantities)
    on_hand_units NUMERIC NOT NULL CHECK (on_hand_units >= 0),
    on_order_units NUMERIC NULL CHECK (on_order_units IS NULL OR on_order_units >= 0),
    safety_stock_units NUMERIC NULL CHECK (safety_stock_units IS NULL OR safety_stock_units >= 0),

    -- derived / diagnostic flags
    stockout_flag BOOLEAN NOT NULL DEFAULT FALSE,
    days_of_supply NUMERIC NULL CHECK (days_of_supply IS NULL OR days_of_supply >= 0),

    created_at TIMESTAMP DEFAULT NOW(),

    -- prevent duplicate rows at the declared gain
    CONSTRAINT uq_fact_inventory_snapshot_monthly UNIQUE (date_key, supplier_key, product_key)

);

CREATE INDEX IF NOT EXISTS idx_fact_inventory_snapshot_date ON fact_inventory_snapshot_monthly_date(date_key);

CREATE INDEX IF NOT EXISTS idx_fact_inventory_snapshot_supplier ON fact_inventory_snapshot_monthly(supplier_key);

CREATE INDEX IF NOT EXISTS idx_fact_inventory_snapshot_product ON fact_inventory_snapshot_monthly(product_key);


-- Supplier metrics (monthly, by supplier × product)
-- Grain: month × supplier × product
-- Purpose: synthetic/composite metrics driven by PPI/commodities + country indicators
-- (cost index, volatility, lead time, risk, reliability)
CREATE TABLE IF NOT EXISTS fact_supplier_metrics_monthly (
    supplier_metrics_key SERIAL PRIMARY KEY,

    -- grain keys
    date_key     INT NOT NULL REFERENCES dim_date(date_key),
    supplier_key INT NOT NULL REFERENCES dim_supplier(supplier_key),
    product_key  INT NOT NULL REFERENCES dim_product(product_key),

    -- cost signals (synthetic but anchored to real series)
    cost_index           NUMERIC(18,6) NULL,  -- e.g., normalized 1.00 baseline
    unit_cost_usd        NUMERIC(18,6) NULL CHECK (unit_cost_usd IS NULL OR unit_cost_usd >= 0),
    price_volatility     NUMERIC(18,6) NULL CHECK (price_volatility IS NULL OR price_volatility >= 0),

    -- logistics signals (anchored to LPI/ports)
    expected_lead_time_days NUMERIC(18,4) NULL CHECK (expected_lead_time_days IS NULL OR expected_lead_time_days >= 0),
    lead_time_variance      NUMERIC(18,6) NULL CHECK (lead_time_variance IS NULL OR lead_time_variance >= 0),

    -- risk / reliability (anchored to WGI + disruptions)
    disruption_probability  NUMERIC(10,6) NULL CHECK (
        disruption_probability IS NULL OR (disruption_probability >= 0 AND disruption_probability <= 1)
    ),
    reliability_score       NUMERIC(10,6) NULL CHECK (
        reliability_score IS NULL OR (reliability_score >= 0 AND reliability_score <= 1)
    ),
    risk_score              NUMERIC(10,6) NULL CHECK (
        risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 1)
    ),

    -- tariff exposure (optional; may be derived via product↔tariff mapping)
    tariff_rate_effective   NUMERIC(10,6) NULL CHECK (
        tariff_rate_effective IS NULL OR tariff_rate_effective >= 0
    ),

    created_at TIMESTAMP DEFAULT NOW(),

    -- prevent duplicate rows at the declared grain
    CONSTRAINT uq_fact_supplier_metrics_monthly UNIQUE (date_key, supplier_key, product_key)
);

CREATE INDEX IF NOT EXISTS idx_fact_supplier_metrics_date
    ON fact_supplier_metrics_monthly(date_key);

CREATE INDEX IF NOT EXISTS idx_fact_supplier_metrics_supplier
    ON fact_supplier_metrics_monthly(supplier_key);

CREATE INDEX IF NOT EXISTS idx_fact_supplier_metrics_product
    ON fact_supplier_metrics_monthly(product_key);