-- =========================
-- copy_staging.sql
-- Run with psql (so \copy works)
-- =========================

-- Purpose: bulk loads the cleaned CSVs into the landing tables

--------------------------------------------------------------------

-- PPI landing table related
--============
-- temporary raw table to handle loading for the stg_ppi and stg_ppi_series_meta table
DROP TABLE IF EXISTS stg_ppi_raw;
CREATE TEMP TABLE stg_ppi_raw (
  date         DATE,
  year         INT,
  month        INT,
  ppi_value    NUMERIC(10,4),
  series_id    TEXT,
  industry     TEXT,
  product      TEXT,
  source       TEXT,
  country_code CHAR(3),
  base_year    INT
);

-- loading all the ppi related data into the temporary table
TRUNCATE TABLE stg_ppi_raw;

\copy stg_ppi_raw (date, year, month, ppi_value, series_id, industry, product, source, country_code, base_year) FROM '/Users/jonathanbeck/Library/CloudStorage/OneDrive-Personal/Desktop/GWU_Spring_26/Business Analytics Capstone/cleaned_data/combined_ppi_data.csv' WITH (FORMAT csv, HEADER true);

-- loading the data from the temporary table into the stg_ppi landing table
TRUNCATE TABLE stg_ppi;

INSERT INTO stg_ppi (date, year, month, ppi_value, series_id, industry, product, source, country_code)
SELECT date, year, month, ppi_value, series_id, industry, product, source, country_code
FROM stg_ppi_raw;

-- loading the data from temporary table into the stg_ppi_series_meta table (one row per series)
TRUNCATE TABLE stg_ppi_series_meta;

INSERT INTO stg_ppi_series_meta (series_id, source, country_code, base_year)
SELECT DISTINCT series_id, source, country_code, base_year
FROM stg_ppi_raw;
------======== end of PPI related table landing handling

-- Commodity prices (single file)
TRUNCATE TABLE stg_commodity_prices;
\copy stg_commodity_prices FROM '/Users/jonathanbeck/Library/CloudStorage/OneDrive-Personal/Desktop/GWU_Spring_26/Business Analytics Capstone/cleaned_data/monthly_world_bank_commodity_prices_1960_2025_v2.csv' WITH (FORMAT csv, HEADER true);

-- Tariffs (single file)
TRUNCATE TABLE stg_tariff;
\copy stg_tariff FROM '/Users/jonathanbeck/Library/CloudStorage/OneDrive-Personal/Desktop/GWU_Spring_26/Business Analytics Capstone/cleaned_data/tarriff_database_2025_only_semiconductor_components_v2.csv' WITH (FORMAT csv, HEADER true);

-- WGI (single file; maping cols by position because of slash header)
TRUNCATE TABLE stg_wgi;
\copy stg_wgi (country_code, year, control_of_corruption, government_effectiveness, political_stability, regulatory_quality, rule_of_law, voice_and_accountability) FROM '/Users/jonathanbeck/Library/CloudStorage/OneDrive-Personal/Desktop/GWU_Spring_26/Business Analytics Capstone/cleaned_data/WGI_Select_Countries_2023.csv' WITH (FORMAT csv, HEADER true);

-- Port calls (single file)
TRUNCATE TABLE stg_port;
\copy stg_port FROM '/Users/jonathanbeck/Library/CloudStorage/OneDrive-Personal/Desktop/GWU_Spring_26/Business Analytics Capstone/cleaned_data/US_PortCalls_Time_for_ContainerShips_2023_Select_Countries.csv' WITH (FORMAT csv, HEADER true);

-- LPI (single file)
TRUNCATE TABLE stg_lpi;
\copy stg_lpi FROM '/Users/jonathanbeck/Library/CloudStorage/OneDrive-Personal/Desktop/GWU_Spring_26/Business Analytics Capstone/cleaned_data/International_LPI_Scorecard_Select_Countries_v2.csv' WITH (FORMAT csv, HEADER true);

-- synthetic supplier load
TRUNCATE TABLE stg_synthetic_suppliers;
\copy stg_synthetic_suppliers FROM '/Users/jonathanbeck/Library/CloudStorage/OneDrive-Personal/Desktop/GWU_Spring_26/Business Analytics Capstone/procurement_agent/cleaned_data/synthetic_suppliers.csv' WITH (FORMAT csv, HEADER true);

-- synthetic products load
TRUNCATE TABLE stg_synthetic_products;
\copy stg_synthetic_products FROM '/Users/jonathanbeck/Library/CloudStorage/OneDrive-Personal/Desktop/GWU_Spring_26/Business Analytics Capstone/procurement_agent/cleaned_data/combined_products_2025_v2-2.csv' WITH (FORMAT csv, HEADER true);

-- synthetic suppliers and products merged
TRUNCATE TABLE stg_supplier_products;
\copy stg_supplier_products FROM '/Users/jonathanbeck/Library/CloudStorage/OneDrive-Personal/Desktop/GWU_Spring_26/Business Analytics Capstone/procurement_agent/cleaned_data/suppliers_products.csv' WITH (FORMAT csv, HEADER true);



