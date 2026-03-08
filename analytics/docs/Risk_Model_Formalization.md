# Risk Model Formalization

### Procurement Decision Intelligence Agent

## 1. Overview
This document formalizes how the procurement intelligence agent evaluates supplier risk and reliability across several operational and institutional dimensions.

The goal of this framework is to transform country-level logistics, governance, and trade profiles into supplier-level risk attributes used in downstream analytics, such as the `scoring.py`.

The notebook `01_suppliers.ipynb` produce an array of supplier-level attributes used in:

- Supplier scoring (`scoring.py`)
- Procurement optimization
- Risk-aware procurement recommendations (to be enhanced)
- Inventory planning (planned)
- Supplier comparisons (to be enhanced)
- Disruption scenario simulations (planned)

Because real supplier-level operational data is not publicly availble, the system generates synthetic suppliers whose characteristics inherit statistical properties from the country in which they operate in. This ensures that the synthetic suppliers represent realistic risk-profiles that are derived from real-world macro-supply chain signals.

This document explicitly details the formulas and logic applied in the `01_suppliers.ipynb` to ultimately evaluate the following supplier dimensions:

1. Delivery Risk (Lead Time Mean & Lead Time Variance)
2. Logistics Reliability
3. Compliance Eligibility
4. Disruption Probability

These metrics ultimately feed the agent's supplier ranking engin, enabling procurement managers tocompare suppliers based on cost, reliability, and geopolitical risk.

## 2. Data Sources
We've integrated multiple publicly available datasets to derive our needed supplier risk dimensions.

| Data Source | Provider | Purpose |
|--------------|-----------|---------|
| Logistics Performance Index (LPI) | World Bank | Measures logistics quality, infrastructure strength, customs efficiency, shipment tracking ability, and the reliability with which shipments reach their destination on time. |
| World Governance Indicators (WGI) | World Bank | Captures institutional and governance quality across countries, including corruption control, political stability, rule of law, and regulatory effectiveness. These indicators act as proxies for geopolitical and regulatory risk affecting supplier operations. |
| Port Call Statistics | UN Trade & Development (UNCTAD) | Provides metrics on vessel turnaround time and port congestion. Used as a proxy for export-side logistics friction and delays occurring at origin ports before shipments depart internationally. |

## 3. Synthetic Supplier Generation
Because supplier-level operational metrics were not available publicly, we generate synthetic suppliers by country.

Countries are categorized into relevance tiers based on semiconductor manufacturing and export presence:

### Supplier Country Tiers
**Tier 1 (Major Semiconductor Producers)**
`['China', 'Japan', 'Singapore', 'Hong Kong', 'Malaysia, 'Thailand', 'Germany']`

**Tier 2 (Moderate Supply)**
`['Mexico', 'India', 'Canada', 'France', 'England', 'Australia', 'Indonesia', 'Netherlands', 'United States']`

**Tier 3 (Low Relevance)**
`['United Arab Emirates', 'Belgium', 'Brazil', 'Finand']`

Supplier counts are then randomly sampled per country:

| Tier | Synthetic Suppliers Generated |
|------|----------------|
| Tier 1 | 7-10 |
| Tier 2 | 2-4 |
| Tier 3 | 1-2 |

Each supplier then inherits its country's baseline logistics and governance signals.

## 4. Supplier Risk Dimensions

### 4.1 Delivery Risk
Delivery risk captures uncertainty in supplier lead times caused by logistics performance, port congestion, and transportation times.

Directly, it measures expected lead time mean and variability (variance and standard deviation).

**Lead Time Components**
Expected lead time is modeled as the sum of multiple operational components:

```python

        lead_time_mean = (
            manufacturing_cycle +
            origin_port_dwell +
            transit_time +
            us_port_dwell +
            border_delay +
            inland_distribution +
            inspection_delay
        )
```

#### 4.1.1 Data Inputs
| Column | Source | Description |
|------|------|-------------|
| `median_days_in_port` | Global port performance dataset | Vessel turnaround time proxy: median number of days cargo ships (vessels) remain at the export port before departure, after arrival. |
| `timeliness` | World Bank Logistics Performance Index (LPI) | Measures the reliability with which shipments reach their destination within the expected or scheduled delivery time. This indicator reflects overall logistics system reliability, including coordination between transport modes and adherence to delivery schedules. |
| `logistics_competence` | World Bank Logistics Performance Index (LPI) | Evaluates the quality and competence of logistics service providers in a country, including freight forwarders, customs brokers, and transport operators. Higher scores indicate stronger logistics service capabilities and more efficient supply chain coordination. |
| `infrastructure` | World Bank Logistics Performance Index (LPI) | Assesses the quality of a country’s trade and transport infrastructure, including ports, roads, railways, and information systems. Strong infrastructure typically reduces shipment delays, improves transit reliability, and lowers overall logistics risk. |
| `customs` | World Bank Logistics Performance Index (LPI) | Measures the efficiency, transparency, and speed of customs clearance processes for international shipments. This indicator reflects the quality of border administration, including documentation requirements, inspection procedures, regulatory enforcement, and coordination between border agencies. Lower customs performance typically results in longer inspection times, administrative delays, and increased variability in shipment processing, which can materially increase export and import lead times. |

#### 4.1.2 Origin Port Dwell
This is the full export-side port dwell time.

Origin port dwell time (in days) includes:
- vessel turnaround time (vessel departure time - vessel arrival time)
- terminal dwell (time container loaded onto vessel - time container enters port)

```python
        if country_code == 'USA':
          origin_port_dwell = 0.0
        elif country_code in ['CAN', 'MEX']:
          origin_port_dwell = 0.0 # land border, not ocean export
        else:
          # vessel turnaround time from the observed US Port Calls data when available
          vessel_turnaround = VESSEL_TURNAROUND_BASE.get(country_code, None)
          if vessel_turnaround is None:
            vessel_turnaround = combined_baselines['median_days_in_port'].median()
          
          # LPI components for terminal/port-side friction of foreign suppliers
          customs = country_baseline.get('customs', 3.0)
          infrastructure = country_baseline.get('infrastructure', 3.0)
          logistics_competence = country_baseline.get('logistics_competence', 3.0)
          timeliness = country_baseline.get('timeliness', 3.0)

          # Weighted LPI quality score (1-5, higher = better)
          export_logistics_quality = (
              0.35 * customs + 0.25 * infrastructure + 0.20 * logistics_competence + 0.20 * timeliness)
          
          # Convert quality to terminal dwell
          # Better logistics -> lower dwell
          # Roughly maps strong countries to ~1 day and weaker ones to ~3+ days
          terminal_dwell = max(0.75, 4.5 - export_logistics_quality)
          # terminal dwell = Time container loaded onto ship - time container enters terminal

          # Full export-side dwell = vessel turnaround time + terminal dwell
          origin_port_dwell = (vessel_turnaround + terminal_dwell) * random.uniform(0.9, 1.1)
```

#### 4.1.3 Transit Time
Transit time represents rough approximation of international transportation times (in days) from supplier country to the U.S.

Baseline shipping times are defined by geographic region:

```python
# Synthetic country-level baseline transit time to first U.S. entry point
# For ocean suppliers: foreign port -> U.S. port
# For CAN/MEX: supplier region -> U.S. land border
TRANSIT_TIME_BASE = {
    "ARE": 35,
    "AUS": 25,
    "BEL": 14,
    "BRA": 16,
    "CHN": 20,
    "DEU": 16,
    "FIN": 20,
    "FRA": 15,
    "GBR": 14,
    "HKG": 20,
    "IDN": 25,
    "IND": 35,
    "JPN": 14,
    "MYS": 24,
    "NLD": 14,
    "SGP": 26,
    "THA": 24
}
```

Special case handling ultiely used to establish transit times per country and introduce random variability.
```python
        if country_code == "USA":
          transit_time = 0.0
        elif country_code == "CAN":
          transit_time = random.uniform(1.5, 3.0)
        elif country_code == "MEX":
          transit_time = random.uniform(2.5, 4.5)
        else:
          transit_base = TRANSIT_TIME_BASE.get(country_code, 22)
          transit_time = transit_base * random.uniform(0.9, 1.1)
```

#### 4.1.4 U.S Port Dwell
Time (in days) cargo sits in U.S ports before in-route distribution.

US, Mexican, and Canadian suppliers face no port dwell.

Asian imports experience higher dwell times due to heavy West Coast port utilization and congestion.

```python
ASIA_COUNTRIES = {"CHN", "HKG", "IDN", "JPN", "MYS", "THA", "SGP"}
```

```python
        if country_code in ["CAN", "MEX", "USA"]:
          us_port_dwell = 0.0
        else:
          if country_code in ASIA_COUNTRIES:
            us_port_dwell = random.uniform(3.25, 4.5)
          else:
            us_port_dwell = random.uniform(2.25, 3.5) # European countries
```

#### 4.1.5 Border Crossing Delay
Applicable only to land-border shipments.

Customs and querie crossing time at U.S. border.

```python
        if country_code == "CAN":
          border_delay = random.uniform(0.05, 0.25)
        elif country_code == "MEX":
          border_delay = random.uniform(0.25, 0.9)
        else:
          border_delay = 0.0
```

#### 4.1.6 Inland Distribution
Represents transport times from U.S entry point to buyer, via freight truck or train.

Our assumption: Buyer located in Washington DC

Europe, Brazil, and the Middle East regions more likely to land in East Coast entry ports; therefore, shorter inland routing.

Asian countries more likely West Coast entrants; therefore, longer inland transportation routes.

U.S suppliers assumed to be Texas-based (promiment domestic fab facilities)

```python
        if country_code == "USA":
          inland_distribution = random.uniform(2.75, 4.75) # Texas -> DC
        elif country_code == "CAN":
          inland_distribution = random.uniform(1.0, 2.5) 
        elif country_code == "MEX":
          inland_distribution = random.uniform(2.0, 4.0) # captures nearby and farther regions
        elif country_code in ASIA_COUNTRIES:
          inland_distribution = random.uniform(4.0, 7.0) # likely West Coast entry -> DC
        else:
          inland_distribution = random.uniform(1.5, 4.0) # likely East/Gulf Cost entry -> DC
```

#### 4.1.7 Customs Inspection Delay
Customs inpection delays depend on the LPI customs score.

```python
        if country_code == "USA":
          inspection_delay = 0.0
        else:
          customs = country_baseline.get('customs', 3.0)
          # converts 1-5 customs score into extra delay
          # Good customs (4-5): very small delay
          # Weak customs (1-2): larger expected delay
          inspection_risk = max(0.0, # lower score better
                                min(1.0, (5.0 - customs) / 4.0))
          
          if country_code == "CAN":
            inspection_delay = inspection_risk * random.uniform(0.05, 0.35)
          elif country_code == "MEX":
            inspection_delay = inspection_risk * random.uniform(0.3, 1.0)
          else:
            inspection_delay = inspection_risk * random.uniform(0.2, 1.2)
```

#### 4.1.8 Manufacturing Cycle
Semiconductor manufacturing average cycle length:

`AVG_SEMICON_CYCLE_DAYS = 70`

Tiered adjustments based on estimated semiconductor manufacturing efficiency:

```python
        if country_code == "USA" or country_code in tier_1:
            manufacturing_cycle = random.uniform(0.85, 0.95) * AVG_SEMICON_CYCLE_DAYS

        elif country_code in tier_2:
            manufacturing_cycle = random.uniform(0.95, 1.1) * AVG_SEMICON_CYCLE_DAYS

        else:  # tier_3
            manufacturing_cycle = random.uniform(1.05, 1.25) * AVG_SEMICON_CYCLE_DAYS
```

#### 4.1.9 Final Lead Time Mean Computation

```python

        lead_time_mean = (
            manufacturing_cycle +
            origin_port_dwell +
            transit_time +
            us_port_dwell +
            border_delay +
            inland_distribution +
            inspection_delay
        )
```

Validation constraint:
```python
        # Prevent unrealistically low values as validation safety measure
        lead_time_mean = max(28, lead_time_mean)
```

#### 4.1.10 Lead Time Variability (Variance and Standard Deviation)
In addition to estimate the average supplier lead time, we also estimated how much that lead time can vary.

To capture this uncertainty, we decomposed expected supplier lead time into its operational components to estimate the variability associated with each component individually. 

The components included:
1. Manufacturing cycle variability
2. Origin port dwell variability
3. International transit variability
4. U.S. port dwell variability
5. Border crossing variability
6. Inland distribution variability
7. Customs inspection variability

Each component is then assigned a coefficienct of variation (cv), from a uniform distribution tiered to country efficiency, that represents the expected relative volatility of the component.

The coefficient of variation statistic expresses the standard deviation as a proportion of the mean value of that component. A lower value is ideal (more certainty).

The expected (theoretical mean) value for each component (original value) is then multipled by its coefficient of variation to estimate a rough standard deviation for that component.

##### Lead Time Variance
The total lead time variance for each supplier is calculated as the sum of the squared standard deviations of each component:

```python

        # Combine component variances assuming approximate independence
        lead_time_variance = (
            manufacturing_std ** 2 +
            origin_port_std ** 2 +
            transit_std ** 2 +
            us_port_std ** 2 +
            border_std ** 2 +
            inland_std ** 2 +
            inspection_std ** 2
        )
```

We then use that value to derive a rough approximation of lead time standard deviation per supplier:

```python
lead_time_stddev = lead_time_variance ** 0.5
```

### 4.2 Logistics Reliability
Logistics reliability measures how consistently shipments arrive on time.

#### Data Inputs
All in (0-5) range (higher score better).

| Column | Source | Description |
|------|------|-------------|
| `timeliness` | World Bank Logistics Performance Index (LPI) | Measures the reliability with which shipments reach their destination within the expected or scheduled delivery time. This indicator captures overall logistics reliability and reflects how frequently shipments experience delays due to transportation coordination or operational inefficiencies. |
| `logistics_competence` | World Bank Logistics Performance Index (LPI) | Evaluates the quality and competence of logistics service providers, including freight forwarders, customs brokers, and transport operators. Higher scores indicate stronger logistics capabilities and more efficient coordination of international supply chains. |
| `infrastructure` | World Bank Logistics Performance Index (LPI) | Assesses the quality of trade and transport infrastructure such as ports, roads, railways, and logistics information systems. Higher infrastructure quality generally reduces transportation delays and improves the predictability of shipment flows. |
| `tracking` | World Bank Logistics Performance Index (LPI) | Measures the ability to track and trace shipments throughout the supply chain. Strong tracking capabilities improve shipment visibility and allow logistics operators to proactively manage disruptions or delays. |
| `customs` | World Bank Logistics Performance Index (LPI) | Evaluates the efficiency of customs clearance processes, including documentation requirements, inspection procedures, and administrative processing times. Efficient customs operations reduce border delays and improve overall trade logistics performance. |

#### Reliability Model
Weighted logistics performance score:

```python
weighted_lpi =
0.30 * timeliness +
0.25 * logistics_competence +
0.20 * infrastructure +
0.15 * tracking +
0.10 * customs
```

We then convert the weighted logistic performance score (on 1-5 scale) to a normalized (0-1) logistics reliability score and add some noise for realistic variation amongst suppliers. Lastly, we clamp the reliability metric to ensure its between 10%-99%:

```python
        # Convert 1–5 LPI scale → 0–1 reliability
        base_reliability = weighted_lpi / 5.0

        # Add proportional noise (±5%)
        noise = random.uniform(-0.05, 0.05) * base_reliability
        logistics_reliability = base_reliability + noise

        # Clamp to 10%–99%
        logistics_reliability = max(0.10, min(0.99, logistics_reliability))
```

### 4.3 Disruption Probability
Disruption probability reflects the stability and overall institutional reliability of the supplier's country.

It is a weighted combination of governance risk and operational risk.

**Formula**
```python
disruption_probability =
0.6 * governance_risk
+ 0.4 * operational_risk
```

Noise applied:

```python
noise = random.uniform(-0.1, 0.1)
```

Clamped final bounds:

`0.01 <= disruption_probabiity <= 0.99`


#### 4.3.1 Governance Risk
Governance risk reflect the stability and overall institutional reliability of the supplier's country.

##### Data Inputs (WGI)

| Column | Source | Description |
|------|------|-------------|
| `political_stability_and_absence_of_violence` | World Bank Worldwide Governance Indicators (WGI) | Measures the likelihood that a government will be destabilized or overthrown through unconstitutional or violent means, including political violence, terrorism, or armed conflict. Lower values indicate higher geopolitical instability, which increases the probability of supply chain disruptions or operational uncertainty. |
| `control_of_corruption` | World Bank Worldwide Governance Indicators (WGI) | Captures the extent to which public power is exercised for private gain, including both petty and grand forms of corruption. Lower scores indicate higher corruption risk, which can increase regulatory uncertainty, compliance challenges, and operational friction for firms operating within that country. |

##### Normalization of WGI Scores

WGI values range (-2.5, 2.5)

Normalized:
`normalized_value = (wgi score + 2.5) / 5.0`

Governance risk (lower score is better):

```python
        wgi_risk = 1 - ((normalized_political_stability + normalized_control_of_corruption) / 2)
```

#### 4.3.1 Operational Risk
Operational disruption risk is derived from logistics infrastructure and logistics capability.

##### Data Inputs (LPI)
All in (0-5) range (higher score better).

| Column | Source | Description |
|------|------|-------------|
| `logistics_competence` | World Bank Logistics Performance Index (LPI) | Evaluates the quality and competence of logistics service providers, including freight forwarders, customs brokers, and transport operators. Higher scores indicate stronger logistics capabilities and more efficient coordination of international supply chains. |
| `infrastructure` | World Bank Logistics Performance Index (LPI) | Assesses the quality of trade and transport infrastructure such as ports, roads, railways, and logistics information systems. Higher infrastructure quality generally reduces transportation delays and improves the predictability of shipment flows. |

Normalized operational risk:

```python
infra_risk = 1 - (infrastructure / 5)
logistics_risk = 1 - (logistics_competence / 5)

operational_risk =
(infra_risk + logistics_risk) / 2
```

### 4.4 Compliance Eligibility
How likely a supplier is to meet corporate, regulatory, ethical, and trade-compliance requirements.

#### Data Inputs

| Column | Source | Description |
|------|------|-------------|
| `political_stability_and_absence_of_violence` | World Bank Worldwide Governance Indicators (WGI) | Measures the likelihood that a government will be destabilized or overthrown through unconstitutional or violent means, including political violence, terrorism, or armed conflict. Lower values indicate higher geopolitical instability, which increases the probability of supply chain disruptions or operational uncertainty. |
| `control_of_corruption` | World Bank Worldwide Governance Indicators (WGI) | Captures the extent to which public power is exercised for private gain, including both petty and grand forms of corruption. Lower scores indicate higher corruption risk, which can increase regulatory uncertainty, compliance challenges, and operational friction for firms operating within that country. |
| `rule_of_law` | World Bank Worldwide Governance Indicators (WGI) | Measures the extent to which individuals and firms have confidence in and abide by the rules of society, including the quality of contract enforcement, property rights, policing, and the judicial system. Higher values indicate stronger legal institutions and greater predictability in commercial and regulatory environments, which reduces contractual and compliance risk for international suppliers. |
| `regulatory_quality` | World Bank Worldwide Governance Indicators (WGI) | Captures the ability of a government to formulate and implement sound policies and regulations that support private sector development. Higher scores indicate more stable and transparent regulatory environments, reducing the likelihood of abrupt policy changes, bureaucratic obstacles, or regulatory barriers that could disrupt international procurement relationships. |
| `customs` | World Bank Logistics Performance Index (LPI) | Evaluates the efficiency of customs clearance processes, including documentation requirements, inspection procedures, and administrative processing times. Efficient customs operations reduce border delays and improve overall trade logistics performance. |

#### Compliance Model

```python
        # --- Compliance Eligibility (WGI + LPI Customs blended) ---

        cc_score   = country_baseline.get('control_of_corruption', 0)
        rq_score   = country_baseline.get('regulatory_quality', 0)
        rol_score  = country_baseline.get('rule_of_law', 0)
        psat_score = country_baseline.get('political_stability_and_absence_of_violence/terrorism', 0)

        customs = country_baseline.get('customs', 3.0)  # LPI Customs (1–5)

        # Normalize WGI (-2.5 → +2.5 mapped to 0–1)
        norm_cc   = (cc_score + 2.5) / 5.0
        norm_rq   = (rq_score + 2.5) / 5.0
        norm_rol  = (rol_score + 2.5) / 5.0
        norm_psav = (psat_score + 2.5) / 5.0

        # Normalize LPI Customs (1–5 → 0–1)
        norm_customs = customs / 5.0

        # Weighted compliance model
        compliance_base = (
          0.40 * norm_cc +
          0.25 * norm_rq +
          0.20 * norm_rol +
          0.05 * norm_psav +
          0.10 * norm_customs
            )

        # Add proportional noise (±5–10%)
        noise = random.uniform(-0.10, 0.10) * compliance_base
        compliance_eligibility = compliance_base + noise

        # Clamp to 5%–95%
        compliance_eligibility = max(0.05, min(0.95, compliance_eligibility))
```
## 5. Output Supplier Profile
The model produces the following supplier-level attributes:

### Synthetic Supplier Output Schema

| Column | Description |
|---|---|
| `supplier_id` | Unique synthetic supplier identifier generated during supplier simulation (format: `SUP_{country_code}_{id}`). This key uniquely identifies each simulated supplier entity and links suppliers to downstream supplier–product relationships used by the procurement agent. |
| `country_code` | ISO-3166-3 country code representing the supplier’s country of operation. This determines the baseline logistics, governance, and geopolitical risk characteristics applied during supplier generation. |
| `lead_time_mean` | Expected supplier lead time in **days**, representing the average time required for semiconductor manufacturing, export processing, and international logistics before goods reach the buyer. The value is derived by scaling country logistics conditions (export port dwell time and logistics reliability) relative to the baseline semiconductor manufacturing cycle. |
| `lead_time_variance` | Variance of the supplier’s lead time distribution (in **days²**). This value represents the statistical spread of delivery times caused by operational uncertainty such as production delays, customs processing variability, and shipping disruptions. |
| `lead_time_stddev` | Standard deviation of supplier lead time (in **days**), calculated as the square root of the lead time variance. This provides a more interpretable measure of delivery uncertainty and is commonly used when modeling stochastic lead-time distributions in supply chain simulations. |
| `disruption_probability` | Estimated probability that a supplier experiences a production, logistics, or geopolitical disruption affecting delivery reliability. This probability is derived from country-level governance stability indicators and logistics performance metrics. |
| `compliance_eligibility` | Probability that a supplier meets governance, regulatory, and legal standards required for international procurement. This metric is influenced by governance indicators such as control of corruption, regulatory quality, and rule of law. |
| `logistics_reliability` | Probability that shipments from the supplier arrive within expected delivery windows. This metric reflects country-level logistics performance derived from the World Bank Logistics Performance Index (LPI), particularly shipment timeliness and logistics competence indicators. |


## 6. Role in Procurement Agent
The risk model feeds directly into the supplier scoring engine, enabling the agent to:
- rank suppliers
- simulate disruptions
- compute risk-adjusted procurement plans
- generate supplier comparison

This allows procurement managers to evaluate trade-offs between:

- Cost
- Reliability
- Lead-time risk
- Governance risk
- Compliance exposure

All in a transparent and interpretable framework.
