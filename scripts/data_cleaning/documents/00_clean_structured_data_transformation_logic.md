
# Transformation and Business Logic: 00_clean_structured_data.ipynb

This document provides a consolidated explanation of the business rules, transformation logic, and data‑quality decisions applied to all structured external datasets used in the procurement agent system. Each dataset—logistics performance, governance indicators, port efficiency, tariff schedules, and price indices—is cleaned, standardized, and reshaped into analytics‑ready tables that share a consistent schema and join keys. The goal of these transformations is to ensure that every downstream component—supplier generation, product mapping, inventory modeling, demand simulation, and cost estimation—operates on reliable, comparable, and defensible data.

The transformations documented here focus on:
 - enforcing consistent country and product identifiers,
 - selecting only the indicators relevant to procurement and logistics risk,
 - reshaping wide or multi‑year datasets into usable formats,
 - normalizing numeric values for cross‑dataset comparability, and
 - producing clean, minimal tables that integrate seamlessly into the project’s SQL and modeling layers.

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

## 5. Producer Price Index (PPI) - BLS

**Purpose**
Anchors baseline cost levels and recent cost trends for semiconductor/electronics-related inputs, used to make synthetic supplier pricing economically plausibly and time consistent.

**Key Trqansformations**

- 

LEFT OFF HERE
---
