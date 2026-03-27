-- load_bom.sql
-- Purpose: Seed dim_bom with BOM mappings (finished-good SKUs → procurement components).
--
-- This is curated business logic / seed data.
-- It is NOT derived from staging tables.
-- Safe to re-run: ON CONFLICT (semiconductor_id, product_key) DO NOTHING.
--
-- Run order: execute AFTER load_dimensions.sql and load_facts.sql.
--   load_dimensions.sql TRUNCATEs dim_semiconductor and dim_product with CASCADE,
--   which wipes dim_bom. Always run this file last to restore BOM seed data.
--
-- ── Family assignments (from finished_family in cleaned_data/finished_goods_demand_table.csv) ──
--
--   compute_control_modules       : SEMICONDUCTOR_6, 7, 8, 10  (high tier)
--   mixed_signal_interface_modules: SEMICONDUCTOR_1, 3, 4, 9   (mid tier)
--   power_management_modules      : SEMICONDUCTOR_2, 5, 11, 12 (low tier)
--
-- ── Component mapping logic ──────────────────────────────────────────────────
--
-- Each family has a base component template. Within each family, a complexity
-- multiplier scales the PRIMARY components only:
--
--   complexity = ROUND(mean_list_price / min_list_price_in_family, 1)
--
-- Secondary and optional components are fixed or toggled by complexity threshold,
-- not scaled, to preserve BOM sparsity.
--
-- compute_control_modules:
--   Primary (scaled)  : microprocessors (base=2.0), integrated_circuit_components (base=3.0)
--   Fixed             : power_devices (1.0) — on-module regulation, constant across complexity
--   Optional (toggle) : transistors (1.0) — only at complexity=1.0 (base SKU discrete support)
--
-- mixed_signal_interface_modules:
--   Primary (scaled)  : integrated_circuit_components (base=3.0), microprocessors (base=1.0)
--   Optional ≤ 1.2    : transistors (1.0) — discrete analog switching in lower-complexity SKUs
--   Optional ≥ 1.6    : power_devices (1.0) — multi-rail supply needed in higher-complexity SKUs
--
-- power_management_modules:
--   Primary (scaled)  : power_devices (base=2.0), transistors (base=3.0), IC (base=1.0)
--   No microprocessors — power management modules do not embed general-purpose compute
--
-- ── Complexity multipliers (derived from mean list price per SKU) ─────────────
--
--   compute_control    : SEMICONDUCTOR_6=1.0, SEMICONDUCTOR_10=1.1,
--                        SEMICONDUCTOR_8=1.1,  SEMICONDUCTOR_7=1.5
--   mixed_signal       : SEMICONDUCTOR_9=1.0, SEMICONDUCTOR_4=1.2,
--                        SEMICONDUCTOR_1=1.6,  SEMICONDUCTOR_3=1.6
--   power_management   : SEMICONDUCTOR_11=1.0, SEMICONDUCTOR_2=1.0,
--                        SEMICONDUCTOR_5=1.0,  SEMICONDUCTOR_12=1.2
--
-- Note: SEMICONDUCTOR_10 and _8 share multiplier 1.1 (prices within 4% of each other).
--       SEMICONDUCTOR_1  and _3 share multiplier 1.6 (prices within 0.1% of each other).
--       SEMICONDUCTOR_11, _2, and _5 share 1.0 (prices within 0.4% of each other).
--       These are honest reflections of the data, not rounding errors.
-- ============================================================================

BEGIN;

WITH pk AS (
    -- Resolve procurement component product_keys by canonical name.
    -- Names match dim_product as loaded by load_dimensions.sql.
    SELECT product_key, product
    FROM dim_product
    WHERE product IN (
        'microprocessors',
        'integrated_circuit_components',
        'power_devices',
        'transistors'
    )
),
bom_seed (semiconductor_id, product, units_per_sku) AS (VALUES

    -- ── compute_control_modules ───────────────────────────────────────────────
    -- High-tier compute modules. Microprocessors and IC components are primary;
    -- on-module power regulation (power_devices) is fixed at 1.0 across all SKUs.
    -- Discrete transistor support included only for the base complexity SKU.

    -- SEMICONDUCTOR_6 | complexity=1.0 | micro=2.0×1.0, IC=3.0×1.0, power=1.0, transistors=1.0
    ('SEMICONDUCTOR_6',  'microprocessors',               2.0),
    ('SEMICONDUCTOR_6',  'integrated_circuit_components', 3.0),
    ('SEMICONDUCTOR_6',  'power_devices',                 1.0),
    ('SEMICONDUCTOR_6',  'transistors',                   1.0),

    -- SEMICONDUCTOR_10 | complexity=1.1 | micro=2.0×1.1=2.2, IC=3.0×1.1=3.3, power=1.0
    ('SEMICONDUCTOR_10', 'microprocessors',               2.2),
    ('SEMICONDUCTOR_10', 'integrated_circuit_components', 3.3),
    ('SEMICONDUCTOR_10', 'power_devices',                 1.0),

    -- SEMICONDUCTOR_8 | complexity=1.1 | micro=2.0×1.1=2.2, IC=3.0×1.1=3.3, power=1.0
    ('SEMICONDUCTOR_8',  'microprocessors',               2.2),
    ('SEMICONDUCTOR_8',  'integrated_circuit_components', 3.3),
    ('SEMICONDUCTOR_8',  'power_devices',                 1.0),

    -- SEMICONDUCTOR_7 | complexity=1.5 | micro=2.0×1.5=3.0, IC=3.0×1.5=4.5, power=1.0
    ('SEMICONDUCTOR_7',  'microprocessors',               3.0),
    ('SEMICONDUCTOR_7',  'integrated_circuit_components', 4.5),
    ('SEMICONDUCTOR_7',  'power_devices',                 1.0),

    -- ── mixed_signal_interface_modules ───────────────────────────────────────
    -- Mid-tier mixed-signal modules. IC components are primary; microprocessors
    -- provide embedded digital control. Lower-complexity SKUs use discrete
    -- transistors for analog switching; higher-complexity SKUs replace these
    -- with multi-rail power regulation (power_devices).

    -- SEMICONDUCTOR_9 | complexity=1.0 | IC=3.0×1.0, micro=1.0×1.0, transistors=1.0
    ('SEMICONDUCTOR_9',  'integrated_circuit_components', 3.0),
    ('SEMICONDUCTOR_9',  'microprocessors',               1.0),
    ('SEMICONDUCTOR_9',  'transistors',                   1.0),

    -- SEMICONDUCTOR_4 | complexity=1.2 | IC=3.0×1.2=3.6, micro=1.0×1.2=1.2, transistors=1.0
    ('SEMICONDUCTOR_4',  'integrated_circuit_components', 3.6),
    ('SEMICONDUCTOR_4',  'microprocessors',               1.2),
    ('SEMICONDUCTOR_4',  'transistors',                   1.0),

    -- SEMICONDUCTOR_1 | complexity=1.6 | IC=3.0×1.6=4.8, micro=1.0×1.6=1.6, power_devices=1.0
    ('SEMICONDUCTOR_1',  'integrated_circuit_components', 4.8),
    ('SEMICONDUCTOR_1',  'microprocessors',               1.6),
    ('SEMICONDUCTOR_1',  'power_devices',                 1.0),

    -- SEMICONDUCTOR_3 | complexity=1.6 | IC=3.0×1.6=4.8, micro=1.0×1.6=1.6, power_devices=1.0
    ('SEMICONDUCTOR_3',  'integrated_circuit_components', 4.8),
    ('SEMICONDUCTOR_3',  'microprocessors',               1.6),
    ('SEMICONDUCTOR_3',  'power_devices',                 1.0),

    -- ── power_management_modules ─────────────────────────────────────────────
    -- Low-tier power modules. Power devices and transistors are the switching
    -- and regulation fabric (primary). IC components provide gate driver and
    -- control logic (secondary). No microprocessors.

    -- SEMICONDUCTOR_11 | complexity=1.0 | power=2.0, transistors=3.0, IC=1.0
    ('SEMICONDUCTOR_11', 'power_devices',                 2.0),
    ('SEMICONDUCTOR_11', 'transistors',                   3.0),
    ('SEMICONDUCTOR_11', 'integrated_circuit_components', 1.0),

    -- SEMICONDUCTOR_2 | complexity=1.0 | power=2.0, transistors=3.0, IC=1.0
    ('SEMICONDUCTOR_2',  'power_devices',                 2.0),
    ('SEMICONDUCTOR_2',  'transistors',                   3.0),
    ('SEMICONDUCTOR_2',  'integrated_circuit_components', 1.0),

    -- SEMICONDUCTOR_5 | complexity=1.0 | power=2.0, transistors=3.0, IC=1.0
    ('SEMICONDUCTOR_5',  'power_devices',                 2.0),
    ('SEMICONDUCTOR_5',  'transistors',                   3.0),
    ('SEMICONDUCTOR_5',  'integrated_circuit_components', 1.0),

    -- SEMICONDUCTOR_12 | complexity=1.2 | power=2.0×1.2=2.4, transistors=3.0×1.2=3.6, IC=1.0×1.2=1.2
    ('SEMICONDUCTOR_12', 'power_devices',                 2.4),
    ('SEMICONDUCTOR_12', 'transistors',                   3.6),
    ('SEMICONDUCTOR_12', 'integrated_circuit_components', 1.2)

)
INSERT INTO dim_bom (semiconductor_id, product_key, units_per_sku)
SELECT
    s.semiconductor_id,
    pk.product_key,
    s.units_per_sku
FROM bom_seed s
JOIN pk ON pk.product = s.product
ON CONFLICT (semiconductor_id, product_key) DO NOTHING;

COMMIT;

-- ── Verification query (run manually to confirm) ──────────────────────────────
-- Expected: 37 rows across 12 semiconductor_ids (13 for compute_control, 12 each for
-- mixed_signal and power_management)
--
-- SELECT b.semiconductor_id, p.product, b.units_per_sku
-- FROM dim_bom b
-- JOIN dim_product p ON p.product_key = b.product_key
-- ORDER BY b.semiconductor_id, p.product;
