# 01 Updated Product Cost Model Formalization

## Overview

The updated **Product Cost Model** constructrs realistic, country-level monthly price series for four semiconductor component categories by combining:

- **FRED** international manufacturing PPIs
- A unified **2012 base-year rebasing** across all regions PPIs
- **Country-specific 2012 baseline cost assumptions for each product**
- **Time-varying inflation scaling** using the mapped PPI series
- **Forecasting PPI extensions** for countries whose PPI series end before 2025-12-01 (e.g., CAN, CHN)

The notebook now produces **complete monthly price series from 2012-06-01 through 2025-12-01** for:

- Integrated circuit components
- Microprocessors
- Transistors
- Power semiconductor devices

These product-level datasets are then concatenated into a unified `combined_products.csv`.

---

## Conceptual Pricing Model

The derive prices, we separate:

- **Structural cost differences** (captured by country-specific baseline prices)
- **Inflation dynamics** (captured by regional PPI series)

Our updated **price formula**, used for all four products, is:

`Price (for country at time t) = Baseline_c x (PPI_r,t / PPI_r,2012)`

Where:
| Term | Meaning |
|---|---|
| `Baseline_c` | Country-specific structural cost level |
| `PPI_r,t` | PPI value for the mapped region (representing a country) at time t |
| `PPI_r,2012` | Mean PPI value for that region in 2012 (serving as the rebased anchor) |

In our notebook, we explicity compute the (mean) `ppi_anchor_2012` for each region (which equals `PPI_r,2012`) by grouping all FRED series by `(source, country_code)` for year 2012, where `country_code` is either USA, CAN, CHN, MEX, or OAC.

---

## Updated Base-Year Handling

**Universal 2012 Base Year**

The notebook now enforces a **common 2012 base year for all countries**, including the U.S., by:

1. Identifying that FRED USA semiconductor PPI originally uses a **2005 base year**.
2. Computing the **mean 2012 USA PPI value** (~ 82.47)
3. Rebasing the entire USA series using the formula: `(ppi_t / 82.47 ) * 100` so that **2012 = ~100**

This ensures all the FRED PPIs share a common 2012 base year; thus, **no country is advantaged or disadvantafed** by differing PPI base years.

---

## Updated PPI Source Mapping

In our notebook, we define a `ppi_map` that assigns each supplier country to:

- A **PPI source** (always FRED in this updated notebook)
- A **PPI region** (USA, CAN, CHN, MEX, OAC)

For example:

- Europe --> `(FRED, USA)`
- Asia --> `(FRED, OAC)`
- China -> `(FRED, CHN)`
- Canada -> `(FRED, CAN)`
- Mexico -> `(FRED, MEX)`

This mapping is applied to the suppliers to determine which PPI series each individual country uses.

---

## Extending Incomplete PPI Series

To extend incomplete FRED PPI series (e.g., China ending in 2018, Canada ending in 2020), the model applies **Holt's Damped Additive Trend Exponential Smoothing**, implemented via `statsmodels.tsa.holtwinters.ExponentialSmoothing`.

This method:

- Fits an **additive trend** to the observed PPI history.
- Applied a **dampened trend** to prevent unrealistic long-run divergence.
- Does **not** include a seasonal component
- Forecasts monthly values through 2012-12-01
- Applies guardrails to keep forecasts within +/-10-20% of the last observed value
- Falls back to a mild constant growwth model when fewer than 12 actual actual observations exist.

This produces a smooth, economically plausible extensions of each regional PPI series while avoiding explosive or collapsing trajectories.

---

## Supplier x Date Grid

In our notebook, we constuct a fully mapped grid that links:
- All supplier countries (20 total)
- All monthly dates from **2012-06-01 --> 2025-12-01**

This produces a **3260-row panel per product**.

The grid is then merged with the ppi series data so that each of the 20 countries is mapped to a specific FRED and "region" PPI series, which supplies a ppi_value for each country (based on the region it is mapped to) for all months between 2012-0-01 and 2025-12-01.

---

## Baseline Price Dictionaries

Each product category has its own **2012 baseline price dictionary**, defined directly in the notebook:

- `baseline_circuits` (for Integrated Circuit Components)
- `baseline_microprocessors_2012`
- `baseline_transistors_2012`
- `baseline_power_devices_2012`

These reflect structural cost differences across countries.

---

## Product-Level Price Generation

For each product category, we:

1. Reuse the supplier grid containing the attached PPI values
2. Apply a `compute_real_price_row` function
3. Assign a product label, dependent on the product we compute real price for
4. Obtain a complete monthly price series for all countries for each product
5. Save each of the four product datasets to a CSV.

Each product produces **3260 rows** (20 countries x 163 months).

---

## Combined Product Dataset

At the end of the notebook, the four product datasets are concatenated:

```python
combined_products = pd.concat([
    ic_components,
    microprocessors,
    transistors,
    power_devices
])
```

This produces a unified dataset containing:
- `date`
- `country_code`
- `ppi_source`
- `ppi_region`
- `ppi_value`
- `real_price`
- `product`

And is saved as: `combined_products_UPDATED.csv`

NOTE: The saved dataset is found within `cleaned_data` as _________

---

## Role in the Procurement gent

The updated model now provides:

- Fully normalized, base-year-consistent price series
- Complete PPI coverage through 2025
- Four product categories with realistic cross-country cost structures
- A unified dataset ready for joining with synthetic supplier tables

These imrovements ensure:
- **Fair cross-country comparisons for all countries**
- **Realistic cost volatility modeling**
- **Consistent inflation scaling**
- **Robust downstream procurement analytics**