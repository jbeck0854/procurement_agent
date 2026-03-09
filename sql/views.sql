
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