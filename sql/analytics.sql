-- sql/analytics.sql
-- Analytical queries for FactoryPulse 360

-- 1. OEE per line/shift/day
SELECT
    d.Date,
    l.LineName,
    s.ShiftName,
    SUM(fp.GoodUnits) AS GoodUnits,
    SUM(fp.TargetUnits) AS TargetUnits,
    SUM(fd.DowntimeMinutes) AS TotalDowntime,
    SUM(fe.EnergyKWh) AS TotalEnergy,
    -- Availability = (Planned - Downtime) / Planned
    ( ( (24*60) - SUM(fd.DowntimeMinutes) ) / (24*60) ) * 100 AS AvailabilityPct,
    -- Performance = ActualUnits / (PlannedUnits * IdealCycleTime)
    ( SUM(fp.GoodUnits) / (SUM(fp.TargetUnits) * 0.5) ) * 100 AS PerformancePct,
    -- Quality = GoodUnits / ProducedUnits
    ( SUM(fp.GoodUnits) / NULLIF(SUM(fp.ProducedUnits),0) ) * 100 AS QualityPct,
    ( ( ( (24*60) - SUM(fd.DowntimeMinutes) ) / (24*60) ) *
      ( SUM(fp.GoodUnits) / (SUM(fp.TargetUnits) * 0.5) ) *
      ( SUM(fp.GoodUnits) / NULLIF(SUM(fp.ProducedUnits),0) ) ) * 100 AS OEE_Pct
FROM FactProduction fp
JOIN FactDowntime fd ON fp.DateKey = fd.DateKey AND fp.ShiftKey = fd.ShiftKey AND fp.MachineKey = fd.MachineKey
JOIN FactEnergy fe ON fp.DateKey = fe.DateKey AND fp.ShiftKey = fe.ShiftKey AND fp.MachineKey = fe.MachineKey
JOIN DimDate d ON fp.DateKey = d.DateKey
JOIN DimShift s ON fp.ShiftKey = s.ShiftKey
JOIN DimLine l ON fp.MachineKey = (SELECT MachineKey FROM DimMachine WHERE MachineKey = fp.MachineKey)
GROUP BY d.Date, l.LineName, s.ShiftName
ORDER BY d.Date;

-- 2. Downtime Pareto by reason (cumulative percentage)
WITH downtime_by_reason AS (
    SELECT r.ReasonCode, SUM(fd.DowntimeMinutes) AS TotalMinutes
    FROM FactDowntime fd
    JOIN DimReason r ON fd.ReasonKey = r.ReasonKey
    GROUP BY r.ReasonCode
), ranked AS (
    SELECT ReasonCode, TotalMinutes,
           SUM(TotalMinutes) OVER (ORDER BY TotalMinutes DESC) AS CumulativeMinutes,
           SUM(TotalMinutes) OVER () AS GrandTotal,
           ROW_NUMBER() OVER (ORDER BY TotalMinutes DESC) AS rn
    FROM downtime_by_reason
)
SELECT ReasonCode, TotalMinutes,
       (CumulativeMinutes * 100.0 / GrandTotal) AS CumPct
FROM ranked
ORDER BY rn;

-- 3. Defect rate per product family
SELECT p.ProductFamily,
       SUM(fq.DefectCount) AS TotalDefects,
       SUM(fp.ProducedUnits) AS TotalProduced,
       (SUM(fq.DefectCount) * 100.0 / NULLIF(SUM(fp.ProducedUnits),0)) AS DefectRatePct
FROM FactQuality fq
JOIN FactProduction fp ON fq.DateKey = fp.DateKey AND fq.ShiftKey = fp.ShiftKey AND fq.MachineKey = fp.MachineKey AND fq.ProductKey = fp.ProductKey
JOIN DimProduct p ON fp.ProductKey = p.ProductKey
GROUP BY p.ProductFamily
ORDER BY DefectRatePct DESC;

-- 4. Energy intensity (kWh per Good Unit) per machine
SELECT m.MachineName,
       SUM(fe.EnergyKWh) AS EnergyKWh,
       SUM(fp.GoodUnits) AS GoodUnits,
       (SUM(fe.EnergyKWh) * 1.0 / NULLIF(SUM(fp.GoodUnits),0)) AS kWhPerGoodUnit
FROM FactEnergy fe
JOIN FactProduction fp ON fe.DateKey = fp.DateKey AND fe.ShiftKey = fp.ShiftKey AND fe.MachineKey = fp.MachineKey
JOIN DimMachine m ON fp.MachineKey = m.MachineKey
GROUP BY m.MachineName
HAVING GoodUnits > 0
ORDER BY kWhPerGoodUnit DESC;

-- 5. Seven‑day rolling OEE per line
WITH daily_oee AS (
    SELECT d.Date,
           l.LineName,
           ( ( ( (24*60) - SUM(fd.DowntimeMinutes) ) / (24*60) ) *
             ( SUM(fp.GoodUnits) / (SUM(fp.TargetUnits) * 0.5) ) *
             ( SUM(fp.GoodUnits) / NULLIF(SUM(fp.ProducedUnits),0) ) ) * 100 AS OEE_Pct
    FROM FactProduction fp
    JOIN FactDowntime fd ON fp.DateKey = fd.DateKey AND fp.ShiftKey = fd.ShiftKey AND fp.MachineKey = fd.MachineKey
    JOIN DimDate d ON fp.DateKey = d.DateKey
    JOIN DimLine l ON fp.MachineKey = (SELECT MachineKey FROM DimMachine WHERE MachineKey = fp.MachineKey)
    GROUP BY d.Date, l.LineName
)
SELECT Date,
       LineName,
       OEE_Pct,
       AVG(OEE_Pct) OVER (PARTITION BY LineName ORDER BY Date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS OEE_7DayAvg
FROM daily_oee
ORDER BY LineName, Date;
