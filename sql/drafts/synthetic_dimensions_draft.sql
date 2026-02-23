----======================
-- Procurement product category dimension (the layer suppliers actually supply - composite/synthetic)
DROP TABLE IF EXISTS dim_product;
CREATE TABLE dim_product (
    product_key SERIAL PRIMARY KEY,
    product_name TEXT NOT NULL UNIQUE,  -- e.g., 'Semiconductor Components'
    product_category TEXT NULL -- e.g., 'Electronics'
)

-- Supplier Dimension (synthetic/composite)
DROP TABLE IF EXISTS dim_supplier;
CREATE TABLE dim_supplier (
    supplier_key SERIAL PRIMARY KEY,
    supplier_name TEXT NOT NULL UNIQUE,
    country_code CHAR(3) NOT NULL REFERENCES dim_country(country_code),
    supplier_type TEXT NOT NULL -- e.g., Manufacturer, Distributor, Foundry, Raw_Material_Supplier, etc.
    

);