# Supplier–Product Linking and Commercial Attribute Modeling

## Overview

This stage of the pipeline takes the previously created:

- `combined_products_2025_v2.csv`
- `synthetic_suppliers.csv`

and links them together to create a more realistic supplier-level procurement dataset.

The purpose of this notebook is not only to assign products to suppliers, but also to generate additional supplier-level commercial and operational attributes that make the procurement agent more credible and analytically useful.

At a high level, this process does six things:

1. Assigns each supplier a semiconductor product category using **country-specific product weight distributions**
2. Creates a **probability of defect** based on product difficulty and country–product alignment
3. Creates a **bulk discount rate** based on product type and country specialization
4. Creates a **bulk-units / minimum order quantity (MOQ)** threshold tied to country–product alignment
5. Pulls in a **baseline supplier price** from the country-level product price table and injects supplier-specific noise
6. Computes a **supplier-level price volatility** metric using recent product price behavior and disruption risk

The final output is a supplier–product dataset that is more realistic than a simple random join and better supports procurement scoring, tradeoff analysis, and recommendation logic.



---

# Input Datasets

## 1. Combined Product Price Dataset

The notebook reads the combined country-level product pricing table:

`combined_products_2025_v2.csv`

This file contains monthly product-level price histories by country and product category.

Core columns include:

| Column | Description |
|---|---|
| `date` | Monthly observation date |
| `country_code` | ISO3 supplier country code |
| `ppi_source` | PPI source used to derive prices |
| `real_price` | Estimated unit price for the product |
| `product` | Semiconductor product category |

This table provides the country-level price foundation that is later transferred to suppliers.

## 2. Synthetic Supplier Dataset

The notebook also reads:

`synthetic_suppliers.csv`

This file contains supplier-level operational and risk attributes already generated in earlier modeling steps.

Core columns include:

| Column | Description |
|---|---|
| `supplier_id` | Unique supplier identifier |
| `country_code` | ISO3 country code |
| `lead_time_mean` | Average lead time for the supplier |
| `lead_time_variance` | Variability in supplier lead time |
| `disruption_probability` | Estimated disruption likelihood |
| `compliance_eligibility` | Whether supplier is procurement-eligible |
| `logistics_reliability` | Country/supplier logistics reliability signal |



---

# Product Categories Used

The supplier assignment process uses four semiconductor product categories:

| Product Label in Supplier Table | Matching Product in Product Price Table |
|---|---|
| `IC Components` | `integrated_circuit_components` |
| `Microprocessors` | `microprocessors` |
| `Power Devices` | `power_devices` |
| `Transistors` | `transistors` |

These same four categories are carried through the remainder of the supplier modeling process.



---

# Country-Specific Product Assignment Using Weighted Tiers

## Purpose

Rather than assigning products to suppliers uniformly at random, the notebook uses a **country-specific weighted assignment system**.

This is one of the most important steps in the file.

The goal is to ensure that suppliers are more likely to be assigned products that are consistent with what their country is actually known for producing in the modern semiconductor ecosystem.

This makes the synthetic supplier base more believable.

## Country Weight Matrix

A custom dictionary called `country_product_weights` is used to define, for each country, the relative likelihood of producing each product category.

The weights vary substantially by country.

Examples:

- China, Malaysia, Thailand, and Singapore are weighted heavily toward **IC Components**
- Germany and Japan are weighted more heavily toward **Power Devices**
- Lower-strength countries are weighted more toward **Transistors** and simpler component production

## Tier Logic

The notebook organizes countries conceptually into industry-aligned groups such as:

### Tier 1A — IC Component and OSAT Powerhouses
Examples:
- China
- Malaysia
- Thailand
- Singapore

These countries receive high weights for:
- IC Components
- moderate Power Devices
- lower Microprocessor exposure

### Tier 1B — Advanced Logic / Specialty Analog
Examples:
- United States
- Japan
- Germany

These countries are more likely to receive:
- Microprocessors
- Power Devices
- Transistors
- lower IC Components in certain cases

### Tier 2 — Moderate Semiconductor Presence
Examples:
- Mexico
- Netherlands
- Canada
- France
- United Kingdom
- India
- Hong Kong
- Indonesia

These countries receive more balanced distributions.

### Tier 3 — Lower Semiconductor Strength
Examples:
- UAE
- Australia
- Belgium
- Brazil
- Finland

These countries are more heavily weighted toward simpler or lower-complexity product categories.

## Assignment Mechanism

For each supplier, the notebook samples a product category using the probability distribution associated with that supplier’s country.

This means:

- product assignment is still randomized
- but the randomization is constrained by economically meaningful country-level specialization weights

As a result, two suppliers from the same country may receive different product assignments, but those assignments still reflect that country’s overall semiconductor profile.



---

# Probability of Defect Modeling

After assigning a product to each supplier, the notebook creates a `probability_of_defect` column.

This variable is designed to reflect how likely a supplier is to produce defective output for its assigned product.

## Inputs Used

The defect probability depends on four ideas explicitly described in the notebook:

- how aligned the supplier’s assigned product is with what that country is actually known for producing
- how mature and reliable the country’s manufacturing base is
- how complex the product category is
- a small amount of random noise to create within-country variation

## Product Difficulty Baselines

The notebook assigns a baseline manufacturing difficulty by product:

| Product | Baseline Difficulty |
|---|---|
| Microprocessors | 0.08 |
| Power Devices | 0.05 |
| IC Components | 0.04 |
| Transistors | 0.03 |

This makes microprocessors the hardest product category and transistors the easiest.

## Alignment Logic

For each supplier:

1. The country’s weight for the assigned product is retrieved
2. An alignment factor is calculated as `1 - weight`
3. Higher misalignment increases defect risk
4. The result is scaled by product difficulty
5. Small random noise is applied

Conceptually, this means:

- a country producing what it is strong at should have lower defect risk
- a country producing something less aligned with its industrial profile should have higher defect risk
- more complex products naturally carry more defect risk



---

# Bulk-Order Discount Rate Modeling

The notebook next creates a `bulk_discount` column.

This models how aggressively a supplier may discount orders placed at larger volume.

## Drivers of Bulk-Order Discount Rates

The notebook explicitly ties discount behavior to:

- how mature and high-volume the country’s semiconductor manufacturing base is
- how aligned the supplier’s assigned product is with what the country is known for producing
- how competitive the country is in packaging markets
- how aggressively suppliers in that country typically discount for volume

## Base Discount by Product

The notebook begins with product-specific baseline discount rates:

| Product | Base Bulk Discount |
|---|---|
| IC Components | 0.15 |
| Transistors | 0.12 |
| Power Devices | 0.08 |
| Microprocessors | 0.05 |

This reflects the idea that simpler, higher-volume components tend to support deeper discounts, while more complex products like microprocessors support smaller discounts.

## Alignment Adjustment

The country’s product weight is then used again:

- stronger alignment leads to deeper discount potential
- weaker alignment reduces discount depth

A small amount of noise is added so suppliers within the same country and product category do not all receive identical discount rates.



---

# Bulk Units / Minimum Order Quantity Modeling

The notebook then adds a `bulk_units` column.

This represents the minimum order quantity required before the bulk discount becomes applicable.

This is effectively the supplier’s MOQ threshold.

## Drivers Used

The notebook explicitly states that MOQ depends on:

- product category
- country manufacturing maturity
- country cost structure
- country alignment with that product

It also states a key assumption:

- if a country is strong in a product, MOQ should be lower
- if a country is weak in a product, MOQ should be higher

## Base MOQ by Product

The notebook starts with product-specific baseline order thresholds:

| Product | Base MOQ |
|---|---|
| Microprocessors | 1000 |
| Power Devices | 2000 |
| Transistors | 5000 |
| IC Components | 8000 |

## Adjustment Logic

The country’s product alignment weight is used to scale MOQ:

- higher alignment lowers MOQ
- lower alignment raises MOQ

Noise is again added to prevent uniform supplier behavior.

This produces more realistic supplier ordering behavior by making specialized countries easier to source from at lower thresholds, while less specialized countries require higher commitment before volume discounts apply.



---

# Baseline Supplier Price Construction

The notebook then links suppliers back to the combined product price table to create a `baseline_price` for each supplier.

This is a major part of the modeling logic and should not be skipped.

## Product Name Normalization

The supplier-side product labels do not exactly match the product price table labels.

A mapping is therefore created:

| Supplier Label | Product Price Table Label |
|---|---|
| IC Components | integrated_circuit_components |
| Transistors | transistors |
| Power Devices | power_devices |
| Microprocessors | microprocessors |

## Price Extraction Logic

The notebook then:

1. normalizes product names
2. sorts the product price table by date
3. groups by `(country_code, product)`
4. takes the **most recent available `real_price`**
5. merges that value into the supplier table

So the supplier’s baseline price is not random.

It is the **latest country-level price estimate for that supplier’s country and assigned product**.

This creates a clean bridge between:

- the earlier country-level cost model
- the later supplier-level commercial model

Suppliers with no matching baseline price are dropped.



---

# Injecting Supplier-Level Noise into Baseline Prices

After merging the latest country-level baseline price, the notebook adds supplier-level variation.

This is done because suppliers within the same country and product category should not all have exactly the same baseline unit cost.

## Product-Specific Noise Ranges

The notebook uses multiplicative noise ranges by product:

| Product | Noise Range |
|---|---|
| Microprocessors | +/-3% |
| Power Devices | +/-15% |
| Transistors | +/-8% |
| IC Components | +/-10% |

## Interpretation

This reflects the idea that:

- microprocessors are more standardized and complex, so supplier prices should vary less
- IC Components and transistors may exhibit greater supplier-level variation
- supplier pricing should remain close to the country-level benchmark, but not identical

The result is a more realistic supplier-level `baseline_price` column.



---

# Price Volatility Modeling

The notebook next creates a supplier-level `price_volatility` metric.

This is not arbitrary. It is derived using both:

- historical product price behavior
- supplier disruption exposure

## Step 1: Rolling Country–Product Price Volatility

For each `(country_code, product)` pair in the product table, the notebook computes a rolling standard deviation of `real_price` over the last 60 months, with a minimum of 12 months required.

This produces a recent 5-year price volatility measure for each country–product pair.

## Step 2: Latest Volatility Snapshot

The most recent rolling volatility value is then extracted for each country–product combination.

That value is merged into the supplier table.

## Step 3: Normalization

Because raw standard deviations are not directly comparable across products and countries, the notebook min-max normalizes the volatility values.

## Step 4: Blending with Disruption Probability

The final supplier-level `price_volatility` metric is constructed as:

- 60% normalized price volatility
- 40% disruption probability

This means supplier price volatility reflects both:

- how unstable product prices have recently been in that country
- how exposed the supplier is to disruption risk

This is a useful feature for procurement because price instability is often driven by both market behavior and supply disruption risk.



---

# Tariff Tagging

The notebook ends by reading a cleaned tariff dataset:

`tarriff_database_2025_only_semiconductor_components_v2.csv`

It filters rows with positive MFN tariff rates and inspects candidate HTS8 codes relevant to semiconductor-related components.

A specific note is made that:

- HTS8 code `85389030`
- “Printed circuit assemblies, suitable for use ...”

could potentially be included under IC Components.

The notebook then creates an `hts8_tariff` field in the supplier table:

- suppliers assigned to `IC Components` receive `85389030`
- all other products receive `None`

This step is preliminary, but it establishes the structure needed to later connect supplier–product rows to tariff logic and landed-cost analysis.



---

# Final Output

The final output of the notebook is:

`suppliers_products.csv`

This dataset contains supplier-level operational, commercial, and pricing attributes tied to an assigned semiconductor product.

Key fields now include:

| Column | Description |
|---|---|
| supplier_id | Unique supplier identifier |
| country_code | Supplier country |
| product | Assigned semiconductor product category |
| lead_time_mean | Average supplier lead time (in days) |
| lead_time_stddev | Standard deviation of supplier lead time |
| lead_time_variance | Variability in lead time |
| disruption_probability | Supplier disruption risk |
| compliance_eligibility | Procurement eligibility |
| logistics_reliability | Logistics performance measure |
| probability_of_defect | Estimated quality / defect risk |
| bulk_discount | Supplier discount rate for large orders |
| bulk_units | MOQ threshold for bulk discount |
| baseline_price | Supplier-specific baseline unit price |
| price_volatility | Blended price instability signal |
| hts8_tariff | Preliminary tariff code tag |



---

# Role in the Procurement Agent

This notebook is the bridge between the earlier country-level pricing model and the later supplier scoring engine.

It transforms a country-level semiconductor cost panel into a supplier-level procurement dataset that contains:

- supplier specialization
- supplier commercial behavior
- supplier pricing
- supplier quality risk
- supplier price volatility
- preliminary tariff tagging

Without this step, the procurement agent would only know country-level prices.

With this step, the system can reason at the supplier level and support questions such as:

- Which suppliers are best for a given product?
- Which suppliers offer stronger volume discounts?
- Which suppliers have higher quality or defect risk?
- Which suppliers combine attractive price with lower volatility?
- How should supplier recommendations change when procurement priorities shift?

This makes the final supplier dataset substantially more useful for ranking, tradeoff analysis, and decision support.