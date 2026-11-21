# FactoryPulse 360 — Manufacturing KPI & Business Metric Definitions

## Executive Summary
This document establishes the official enterprise definitions, mathematical formulations, units of measurement, numerators, denominators, and aggregation rules for all Key Performance Indicators (KPIs) in the FactoryPulse 360 manufacturing analytics system.

These definitions eliminate arbitrary multipliers (such as artificial 0.5 factors) and hardcoded 24-hour assumptions, implementing standard **Overall Equipment Effectiveness (OEE)** and sustainability metrics adhering to **SEMI E10 / ISO 22400** manufacturing standards.

---

## 1. Primary Manufacturing Metrics Catalog

| Metric Name | Domain | Formula / Calculation | Standard Unit | Benchmark Value (30-Day Curated) |
|:---|:---|:---|:---|:---|
| **Availability (A)** | Asset Utilization | $\frac{\text{Operating Minutes}}{\text{Planned Production Minutes}} \times 100\%$ | Percentage (`%`) | **99.42%** |
| **Performance (P)** | Production Efficiency | $\frac{\text{Ideal Production Minutes}}{\text{Operating Minutes}} \times 100\%$ | Percentage (`%`) | **19.51%** |
| **Quality (Q)** | First Pass Yield | $\frac{\text{Good Units}}{\text{Total Produced Units}} \times 100\%$ | Percentage (`%`) | **95.25%** |
| **OEE** | Overall Effectiveness | $\text{Availability} \times \text{Performance} \times \text{Quality}$ | Percentage (`%`) | **18.48%** |
| **Energy Intensity** | Sustainability | $\frac{\text{Total Electrical Energy (kWh)}}{\text{Good Units Produced}}$ | kWh / Good Unit | **0.7306 kWh/unit** |
| **Defect Rate** | Quality Control | $\frac{\text{Total Defects Count}}{\text{Total Produced Units}} \times 100\%$ | Percentage (`%`) | **4.79%** |
| **Scrap Rate** | Quality Loss | $\frac{\text{Rejected Units}}{\text{Total Produced Units}} \times 100\%$ | Percentage (`%`) | **4.75%** |
| **Production Target Variance** | Plan Adherence | $\frac{\text{Produced Units} - \text{Target Units}}{\text{Target Units}} \times 100\%$ | Percentage (`%`) | **-4.85%** |

---

## 2. Mathematical Formulations & Component Logic

### 2.1 Availability ($A$)
Availability measures the proportion of planned production time that equipment is physically operating without unscheduled stoppages.

$$\text{Scheduled Production Minutes} = \sum_{\text{machines, shifts}} \text{ScheduledMinutes (default 480 min/shift)}$$

$$\text{Planned Production Minutes} = \text{Scheduled Production Minutes} - \text{Planned Maintenance Minutes}$$

$$\text{Operating Minutes} = \text{Planned Production Minutes} - \text{Unplanned Downtime Minutes}$$

$$\text{Availability} = \frac{\text{Operating Minutes}}{\text{Planned Production Minutes}}$$

- **Numerator**: Operating Minutes ($\text{Planned Production} - \text{Unplanned Downtime}$).
- **Denominator**: Planned Production Minutes ($\text{Scheduled Minutes} - \text{Planned Maintenance Minutes}$).
- **Boundary Conditions**:
  - Clamped between $0.0\%$ and $100.0\%$.
  - If $\text{Planned Production Minutes} \le 0$, Availability returns $0.0\%$.
- **Curated 30-Day Totals**:
  - Scheduled Minutes: $691,200.00\text{ min}$
  - Planned Maintenance: $3,079.02\text{ min}$
  - Planned Production: $688,120.98\text{ min}$
  - Unplanned Downtime: $3,977.81\text{ min}$
  - Operating Minutes: $684,143.17\text{ min}$
  - **Availability = $\frac{684,143.17}{688,120.98} \times 100 = 99.42\%$**

---

### 2.2 Performance ($P$)
Performance quantifies operating speed losses, measuring how closely operating equipment ran compared to its theoretical nameplate speed.

$$\text{Ideal Production Minutes} = \sum_{p} (\text{ProducedUnits}_p \times \text{IdealCycleTimeMinutes}_p)$$

$$\text{Performance} = \frac{\text{Ideal Production Minutes}}{\text{Operating Minutes}}$$

- **Numerator**: Ideal Production Minutes (Units Produced $\times$ Product Ideal Cycle Time in minutes).
  - Note: Product Ideal Cycle Time is explicitly modeled in `DimProduct.IdealCycleTimeMinutes` (average 1.0 min).
- **Denominator**: Operating Minutes.
- **Boundary Conditions**:
  - Clamped at $0.0\%$ when Operating Minutes $\le 0$ or Produced Units $\le 0$.
- **Curated 30-Day Totals**:
  - Ideal Production Minutes: $133,478.00\text{ min}$
  - Operating Minutes: $684,143.17\text{ min}$
  - **Performance = $\frac{133,478.00}{684,143.17} \times 100 = 19.51\%$**

---

### 2.3 Quality ($Q$)
Quality measures the ratio of saleable units produced without defects to the total units processed.

$$\text{Quality} = \frac{\text{Good Units}}{\text{Total Produced Units}} = \frac{\text{Total Produced Units} - \text{Rejected Units}}{\text{Total Produced Units}}$$

- **Numerator**: Good Units (`FactProduction.GoodUnits`).
- **Denominator**: Total Produced Units (`FactProduction.ProducedUnits`).
- **Conservation Rule**: `ProducedUnits = GoodUnits + RejectedUnits`.
- **Curated 30-Day Totals**:
  - Total Produced Units: $133,478$
  - Good Units: $127,133$
  - Rejected Units: $6,345$
  - **Quality = $\frac{127,133}{133,478} \times 100 = 95.25\%$**

---

### 2.4 Overall Equipment Effectiveness (OEE)
OEE is the holistic product of Availability, Performance, and Quality, capturing all equipment utilization, rate, and scrap losses.

$$\text{OEE} = A \times P \times Q$$

Equivalently, expressing OEE directly via total ideal time produced versus total planned production time:
$$\text{OEE} = \frac{\text{Good Units} \times \text{Ideal Cycle Time}}{\text{Planned Production Minutes}} = \frac{127,133 \times 1.0\text{ min}}{688,120.98\text{ min}} = 18.48\%$$

- **Verification Check**:
  - $0.994219 \times 0.195102 \times 0.952464 = 0.184754 = \mathbf{18.48\%}$.

---

### 2.5 Energy Intensity
Energy Intensity measures the specific electrical energy footprint required to produce each first-quality saleable unit.

$$\text{Energy Intensity} = \frac{\sum \text{FactEnergy.EnergyKWh}}{\sum \text{FactProduction.GoodUnits}}$$

- **Numerator**: Total Kilowatt-Hours consumed (`FactEnergy.EnergyKWh`).
- **Denominator**: Total Good Units (`FactProduction.GoodUnits`).
- **Curated 30-Day Totals**:
  - Total Energy: $92,885.22\text{ kWh}$
  - Good Units: $127,133$
  - **Energy Intensity = $\frac{92,885.22}{127,133} = \mathbf{0.7306\text{ kWh / good unit}}$**

---

## 3. Secondary & Diagnostic Manufacturing Analytics

### 3.1 Downtime Pareto Loss Analysis
- **Definition**: Equipment stoppages categorized by root-cause reason code (`DimReason.ReasonCode`), ranked in descending order of duration, with cumulative percentage contribution.
- **Mathematical Formula**:
  $$\text{PctOfTotal}_r = \frac{\text{DowntimeMinutes}_r}{\sum_{k} \text{DowntimeMinutes}_k} \times 100\%$$
  $$\text{CumPct}_r = \frac{\sum_{i \le r} \text{DowntimeMinutes}_i}{\sum_{k} \text{DowntimeMinutes}_k} \times 100\%$$
- **Pareto Ranking Findings**:
  1. `Planned_Maintenance`: 3,079.02 min (43.63%) [Cum: 43.63%]
  2. `Mechanical_Failure`: 1,830.34 min (25.94%) [Cum: 69.57%]
  3. `Changeover`: 782.40 min (11.09%) [Cum: 80.66%]
  4. `Electrical_Failure`: 767.41 min (10.87%) [Cum: 91.53%]
  5. `Setup`: 597.66 min (8.47%) [Cum: 100.00%]

### 3.2 Product Family Quality & Yield
- **Yield Percentage**:
  $$\text{YieldPct} = \frac{\text{Total Good Units}}{\text{Total Produced Units}} \times 100\%$$
- **Product Family Defect Rankings**:
  - `Family_E`: 5.97% Rejection Rate (Scrap Spike anomaly in discrete simulation)
  - `Family_B`: 4.50% Rejection Rate
  - `Family_C`: 4.51% Rejection Rate
  - `Family_A`: 4.48% Rejection Rate
  - `Family_D`: 4.48% Rejection Rate

### 3.3 Production Line Energy Hotspot Identification
- Line 1: $0.6980\text{ kWh/unit}$
- Line 2: $0.7088\text{ kWh/unit}$
- Line 3: $0.7853\text{ kWh/unit}$ (+12.5% hotspot driven by Cell 2 Machines 321–324 with elevated motor draw)
