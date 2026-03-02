-- =========================
-- 02_load_dimensions.sql
-- Purpose: Populate dimensions from staging tables created in stage.sql
-- =========================

BEGIN;

TRUNCATE
  dim_supplier,
  dim_product_country,
  dim_product,
  dim_inventory_policy
RESTART IDENTITY CASCADE;

-- ------------------------------------------------------------
-- 1) dim_country (ISO3 only + any aggregates like OAC)
-- Sources: WGI, LPI, Port calls (these are the tables that actually contain country_code)
-- DONE
-- ------------------------------------------------------------

-- Temporary country lookup table 
DROP TABLE IF EXISTS tmp_country_lookup;
CREATE TEMP TABLE tmp_country_lookup (
    country_name TEXT,
    country_code CHAR(3)
);

INSERT INTO tmp_country_lookup (country_name, country_code) VALUES
('Australia','AUS'),
('Belgium','BEL'),
('Brazil','BRA'),
('Canada','CAN'),
('China','CHN'),
('Finland','FIN'),
('France','FRA'),
('Germany','DEU'),
('Hong Kong SAR, China','HKG'),
('India','IND'),
('Indonesia','IDN'),
('Japan','JPN'),
('Malaysia','MYS'),
('Mexico','MEX'),
('Netherlands','NLD'),
('Other Asian Countries', 'OAC'),
('Singapore','SGP'),
('Thailand','THA'),
('United Arab Emirates','ARE'),
('United Kingdom','GBR'),
('United States','USA');

-- load dim_country
TRUNCATE dim_country CASCADE;
INSERT INTO dim_country (country_code, country_name)
SELECT DISTINCT
    s.country_code,
    l.country_name
FROM (
    SELECT country_code FROM stg_wgi
    UNION
    SELECT country_code FROM stg_lpi
    UNION
    SELECT country_code FROM stg_port
    UNION
    SELECT country_code FROM stg_ppi_series_meta
) s
LEFT JOIN tmp_country_lookup l
  ON s.country_code = l.country_code
WHERE s.country_code IS NOT NULL;


-- ------------------------------------------------------------
-- dim_date (month grain)
-- dim_date has: date_key (YYYYMM), date (DATE), year, month, year_month (as text)
-- store date as first-of-month to keep it consistent.
-- Sources: PPI + commodity prices
-- DONE
-- ------------------------------------------------------------
TRUNCATE dim_date;
INSERT INTO dim_date (date_key, date, year, month, year_month)
SELECT DISTINCT
    (year * 100 + month)                          AS date_key,
    MAKE_DATE(year, month, 1)                     AS date,
    year,
    month,
    TO_CHAR(MAKE_DATE(year, month, 1), 'YYYY-MM') AS year_month
FROM (
    SELECT year, month 
    FROM stg_ppi
    WHERE year IS NOT NULL AND month IS NOT NULL

    UNION

    SELECT year, month 
    FROM stg_commodity_prices
    WHERE year IS NOT NULL AND month IS NOT NULL
) AS distinct_year_months;

-- -----------------------------
-- dim_ppi_series_meta
-- DONE
-- -------------
TRUNCATE dim_ppi_series_meta RESTART IDENTITY;
INSERT INTO dim_ppi_series_meta (series_id, source, country_code, base_year)
SELECT DISTINCT series_id, source, country_code, base_year
FROM stg_ppi_series_meta
WHERE series_id IS NOT NULL;


-- ------------------------------------------------------------
-- dim_ppi_series (FRED/BLS - merged series and descriptors)
-- SOURCE: stg_ppi_series_meta (meta) and stg_ppi (industry/product/labels)
-- Note: If industry/product are constant per series_id (as expected), MAX() works. 
-- ------------------------------------------------------------
-- DONE
TRUNCATE dim_ppi_series RESTART IDENTITY;
INSERT INTO dim_ppi_series (series_id, source, country_code, base_year, industry, ppi_product)
SELECT
  m.series_id,
  m.source,
  m.country_code,
  m.base_year,
  p.industry,
  p.product
FROM dim_ppi_series_meta AS m
LEFT JOIN (
  SELECT series_id, MAX(industry) AS industry, MAX(product) AS product
  FROM stg_ppi
  WHERE series_id IS NOT NULL
  GROUP BY series_id
) p 
  ON p.series_id = m.series_id;

-- ------------------------------------------------------------
-- dim_commodity (World Bank Pink Sheet)
-- Staging has: commodity_family, commodity_variant, unit, source
-- DONE
-- ------------------------------------------------------------
TRUNCATE dim_commodity RESTART IDENTITY;
INSERT INTO dim_commodity (commodity_family, commodity_variant, unit, source)
SELECT DISTINCT commodity_family, commodity_variant, unit, source
FROM stg_commodity_prices
WHERE commodity_family IS NOT NULL;


-- ------------------------------------------------------------
-- dim_tariff_code (HTS8)
-- Assummes hts8 is cleaned to 8 digits
-- ------------------------------------------------------------
TRUNCATE dim_tariff_code;
INSERT INTO dim_tariff_code (hts8, brief_description, how_measured)
SELECT DISTINCT hts8, brief_description, how_measured
FROM stg_tariff
WHERE hts8 IS NOT NULL;

-- ------------------------------------------------------------
-- dim_product load
-- ------------------------------------------------------------
INSERT INTO dim_product (product)
SELECT DISTINCT product
FROM stg_products
WHERE product IS NOT NULL;

-- ---------------------------------------------
-- dim_product_country load
-- ----------------------------------------------
INSERT INTO dim_product_country (product_key, country_code, ppi_source, ppi_region)
SELECT DISTINCT
    dp.product_key,
    sp.country_code,
    sp.ppi_source,
    sp.ppi_region
FROM stg_products sp
JOIN dim_product dp ON dp.product = sp.product;


-- ------------------------------------------------------------
-- dim_supplier load
-- ------------------------------------------------------------
INSERT INTO dim_supplier (supplier_id, country_code, product_key, lead_time_mean, lead_time_variance, disruption_probability, compliance_eligibility, logistics_reliability)
SELECT s.supplier_id, s.country_code, dp.product_key, s.lead_time_mean, s.lead_time_variance, s.disruption_probability, s.compliance_eligibility, s.logistics_reliability
FROM stg_suppliers s 
JOIN stg_supplier_products sp ON sp.supplier_id = s.supplier_id
JOIN dim_product dp ON dp.product = CASE trim(sp.product)
    WHEN 'IC Components' THEN 'integrated_circuit_components'
    WHEN 'Microprocessors' THEN 'microprocessors'
    WHEN 'Transistors' THEN 'transistors'
    WHEN 'Power Devices' THEN 'power_devices'
    END;


-- ------------------------------------------------------------
-- dim_inventory_policy load 
-- ------------------------------------------------------------
INSERT INTO dim_inventory_policy (
  product_key,
  unit_value,
  unit_holding_cost_per_month,
  lead_time_months,
  stockout_probability,
  fixed_ordering_cost
)
SELECT DISTINCT
  dp.product_key,
  sid.unit_value,
  sid.unit_holding_cost_per_month,
  sid.lead_time_months,
  sid.stockout_probability,
  sid.fixed_ordering_cost
FROM stg_inventory_demand sid
JOIN dim_product dp ON dp.product = sid.product;


COMMIT;



-- DONE