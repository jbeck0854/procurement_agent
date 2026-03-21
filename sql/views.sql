
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



