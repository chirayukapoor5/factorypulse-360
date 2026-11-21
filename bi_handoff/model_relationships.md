# FactoryPulse 360 — Dimensional Model & Entity Relationships Specification

## Executive Summary
This document defines the relational star schema and entity relationships for the FactoryPulse 360 discrete manufacturing analytics data model. Designed for downstream implementation in **Microsoft Power BI** and **Microsoft Excel Power Pivot**, this architecture eliminates Cartesian products, avoids bi-directional filter ambiguities, and supports accurate multi-fact aggregation across production lines, cells, and machines.

---

## Semantic Model Architecture: Pure Star Schema
The semantic model is architected around 6 dimension entities and 5 core fact tables, plus an isolated data quality exception register.

```
       +-------------------+         +-------------------+
       |     DimDate       |         |     DimShift      |
       |-------------------|         |-------------------|
       | DateKey (PK)      |         | ShiftKey (PK)     |
       +---------+---------+         +---------+---------+
                 | 1                                   | 1
                 |                                     |
                 | *               *                   | *
         +-------+--------+------------------+         |
         |                |                  |         |
+--------v-------+  +-----v----------+  +----v---------v-+  +----------------+  +----------------+
| FactProduction |  |  FactDowntime  |  |  FactQuality   |  |   FactEnergy   |  |   FactSensor   |
+--------^-------+  +-----^----------+  +----^---------^-+  +----^---------^-+  +----^---------^-+
         | *              | *                | *       |         | *       |         | *       |
         | 1              | 1                | 1       |         | 1       |         | 1       |
+--------+-------+        |                  |         |         |         |         |         |
|   DimProduct   |        |                  |         |         |         |         |         |
|----------------|        |                  |         |         |         |         |         |
| ProductKey(PK) |        |                  |         |         |         |         |         |
+----------------+        |                  |         |         |         |         |         |
                          |                  |         | 1       |         |         |         |
                 +--------+                  |  +------+---------+         |         |         |
                 |                           |  |  DimReason               |         |         |
                 | *                         |  |--------------------------|         |         |
                 | 1                         |  | ReasonKey (PK)           |         |         |
       +---------+---------+                 |  +--------------------------+         |         |
       |   DimMachine      <-----------------+                                       |         |
       |-------------------|                                                         |         |
       | MachineKey (PK)   <---------------------------------------------------------+         |
       | LineKey (FK)      <-------------------------------------------------------------------+
       +---------+---------+
                 | *
                 | 1
       +---------v---------+
       |     DimLine       |
       |-------------------|
       | LineKey (PK)      |
       +-------------------+
```

---

## Relationship Catalog & Cardinality Table

| From Table (Many / Fact) | Foreign Key Column | To Table (One / Dim) | Primary Key Column | Cardinality | Cross Filter Direction | Security / Inactive |
|:---|:---|:---|:---|:---|:---|:---|
| `FactProduction` | `DateKey` | `DimDate` | `DateKey` | Many to One (`*:1`) | Single (`DimDate` filters `FactProduction`) | Active |
| `FactProduction` | `ShiftKey` | `DimShift` | `ShiftKey` | Many to One (`*:1`) | Single (`DimShift` filters `FactProduction`) | Active |
| `FactProduction` | `MachineKey` | `DimMachine` | `MachineKey` | Many to One (`*:1`) | Single (`DimMachine` filters `FactProduction`) | Active |
| `FactProduction` | `ProductKey` | `DimProduct` | `ProductKey` | Many to One (`*:1`) | Single (`DimProduct` filters `FactProduction`) | Active |
| `FactDowntime` | `DateKey` | `DimDate` | `DateKey` | Many to One (`*:1`) | Single (`DimDate` filters `FactDowntime`) | Active |
| `FactDowntime` | `ShiftKey` | `DimShift` | `ShiftKey` | Many to One (`*:1`) | Single (`DimShift` filters `FactDowntime`) | Active |
| `FactDowntime` | `MachineKey` | `DimMachine` | `MachineKey` | Many to One (`*:1`) | Single (`DimMachine` filters `FactDowntime`) | Active |
| `FactDowntime` | `ReasonKey` | `DimReason` | `ReasonKey` | Many to One (`*:1`) | Single (`DimReason` filters `FactDowntime`) | Active |
| `FactQuality` | `DateKey` | `DimDate` | `DateKey` | Many to One (`*:1`) | Single (`DimDate` filters `FactQuality`) | Active |
| `FactQuality` | `ShiftKey` | `DimShift` | `ShiftKey` | Many to One (`*:1`) | Single (`DimShift` filters `FactQuality`) | Active |
| `FactQuality` | `MachineKey` | `DimMachine` | `MachineKey` | Many to One (`*:1`) | Single (`DimMachine` filters `FactQuality`) | Active |
| `FactQuality` | `ProductKey` | `DimProduct` | `ProductKey` | Many to One (`*:1`) | Single (`DimProduct` filters `FactQuality`) | Active |
| `FactQuality` | `DefectReasonKey` | `DimReason` | `ReasonKey` | Many to One (`*:1`) | Single (`DimReason` filters `FactQuality`) | Active |
| `FactEnergy` | `DateKey` | `DimDate` | `DateKey` | Many to One (`*:1`) | Single (`DimDate` filters `FactEnergy`) | Active |
| `FactEnergy` | `ShiftKey` | `DimShift` | `ShiftKey` | Many to One (`*:1`) | Single (`DimShift` filters `FactEnergy`) | Active |
| `FactEnergy` | `MachineKey` | `DimMachine` | `MachineKey` | Many to One (`*:1`) | Single (`DimMachine` filters `FactEnergy`) | Active |
| `FactSensor` | `DateKey` | `DimDate` | `DateKey` | Many to One (`*:1`) | Single (`DimDate` filters `FactSensor`) | Active |
| `FactSensor` | `MachineKey` | `DimMachine` | `MachineKey` | Many to One (`*:1`) | Single (`DimMachine` filters `FactSensor`) | Active |
| `DimMachine` | `LineKey` | `DimLine` | `LineKey` | Many to One (`*:1`) | Single (`DimLine` filters `DimMachine`) | Active |

---

## Fact Table Grain & Dimensionality

### 1. `FactProduction`
- **Business Concept**: Machine-level finished and semi-finished unit production per shift and product variant.
- **Grain**: One record per `DateKey` + `ShiftKey` + `MachineKey` + `ProductKey`.
- **Primary Measures**: `TargetUnits`, `ProducedUnits`, `GoodUnits`, `RejectedUnits`.
- **Conservation Law**: `ProducedUnits = GoodUnits + RejectedUnits`.

### 2. `FactDowntime`
- **Business Concept**: Stoppages and equipment availability loss categorized by root cause.
- **Grain**: One record per `DateKey` + `ShiftKey` + `MachineKey` + `ReasonKey`.
- **Primary Measures**: `DowntimeMinutes`, `Planned` (Boolean: 1 = Planned Maintenance, 0 = Unplanned Breakdown).
- **Duration Constraint**: `DowntimeMinutes <= ScheduledMinutes (480.0)`.

### 3. `FactQuality`
- **Business Concept**: Defect occurrences cataloged by defect classification and machine cell.
- **Grain**: One record per `DateKey` + `ShiftKey` + `MachineKey` + `ProductKey` + `DefectReasonKey`.
- **Primary Measures**: `DefectCount`.

### 4. `FactEnergy`
- **Business Concept**: Electrical energy consumption telemetry per machine per operating shift.
- **Grain**: One record per `DateKey` + `ShiftKey` + `MachineKey`.
- **Primary Measures**: `EnergyKWh`.

### 5. `FactSensor`
- **Business Concept**: High-frequency condition monitoring and benchmark predictive maintenance sensor telemetry.
- **Grain**: One record per `DateKey` + `MachineKey` + Sensor Observation (`SensorKey`).
- **Primary Measures**: `SensorValue` (Real continuous measurement).
- **Provenance Segmentation**: `is_external = 0` (Factory internal telemetry), `is_external = 1` (UCI AI4I 2020 predictive maintenance benchmark dataset).

### 6. `FactDQExceptions`
- **Business Concept**: Quarantined records violating structural, referential, domain, temporal, or KPI bounds.
- **Grain**: One record per detected exception (`ExceptionKey`).
- **Integration**: Standalone audit table disconnected from active reporting relationships to prevent downstream query skew.

---

## Modeling Best Practices for Power BI & Power Pivot
1. **Never Create Fact-to-Fact Relationships**: Fact tables must only filter through shared conforming dimensions (`DimDate`, `DimShift`, `DimMachine`, `DimProduct`, `DimReason`). Direct relationships between fact tables cause many-to-many Cartesian fan-outs.
2. **Strictly Single-Direction Cross-Filtering**: Do not enable bi-directional filtering (`Both`). Bi-directional filtering creates ambiguity in DAX filter context and leads to non-deterministic metric totals.
3. **Star Schema Denormalization Option**: Downstream modelers may optionally denormalize `DimLine` into `DimMachine` during Power Query import (merging `LineName` directly onto `DimMachine`) to achieve a 100% pure star schema without sub-dimensions.
4. **Surrogate Key Integrity**: All relationships utilize integer surrogate keys (`DateKey`, `ShiftKey`, `MachineKey`, `ProductKey`, `ReasonKey`, `LineKey`), providing optimal columnar compression in VertiPaq.
