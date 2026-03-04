CREATE OR REPLACE VIEW vw_supplier_product_pricing AS
SELECT
  s.supplier_id,
  s.country_code,
  p.product,
  f.baseline_price,
  f.bulk_discount,
  f.bulk_units,
  f.price_volatility,
  f.probability_of_defect,
  f.hts8,
  t.mfn_text_rate_pct
  dt.how measured
FROM dim_supplier s
JOIN fact_supplier_product_profile f
  ON f.supplier_key = s.supplier_key
JOIN dim_product p
  ON p.product_key = f.product_key
LEFT JOIN fact_tariff_schedule_yearly t
  ON t.hts8 = f.hts8;
LEFT JOIN dim_tariff_code ON dt.hts8 = f.htsq;