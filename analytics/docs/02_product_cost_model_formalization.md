# 02 Product Cost Model Formalization

## Product Augmentation and Time-Series Extension

After generating country-level semiconductor component price series, additional processing was required to:

1. Extend price series to a consistent forecast horizon (2025)
2. Generate continuous monthly price histories for each country and product
3. Combine all component datasets into a single standardized product table

These steps ensure that the procurement agent has **complete and consistent price histories for all products across all supplier countries.**


---

# Forecasting Missing PPI Data

Many of the PPI series used to generate semiconductor component prices ended before the desired modeling horizon.

Examples include:

- Integrated circuit component datasets ending in **2023**
- Microprocessor datasets ending in **2015**

To support procurement simulation and supplier comparison, each **country–product pair** was extended to **December 2025**.

This was accomplished using **time-series forecasting techniques applied to the PPI index values.**


---

# Forecasting Method

For each `(country_code, ppi_source)` pair:

1. Historical monthly PPI values were ordered chronologically.
2. Missing internal values were filled using forward and backward filling.
3. If sufficient historical observations existed, the series was forecast using:

**Holt’s Linear Trend Exponential Smoothing**

This method was selected because it:

- Captures long-term inflation trends
- Produces smooth forecasts
- Avoids overfitting short economic time series
- Is widely used for economic indicator forecasting

The forecasting model used:

- Additive trend
- Damped trend
- No seasonal component

This configuration produces **stable long-run semiconductor price projections.**


---

# Fallback Forecast Method

In cases where insufficient historical observations were available for a country–product pair, a fallback method was used.

This fallback assumes a **2% annual cost growth rate**, applied monthly.

This ensures:

- Every country has a complete price series
- No missing values exist in the final dataset
- Prices evolve in a reasonable long-term direction even with sparse data


---

# COVID Supply Chain Shock Adjustment

The semiconductor industry experienced major supply disruptions during the COVID-19 pandemic.

To reflect these conditions, the microprocessor price model includes a temporary inflation shock between **2020 and 2022**.

During this period:

- PPI values are increased by **20% to 40%**
- The multiplier increases gradually across the shock period

This adjustment reflects real industry conditions including:

- Global semiconductor shortages
- Supply chain bottlenecks
- Increased fabrication and logistics costs

Following the shock period, the model simulates market stabilization.

From **2023 onward**, prices gradually normalize by applying a **cooling factor**, reducing price levels by roughly **10% from pandemic peaks** while remaining elevated relative to pre-pandemic levels.

This produces price trajectories consistent with observed semiconductor market behavior.


---

# Extending Real Prices Using PPI Ratios

Real semiconductor component prices are derived from baseline prices scaled by the corresponding PPI index.

When PPI values are forecast beyond the historical dataset, real prices are extended using the **relative change in the PPI index**.

The process follows these steps:

1. Identify the last observed real price and its corresponding PPI value.
2. Calculate the ratio of the forecasted PPI value to the last observed PPI value.
3. Scale the last known real price using this ratio.

Formula:

new_price = last_real_price × (forecast_ppi / last_observed_ppi)

This ensures that forecasted prices remain consistent with historical inflation patterns.


---

# Ensuring Data Completeness

After forecasting and price scaling:

- Remaining missing values are filled using forward and backward propagation
- Data validation checks confirm that **no missing PPI or price values exist before the 2025 forecast horizon**

This guarantees that the final dataset contains **complete monthly observations for every supplier country and product.**


---

# Product Dataset Standardization

After extending the time series, each semiconductor component dataset was standardized into a common structure.

The following product datasets were prepared:

| Product | Description |
|------|------|
| integrated_circuit_components | General semiconductor IC components |
| microprocessors | CPUs and microcontroller devices |
| transistors | Discrete semiconductor switching devices |
| power_devices | Power semiconductor components |

Each dataset contains the following columns:

| Column | Description |
|------|------|
| date | Monthly observation date |
| country_code | ISO3 supplier country code |
| ppi_value | Producer Price Index value |
| real_price | Estimated component unit price |
| product | Semiconductor component category |


---

# Removing Regional Placeholder Rows

During intermediate processing, some datasets contained aggregated regional rows such as **OAC (Other Asian Countries)**.

These rows were removed before combining datasets so that the final product table contains **only individual country observations.**


---

# Combining Product Datasets

Once standardized, the four semiconductor component datasets were merged into a single dataset.

The combined dataset contains monthly price data for:

- Integrated circuit components
- Microprocessors
- Transistors
- Power semiconductor devices

This unified dataset enables the procurement agent to compare suppliers across multiple semiconductor component categories.


---

# Country-Level PPI Region Mapping

To ensure consistent price modeling across countries, each supplier country is mapped to the most appropriate PPI region.

Examples include:

| Country | PPI Region Used | Rationale |
|------|------|------|
| USA | USA (BLS) | Domestic semiconductor manufacturing inflation |
| China | CHN | Chinese semiconductor manufacturing inflation |
| Canada | CAN | North American electronics manufacturing inflation |
| Mexico | MEX | North American electronics manufacturing inflation |
| Japan | OAC | Asian semiconductor production ecosystem |
| Singapore | OAC | Southeast Asian electronics manufacturing hub |
| Germany | USA proxy | European semiconductor exporters track global semiconductor trade prices |
| France | USA proxy | European semiconductor inflation aligns with global import markets |
| Netherlands | USA proxy | Major semiconductor equipment and trade hub |

This mapping ensures that each country’s semiconductor component prices evolve according to the **most relevant global semiconductor production region.**


---

# Final Output Dataset

The final dataset generated by this process is:

`combined_products_2025_v2.csv`

This dataset contains:

- Monthly semiconductor component prices
- Four semiconductor component categories
- All supplier countries included in the procurement agent
- Data coverage extending through **December 2025**
