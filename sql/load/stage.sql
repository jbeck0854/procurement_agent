-- =========================
-- 00 stage.sql
-- =========================

-- Purpose:
-- create empty landing tables that match incoming files for quick and reliable bulk-loading


DROP TABLE IF EXISTS stg_commodity_prices;
CREATE TABLE stg_commodity_prices (
  date             DATE,
  year             INT,
  month            INT,
  commodity_family TEXT,
  commodity_variant TEXT, -- can hold null values
  unit             TEXT,
  nominal_price    NUMERIC,
  source           TEXT
);

-- Producer Price Indexes (BLS + FRED)
DROP TABLE IF EXISTS stg_ppi;
CREATE TABLE stg_ppi (
  date      DATE,
  year      INT,
  month     INT,
  ppi_value NUMERIC(10,4),
  series_id TEXT,
  industry  TEXT,
  product   TEXT,
  source TEXT, -- 'BLS' or 'FRED'
  country_code CHAR(3)

);

--  PPI Series Metadata (base/reference period per series_id)
DROP TABLE IF EXISTS stg_ppi_series_meta;
CREATE TABLE stg_ppi_series_meta (
  series_id TEXT PRIMARY KEY,
  source TEXT, -- 'BLS' or 'FRED
  country_code CHAR(3),
  base_year INT NOT NULL 
);

-- Tarrifs
DROP TABLE IF EXISTS stg_tariff;
CREATE TABLE stg_tariff (
  hts8              TEXT,
  brief_description TEXT,
  mfn_text_rate     NUMERIC(6,3),
  how_measured TEXT -- NO==Number of units; KG==Kilograms (1 null value)
);

-- Word Governance Indicators 2023
DROP TABLE IF EXISTS stg_wgi;
CREATE TABLE stg_wgi (
  country_code CHAR(3),
  year INT,
  control_of_corruption NUMERIC(3,2),
  government_effectiveness NUMERIC(3,2),
  political_stability NUMERIC(3,2),  -- from "political_stability_and_absence_of_violence/terrorism"
  regulatory_quality NUMERIC(3,2),
  rule_of_law NUMERIC(3,2),
  voice_and_accountability NUMERIC(3,2)
);

-- International Scorecard for Select Countries 2023 (Logistics Performance Indicators - LPI)
DROP TABLE IF EXISTS stg_lpi;
CREATE TABLE stg_lpi (
  country_code CHAR(3),
  year INT,
  customs NUMERIC(3,2),
  infrastructure NUMERIC(3,2),
  international_shipments NUMERIC(3,2),
  logistics_competence NUMERIC(3,2),
  tracking NUMERIC(3,2),
  timeliness NUMERIC(3,2)
);

-- UN Trade Development (US Port Calls)
DROP TABLE IF EXISTS stg_port;
CREATE TABLE stg_port (
  country_code CHAR(3),
  year INT,
  median_days_in_port NUMERIC(4,2)
);

-- Synthetic Suppliers (one row per supplier)
DROP TABLE IF EXISTS stg_synthetic_suppliers;
CREATE TABLE stg_synthetic_suppliers (
  country_code CHAR(3),
  supplier_id TEXT,
  lead_time_mean NUMERIC,
  lead_time_variance NUMERIC,
  disruption_probability NUMERIC,
  compliance_eligibility NUMERIC,
  logistics_reliability NUMERIC
);

-- Synthetic Products
DROP TABLE IF EXISTS stg_products;
CREATE TABLE stg_products (
  date DATE,
  ppi_value NUMERIC,
  country_code CHAR(3),
  ppi_source TEXT,     -- 'BLS' or 'FRED'
  real_price NUMERIC,  -- real_price = (synthetic) baseline_cost of product at base year x (PPI value of product in series at time t)/ PPI value in the baseline year for that country's PPI series). Provides an inflation-adjusted cost trajectory for each country and product.
  product TEXT, -- e.g., integrated_circuit_components, power_devices, transistors, microprocessor
  ppi_region TEXT, -- regional PPI series assined to a supplier's country when country did and didn't have its own dedicated PPI data. e.g., many Asian exporters mapped to OAC
  year INT,
  month INT
);

-- Supplier-Product merged table
DROP TABLE IF EXISTS stg_supplier_products;
CREATE TABLE stg_supplier_products (
  country_code CHAR(3),
  supplier_id TEXT,

  lead_time_mean NUMERIC,
  lead_time_variance NUMERIC,
  disruption_probability NUMERIC,
  logistics_reliability NUMERIC,

  product TEXT, -- the product manufactured by the supplier (e.g., integrated_circuit_components)

  probability_of_defect NUMERIC, -- a synthetic measure that a supplier's product will be defective
  bulk_discount NUMERIC, -- a synthetic measure of the bulk discount offered by a supplier for large orders
  bulk_units INT, -- the number of units that must be ordered to receive the bulk discount
  baseline_price NUMERIC, -- the baseline price of the product from that supplier (e.g., the real_price from stg_products at the baseline year for that supplier's country) * some random noise injection
  price_volatility NUMERIC, -- a weighted synthetic measure of the price volatility of that supplier's product. See colab notebook for details on how this is calculated

  hts8_tariff TEXT -- HTS8 code that applies to the product for the supplier (or 'None')

);