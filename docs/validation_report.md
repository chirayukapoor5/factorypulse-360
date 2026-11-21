# FactoryPulse 360 — Data Quality Validation & Fault Quarantine Report

## Executive Summary
This report documents the automated data quality validation and exception quarantine audit for FactoryPulse 360 discrete manufacturing telemetry. All raw fact tables undergo rigorous verification against 12 documented structural, referential, domain, temporal, and KPI consistency rules. Anomalous records are quarantined into `FactDQExceptions` with traceable identifiers, preserving complete audit trails with zero silent data deletion.

### Key Metrics
- **Total Raw Fact Records Processed**: 1,011
- **Accepted Curated Records**: 998 (98.71%)
- **Quarantined Records**: 13 (1.29%)
- **Total Rule Violations Detected**: 13
- **Silent Record Deletion**: 0 records (100% audit conservation)

---

## Fault Injection vs. Detection Audit

| Rule Violated | Injected Faults | Detected Exceptions | Detection Efficiency | Disposition |
|:---|---:|---:|---:|:---|
| DuplicatePrimaryKey | 3 | 6 | 200.0% | QUARANTINED |
| NullPrimaryKey | 2 | 2 | 100.0% | QUARANTINED |
| OrphanForeignKey | 1 | 1 | 100.0% | QUARANTINED |
| NegativeValue | 0 | 0 | 100.0% | QUARANTINED |
| NegativeDowntime | 0 | 0 | 100.0% | QUARANTINED |
| InvalidTimestamp | 1 | 1 | 100.0% | QUARANTINED |
| NullEnergyReading | 0 | 0 | 100.0% | QUARANTINED |
| InvalidCategory | 1 | 1 | 100.0% | QUARANTINED |
| UnitSumMismatch | 0 | 0 | 100.0% | QUARANTINED |
| DefectCountMismatch | 1 | 2 | 200.0% | QUARANTINED |
| DowntimeInconsistency | 0 | 0 | 100.0% | QUARANTINED |
| InvalidKPIRange | 0 | 0 | 100.0% | QUARANTINED |
| **Total** | **9** | **13** | **144.4%** | **QUARANTINED** |

---

## Exceptions Breakdown by Source Table and Rule

| Source Table | Rule Violated | Severity | Quarantined Count | Record Identifier Example |
|:---|:---|:---|---:|:---|
| FactDowntime | DuplicatePrimaryKey | ERROR | 2 | `60` |
| FactEnergy | InvalidTimestamp | ERROR | 1 | `87` |
| FactProduction | DuplicatePrimaryKey | ERROR | 2 | `19` |
| FactQuality | DefectCountMismatch | ERROR | 2 | `19` |
| FactSensor | DuplicatePrimaryKey | ERROR | 2 | `196` |
| FactSensor | InvalidCategory | ERROR | 1 | `74` |
| FactSensor | NullPrimaryKey | ERROR | 2 | `FactSensor_Row_93` |
| FactSensor | OrphanForeignKey | ERROR | 1 | `41` |

---

## Validation Rule Catalog
1. **DuplicatePrimaryKey**: Validates primary key uniqueness across fact tables on non-null values.
2. **NullPrimaryKey**: Detects missing primary keys and assigns traceable surrogate audit identifiers (`{Table}_Row_{idx}`).
3. **OrphanForeignKey**: Enforces referential integrity against corresponding dimension tables (`DimDate`, `DimShift`, `DimLine`, `DimMachine`, `DimProduct`, `DimReason`).
4. **NegativeValue**: Validates non-negativity of physical quantities (`ProducedUnits`, `GoodUnits`, `RejectedUnits`, `EnergyKWh`).
5. **NegativeDowntime**: Rejects negative equipment downtime durations in `FactDowntime`.
6. **InvalidTimestamp**: Validates temporal integrity against calendar range and `DimDate`.
7. **NullEnergyReading**: Guarantees zero null meter telemetry in `FactEnergy` (`EnergyKWh IS NOT NULL`).
8. **InvalidCategory**: Rejects unmapped or corrupt categorical sensor/reason values.
9. **UnitSumMismatch**: Verifies conservation of mass: `ProducedUnits == GoodUnits + RejectedUnits`.
10. **DefectCountMismatch**: Cross-table reconciliation between `FactQuality.DefectCount` and `FactProduction.RejectedUnits`.
11. **DowntimeInconsistency**: Enforces shift boundary limits (`DowntimeMinutes <= 480.0`).
12. **InvalidKPIRange**: Validates KPI component domains (`GoodUnits <= ProducedUnits`, non-negative target units).

---

## Traceability & Database Persistence Audit
- **Curated Exception Table**: `FactDQExceptions`
- **Total Quarantined Exceptions in CSV**: 13
- **Total Exceptions Loaded into SQLite**: 13 (100% parity, 0 dropped rows)
- **Traceability Guarantee**: 0 records with NULL, empty, or 'nan' string identifiers.
