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
