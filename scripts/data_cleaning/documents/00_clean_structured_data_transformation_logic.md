
# Transformation and Business Logic: 00_clean_structured_data.ipynb

This document provides a consolidated explanation of the business use, transformation logic, and data‑quality decisions applied to all structured external datasets used in the `scripts/00_clean_structured_data.ipynb`. Each dataset - logistics performance, governance indicators, port efficiency, tariff schedules, and price indices - is cleaned, standardized, and reshaped into analytics‑ready tables that share a consistent schema and join keys. The goal of these transformations is to ensure that every downstream component—supplier generation, product mapping, inventory modeling, demand simulation, and cost estimation—operates on reliable, comparable, and defensible data.

The transformations documented here focus on:
 - enforcing consistent country and product identifiers,
 - selecting only the indicators relevant to procurement and logistics risk,
 - reshaping wide or multi‑year datasets into usable formats,
 - normalizing numeric values for cross‑dataset comparability, and
 - producing clean, minimal tables that integrate seamlessly into the project’s SQL, modeling layers, and composite data engineering sections.

This document serves as the authoritative reference for how raw external data is converted into the structured foundation of the procurement agent’s analytical environment.

## 1. International LPI Scorecore (Select Countries)

**Purpose**
Provides country-level logistics performance indicators (LPI) used to estimate logistics reliability, customs efficiency, and infrastructure quality for supplier risk scoring.

**Key Transformations**

- **Country normalization:** Converted country names to ISO-3 codes to ensure consisten joins across datasets. 
*Reason:* Supplier, tariff, and governance datasets all rey on ISO-3.

- **Column reduction:** Removed rank-based fields (e.g., *LPI Rank*, *Customs Rank*) and retained only numeric score indicators.
*Reason:* Scores are continuous and more suitable for modeling; ranks are relative.

- **Column renaming:** Standardizes names to lowercase, underscore-separated fields.
*Reason:* Ensures consistency across the analytics layer and SQL schema.

- **Reordering columns:** Ensured `country_code` appears first for consitent dimensional modeling.
*Reason:* Supports-star schema design and simplifies joins.

**Output**
`cleaned_data/International_LPI_Scorecard_Select_Countries_v2.csv`
A clean, 8-column dataset containing insightful LPI scores for 20 countries (for most recent year - 2023); backbone of 'supplier universe'.

## 2. World Governance Indicators (WGI)

**Purpose**
Provides governance-quality metrics used to estimate institutional risk, regulatory stability, and political risk for supplier countries.

**Key Transformations**

- **Filtering to "Estimate" series only:** The raw dataset included multiple variants for each dimension (e.g., percentile ranks, lower/upper bounds, standard errors). Only `.EST` series were retained, such as:
    - "Control of Corruption: Estimate"
    - "Government Effectiveness: Estimate"
*Reason:* Estimate values are the primary governance indicators used in risk modeling.

- **Wide-to-long transformation:** Year columns like "1996 [YR1996]", "2000 [YR2000]", ..., "2023 [YR2023]" are melted into a single `year` column.
*Reason:* Enables time-series filtering and aligns with SQL long-format design.

- **Year extraction and numeric conversion:** Extracted just the year numnber from the year_col and converted to integer.
*Reason:* Ensures clean temporal filtering and numeric modeling.

- **Series name normalization:** Verbose names are converted to snake-case (e.g., `control_of_corruption`, `regulatory_quality`)
*Reason:* Standardizes naming across governance metrics.

- **Filtering to 2023 only:** After melting, only the most recent year is retained.
*Reason:* Aligns with LPI and port-call datasets for a unified risk year (what matters to procurement departments)

- **Filtering to project countries:** Only countries present in the ISO-3 mapping are kept.
*Reason:* Ensures governance data aligns with supplier universe. In other worlds, countries that have available public logistic data.

- **Pivoting to one row per country:** The long format is pivoted so each country has one row with all governance indicators as columns.
*Reason:* Supports direct joins with LPI and port-call tables.

**Output**
`cleaned_data/WGI_Select_Countries_2023.csv`
A 20-row dataset containing six governance indicators for each country in 2023.

## 3. UNCTAD Port Calls (Container Ships Only)

**Purpose**
Provides median port dwell time for container ships, used as a proxy for port efficiency and logistics delay risk.

**Key Transformations**

- **Filtering to 2023:** Only the most recent year is retained.
*Reason:* Aligns with the other datasets and reflects current port performance (or as close to current as possible).

- **Fitering to project countries:** The raw dataset includes global entries (e.g., "World"). Only countries in the ISO-3 mapping are kept.
*Reason:** Ensures comparability across all risk dimensions. Disregards port information for countriers not included in 'supplier universe'.

- **Filtering to "Container Ships":** The raw file includes multiple vessel types (e.g., "Liquid bulk carriers", "Passenger ships"). Only "Container ships" are retained.
*Reason:* Containerized freight is the relevant mode of transportation for semiconductor and electronics supply chains.

- **Column renaming and reduction:** Only `country_code`, `year`, and `median_days_in_port` are kept.
*Reason:* Simplifies the dataset to the single KPI needed for logistics modeling.

**Output**
`cleaned_data/US_PortCalls_Time_for_ContainerShips_2023_Select_Countries.csv`
A 9-country dataset containing median container-ship dwell time for 2023.

## 4. Tariff Database (HTS-8, 2025)

**Purpose**
Provides tariff rates for U.S. imports, used to estimate landed cost, trade compliance exposure, and country-specific tariff risk for electronic components.

**Key Transformations**

- **HTS code normalization:** The raw `hts8` column is converted to string.
*Reason:* Numeric types strip leading zeros and break HTS code integrity.

- **Filtering to electronics-related chapters:** Only HTS codes beginning with 84. 85, or 90 are retained.
*Reason:* These chapters cover machinery, electrical equipment, and precision instruments - core to semiconductor procurement.

- **Retention of tariff-relevant fields:** The dataset cotnains 122 columns; downstream steps retain only tariff-specific fields (e.g., MFN rates)
*Reason:** Reduces dataset size and focuses on actionable tariff metrics.

**Output**
`cleaned_data/tariff_database_2025_only_semiconductor_components_v2.csv`
A filtered dataset containing electronics-related HTS codes and their tariff attrbutes.

## 5. Producer Price Index (PPI) - BLS (Aggregated Explanation)

**Purpose**
Provides a trusted, government-maintained measure of how the underlying production costs of these componnents (*Integrated Circuit Components*, *Transistors*, and other *related electronics categories*) have changed over time in the United States.

 - **What PPI measures:** The Producer Price Index tracks how much domestic U.S. producers receive for their goods over time. For electronics categories (e.g., integrated circuits, transistors, related semiconductor devices), the PPI reflects:

    - changes in input costs (materials, labor, energy)
    - changes in manufacturing efficiency
    - supply-demand pressures
    - technology-driven cost shifts
    - macroeconomic conditions affecting the electronics sector.

It is a clean, quantitative signal of cost movement inside the domestic semiconductor manufacturing ecosystem.

- **What the PPI values represent for each component across months:**

Each monthly PPI value is an index, not a dollar price.

 - A value of 100 is the baseline (the index's reference period).
 - A value of 110 means producer prices are 10% higher than the baseline.
 - A value of 95 means prices are 5% lower than the baseline.

 Allows us to:
 - Track month-to-month cost inflation or deflation for IC components.
 - Compare relative cost pressures across different component categories.
 - Anchor synthetic supplier pricing to real economic behavior, not arbitrary number.

 - **Why Useful:**

 1. Provides realistic baseline for synthetic supplier pricing that are tied to a macro-economic cost curve.
 2. Allows us to simulate:
  - Supply shocks
  - inflationary periods
  - cost declines from technological improvements

 3. Country-adjusted cost modeling when combined with FRED import indices
 - BLS PPI = domestic U.S. production cost trend
 - FRED import price index = cost trend for imports from China, Mexico, etc.

 ## 6. Producer Price Index (FRED) Mexico & Canada Computer and Electronic Manufacturing

 **Purpose and Business Value**
 Mexico and Canda do not publish semiconductor-specific PPIs, but both countries are major manufacturing and assembly hubs for electronics, PCB assemblies, and intermediate components used in semiconductor-adjacent suppy chains.

 The FRED Producer Price  Index for "Computer and Electronic Product Manufacturing" serves as a practical proxy for semiconductor-related cost trends from these countries.

 This index captures how the landed cost of importing electronics from Mexico and Canda into the U.S. changes over time, reflecting shifts in labor costs, energy prices, supply chain constraints, exchange rates, and manufacturing competitiveness. For procurement analytics, this provides a country-specific cost signal that differentiates Mexico and Canada from China, the U.S., and other Asian suppliers.

 **What the Index Values Represent**
 Each monthly index value reflects the relative change in import prices for electronics from that country compared to a baseline period.

 This provides a time-based cost curve for electronics manufacturing in each country, even without semiconductor-specific data.

 **Why This Data is Useful**

- Provides country-level cost differentation for Mexico and Canada when semiconductor-specific PPIs are unavailable.

- Anchors synthetic supplier pricing in real economic behavior, not arbitrary assumptions.

- Captures regional cost pressures that influence sourcing decisions.

- Ensure model treats Mexico and Canada as distinct economic environments, not generic placeholders.

## 7. Producer Price Index (FRED) China & Other Asian Countries - Semiconductor-specific

**Purpose and Business Value**
China publishes PPIs specifically for semiconductors, integrated circuits, and electronic components. These indices reflect the production-side cost structure of the global semiconductor supply chain.

For Asian countries in supplier universe that do not publish semiconductor or electronic PPIs (e.g., Malaysa, Thailand, Indonesioa), the "Other Asian Countries - Semiconductor PPI" serves as a regional representative benchmark to approximate cost movement.

**What the Index Vales Represent**
Each monthly value reflects how semiconductor manufacturing costs in Asia are changing, driven by:
- wafer pricing
- foundry capacity constraints
- energy and materials cost
- energy and materials cost
- technology node transitions
- geopolitical disruptions

Because Asia dominates global semiconductor fabrication, these PPIs are high-signal indicators of real cost pressure.

**Why Data is Useful**
- Provides direct semiconductor-specific cost trends for China and other Asian producers.

- Supplies a regional proxy for ocuntries lacking their own semiconductor PPIs, ensuring consistent modeling across the supplier universe.

- Allows synthetic suppliers in Asia to reflect realistic, region-specific cost dynamics.

## 8. Producer Price Index (FRED) US Semiconductor-specific

**Purpose and Business Value**
The U.S. FRED Semiconductor PPI tracks the domestic production cost of semiconductor devices manufactured in the United States.

Where the BLS PPI covers multipled electronics-related categories, the FRED Semiconductor PPI is narrowly focused on semiconductor manufacturing itself. It reflects U.S.-specific cost drivers such as:
 - advanced node fabrication costs
 - domestic labor and energy prices
 - CHIPS ACT-related investment cycles
 - U.S. supply chain constraints

**What the Index Values Represent**

Each monthly value shows how U.S. semiconductor production costs have changed relative to a baseline.
 - Rising values indicate increasing domestic fabrication costs.
 - Falling values indicate efficiency gains or easing supply constraints.

**How Differs From BLS PPI**
- **BLS PPI:** broader electronics categories (IC components, transistors, electronic assemblies).

- **FRED Semiconductor PPI:** narrowly focused on semiconductor device manufacturing.

- **Business Implication:** BLS PPI acnhor general electronics cost trends; FRED Semiconductor PPI anchors true semiconductor fabrication cost trends.



**Key Transformations Across All PPI Related Sources**

- **Ensured complete, interpretable cost signals** - Addressed missing monthly PPI values using a tiered interpolation approach to preserve economic realism. Short gaps (up to 4 consecutive months) were filled using linear interpolation to maintain smooth month-to-month continuity. Larger gaps were filled using spline interpolation to better reflect the natural curvature of economic cost treds. Only leading or trailing missing records - where no surrounding data exists (e.g., the first six months or the last fifteen months) - were removed entirely, since these cannot be reliably constructred.

**PPI Table Output**
After cleaning, concatenated each file to create one master table to communicate price pressure and volatility metrics used in procurement risk/value scoring.
`combined_ppi_data.csv`

## 9. World Bank Commodity Prices - Monthly (1960 - 2025)

**Purpose and Business Value**

The World Bank's Monthly Commodity Price dataset provides globally recognized benchmark prices for key industrial inputs - energy, metals, and raw materials - that directly influence the cost structure of semiconductor and electronics manufacturing. Even though these commodities are not semiconductor components themselves, they represent the upstream cost drivers that shape fabrication, packaging, assembly, and logistics economics.

For a procurement agent, this dataset serves as a macro-economic cost environment layer, enabling the system to understand how global commodity markets affect supplier pricing, risk exposure, and negotiation leverage.

**Why this dataset is valuable for semiconductor procurement**

 - **Energy prices (crude oil, natural gas):** influence wafer fabrication, chemical processing, and global freight costs.

 - **Industrial metals (copper, aluminum):** are core materials in PCBs, interconnects, wiring, and packaging.

 - **Petrochemical Derivatives:** affect plastics, resin, and encapsulation materials used in IC packaging.

 - **Global commodity volatility:** is a major driver of supplier cost changes, especially in Asia-Pacific manufacturing hubs.

 Because these commodities are globally traded and priced, they provide a neutral, internationally comparable signal of cost pressure that applies across all supplier countries.

 **What the Commodity Prices Represent**

 Each monthly value represents the spot or benchmark price of a commodity in nominal USD. These prices reflect real market conditions driven by:

  - supply/demand imablances
  - geopolitical disruptions
  - energy shocks
  - mining output changes
  - shipping and logistics constraints

These values act as macro-level cost indicators that help explain why supplier prices rise or fall over time - even when component-specific PPIs remain stable.

**Key Transformations**

- **Filtered to semiconductor-revelvant only commodities:** Avoids noise from unrelated commodities like agriculture.

- **Ensured complete and usable price signals:** Removed or interpolated missing values ONLY when economically defensible, ensuring that each retained commodity series provides a continuous, interpretable monthly cost trend.

**Output**
`monthly_world_bank_commodity_prices_1960_2025_v2.csv`
---
 