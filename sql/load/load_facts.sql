-- =======
-- load_facts.sql
-- Populates fact tables from stage and dimension tables
-- NOTE: Dimension and stage tables must be loaded first
-- ========

BEGIN;

-- wipds facts (makes safe to re-run without issues)
TRUNCATE fact_product_monthly;
TRUNCATE fact_supplier_product_profile;

-- ----------------
-- fact_ppi_monthly
-- --------------
TRUNCATE fact_ppi_monthly;
INSERT INTO fact_ppi_monthly (date_key, ppi_series_key, ppi_value)
SELECT
    d.date_key,
    s.ppi_series_key,
    p.ppi_value
FROM stg_ppi p
JOIN dim_date d
    ON d.year = p.year
    AND d.month = p.month
JOIN dim_ppi_series s
    ON s.series_id = p.series_id
WHERE p.ppi_value IS NOT NULL;

-- ---------
-- fact_commodity_price_monthly
-- -----------
TRUNCATE fact_commodity_price_monthly;
INSERT INTO fact_commodity_price_monthly (date_key, commodity_key, nominal_price)
SELECT
  d.date_key,
  c.commodity_key,
  cp.nominal_price
FROM stg_commodity_prices cp
JOIN dim_date d
  ON d.year = cp.year
 AND d.month = cp.month
JOIN dim_commodity c
  ON c.commodity_family = cp.commodity_family
 AND COALESCE(c.commodity_variant,'') = COALESCE(cp.commodity_variant,'') -- if both null, will match on ''
 AND c.unit = cp.unit
 AND c.source = cp.source
WHERE cp.nominal_price IS NOT NULL;

-- ------------------------------------------------------------
-- fact_country_indicators_yearly
-- Sources: stg_wgi, stg_lpi, stg_port
-- Strategy:
--   - Build a base set of (country_code, year)
--   - Left join each source to populate nullable columns
-- ------------------------------------------------------------
TRUNCATE fact_country_indicators_yearly;

WITH base AS (
  SELECT country_code, year FROM stg_wgi
  UNION
  SELECT country_code, year FROM stg_lpi
  UNION
  SELECT country_code, year FROM stg_port
)
INSERT INTO fact_country_indicators_yearly (
  country_code, year,
  control_of_corruption, government_effectiveness, political_stability,
  regulatory_quality, rule_of_law, voice_and_accountability,
  lpi_customs, lpi_infrastructure, lpi_international_shipments,
  lpi_logistics_competence, lpi_tracking, lpi_timeliness,
  median_days_in_port
)
SELECT
  b.country_code,
  b.year,

  -- WGI
  w.control_of_corruption,
  w.government_effectiveness,
  w.political_stability,
  w.regulatory_quality,
  w.rule_of_law,
  w.voice_and_accountability,

  -- LPI
  l.customs,
  l.infrastructure,
  l.international_shipments,
  l.logistics_competence,
  l.tracking,
  l.timeliness,

  -- Port
  p.median_days_in_port
FROM base b
LEFT JOIN stg_wgi w
  ON w.country_code = b.country_code AND w.year = b.year
LEFT JOIN stg_lpi l
  ON l.country_code = b.country_code AND l.year = b.year
LEFT JOIN stg_port p
  ON p.country_code = b.country_code AND p.year = b.year
WHERE b.country_code IS NOT NULL
  AND b.year IS NOT NULL;

-- ------------------------------------------------------------
-- fact_tariff_schedule_yearly (hts8 × year)
-- ------------------------------------------------------------
TRUNCATE fact_tariff_schedule_yearly;
INSERT INTO fact_tariff_schedule_yearly (hts8, year, mfn_text_rate_pct)
SELECT
  t.hts8,
  2025 AS year,
  t.mfn_text_rate
FROM stg_tariff t
JOIN dim_tariff_code d
  ON d.hts8 = t.hts8
WHERE t.hts8 IS NOT NULL AND t.mfn_text_rate IS NOT NULL;

-- ---------------------------------------------
-- fact_product_monthly
-- ----------------------------------------------
INSERT INTO fact_product_monthly (date_key, product_country_key, ppi_value, real_price)
SELECT d.date_key, pc.product_country_key, sp.ppi_value, sp.real_price
FROM stg_products sp
JOIN dim_date d ON d.year = sp.year AND d.month = sp.month
JOIN dim_product dp ON dp.product = sp.product
JOIN dim_product_country pc ON pc.product_key = dp.product_key AND pc.country_code = sp.country_code;

-- ------------------------------------------------------------
-- Load fact_supplier_product_profile from stg_supplier_products
-- (joins through dim_supplier using supplier_id)
-- ------------------------------------------------------------
INSERT INTO fact_supplier_product_profile (
    supplier_key,
    probability_of_defect,
    bulk_discount,
    bulk_units,
    baseline_price,
    price_volatility,
    hts8
)
SELECT
    ds.supplier_key,
    sp.probability_of_defect,
    sp.bulk_discount,
    sp.bulk_units,
    sp.baseline_price,
    sp.price_volatility,
    NULLIF(NULLIF(trim(sp.hts8_tariff), ''), 'None')::CHAR(8) AS hts8
FROM stg_supplier_products sp
JOIN dim_supplier ds
  ON ds.supplier_id = sp.supplier_id;


COMMIT;