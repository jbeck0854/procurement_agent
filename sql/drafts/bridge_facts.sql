-- Supplier supplies which procurement products (many-to-many)
CREATE TABLE IF NOT EXISTS bridge_supplier_product (
    supplier_key INT NOT NULL REFERENCES dim_supplier(supplier_key),
    product_key  INT NOT NULL REFERENCES dim_product(product_key),
    PRIMARY KEY (supplier_key, product_key)
);

-- Product is cost-proxied by which PPI series
CREATE TABLE IF NOT EXISTS bridge_product_ppi_series (
    product_key     INT NOT NULL REFERENCES dim_product(product_key),
    ppi_series_key  INT NOT NULL REFERENCES dim_ppi_series(ppi_series_key),
    weight          NUMERIC(10,6) NULL CHECK (weight IS NULL OR weight >= 0),
    PRIMARY KEY (product_key, ppi_series_key)
);

-- Product is cost-proxied by which commodities
CREATE TABLE IF NOT EXISTS bridge_product_commodity (
    product_key    INT NOT NULL REFERENCES dim_product(product_key),
    commodity_key  INT NOT NULL REFERENCES dim_commodity(commodity_key),
    weight         NUMERIC(10,6) NULL CHECK (weight IS NULL OR weight >= 0),
    PRIMARY KEY (product_key, commodity_key)
);

-- Product is associated with which tariff codes (for tariff risk)
CREATE TABLE IF NOT EXISTS bridge_product_tariff_code (
    product_key INT NOT NULL REFERENCES dim_product(product_key),
    hts8        CHAR(8) NOT NULL REFERENCES dim_tariff_code(hts8),
    PRIMARY KEY (product_key, hts8)
);