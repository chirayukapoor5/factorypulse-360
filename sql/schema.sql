PRAGMA foreign_keys = ON;

-- sql/schema.sql
-- Star schema for FactoryPulse 360

-- Dimension tables
CREATE TABLE DimDate (
    DateKey INTEGER PRIMARY KEY, -- YYYYMMDD integer
    Date DATE NOT NULL,
    Year INTEGER NOT NULL,
    Month INTEGER NOT NULL,
    Day INTEGER NOT NULL,
    Week INTEGER NOT NULL,
    IsWeekend BOOLEAN NOT NULL
);

CREATE TABLE DimShift (
    ShiftKey INTEGER PRIMARY KEY,
    ShiftId INTEGER NOT NULL,
    ShiftName TEXT NOT NULL,
    StartTime TIME NOT NULL,
    EndTime TIME NOT NULL,
    ScheduledMinutes REAL NOT NULL DEFAULT 480.0
);

CREATE TABLE DimLine (
    LineKey INTEGER PRIMARY KEY,
    LineId INTEGER NOT NULL,
    LineName TEXT NOT NULL
);

CREATE TABLE DimMachine (
    MachineKey INTEGER PRIMARY KEY,
    MachineId TEXT NOT NULL,
    LineKey INTEGER NOT NULL,
    CellId INTEGER NOT NULL,
    MachineName TEXT NOT NULL,
    StageSequence INTEGER,
    IsEndOfLine BOOLEAN DEFAULT 0,
    FOREIGN KEY (LineKey) REFERENCES DimLine(LineKey)
);

CREATE TABLE DimProduct (
    ProductKey INTEGER PRIMARY KEY,
    ProductId TEXT NOT NULL,
    ProductFamily TEXT NOT NULL,
    ProductName TEXT NOT NULL,
    IdealCycleTimeSeconds REAL NOT NULL DEFAULT 270.0,
    IdealCycleTimeMinutes REAL NOT NULL DEFAULT 4.5
);

CREATE TABLE DimReason (
    ReasonKey INTEGER PRIMARY KEY,
    ReasonCode TEXT NOT NULL,
    ReasonCategory TEXT NOT NULL,
    ReasonDescription TEXT
);

-- Fact tables
CREATE TABLE FactProduction (
    ProductionKey INTEGER PRIMARY KEY,
    DateKey INTEGER NOT NULL,
    ShiftKey INTEGER NOT NULL,
    MachineKey INTEGER NOT NULL,
    ProductKey INTEGER NOT NULL,
    TargetUnits INTEGER NOT NULL,
    ProducedUnits INTEGER NOT NULL,
    GoodUnits INTEGER NOT NULL,
    RejectedUnits INTEGER NOT NULL,
    FOREIGN KEY (DateKey) REFERENCES DimDate(DateKey),
    FOREIGN KEY (ShiftKey) REFERENCES DimShift(ShiftKey),
    FOREIGN KEY (MachineKey) REFERENCES DimMachine(MachineKey),
    FOREIGN KEY (ProductKey) REFERENCES DimProduct(ProductKey)
);

CREATE TABLE FactDowntime (
    DowntimeKey INTEGER PRIMARY KEY,
    DateKey INTEGER NOT NULL,
    ShiftKey INTEGER NOT NULL,
    MachineKey INTEGER NOT NULL,
    ReasonKey INTEGER NOT NULL,
    DowntimeMinutes REAL NOT NULL,
    Planned BOOLEAN NOT NULL,
    FOREIGN KEY (DateKey) REFERENCES DimDate(DateKey),
    FOREIGN KEY (ShiftKey) REFERENCES DimShift(ShiftKey),
    FOREIGN KEY (MachineKey) REFERENCES DimMachine(MachineKey),
    FOREIGN KEY (ReasonKey) REFERENCES DimReason(ReasonKey)
);

CREATE TABLE FactQuality (
    QualityKey INTEGER PRIMARY KEY,
    DateKey INTEGER NOT NULL,
    ShiftKey INTEGER NOT NULL,
    MachineKey INTEGER NOT NULL,
    ProductKey INTEGER NOT NULL,
    DefectReasonKey INTEGER NOT NULL,
    DefectCount INTEGER NOT NULL,
    FOREIGN KEY (DateKey) REFERENCES DimDate(DateKey),
    FOREIGN KEY (ShiftKey) REFERENCES DimShift(ShiftKey),
    FOREIGN KEY (MachineKey) REFERENCES DimMachine(MachineKey),
    FOREIGN KEY (ProductKey) REFERENCES DimProduct(ProductKey),
    FOREIGN KEY (DefectReasonKey) REFERENCES DimReason(ReasonKey)
);

CREATE TABLE FactEnergy (
    EnergyKey INTEGER PRIMARY KEY,
    DateKey INTEGER NOT NULL,
    ShiftKey INTEGER NOT NULL,
    MachineKey INTEGER NOT NULL,
    EnergyKWh REAL NOT NULL,
    FOREIGN KEY (DateKey) REFERENCES DimDate(DateKey),
    FOREIGN KEY (ShiftKey) REFERENCES DimShift(ShiftKey),
    FOREIGN KEY (MachineKey) REFERENCES DimMachine(MachineKey)
);

CREATE TABLE FactSensor (
    SensorKey INTEGER PRIMARY KEY,
    DateKey INTEGER NOT NULL,
    MachineKey INTEGER NOT NULL,
    SensorName TEXT NOT NULL,
    SensorValue REAL NOT NULL,
    external_machine_id TEXT,
    is_external INTEGER NOT NULL DEFAULT 0,
    UDI INTEGER,
    FOREIGN KEY (DateKey) REFERENCES DimDate(DateKey),
    FOREIGN KEY (MachineKey) REFERENCES DimMachine(MachineKey)
);

CREATE TABLE FactDQExceptions (
    ExceptionKey INTEGER PRIMARY KEY,
    ExecutionTimestamp TEXT,
    SourceTable TEXT NOT NULL,
    RecordIdentifier TEXT NOT NULL,
    RuleViolated TEXT NOT NULL,
    Severity TEXT NOT NULL,
    Disposition TEXT NOT NULL,
    Description TEXT,
    RawPayload TEXT
);

-- Analytical View: Machine-level Manufacturing Metrics
CREATE VIEW IF NOT EXISTS v_ManufacturingMetrics AS
WITH agg_prod AS (
    SELECT DateKey, ShiftKey, MachineKey,
           SUM(TargetUnits) AS TargetUnits,
           SUM(ProducedUnits) AS TotalUnits,
           SUM(GoodUnits) AS GoodUnits,
           SUM(RejectedUnits) AS RejectedUnits,
           SUM(fp.ProducedUnits * dp.IdealCycleTimeMinutes) AS IdealProductionMinutes
    FROM FactProduction fp
    JOIN DimProduct dp ON fp.ProductKey = dp.ProductKey
    GROUP BY DateKey, ShiftKey, MachineKey
),
agg_down AS (
    SELECT DateKey, ShiftKey, MachineKey,
           SUM(DowntimeMinutes) AS TotalDowntimeMinutes,
           SUM(CASE WHEN Planned = 1 THEN DowntimeMinutes ELSE 0.0 END) AS PlannedMaintenanceMinutes,
           SUM(CASE WHEN Planned = 0 THEN DowntimeMinutes ELSE 0.0 END) AS UnplannedDowntimeMinutes
    FROM FactDowntime
    GROUP BY DateKey, ShiftKey, MachineKey
),
agg_energy AS (
    SELECT DateKey, ShiftKey, MachineKey,
           SUM(EnergyKWh) AS TotalEnergyKWh
    FROM FactEnergy
    GROUP BY DateKey, ShiftKey, MachineKey
)
SELECT
    d.DateKey,
    d.Date,
    s.ShiftKey,
    s.ShiftName,
    m.MachineKey,
    m.MachineId,
    m.MachineName,
    l.LineKey,
    l.LineName,
    m.CellId,
    s.ScheduledMinutes AS ScheduledProductionMinutes,
    COALESCE(ad.PlannedMaintenanceMinutes, 0.0) AS PlannedMaintenanceMinutes,
    MAX(0.0, s.ScheduledMinutes - COALESCE(ad.PlannedMaintenanceMinutes, 0.0)) AS PlannedProductionMinutes,
    COALESCE(ad.UnplannedDowntimeMinutes, 0.0) AS UnplannedDowntimeMinutes,
    MAX(0.0, MAX(0.0, s.ScheduledMinutes - COALESCE(ad.PlannedMaintenanceMinutes, 0.0)) - COALESCE(ad.UnplannedDowntimeMinutes, 0.0)) AS OperatingMinutes,
    COALESCE(ap.IdealProductionMinutes, 0.0) AS IdealProductionMinutes,
    COALESCE(ap.TargetUnits, 0) AS TargetUnits,
    COALESCE(ap.TotalUnits, 0) AS TotalUnits,
    COALESCE(ap.GoodUnits, 0) AS GoodUnits,
    COALESCE(ap.RejectedUnits, 0) AS RejectedUnits,
    COALESCE(ae.TotalEnergyKWh, 0.0) AS TotalEnergyKWh,
    ROUND(CASE WHEN MAX(0.0, s.ScheduledMinutes - COALESCE(ad.PlannedMaintenanceMinutes, 0.0)) > 0
         THEN (MAX(0.0, MAX(0.0, s.ScheduledMinutes - COALESCE(ad.PlannedMaintenanceMinutes, 0.0)) - COALESCE(ad.UnplannedDowntimeMinutes, 0.0)) * 100.0) /
              MAX(0.0, s.ScheduledMinutes - COALESCE(ad.PlannedMaintenanceMinutes, 0.0))
         ELSE 0.0 END, 2) AS AvailabilityPct,
    ROUND(CASE WHEN MAX(0.0, MAX(0.0, s.ScheduledMinutes - COALESCE(ad.PlannedMaintenanceMinutes, 0.0)) - COALESCE(ad.UnplannedDowntimeMinutes, 0.0)) > 0
         THEN (COALESCE(ap.IdealProductionMinutes, 0.0) * 100.0) /
              MAX(0.0, MAX(0.0, s.ScheduledMinutes - COALESCE(ad.PlannedMaintenanceMinutes, 0.0)) - COALESCE(ad.UnplannedDowntimeMinutes, 0.0))
         ELSE 0.0 END, 2) AS PerformancePct,
    ROUND(CASE WHEN COALESCE(ap.TotalUnits, 0) > 0
         THEN (COALESCE(ap.GoodUnits, 0) * 100.0) / COALESCE(ap.TotalUnits, 0)
         ELSE 0.0 END, 2) AS QualityPct,
    ROUND(CASE WHEN COALESCE(ap.GoodUnits, 0) > 0
         THEN (COALESCE(ae.TotalEnergyKWh, 0.0) * 1.0) / COALESCE(ap.GoodUnits, 0)
         ELSE 0.0 END, 4) AS EnergyIntensity
FROM DimDate d
CROSS JOIN DimShift s
CROSS JOIN DimMachine m
JOIN DimLine l ON m.LineKey = l.LineKey
LEFT JOIN agg_prod ap ON d.DateKey = ap.DateKey AND s.ShiftKey = ap.ShiftKey AND m.MachineKey = ap.MachineKey
LEFT JOIN agg_down ad ON d.DateKey = ad.DateKey AND s.ShiftKey = ad.ShiftKey AND m.MachineKey = ad.MachineKey
LEFT JOIN agg_energy ae ON d.DateKey = ae.DateKey AND s.ShiftKey = ae.ShiftKey AND m.MachineKey = ae.MachineKey;

-- Analytical View: Line-Shift Level OEE Summary
CREATE VIEW IF NOT EXISTS v_LineShiftOEE AS
SELECT
    DateKey,
    Date,
    LineKey,
    LineName,
    ShiftKey,
    ShiftName,
    COUNT(DISTINCT MachineKey) AS ActiveMachines,
    SUM(ScheduledProductionMinutes) AS ScheduledProductionMinutes,
    SUM(PlannedMaintenanceMinutes) AS PlannedMaintenanceMinutes,
    SUM(PlannedProductionMinutes) AS PlannedProductionMinutes,
    SUM(UnplannedDowntimeMinutes) AS UnplannedDowntimeMinutes,
    SUM(OperatingMinutes) AS OperatingMinutes,
    SUM(IdealProductionMinutes) AS IdealProductionMinutes,
    SUM(TargetUnits) AS TargetUnits,
    SUM(TotalUnits) AS TotalUnits,
    SUM(GoodUnits) AS GoodUnits,
    SUM(RejectedUnits) AS RejectedUnits,
    SUM(TotalEnergyKWh) AS TotalEnergyKWh,
    ROUND(CASE WHEN SUM(PlannedProductionMinutes) > 0
         THEN (SUM(OperatingMinutes) * 100.0) / SUM(PlannedProductionMinutes)
         ELSE 0.0 END, 2) AS AvailabilityPct,
    ROUND(CASE WHEN SUM(OperatingMinutes) > 0
         THEN (SUM(IdealProductionMinutes) * 100.0) / SUM(OperatingMinutes)
         ELSE 0.0 END, 2) AS PerformancePct,
    ROUND(CASE WHEN SUM(TotalUnits) > 0
         THEN (SUM(GoodUnits) * 100.0) / SUM(TotalUnits)
         ELSE 0.0 END, 2) AS QualityPct,
    ROUND((
        (CASE WHEN SUM(PlannedProductionMinutes) > 0 THEN (SUM(OperatingMinutes) * 1.0) / SUM(PlannedProductionMinutes) ELSE 0.0 END) *
        (CASE WHEN SUM(OperatingMinutes) > 0 THEN (SUM(IdealProductionMinutes) * 1.0) / SUM(OperatingMinutes) ELSE 0.0 END) *
        (CASE WHEN SUM(TotalUnits) > 0 THEN (SUM(GoodUnits) * 1.0) / SUM(TotalUnits) ELSE 0.0 END)
    ) * 100.0, 2) AS OEE_Pct,
    ROUND(CASE WHEN SUM(GoodUnits) > 0
         THEN (SUM(TotalEnergyKWh) * 1.0) / SUM(GoodUnits)
         ELSE 0.0 END, 4) AS EnergyIntensity
FROM v_ManufacturingMetrics
GROUP BY DateKey, Date, LineKey, LineName, ShiftKey, ShiftName;

-- End of schema
