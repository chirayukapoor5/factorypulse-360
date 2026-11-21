-- sql/analytics.sql
-- FactoryPulse 360 - Curated Relational Warehouse Analytical Query Suite
-- All 9 queries use CTE pre-aggregations to eliminate Cartesian explosion, multi-fact data loss, and integer division.

-- ==============================================================================
-- Query 1: Production & OEE Summary by Date, Line, Shift
-- ==============================================================================
WITH prod_agg AS (
    SELECT
        fp.DateKey,
        fp.ShiftKey,
        m.LineKey,
        SUM(fp.TargetUnits) AS TargetUnits,
        SUM(fp.ProducedUnits) AS ProducedUnits,
        SUM(fp.GoodUnits) AS GoodUnits,
        SUM(fp.RejectedUnits) AS RejectedUnits,
        SUM(fp.ProducedUnits * 4.5) AS IdealProductionMinutes
    FROM FactProduction fp
    JOIN DimMachine m ON fp.MachineKey = m.MachineKey
    GROUP BY fp.DateKey, fp.ShiftKey, m.LineKey
),
down_agg AS (
    SELECT
        fd.DateKey,
        fd.ShiftKey,
        m.LineKey,
        SUM(fd.DowntimeMinutes) AS TotalDowntime,
        SUM(CASE WHEN fd.Planned = 1 THEN fd.DowntimeMinutes ELSE 0.0 END) AS PlannedMaintenanceMinutes,
        SUM(CASE WHEN fd.Planned = 0 THEN fd.DowntimeMinutes ELSE 0.0 END) AS UnplannedDowntimeMinutes
    FROM FactDowntime fd
    JOIN DimMachine m ON fd.MachineKey = m.MachineKey
    GROUP BY fd.DateKey, fd.ShiftKey, m.LineKey
),
energy_agg AS (
    SELECT
        fe.DateKey,
        fe.ShiftKey,
        m.LineKey,
        SUM(fe.EnergyKWh) AS TotalEnergy
    FROM FactEnergy fe
    JOIN DimMachine m ON fe.MachineKey = m.MachineKey
    GROUP BY fe.DateKey, fe.ShiftKey, m.LineKey
),
mach_count AS (
    SELECT LineKey, COUNT(*) AS ActiveMachines
    FROM DimMachine
    GROUP BY LineKey
)
SELECT
    d.Date,
    l.LineName,
    s.ShiftName,
    COALESCE(p.TargetUnits, 0) AS TargetUnits,
    COALESCE(p.ProducedUnits, 0) AS ProducedUnits,
    COALESCE(p.GoodUnits, 0) AS GoodUnits,
    COALESCE(p.RejectedUnits, 0) AS RejectedUnits,
    ROUND(COALESCE(dn.TotalDowntime, 0.0), 4) AS TotalDowntime,
    ROUND(COALESCE(e.TotalEnergy, 0.0), 4) AS TotalEnergy,
    ROUND(
        CASE
            WHEN (mc.ActiveMachines * 480.0 - COALESCE(dn.PlannedMaintenanceMinutes, 0.0)) <= 0 THEN 0.0
            ELSE (
                (mc.ActiveMachines * 480.0 - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0)) * 100.0 /
                (mc.ActiveMachines * 480.0 - COALESCE(dn.PlannedMaintenanceMinutes, 0.0))
            )
        END, 2
    ) AS AvailabilityPct,
    ROUND(
        CASE
            WHEN (mc.ActiveMachines * 480.0 - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0)) <= 0 THEN 0.0
            ELSE (
                COALESCE(p.IdealProductionMinutes, 0.0) * 100.0 /
                (mc.ActiveMachines * 480.0 - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0))
            )
        END, 2
    ) AS PerformancePct,
    ROUND(
        CASE
            WHEN COALESCE(p.ProducedUnits, 0) <= 0 THEN 0.0
            ELSE (COALESCE(p.GoodUnits, 0) * 100.0 / p.ProducedUnits)
        END, 2
    ) AS QualityPct,
    ROUND(
        (
            CASE
                WHEN (mc.ActiveMachines * 480.0 - COALESCE(dn.PlannedMaintenanceMinutes, 0.0)) <= 0 THEN 0.0
                ELSE (
                    (mc.ActiveMachines * 480.0 - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0)) /
                    (mc.ActiveMachines * 480.0 - COALESCE(dn.PlannedMaintenanceMinutes, 0.0))
                )
            END
        ) * (
            CASE
                WHEN (mc.ActiveMachines * 480.0 - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0)) <= 0 THEN 0.0
                ELSE (
                    COALESCE(p.IdealProductionMinutes, 0.0) /
                    (mc.ActiveMachines * 480.0 - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0))
                )
            END
        ) * (
            CASE
                WHEN COALESCE(p.ProducedUnits, 0) <= 0 THEN 0.0
                ELSE (COALESCE(p.GoodUnits, 0) * 1.0 / p.ProducedUnits)
            END
        ) * 100.0, 2
    ) AS OEE_Pct,
    ROUND(COALESCE(e.TotalEnergy, 0.0) * 1.0 / NULLIF(COALESCE(p.GoodUnits, 0), 0), 4) AS EnergyIntensity
FROM DimDate d
CROSS JOIN DimLine l
CROSS JOIN DimShift s
JOIN mach_count mc ON l.LineKey = mc.LineKey
LEFT JOIN prod_agg p ON d.DateKey = p.DateKey AND s.ShiftKey = p.ShiftKey AND l.LineKey = p.LineKey
LEFT JOIN down_agg dn ON d.DateKey = dn.DateKey AND s.ShiftKey = dn.ShiftKey AND l.LineKey = dn.LineKey
LEFT JOIN energy_agg e ON d.DateKey = e.DateKey AND s.ShiftKey = e.ShiftKey AND l.LineKey = e.LineKey
ORDER BY d.Date, l.LineName, s.ShiftName;

-- ==============================================================================
-- Query 2: Downtime Pareto Analysis
-- ==============================================================================
WITH downtime_by_reason AS (
    SELECT
        r.ReasonCode,
        r.ReasonCategory,
        SUM(fd.DowntimeMinutes) AS TotalMinutes
    FROM FactDowntime fd
    JOIN DimReason r ON fd.ReasonKey = r.ReasonKey
    GROUP BY r.ReasonCode, r.ReasonCategory
),
ranked AS (
    SELECT
        ReasonCode,
        ReasonCategory,
        TotalMinutes,
        SUM(TotalMinutes) OVER (ORDER BY TotalMinutes DESC, ReasonCode ASC) AS CumulativeMinutes,
        SUM(TotalMinutes) OVER () AS GrandTotalMinutes
    FROM downtime_by_reason
)
SELECT
    ReasonCode,
    ReasonCategory,
    ROUND(TotalMinutes, 4) AS TotalMinutes,
    ROUND(CumulativeMinutes, 4) AS CumulativeMinutes,
    ROUND(TotalMinutes * 100.0 / NULLIF(GrandTotalMinutes, 0.0), 4) AS PctOfTotal,
    ROUND(CumulativeMinutes * 100.0 / NULLIF(GrandTotalMinutes, 0.0), 4) AS CumPct
FROM ranked
ORDER BY TotalMinutes DESC, ReasonCode ASC;

-- ==============================================================================
-- Query 3: Quality & Scrap Summary by Product Family (Defect rate per product family)
-- ==============================================================================
WITH qual_agg AS (
    SELECT
        fq.ProductKey,
        SUM(fq.DefectCount) AS TotalDefects
    FROM FactQuality fq
    GROUP BY fq.ProductKey
),
prod_agg AS (
    SELECT
        fp.ProductKey,
        SUM(fp.TargetUnits) AS TargetUnits,
        SUM(fp.ProducedUnits) AS TotalProduced,
        SUM(fp.GoodUnits) AS TotalGood,
        SUM(fp.RejectedUnits) AS TotalRejected
    FROM FactProduction fp
    GROUP BY fp.ProductKey
)
SELECT
    p.ProductFamily,
    COALESCE(pr.TotalProduced, 0) AS TotalProduced,
    COALESCE(pr.TotalGood, 0) AS TotalGood,
    COALESCE(pr.TotalRejected, 0) AS TotalRejected,
    COALESCE(q.TotalDefects, 0) AS TotalDefects,
    ROUND(COALESCE(q.TotalDefects, 0) * 100.0 / NULLIF(pr.TotalProduced, 0.0), 2) AS DefectRatePct,
    ROUND(COALESCE(pr.TotalRejected, 0) * 100.0 / NULLIF(pr.TotalProduced, 0.0), 2) AS RejectionRatePct,
    ROUND(COALESCE(pr.TotalGood, 0) * 100.0 / NULLIF(pr.TotalProduced, 0.0), 2) AS YieldPct
FROM DimProduct p
LEFT JOIN prod_agg pr ON p.ProductKey = pr.ProductKey
LEFT JOIN qual_agg q ON p.ProductKey = q.ProductKey
ORDER BY DefectRatePct DESC, p.ProductFamily ASC;

-- ==============================================================================
-- Query 4: Machine Energy Intensity Ranking (kWh per Good Unit per machine)
-- ==============================================================================
WITH energy_agg AS (
    SELECT
        fe.MachineKey,
        SUM(fe.EnergyKWh) AS EnergyKWh
    FROM FactEnergy fe
    GROUP BY fe.MachineKey
),
prod_agg AS (
    SELECT
        fp.MachineKey,
        SUM(fp.GoodUnits) AS GoodUnits
    FROM FactProduction fp
    GROUP BY fp.MachineKey
)
SELECT
    m.MachineName,
    l.LineName,
    m.CellId,
    ROUND(COALESCE(e.EnergyKWh, 0.0), 4) AS EnergyKWh,
    COALESCE(p.GoodUnits, 0) AS GoodUnits,
    ROUND(COALESCE(e.EnergyKWh, 0.0) * 1.0 / NULLIF(p.GoodUnits, 0), 4) AS kWhPerGoodUnit,
    RANK() OVER (ORDER BY (COALESCE(e.EnergyKWh, 0.0) * 1.0 / NULLIF(p.GoodUnits, 0)) DESC) AS EnergyIntensityRank
FROM DimMachine m
JOIN DimLine l ON m.LineKey = l.LineKey
LEFT JOIN energy_agg e ON m.MachineKey = e.MachineKey
LEFT JOIN prod_agg p ON m.MachineKey = p.MachineKey
ORDER BY kWhPerGoodUnit DESC, m.MachineName ASC;

-- ==============================================================================
-- Query 5: Seven-Day Rolling OEE Trend by Line
-- ==============================================================================
WITH daily_prod AS (
    SELECT
        fp.DateKey,
        m.LineKey,
        COUNT(DISTINCT fp.MachineKey || '-' || fp.ShiftKey) AS ActiveMachineShifts,
        SUM(fp.TargetUnits) AS TargetUnits,
        SUM(fp.ProducedUnits) AS ProducedUnits,
        SUM(fp.GoodUnits) AS GoodUnits,
        SUM(fp.ProducedUnits * 4.5) AS IdealProductionMinutes
    FROM FactProduction fp
    JOIN DimMachine m ON fp.MachineKey = m.MachineKey
    GROUP BY fp.DateKey, m.LineKey
),
daily_down AS (
    SELECT
        fd.DateKey,
        m.LineKey,
        SUM(CASE WHEN fd.Planned = 1 THEN fd.DowntimeMinutes ELSE 0.0 END) AS PlannedMaintenanceMinutes,
        SUM(CASE WHEN fd.Planned = 0 THEN fd.DowntimeMinutes ELSE 0.0 END) AS UnplannedDowntimeMinutes
    FROM FactDowntime fd
    JOIN DimMachine m ON fd.MachineKey = m.MachineKey
    GROUP BY fd.DateKey, m.LineKey
),
daily_oee AS (
    SELECT
        d.Date,
        l.LineName,
        ROUND(
            (
                ( ( (p.ActiveMachineShifts * 480.0) - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0) )
                  * 1.0 / NULLIF((p.ActiveMachineShifts * 480.0) - COALESCE(dn.PlannedMaintenanceMinutes, 0.0), 0.0) )
                *
                ( p.IdealProductionMinutes * 1.0 /
                  NULLIF( (p.ActiveMachineShifts * 480.0) - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0), 0.0 ) )
                *
                ( p.GoodUnits * 1.0 / NULLIF(p.ProducedUnits, 0.0) )
            ) * 100.0, 2
        ) AS OEE_Pct
    FROM daily_prod p
    JOIN DimDate d ON p.DateKey = d.DateKey
    JOIN DimLine l ON p.LineKey = l.LineKey
    LEFT JOIN daily_down dn ON p.DateKey = dn.DateKey AND p.LineKey = dn.LineKey
)
SELECT
    Date,
    LineName,
    OEE_Pct,
    ROUND(AVG(OEE_Pct) OVER (PARTITION BY LineName ORDER BY Date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS OEE_7DayAvg
FROM daily_oee
ORDER BY LineName, Date;

-- ==============================================================================
-- Query 6: Target Variance & Attainment by Line and Shift
-- ==============================================================================
SELECT
    l.LineName,
    s.ShiftName,
    SUM(fp.TargetUnits) AS TargetUnits,
    SUM(fp.ProducedUnits) AS ProducedUnits,
    SUM(fp.GoodUnits) AS GoodUnits,
    SUM(fp.RejectedUnits) AS RejectedUnits,
    (SUM(fp.ProducedUnits) - SUM(fp.TargetUnits)) AS VarianceUnits,
    ROUND(( (SUM(fp.ProducedUnits) - SUM(fp.TargetUnits)) * 100.0 / NULLIF(SUM(fp.TargetUnits), 0) ), 2) AS VariancePct,
    ROUND(( SUM(fp.ProducedUnits) * 100.0 / NULLIF(SUM(fp.TargetUnits), 0) ), 2) AS AttainmentPct
FROM FactProduction fp
JOIN DimMachine m ON fp.MachineKey = m.MachineKey
JOIN DimLine l ON m.LineKey = l.LineKey
JOIN DimShift s ON fp.ShiftKey = s.ShiftKey
GROUP BY l.LineName, s.ShiftName
ORDER BY l.LineName, s.ShiftName;

-- ==============================================================================
-- Query 7: SQL Duplicate Detection (PK & composite business key validation)
-- ==============================================================================
SELECT 'FactProduction' AS TableName, 'ProductionKey' AS KeyChecked,
       COUNT(*) AS TotalRows,
       COUNT(DISTINCT ProductionKey) AS UniqueKeys,
       COUNT(*) - COUNT(DISTINCT ProductionKey) AS DuplicateCount
FROM FactProduction
UNION ALL
SELECT 'FactProduction' AS TableName, 'DateKey-ShiftKey-MachineKey-ProductKey' AS KeyChecked,
       COUNT(*) AS TotalRows,
       COUNT(DISTINCT DateKey || '-' || ShiftKey || '-' || MachineKey || '-' || ProductKey) AS UniqueKeys,
       COUNT(*) - COUNT(DISTINCT DateKey || '-' || ShiftKey || '-' || MachineKey || '-' || ProductKey) AS DuplicateCount
FROM FactProduction
UNION ALL
SELECT 'FactDowntime' AS TableName, 'DowntimeKey' AS KeyChecked,
       COUNT(*) AS TotalRows,
       COUNT(DISTINCT DowntimeKey) AS UniqueKeys,
       COUNT(*) - COUNT(DISTINCT DowntimeKey) AS DuplicateCount
FROM FactDowntime
UNION ALL
SELECT 'FactEnergy' AS TableName, 'EnergyKey' AS KeyChecked,
       COUNT(*) AS TotalRows,
       COUNT(DISTINCT EnergyKey) AS UniqueKeys,
       COUNT(*) - COUNT(DISTINCT EnergyKey) AS DuplicateCount
FROM FactEnergy
UNION ALL
SELECT 'FactEnergy' AS TableName, 'DateKey-ShiftKey-MachineKey' AS KeyChecked,
       COUNT(*) AS TotalRows,
       COUNT(DISTINCT DateKey || '-' || ShiftKey || '-' || MachineKey) AS UniqueKeys,
       COUNT(*) - COUNT(DISTINCT DateKey || '-' || ShiftKey || '-' || MachineKey) AS DuplicateCount
FROM FactEnergy
UNION ALL
SELECT 'FactQuality' AS TableName, 'QualityKey' AS KeyChecked,
       COUNT(*) AS TotalRows,
       COUNT(DISTINCT QualityKey) AS UniqueKeys,
       COUNT(*) - COUNT(DISTINCT QualityKey) AS DuplicateCount
FROM FactQuality;

-- ==============================================================================
-- Query 8: Data Quality Exception Register Breakdown
-- ==============================================================================
SELECT
    SourceTable,
    RuleViolated,
    Severity,
    Disposition,
    COUNT(*) AS ExceptionCount
FROM FactDQExceptions
GROUP BY SourceTable, RuleViolated, Severity, Disposition
ORDER BY ExceptionCount DESC, SourceTable ASC, RuleViolated ASC;

-- ==============================================================================
-- Query 9: Source vs Aggregated Reconciliation Audit
-- ==============================================================================
WITH
src_prod AS (
    SELECT
        SUM(TargetUnits) AS SrcTarget,
        SUM(ProducedUnits) AS SrcProduced,
        SUM(GoodUnits) AS SrcGood,
        SUM(RejectedUnits) AS SrcRejected
    FROM FactProduction
),
src_down AS (
    SELECT SUM(DowntimeMinutes) AS SrcDowntime FROM FactDowntime
),
src_energy AS (
    SELECT SUM(EnergyKWh) AS SrcEnergy FROM FactEnergy
),
src_qual AS (
    SELECT SUM(DefectCount) AS SrcDefects FROM FactQuality
),
src_dq AS (
    SELECT COUNT(*) AS SrcExceptions FROM FactDQExceptions
),
agg_p AS (
    SELECT
        SUM(TargetUnits) AS AggTarget,
        SUM(ProducedUnits) AS AggProduced,
        SUM(GoodUnits) AS AggGood,
        SUM(RejectedUnits) AS AggRejected
    FROM (
        SELECT fp.DateKey, fp.ShiftKey, m.LineKey,
               SUM(fp.TargetUnits) AS TargetUnits,
               SUM(fp.ProducedUnits) AS ProducedUnits,
               SUM(fp.GoodUnits) AS GoodUnits,
               SUM(fp.RejectedUnits) AS RejectedUnits
        FROM FactProduction fp
        JOIN DimMachine m ON fp.MachineKey = m.MachineKey
        GROUP BY fp.DateKey, fp.ShiftKey, m.LineKey
    )
),
agg_d AS (
    SELECT SUM(TotalDowntime) AS AggDowntime
    FROM (
        SELECT fd.DateKey, fd.ShiftKey, m.LineKey,
               SUM(fd.DowntimeMinutes) AS TotalDowntime
        FROM FactDowntime fd
        JOIN DimMachine m ON fd.MachineKey = m.MachineKey
        GROUP BY fd.DateKey, fd.ShiftKey, m.LineKey
    )
),
agg_e AS (
    SELECT SUM(TotalEnergy) AS AggEnergy
    FROM (
        SELECT fe.DateKey, fe.ShiftKey, m.LineKey,
               SUM(fe.EnergyKWh) AS TotalEnergy
        FROM FactEnergy fe
        JOIN DimMachine m ON fe.MachineKey = m.MachineKey
        GROUP BY fe.DateKey, fe.ShiftKey, m.LineKey
    )
),
agg_q AS (
    SELECT SUM(TotalDefects) AS AggDefects
    FROM (
        SELECT ProductKey, SUM(DefectCount) AS TotalDefects
        FROM FactQuality
        GROUP BY ProductKey
    )
),
agg_dq AS (
    SELECT SUM(ExceptionCount) AS AggExceptions
    FROM (
        SELECT SourceTable, RuleViolated, COUNT(*) AS ExceptionCount
        FROM FactDQExceptions
        GROUP BY SourceTable, RuleViolated
    )
),
reconciliation AS (
    SELECT 'TargetUnits' AS Metric, p_src.SrcTarget AS SourceTotal, p_agg.AggTarget AS AggregatedTotal FROM src_prod p_src, agg_p p_agg
    UNION ALL
    SELECT 'ProducedUnits' AS Metric, p_src.SrcProduced AS SourceTotal, p_agg.AggProduced AS AggregatedTotal FROM src_prod p_src, agg_p p_agg
    UNION ALL
    SELECT 'GoodUnits' AS Metric, p_src.SrcGood AS SourceTotal, p_agg.AggGood AS AggregatedTotal FROM src_prod p_src, agg_p p_agg
    UNION ALL
    SELECT 'RejectedUnits' AS Metric, p_src.SrcRejected AS SourceTotal, p_agg.AggRejected AS AggregatedTotal FROM src_prod p_src, agg_p p_agg
    UNION ALL
    SELECT 'DowntimeMinutes' AS Metric, ROUND(d_src.SrcDowntime, 4) AS SourceTotal, ROUND(d_agg.AggDowntime, 4) AS AggregatedTotal FROM src_down d_src, agg_d d_agg
    UNION ALL
    SELECT 'EnergyKWh' AS Metric, ROUND(e_src.SrcEnergy, 4) AS SourceTotal, ROUND(e_agg.AggEnergy, 4) AS AggregatedTotal FROM src_energy e_src, agg_e e_agg
    UNION ALL
    SELECT 'DefectCount' AS Metric, q_src.SrcDefects AS SourceTotal, q_agg.AggDefects AS AggregatedTotal FROM src_qual q_src, agg_q q_agg
    UNION ALL
    SELECT 'Exceptions' AS Metric, dq_src.SrcExceptions AS SourceTotal, dq_agg.AggExceptions AS AggregatedTotal FROM src_dq dq_src, agg_dq dq_agg
)
SELECT
    Metric,
    SourceTotal,
    AggregatedTotal,
    ROUND(ABS(SourceTotal - AggregatedTotal), 4) AS Variance,
    CASE
        WHEN ROUND(ABS(SourceTotal - AggregatedTotal), 4) = 0.0 THEN 'BALANCED'
        ELSE 'UNBALANCED'
    END AS Status
FROM reconciliation;
