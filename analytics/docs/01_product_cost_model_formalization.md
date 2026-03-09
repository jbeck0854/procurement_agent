# 01 Product Cost Model Formalization

## Overview

The **Product Cost Model** generates country-level price estimates for semiconductor components used within the procurement decision intelligence agent.

Because **supplier-level price data does not exist publicly**, the model constructs realistic price series using a combination of:

- Real **Producer Price Index (PPI)** datasets from the **U.S. Bureau of Labor Statistics (BLS)** and **Federal Reserve Economic Data (FRED)**
- Country-level **baseline cost assumptions**
- Time-based **inflation scaling using PPI indices**

The result is a **monthly price estimate for each product type and supplier country** that reflects:

- Structural cost differences between countries
- Inflation and cost trends over time
- Regional semiconductor manufacturing dynamics

These price estimates are then interpolated to the end of 2025 (`02_product_cost_model_formalization.md`), before being selectively joined with each derived supplier. This eventual aggregation of suppliers and products is then used by the procurement agent to evaluate:

- Supplier cost competitiveness
- Cost volatility
- Procurement cost tradeoffs across suppliers and regions



---

# Conceptual Pricing Model

The model separates **structural manufacturing cost differences between countries** from **price changes over time**.

Each country begins with a **baseline component cost assumption**, which represents the relative manufacturing cost level for that country.

Prices then evolve over time according to the inflation behavior of semiconductor manufacturing within that region.

The general price calculation is:

`Price_{country,t} = BaselinePrice_{country} * (PPI_value{region,t} / PPI_value(region,base_year))`

Where:

| Variable | Description |
|---|---|
| `BaselinePrice_country` | Country-specific starting cost assumption for a component |
| `PPI_region,t` | Producer Price Index value at time *t* |
| `PPI_region,base` | Reference PPI value used as the scaling base |

**NOTE**: PPI region is used in the fractile component of the fomula, rather than country, because some countries (e.g., Indonesia) did not have available PPI data; thus, the `OAC` region (FRED) was used to represent these countries.

This approach allows the model to capture:

- **Structural differences in semiconductor production costs**
- **Real-world price inflation trends within semiconductor manufacturing**



---

# Anchor and Base-Year Handling

Producer Price Index datasets often begin at different points in time.

For example:

| Data Source | Example Start Year |
|---|---|
| BLS U.S. semiconductor PPI | 1976 |
| FRED China semiconductor manufacturing | 2012 |
| FRED Mexico electronics manufacturing | 2012 |
| FRED U.S. import semiconductor index | 2005 |

Because the available PPI datasets begin in different years, the model uses a **mixed anchoring approach**.

### U.S. BLS Series

### PPI Base-Year Alignment and Data Source Usage

The cost model uses a combination of **U.S. Bureau of Labor Statistics (BLS)** and **Federal Reserve Economic Data (FRED)** Producer Price Index datasets to generate country-level semiconductor component price series.

The choice of index source depends on:

1. The availability of semiconductor-specific PPI datasets
2. The geographic region of the supplier country

This hybrid approach allows the model to combine **high-quality U.S. semiconductor manufacturing price signals** with **regional manufacturing price proxies for international suppliers**.



---

### U.S. Semiconductor Components (BLS)

For semiconductor components where **U.S. BLS Producer Price Index data is available**, the model uses the **true base year of the corresponding BLS dataset** as the reference anchor for price scaling.

Each semiconductor product category was aligned with the base year defined by its underlying BLS price series to ensure that baseline price assumptions correspond to the same economic reference period used by the official PPI data.

Examples include:

| Product Category | Base Year Used | Source |
|---|---|---|
| Integrated circuit components | 1998 | BLS Integrated circuit components PPI |
| Microprocessors | 2007 | BLS Microprocessors and microcontrollers PPI |
| Transistors | 1981 | BLS Transistors, diodes, and lesser components PPI |

For these three component categories, **U.S. prices evolve directly according to the BLS semiconductor manufacturing PPI series**.



---

### International Semiconductor Price Dynamics (FRED)

Equivalently grained semiconductor component PPI datasets are **not widely available for most countries outside the United States**.

To approximate semiconductor cost inflation across global suppliers, the model therefore uses **FRED datasets representing semiconductor or electronics manufacturing price indices in major production regions**.

These indices are applied as **regional proxies** for supplier countries with similar manufacturing ecosystems.

Examples include:

| Region Represented | FRED Dataset Type |
|---|---|
| China | Semiconductor manufacturing PPI |
| Other Asian Countries (OAC) | Regional semiconductor manufacturing index |
| Canada | Computer and electronic manufacturing PPI |
| Mexico | Computer and electronic manufacturing PPI |

These indices capture the **price evolution of semiconductor and electronics manufacturing inputs within major production hubs**.



---

### European Semiconductor Producers (Proxy Method)

Direct semiconductor PPI datasets were not available for several **European semiconductor manufacturing countries** included in the supplier dataset (e.g., Germany, France, Belgium, Finland, and the United Kingdom).

To model semiconductor price inflation for these countries, the model uses the **U.S. semiconductor import price index available through FRED**.

This index reflects **the prices paid by U.S. firms for imported semiconductor products**, which are sourced from major global semiconductor exporters — including European manufacturers.

Because European semiconductor firms such as **Infineon, STMicroelectronics, NXP, and ASML suppliers** participate heavily in global semiconductor trade flows, movements in U.S. semiconductor import prices provide a reasonable proxy for price trends affecting European semiconductor production.

Using this import-based index allows the model to capture **global semiconductor trade price dynamics** even when country-specific producer price indices are unavailable.



---

### Power Semiconductor Devices

The **power semiconductor device category** was modeled entirely using **FRED datasets**, as BLS did not provide a directly matching semiconductor PPI series for this component type.

The FRED semiconductor and electronics manufacturing indices used for this category share a **2012 base year**, so the model adopts **2012 as the reference year** for the power semiconductor component price series.



---

### Resulting Data Structure

The final pricing framework uses the following structure:

| Country | Price Index Source |
|---|---|
| United States | BLS semiconductor manufacturing PPI |
| China | FRED semiconductor manufacturing PPI |
| Canada | FRED electronics manufacturing PPI |
| Mexico | FRED electronics manufacturing PPI |
| Southeast Asian producers | FRED Asian semiconductor manufacturing index |
| European semiconductor producers | FRED U.S. semiconductor import price index (proxy) |

This hybrid framework allows the model to combine:

- **high-resolution semiconductor manufacturing price data for the United States**
- **regional semiconductor manufacturing inflation signals**
- **global semiconductor trade price dynamics**

to construct consistent semiconductor component price estimates across all supplier countries represented in the procurement agent.



---

# Core Data Sources

The cost model integrates multiple public datasets that capture semiconductor price behavior.

## Bureau of Labor Statistics (BLS)

The **BLS Producer Price Index (PPI)** measures changes in prices received by producers for their output.

These datasets provide **direct pricing signals for semiconductor manufacturing in the United States**.

### Semiconductor series used

| Product Category | Description |
|---|---|
| Integrated circuit packages | Semiconductor packaging and assembly components |
| Microprocessors and microcontrollers | Logic and computing semiconductor chips |
| Other semiconductor devices | Transistors, diodes, and lesser semiconductor devices |
| Aggregated semiconductor products | Broader semiconductor manufacturing indices |

### Key dataset fields

| Field | Description |
|---|---|
| `date` | Observation date |
| `year`, `month` | Time components |
| `ppi_value` | Producer Price Index value |
| `series_id` | BLS series identifier |
| `industry` | Industry classification |
| `product` | Semiconductor product category |

These BLS datasets provide long historical price coverage for semiconductor production.

---

## Federal Reserve Economic Data (FRED)

FRED provides **international manufacturing price indicators** that serve as proxies for semiconductor cost inflation outside the United States.

Examples include:

| Region | Description |
|---|---|
| China | Semiconductor manufacturing PPI |
| Mexico | Computer and electronics manufacturing PPI |
| Other Asian Countries (OAC) | Regional semiconductor manufacturing index |
| U.S. semiconductor import index | Proxy for European semiconductor cost dynamics |

These indices allow the model to approximate **regional semiconductor cost inflation trends across global supply chains**.



---

# Country-to-PPI Mapping

Because most countries do not publish semiconductor-specific PPIs, the model maps supplier countries to the **most appropriate available regional proxy**.

Example mapping:

| Supplier Country | PPI Source | Proxy Region |
|---|---|---|
| USA | BLS | U.S. semiconductor manufacturing |
| Canada | FRED | Canada electronics manufacturing |
| China | FRED | China semiconductor manufacturing |
| Mexico | FRED | Mexico electronics manufacturing |
| Germany | FRED | U.S. semiconductor import proxy |
| France | FRED | U.S. semiconductor import proxy |
| Japan | FRED | Asian semiconductor manufacturing basket |
| Malaysia | FRED | Asian semiconductor manufacturing basket |
| Singapore | FRED | Asian semiconductor manufacturing basket |

This reflects the reality that semiconductor cost inflation often follows **regional supply chain dynamics rather than purely national factors**.



---

# Semiconductor Product Categories Modeled

The cost model generates price series for several semiconductor component categories.

## Integrated Circuit Components

Includes semiconductor packaging and integrated circuit assembly components.

Packaging is typically **labor-intensive**, so costs vary significantly across regions.

Example supplier countries modeled:

- United States
- Japan
- Germany
- China
- Malaysia
- Singapore
- Mexico



## Microprocessors and Microcontrollers

These are **higher-value semiconductor products** used in computing and embedded systems.

Cost drivers include:

- Fabrication technology
- Yield rates
- Capital intensity of fabrication facilities

Advanced semiconductor ecosystems such as Japan, and Europe generally exhibit higher manufacturing costs.



## Transistors and Discrete Semiconductor Devices

Lower-cost semiconductor components such as:

- Transistors
- Diodes
- Other discrete semiconductor devices

These products are commonly manufactured in **high-volume Asian production hubs**.



## Power Semiconductor Devices

Power semiconductors are widely used in:

- power management systems
- industrial electronics
- automotive systems

Manufacturing is concentrated in:

- China
- Southeast Asia
- European automotive semiconductor producers.



---

# Country Baseline Prices

Each country receives a **baseline cost level** for each semiconductor product category.

These baseline values represent structural differences driven by:

| Cost Driver | Effect |
|---|---|
| Labor costs | Higher wages increase manufacturing costs |
| Manufacturing scale | Larger fabs reduce marginal costs |
| Supply chain maturity | Mature ecosystems reduce production costs |
| Technology capability | Advanced fabs require higher capital investment |

These baseline values serve as the **starting point for time-adjusted price series**.



---

# Price Time-Series Generation

For each semiconductor product category the model performs the following steps:

1. Define the set of supplier countries.
2. Create a **supplier × date grid** covering the full time range of the PPI datasets.
3. Map each supplier country to its assigned **PPI source and region**.
4. Merge the corresponding PPI time series into the supplier grid.
5. Compute the price for each country and date using the inflation scaling formula.

This produces a dataset of the form:

| Date | Country | Product | Estimated Price (per unit) |
|---|---|---|---|
| 2010-01 | Malaysia | Transistors | 0.035 |
| 2010-01 | USA | Microprocessors | 1.18 |
| 2010-01 | Germany | IC Components | 0.27 |

The resulting datasets form a **monthly panel of semiconductor component prices by supplier country**.



---

# Output Datasets

The model produces several structured datasets that serve as our product basket.

| Dataset | Description |
|---|---|
| `ic_components_2023.csv` | Integrated circuit component prices |
| `microprocessors_2015.csv` | Microprocessor price estimates |
| `transistors_2025.csv` | Discrete semiconductor device prices |
| `power_devices_2025.csv` | Power semiconductor device prices |

Each dataset contains monthly country-level price estimates.



---

# Role in the Procurement Agent

The cost model provides the **baseline pricing signal used in supplier evaluation**.

These estimates are the foundation that enable the procurement agent to analyze:

- Supplier cost competitiveness
- Price volatility
- Procurement cost tradeoffs
- Cost-risk balancing across suppliers

When combined with:

- logistics performance metrics
- geopolitical risk indicators
- lead-time variability

the agent can generate **credible supplier comparisons and procurement recommendations** for semiconductor sourcing decisions.