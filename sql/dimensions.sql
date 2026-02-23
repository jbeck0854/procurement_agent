-- dimensions.sql
-- Purpose: Creating final dimension table definitions for fact tables to reference.
-- Loading/ETL handled in separate script

-- These tables provide context (dimensions) for the measurements in Fact tables
--==================================

-- Date dimension (month granularity) DONE
DROP TABLE IF EXISTS dim_date CASCADE;
CREATE TABLE dim_date (
    date_key INT PRIMARY KEY, -- Use YYYMM as the key
    date DATE NOT NULL UNIQUE,
    year INT NOT NULL,
    month INT NOT NULL, -- e.g., 1=Jan, 2=Feb, etc.
    year_month TEXT NOT NULL
);

-- Country / region dimension DONE
DROP TABLE IF EXISTS dim_country CASCADE;
CREATE TABLE dim_country (
    country_code CHAR(3) PRIMARY KEY,
    country_name TEXT NOT NULL,
    CONSTRAINT chk_country_code_format CHECK (country_code ~ '^[A-Z]{3}$')

);

-- PPI Series dimension (DONE)
DROP TABLE IF EXISTS dim_ppi_series CASCADE;
CREATE TABLE dim_ppi_series (
    ppi_series_key SERIAL PRIMARY KEY,
    series_id      TEXT NOT NULL UNIQUE,
    source         TEXT NOT NULL CHECK (source IN ('BLS','FRED')),
    country_code   CHAR(3) NULL REFERENCES dim_country(country_code),
    base_year      INT NOT NULL CHECK (base_year >= 1900),
    industry       TEXT NULL,
    product        TEXT NULL
);

-- PPI Metadata series dimension DONE
DROP TABLE IF EXISTS dim_ppi_series_meta CASCADE;
CREATE TABLE dim_ppi_series_meta (
    ppi_series_meta_key SERIAL PRIMARY KEY,
    series_id TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL, -- 'BLS' or 'FRED'
    country_code CHAR(3) NULL REFERENCES dim_country(country_code),
    base_year INT NOT NULL
);

-- Commodity dimension (World Bank) DONE
DROP TABLE IF EXISTS dim_commodity CASCADE;
CREATE TABLE dim_commodity(
    commodity_key SERIAL PRIMARY KEY,
    commodity_family TEXT NOT NULL, -- e.g., 'Crude Oil', 'Natural Gas', etc.
    commodity_variant TEXT NULL, -- e.g., 'WTI', 'Europe', etc.
    unit TEXT NOT NULL, -- e.g., '$/bbl', '$/mt'
    source TEXT NOT NULL, -- 'World Bank Pink Sheet
    CONSTRAINT uq_dim_commodity_nk UNIQUE (
        commodity_family,
        commodity_variant,
        unit,
        source
    )
);

-- Tariff code dimension (HTS8) DONE
DROP TABLE IF EXISTS dim_tariff_code CASCADE;
CREATE TABLE dim_tariff_code (
    hts8 CHAR(8) PRIMARY KEY,
    brief_description TEXT NULL,
    how_measured TEXT NULL
      CHECK (how_measured IN ('NO','KG','NA') OR how_measured IS NULL),
    CONSTRAINT chk_hts8_digits CHECK (hts8 ~ '^[0-9]{8}$')
);

-- DONE