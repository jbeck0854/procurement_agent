
-- View for supplier product pricing profile
CREATE OR REPLACE VIEW vw_supplier_pricing_profile AS
SELECT
  s.supplier_id,
  s.country_code,
  p.product,
  f.baseline_price,
  f.bulk_discount,
  f.bulk_units,
  f.price_volatility,
  f.probability_of_defect,
  t.mfn_text_rate_pct,
  f.hts8,
  dt.brief_description AS tariff_description,
  dt.how_measured
FROM dim_supplier s
JOIN fact_supplier_product_profile f
  ON f.supplier_key = s.supplier_key
JOIN dim_product p
  ON p.product_key = s.product_key
LEFT JOIN fact_tariff_schedule_yearly t
  ON t.hts8 = f.hts8
LEFT JOIN dim_tariff_code dt ON dt.hts8 = f.hts8;

-- View for supplier risk profile
CREATE OR REPLACE VIEW vw_supplier_risk_profile AS
SELECT 
  s.supplier_id,
  s.country_code,
  p.product,

  s.lead_time_mean,
  s.lead_time_stddev,
  s.lead_time_variance,
  s.disruption_probability,
  s.compliance_eligibility,
  s.logistics_reliability

FROM dim_supplier s 
LEFT JOIN dim_product p
  ON p.product_key = s.product_key;

-- View for complete supplier profile (pricing + risk)
CREATE OR REPLACE VIEW vw_supplier_complete_profile AS
SELECT
    s.supplier_id,
    s.country_code,
    p.product,

    -- risk inputs (dim_supplier)
    s.lead_time_mean,
    s.lead_time_stddev,
    s.lead_time_variance,
    s.disruption_probability,
    s.compliance_eligibility,
    s.logistics_reliability,

    -- value + quality inputs (fact_supplier_product_profile)
    f.baseline_price,
    f.price_volatility,
    f.probability_of_defect,
    f.bulk_discount,
    f.bulk_units,

    -- tariff inputs + metadata
    f.hts8,
    t.mfn_text_rate_pct,
    dt.how_measured,
    dt.brief_description AS tariff_description

FROM dim_supplier s JOIN fact_supplier_product_profile f
  ON f.supplier_key = s.supplier_key
JOIN dim_product p ON p.product_key = s.product_key
LEFT JOIN fact_tariff_schedule_yearly t ON t.hts8 = f.hts8
LEFT JOIN dim_tariff_code dt ON dt.hts8 = f.hts8;

-----------------
---- Views for explanability and plotting analytics
-----------------

------- View for monthly product-country price history view for charting, explainability, and time-series analytics.
-- Product-country price trends
-- rolling volatility trend
-- relative trend comparisons across countries and products

CREATE OR REPLACE VIEW vw_product_price_history AS
SELECT
    fpm.date_key,
    d.date,
    d.year,
    d.month,
    d.year_month,
    fpm.product_country_key,
    dpc.product_key,
    dp.product,
    dpc.country_code,
    dc.country_name,
    dpc.ppi_source,
    dpc.ppi_region,
    fpm.ppi_value,
    fpm.real_price

FROM fact_product_monthly fpm
JOIN dim_date d ON fpm.date_key = d.date_key
JOIN dim_product_country dpc ON fpm.product_country_key = dpc.product_country_key
JOIN dim_product dp ON dpc.product_key = dp.product_key
JOIN dim_country dc ON dpc.country_code = dc.country_code;

-- View for commodity trend plots
-- commodities act as indirect cost drivers for many products, so tracking their price trends can provide insight into potential cost pressures and inflationary trends that may impact supplier pricing and risk profiles.
-- Use for: nominal commodity trend, "what may be driving price pressure" visualizations, and perhaps as a benchmark for comparing supplier price trends against broader market trends.
CREATE OR REPLACE VIEW vw_commodity_price_history AS
SELECT
    f.date_key,
    d.date,
    d.year,
    d.month,
    d.year_month,
    c.commodity_key,
    c.commodity_family,
    c.commodity_variant,
    c.unit,
    c.source,
    f.nominal_price
FROM fact_commodity_price_monthly f
JOIN dim_date d ON f.date_key = d.date_key
JOIN dim_commodity c ON f.commodity_key = c.commodity_key;

-- View to support comparison visualizations across countries
-- Use for: country benchmark bar charts comparing supplier countries across key risk and value metrics (e.g., average supplier lead time, average baseline price, average price volatility, average logistics reliability, WGI governance indicators, LPI scores, etc.)
-- Use for: governance and logistics scorecard visualizations that compare supplier countries across key governance and logistics indicators to provide context on the operating environment in those countries and how it may impact supplier risk profiles.
-- Use for: supplier-country risk annotations on the supplier profile page to provide context on how a supplier's country may be contributing to their risk profile and what specific governance or logistics challenges they may face.
CREATE OR REPLACE VIEW vw_country_risk_snapshot AS
SELECT
    f.country_code,
    c.country_name,
    f.year,
    f.control_of_corruption,
    f.government_effectiveness,
    f.political_stability,
    f.regulatory_quality,
    f.rule_of_law,
    f.voice_and_accountability,
    f.lpi_customs,
    f.lpi_infrastructure,
    f.lpi_international_shipments,
    f.lpi_logistics_competence,
    f.lpi_tracking,
    f.lpi_timeliness
FROM fact_country_indicators_yearly f
JOIN dim_country c ON f.country_code = c.country_code;


-----------------
---- BOM Layer views
-----------------

-- Exploded component requirement detail
-- Grain: forecast_run_id × target_week_date × facility_id × semiconductor_id × product_key
-- One row per finished-good SKU × procurement component per forecast week.
-- gross_component_requirement is NOT rounded here; rounding belongs at the LP layer.
CREATE OR REPLACE VIEW vw_component_requirement_detail AS
SELECT
    f.forecast_run_id,
    f.target_week_date,
    f.facility_id,
    f.semiconductor_id,
    b.product_key,
    f.predicted_demand,
    b.units_per_sku,
    f.predicted_demand * b.units_per_sku  AS gross_component_requirement
FROM fact_semiconductor_demand_forecast f
JOIN dim_bom b ON b.semiconductor_id = f.semiconductor_id;

-- Aggregated LP-ready component requirements
-- Grain: forecast_run_id × target_week_date × facility_id × product_key
-- SKU dimension collapsed. This is the surface the LP optimizer consumes.
CREATE OR REPLACE VIEW vw_component_requirement_lp AS
SELECT
    forecast_run_id,
    target_week_date,
    facility_id,
    product_key,
    SUM(gross_component_requirement)  AS total_component_requirement
FROM vw_component_requirement_detail
GROUP BY
    forecast_run_id,
    target_week_date,
    facility_id,
    product_key;


-----------------
---- Inventory + Procurement Requirement Layer views
-----------------

-- Procurement requirement per forecast week per facility per component.
-- Grain: forecast_run_id × target_week_date × facility_id × product_key
--
-- Inventory state (on_hand, scheduled_receipts, backorder) is read from the
-- last historical week of fact_component_inventory_history (the decision point).
-- These are FIXED starting conditions — the same for all forecast weeks.
--
-- scheduled_receipts_qty = total outstanding on-order at decision point (MRP convention).
--
-- Formula:
--   net_requirement = max(0,
--       gross_requirement + backorder_qty + safety_stock_qty
--       - on_hand_qty - scheduled_receipts_qty
--   )
CREATE OR REPLACE VIEW vw_procurement_requirement AS
WITH decision_point AS (
    SELECT
        facility_id,
        product_key,
        on_hand_qty,
        scheduled_receipts_qty,
        backorder_qty,
        inventory_position
    FROM fact_component_inventory_history
    WHERE week_date = (SELECT MAX(week_date) FROM fact_component_inventory_history)
)
SELECT
    lp.forecast_run_id,
    lp.target_week_date,
    lp.facility_id,
    lp.product_key,
    lp.total_component_requirement          AS gross_requirement,
    dp.on_hand_qty,
    dp.scheduled_receipts_qty,
    dp.backorder_qty,
    pol.safety_stock_qty,
    pol.base_stock_target_qty,
    GREATEST(
        0::numeric,
        lp.total_component_requirement
        + dp.backorder_qty
        + pol.safety_stock_qty
        - dp.on_hand_qty
        - dp.scheduled_receipts_qty
    )                                       AS net_requirement
FROM vw_component_requirement_lp lp
JOIN decision_point dp
    ON  dp.facility_id = lp.facility_id
    AND dp.product_key = lp.product_key
JOIN fact_inventory_policy pol
    ON  pol.forecast_run_id = lp.forecast_run_id
    AND pol.facility_id     = lp.facility_id
    AND pol.product_key     = lp.product_key;
