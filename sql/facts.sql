-- facts.sql
-- Purpose: Define all fact tables for the Procurement Analytics
--          Star Schema Data Warehouse.
--
-- Description:
--   Fact tables store measurable, time-indexed economic and
--   trade metrics that support procurement cost, risk, and
--   supply chain analytics.
-- NOTE: Loading data into tables handled in separate script
-- ================================


-- producer price indexes (BLS + FRED): Monthly fact grain = month x PPI Series DONE
DROP TABLE IF EXISTS fact_ppi_monthly;
CREATE TABLE fact_ppi_monthly (
    date_key INT NOT NULL REFERENCES dim_date(date_key),
    ppi_series_key INT NOT NULL REFERENCES dim_ppi_series(ppi_series_key),
    ppi_value NUMERIC(10,4) NOT NULL, -- index level
    PRIMARY KEY (date_key, ppi_series_key)

);

CREATE INDEX IF NOT EXISTS idx_fact_ppi_date ON fact_ppi_monthly(date_key);
CREATE INDEX  IF NOT EXISTS idx_fact_ppi_series ON fact_ppi_monthly(ppi_series_key);

-- Commodity prices (World Bank): monthly grain DONE
DROP TABLE IF EXISTS fact_commodity_price_monthly;
CREATE TABLE fact_commodity_price_monthly (
    date_key INT NOT NULL REFERENCES dim_date(date_key),
    commodity_key INT NOT NULL REFERENCES dim_commodity(commodity_key),
    nominal_price NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (date_key, commodity_key)
);

CREATE INDEX IF NOT EXISTS idx_fact_commodity_date ON fact_commodity_price_monthly(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_commodity_key ON fact_commodity_price_monthly(commodity_key);

-- Unified country indicators fact: grain = country x year
-- This merges WPI + LPI + PortCalls into on 'country risk /logistics' table
-- Columns are nullable just in case some source doesn't cover all measurements
DROP TABLE IF EXISTS fact_country_indicators_yearly;
CREATE TABLE fact_country_indicators_yearly (
    country_code CHAR(3) NOT NULL REFERENCES dim_country(country_code),
    year INT NOT NULL, -- based on query

    -- WGI (all NUMERIC because WGI values can be negative/positive)
    control_of_corruption NUMERIC(3,2) NULL,
    government_effectiveness NUMERIC(3,2) NULL,
    political_stability NUMERIC(3,2) NULL,
    regulatory_quality NUMERIC(3,2) NULL,
    rule_of_law NUMERIC(3,2) NULL,
    voice_and_accountability NUMERIC(3,2) NULL,

    -- LPI 
    lpi_customs NUMERIC(3,2) NULL,
    lpi_infrastructure NUMERIC(3,2) NULL,
    lpi_international_shipments NUMERIC(3,2) NULL,
    lpi_logistics_competence NUMERIC(3,2) NULL,
    lpi_tracking NUMERIC(3,2) NULL,
    lpi_timeliness NUMERIC(3,2) NULL,

    -- Port calls
    median_days_in_port NUMERIC(4,2) NULL,

    PRIMARY KEY (country_code, year)
);

CREATE INDEX IF NOT EXISTS idx_country_indicators_year ON fact_country_indicators_yearly(year);

-- Tariff schedule fact: grain = hts8 x year
DROP TABLE IF EXISTS fact_tariff_schedule_yearly;
CREATE TABLE fact_tariff_schedule_yearly (
    hts8 CHAR(8) NOT NULL REFERENCES dim_tariff_code(hts8),
    year INT NOT NULL, -- set to 2025
    mfn_text_rate_pct NUMERIC(6,3) NOT NULL, -- e.g., 0.00, 2.5
    PRIMARY KEY (hts8, year)
);

CREATE INDEX IF NOT EXISTS idx_tariff_year ON fact_tariff_schedule_yearly(year);

-- fact_product_monthly; measures: ppi_value, real_price
DROP TABLE IF EXISTS fact_product_monthly CASCADE;
CREATE TABLE fact_product_monthly (
    date_key INT NOT NULL REFERENCES dim_date(date_key),
    product_country_key INT NOT NULL REFERENCES dim_product_country(product_country_key),

    ppi_value NUMERIC(12,4) NULL,
    real_price NUMERIC(12,4) NULL,

    PRIMARY KEY (date_key, product_country_key)
);

-- fact_supplier_product_profile; 1 row per supplier; measures: defect probability, bulk pricing parameters, baseline price and volatility
DROP TABLE IF EXISTS fact_supplier_product_profile CASCADE;
CREATE TABLE fact_supplier_product_profile (
    supplier_key INT NOT NULL REFERENCES dim_supplier(supplier_key),

    probability_of_defect NUMERIC(5,4) NOT NULL,
    bulk_discount NUMERIC(5,4) NOT NULL,
    bulk_units INT NOT NULL,
    baseline_price NUMERIC(10,5) NOT NULL,
    price_volatility NUMERIC(5,4) NOT NULL,

    hts8 CHAR(8) NULL REFERENCES dim_tariff_code(hts8), -- for tariff lookup

    PRIMARY KEY (supplier_key)
);


-- Finished-good semiconductor demand: weekly grain = week_date × facility × semiconductor_id
-- NOTE: dim_date is at month grain (YYYYMM key) and cannot be used here.
--       week_date DATE is the temporal anchor stored directly in the fact table.
DROP TABLE IF EXISTS fact_semiconductor_demand CASCADE;
CREATE TABLE fact_semiconductor_demand (
    week_date            DATE NOT NULL,
    facility_id          TEXT NOT NULL REFERENCES dim_facility(facility_id),
    semiconductor_id     TEXT NOT NULL REFERENCES dim_semiconductor(semiconductor_id),

    -- time helpers (denormalized from source; avoids date math in queries)
    week_number          INT  NOT NULL,  -- sequential week 1–145
    year                 INT  NOT NULL,
    month                INT  NOT NULL,
    year_month           TEXT NOT NULL,

    -- measures
    customer_orders           INT           NOT NULL,
    realized_selling_price    NUMERIC(14,6) NOT NULL,
    list_price                NUMERIC(14,6) NOT NULL,
    emailer_for_promotion     SMALLINT      NOT NULL,  -- 0/1 flag
    homepage_featured         SMALLINT      NOT NULL,  -- 0/1 flag

    -- analytical attributes (key finished-goods demand features)
    sku_performance_tier      TEXT          NOT NULL,  -- low / mid / high
    finished_family           TEXT          NOT NULL,  -- power_management_modules, mixed_signal_interface_modules, compute_control_modules

    PRIMARY KEY (week_date, facility_id, semiconductor_id)
);

CREATE INDEX IF NOT EXISTS idx_fact_semicon_demand_date
    ON fact_semiconductor_demand(week_date);
CREATE INDEX IF NOT EXISTS idx_fact_semicon_demand_facility
    ON fact_semiconductor_demand(facility_id);
CREATE INDEX IF NOT EXISTS idx_fact_semicon_demand_sku
    ON fact_semiconductor_demand(semiconductor_id);

-- Production demand forecast fact table
-- Grain: one row per (forecast_run_id, facility_id, semiconductor_id, target_week_date)
-- Consistency rule (enforced at application layer):
--   horizon_weeks = (target_week_date - observed_through_week_date) / 7
--   where observed_through_week_date is in dim_forecast_run for this run.
DROP TABLE IF EXISTS fact_semiconductor_demand_forecast CASCADE;
CREATE TABLE fact_semiconductor_demand_forecast (
    forecast_id             BIGSERIAL       NOT NULL,
    forecast_run_id         INT             NOT NULL
                            REFERENCES dim_forecast_run (forecast_run_id),
    facility_id             TEXT            NOT NULL
                            REFERENCES dim_facility (facility_id),
    semiconductor_id        TEXT            NOT NULL
                            REFERENCES dim_semiconductor (semiconductor_id),
    target_week_date        DATE            NOT NULL,
    horizon_weeks           SMALLINT        NOT NULL
                            CHECK (horizon_weeks BETWEEN 1 AND 30),
    predicted_demand        NUMERIC(14, 2)  NOT NULL
                            CHECK (predicted_demand >= 0),
    interval_lower_90       NUMERIC(14, 2)  NULL,
    interval_upper_90       NUMERIC(14, 2)  NULL,
    interval_method         TEXT            NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    PRIMARY KEY (forecast_id),

    CONSTRAINT uq_forecast_grain
        UNIQUE (forecast_run_id, facility_id, semiconductor_id, target_week_date)
);

CREATE INDEX IF NOT EXISTS idx_fact_fcast_run_id
    ON fact_semiconductor_demand_forecast (forecast_run_id);

CREATE INDEX IF NOT EXISTS idx_fact_fcast_entity_date
    ON fact_semiconductor_demand_forecast (facility_id, semiconductor_id, target_week_date);

CREATE INDEX IF NOT EXISTS idx_fact_fcast_target_run
    ON fact_semiconductor_demand_forecast (target_week_date, forecast_run_id);

CREATE INDEX IF NOT EXISTS idx_fact_fcast_horizon
    ON fact_semiconductor_demand_forecast (horizon_weeks);

