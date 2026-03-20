# Supplier–Product Linking and Commercial Attribute Modeling

## Overview

This file details the workdone in `scripts/data_cleaning/03_link_suppliers_products` notebook, which takes the previously generated:

- `combined_products_UPDATED.csv`
- `synthetic_suppliers.csv`

and produces a **supplier-level procurement dataset** by assigning each supplier a semiconductor product category and generating realistic commercial attributes.

The updated notebook performs the following major steps:

1. Assigns each supplier a product category using **country-specific manufacturing weight distributions**
2. Computes a **probability of defect** using "general difficulty in manufacture" values and alignment with country manufacturing weight logic
3. Generates a **bulk-order discount** rate using base discount values and alighnmet scaling
4. Computes **bulk_units (MOQ)** using multipliers tied to country-product alignment
5. Extracts a **baseline supplier price** from the latest country-level product price
6. Injects **supplier-level price noise** to differentiate suppliers
7. Computes **price volatility** using rolling 60-month volatility blended with disruption risk
8. Tags suppliers with **HTS8 tariff codes**, applied only to imported IC Components

The final output is a supplier-level dataset with realistic commercial behavior and pricing characteristics.

---

## Input Datasets

**1. Combined Product Price Dataset**

The notebook reads:

`combined_products_UPDATED.csv`

This file contains monthly price histories for:

- integrated circuit components
- microprocessors
- transistors
- power devices

Columns include:

| Column | Description |
|---|---|
| `date` | Monthly observation date |
| `country_code` | Supplier country |
| `ppi_source` | PPI source used (FRED) |
| `ppi_region` | Regional PPI mapping |
| `ppi_value` | Monthly PPI value |
| `real_price` | Country-level unit price |
| `product` | Product category |

**2. Synthetic Supplier Dataset**

The notebook reads:

`synthetic_suppliers.csv`

Columns include:

- `supplier_id`
- `country_code`
- `lead_time_mean`
- `lead_time_stddev`
- `lead_time_variance`
- `disruption_probability`
- `compliance_eligibility`
- `logistics_reliability`

These attributes are preserved and extended with commerical modeling.

---

## Product Categories Used

| Supplier Label | Product Table Label |
|---|---|
| IC Components | integrated_circuit_components |
| Microprocessors | microprocessors |
| Power Devices | power_devices |
| Transistors | transistors |

These categories drive all downstream modeling.

---

## Country-Specific Product Assignment (Weighted)

**Purpose**

Suppliers are assigned products using **country-specific probability distributions** that reflect real-world semiconductor specialization.

This prevents unrealistic assignments (e.g., UAE lower chance of producing microprocessors) and ensures the synthetic supplier base mirrors global manufacuring patterns.

**Weight Matrix**

In our notebook, we defined a `country_product_weights` dictionary with weights for each product category per country.

For example:

- **China, Malaysia, Thailand, Singapore** --> heavily weighted toward IC Components
- **USA, Japan, Germany** --> higher weights for Microprocessors and Power Devices
- **Tier-2 Countries (Mexico, Netherlands, Canada, France, UK, India, Hong Kong, Indonesia)** -> balanced distributions
- **Tier-3 Countries (UAE, Australia, Belgium, Brazil, Finland)** --> weighted toward Transistors and IC Components

**Assignment Mechanism**

A seeded NumPy RNG (`np.random.default_rng(SEED)`) samples a product for each supplier:

```python
rng.choice(products, p=probs)
```

This ensures:

- reproducibility
- realistic specialization
- within-country variation

---

## Probability of Defect Modeling

In our notebook, we compute `probability_of_defect` using:

- product difficulty values, to represent how difficult it is to manufacture these components to a high-quality standard
- alignment with country specialization
- random variation

**Product Difficulty**

The difficulty (in manufacturing) values are:

| Product | Difficulty |
|---|---|
| Microprocessors | 0.12 |
| Power Devices | 0.07 |
| Transistors | 0.05 |
| IC Components | 0.025 |

**Alignment Logic**

For each supplier:

1. Retrive the country's weight for the assigned product
2. Compute the alignment factor: `alignment = 1 - weight (of country alignment with product)`
3. Scale difficulty value by alignment value
4. Multiply that value by a random uniform factor

This yields:

- lower defect risk for countries producing what they specialize in
- higher defect risk for misaligned production
- higher defect risk for more complex products

---

## Bulk-Order Discount Rate Modeling

In our notebook, we compute `bulk_discount` using base discounts and alignment scaling.

**Updated Base Discounts**

| Product | Base Discount |
|---|---|
| Microprocessors | 0.04 |
| Power Devices | 0.07 |
| Transistors | 0.11 |
| IC Components | 0.14 |

**Discount Formula**

`discount = base_discount * (0.3 + 0.7 * alighnment_weight) * rng.uniform(0.95, 1.05)`

- Strong alignment --> deeper discounts
- Weak alignment --> shallower discounts
- Noise ensures supplier-level variation

---

## Bulk Units / MOQ Modeling

In our notebook, we compute `bulk_units` (MOQ threshold) using multipliers.

**Base MOQ**

| Product | Base MOQ |
|---|---|
| Microprocessors | 1000 |
| Power Devices | 2000 |
| Transistors | 5000 |
| IC Components | 8000 |

**MOQ Formula**

```python
multiplier = 1.15 - 0.6 * alignment_weight
moq = base_moq * multiplier * rng.uniform(0.95, 1.05)
```

- Strong alignment --> lower MOQ (to activate `bulk_discount_rates`)
- Weak alignment --> higher MOQ (to activate `bulk_discount_rates`)
- MOQ is always >= 1

---

## Baseline Supplier Price Construction

In our notebook, we merge suppliers with the **latest available** country-level price for their assigned product.

**Steps**

1. Normalize product names using `product_name_map`
2. Sort product price table by date
3. Group by `(country_code, product_norm)`
4. Take the **last** (most recent) `real_price`
5. Merge into supplier table as `baseline_price`
6. Drop suppliers with missing price data

This ensures supplier prices reflect the most recent country-level cost model prices.

---

## Injecting Supplier-Level Price Noise

After merging the latest country-level product price into each supplier row, we introduce **structured supplier-level price variation**. This step is essential because suppliers operating in the same country and producing the same product should not have identical baseline prices. Real markets exhibit:

- supplier-specific efficiency differences
- country-level systematic cost differences
- product-specific variability in manufacturing cost stability

In our notebook, these effects are modeled using a **three-layered noise system**:

1. **Product-level variability** (how volatile the product category is)

Each product category has a characteristic noise range reflecting how much supplier prices for these products typically vary:

| Product | Noise Range (+/-) |
|---|---|
| Microprocessors | 3% |
| Power Devices | 5% |
| Transistors | 8% |
| IC Components | 10% |

This determines how wide the supplier-level price band is for that product.

2. **Country-level cost factor (systematic)**

A signle factor is generated **once per country**:

`country_cost_factors[country] = uniform(o.95, 1.05)`

This captures persistent structural cost differences (labor, energy, regulatory burden, subsidies) that affect **all suppliers** in that country.

3. **Supplier-level idiosyncratic noise**

Within each country and product, suppliers receive their own variation:

`supplier_noise = uniform(1 - product_noise_range, 1 + product_noise_range)`

This represents differences in supplier efficiency, yield, and overhead.

**Final Price**

Each supplier's final baseline price is:
`price = baseline_price * country_factor * supplier_noise`

This produces:
- clustering of prices by country
- wider spreads for commoditized products
- unique prices for each supplier
- deterministic, reproducible variation (due to the fixed RNG seed)

---

## Price Volatility Modeling

In our notebook, we compute a supplier-level `price_volatility` metric by combining **recent product price instability** with each supplier's **disruption probability**.

This produces a volatility signal that reflects both market behavior and operational risk.

The calculation has three stages:

1. **Rolling 60-month price volatility (country x product)**

For each `(country_code, product)` pair in the product price table, we compute a rolling standard deviation of `real_price`:

- 60-month window
- minimum of 12 months required
- computed after sorting by country, product, and date

```python
products_sorted["price_volatility_raw"] = (
    products_sorted.groupby(
        ["country_code", "product"]
    ).real_price.rolling(
        60, min_periods=12
    ).std().reset_index(level=[0,1], drop=True)
)
```

This captures recent 5-year price instability for each country-product combination.

2. **Latest volatility snapshot merged into suppliers**

In our notebook, we extract the most recent rolling volatility value for each `(country_code, product)` pair:

```python
latest_volatility = (
    products_sorted.groupby(["country_code", "product"]
    ).price_volatility_raw.last().reset_index()
)
```

This is merged into the supplier table based on the supplier's country and assigned product.

3. **Normalization and blending with disruption risk**

Because raw standard deviations are not comparable across products or countries, we apply min-max normalization:

```python
suppliers["price_volatility_norm"] = (
    (suppliers.price_volatility_raw - min_v) / (max_v - min_v)
)
```

Finally, the supplier's volatility score blends:
- 60% normalized price volatility
- 40% supplier disruption probability

```python
suppliers["price_volatility"] = (
    0.6 * suppliers.price_volatility_norm +
    0.4 * suppliers.disruption_probability
)
```

This produces a volatility metric that reflects:
- **market-driven price instability** (historical price behavior)
- **supplier-specific operational instability** (disruption risk)

The intermediate columns are dropped, leaving a clean `price_volatility` field.

---

## Tariff Tagging

In our notebook, we read the cleaned tariff dataset and assign HTS8 codes only to **imported** IC Components.

```python
if product == "IC Components" and country_code != "USA":
    hts8_tariff = "85389030"
else:
    hts8_tariff = "None"
```

This ensures:

- **Foreign IC suppliers** --> tariff code
- **U.S. IC suppliers** --> no tariff
- All other products --> no tariff

NOTE: HTS8 tariff code '85389030` reads "Printed circuit assemblies"

---

## Final Output

Our notebook produces:

`suppliers_products_UPDATED.csv`

This dataset contains supplier-level operational, commercial, pricing attributes tied to an assigned semiconductor product.

---

## Role in the Procurement Agent

The notebook described by this file is the bridge between the country-level cost model and the supplier-level scoring engine. It transforms macro-level pricing signals into supplier-specific commercial behavior, enabling the procurement agent to:

- compare suppliers
- evaluate tradeoffs
- assess quality and volatility
- reason about discounts and MOQ
- incorporate tariff logic
- generate realistic procurement recommendations

This step is essential for producing a credible, analytically rich supplier dataset that supports robust decision intelligence.


