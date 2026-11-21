/* ==========================================================================
   FactoryPulse 360 — Power Query M Transformations Library
   Compatible with: Microsoft Power BI & Excel Get & Transform
   ========================================================================== */

// --------------------------------------------------------------------------
// 1. ENVIRONMENT PARAMETER: DataRootPath
// --------------------------------------------------------------------------
// Define as a parameter in Power Query Editor:
// Name: DataRootPath
// Type: Text
// Value: "E:\FactoryPulse-360\bi_handoff" (adjust to your local directory)

let
    DataRootPath = "E:\FactoryPulse-360\bi_handoff" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]
in
    DataRootPath;


// --------------------------------------------------------------------------
// 2. DIMENSION TRANSFORMATIONS
// --------------------------------------------------------------------------

// DimDate
let
    Source = Csv.Document(File.Contents(DataRootPath & "\dimensions\DimDate.csv"), [Delimiter=",", Columns=7, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"DateKey", Int64.Type},
        {"Date", type date},
        {"Year", Int64.Type},
        {"Month", Int64.Type},
        {"Day", Int64.Type},
        {"Week", Int64.Type},
        {"IsWeekend", Int64.Type}
    })
in
    #"Changed Type";

// DimShift
let
    Source = Csv.Document(File.Contents(DataRootPath & "\dimensions\DimShift.csv"), [Delimiter=",", Columns=6, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"ShiftKey", Int64.Type},
        {"ShiftId", Int64.Type},
        {"ShiftName", type text},
        {"StartTime", type text},
        {"EndTime", type text},
        {"ScheduledMinutes", type number}
    })
in
    #"Changed Type";

// DimLine
let
    Source = Csv.Document(File.Contents(DataRootPath & "\dimensions\DimLine.csv"), [Delimiter=",", Columns=3, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"LineKey", Int64.Type},
        {"LineId", Int64.Type},
        {"LineName", type text}
    })
in
    #"Changed Type";

// DimMachine
let
    Source = Csv.Document(File.Contents(DataRootPath & "\dimensions\DimMachine.csv"), [Delimiter=",", Columns=7, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"MachineKey", Int64.Type},
        {"MachineId", type text},
        {"LineKey", Int64.Type},
        {"CellId", Int64.Type},
        {"MachineName", type text},
        {"StageSequence", Int64.Type},
        {"IsEndOfLine", Int64.Type}
    })
in
    #"Changed Type";

// DimProduct
let
    Source = Csv.Document(File.Contents(DataRootPath & "\dimensions\DimProduct.csv"), [Delimiter=",", Columns=6, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"ProductKey", Int64.Type},
        {"ProductId", type text},
        {"ProductFamily", type text},
        {"ProductName", type text},
        {"IdealCycleTimeSeconds", type number},
        {"IdealCycleTimeMinutes", type number}
    })
in
    #"Changed Type";

// DimReason
let
    Source = Csv.Document(File.Contents(DataRootPath & "\dimensions\DimReason.csv"), [Delimiter=",", Columns=4, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"ReasonKey", Int64.Type},
        {"ReasonCode", type text},
        {"ReasonCategory", type text},
        {"ReasonDescription", type text}
    })
in
    #"Changed Type";


// --------------------------------------------------------------------------
// 3. FACT TRANSFORMATIONS
// --------------------------------------------------------------------------

// FactProduction
let
    Source = Csv.Document(File.Contents(DataRootPath & "\facts\FactProduction.csv"), [Delimiter=",", Columns=9, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"ProductionKey", Int64.Type},
        {"DateKey", Int64.Type},
        {"ShiftKey", Int64.Type},
        {"MachineKey", Int64.Type},
        {"ProductKey", Int64.Type},
        {"TargetUnits", Int64.Type},
        {"ProducedUnits", Int64.Type},
        {"GoodUnits", Int64.Type},
        {"RejectedUnits", Int64.Type}
    })
in
    #"Changed Type";

// FactDowntime
let
    Source = Csv.Document(File.Contents(DataRootPath & "\facts\FactDowntime.csv"), [Delimiter=",", Columns=7, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"DowntimeKey", Int64.Type},
        {"DateKey", Int64.Type},
        {"ShiftKey", Int64.Type},
        {"MachineKey", Int64.Type},
        {"ReasonKey", Int64.Type},
        {"DowntimeMinutes", type number},
        {"Planned", Int64.Type}
    })
in
    #"Changed Type";

// FactQuality
let
    Source = Csv.Document(File.Contents(DataRootPath & "\facts\FactQuality.csv"), [Delimiter=",", Columns=7, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"QualityKey", Int64.Type},
        {"DateKey", Int64.Type},
        {"ShiftKey", Int64.Type},
        {"MachineKey", Int64.Type},
        {"ProductKey", Int64.Type},
        {"DefectReasonKey", Int64.Type},
        {"DefectCount", Int64.Type}
    })
in
    #"Changed Type";

// FactEnergy
let
    Source = Csv.Document(File.Contents(DataRootPath & "\facts\FactEnergy.csv"), [Delimiter=",", Columns=5, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"EnergyKey", Int64.Type},
        {"DateKey", Int64.Type},
        {"ShiftKey", Int64.Type},
        {"MachineKey", Int64.Type},
        {"EnergyKWh", type number}
    })
in
    #"Changed Type";

// FactSensor
let
    Source = Csv.Document(File.Contents(DataRootPath & "\facts\FactSensor.csv"), [Delimiter=",", Columns=8, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"SensorKey", Int64.Type},
        {"DateKey", Int64.Type},
        {"MachineKey", Int64.Type},
        {"SensorName", type text},
        {"SensorValue", type number},
        {"external_machine_id", type text},
        {"is_external", Int64.Type},
        {"UDI", Int64.Type}
    })
in
    #"Changed Type";

// FactDQExceptions
let
    Source = Csv.Document(File.Contents(DataRootPath & "\exceptions\FactDQExceptions.csv"), [Delimiter=",", Columns=9, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"ExceptionKey", Int64.Type},
        {"ExecutionTimestamp", type text},
        {"SourceTable", type text},
        {"RecordIdentifier", type text},
        {"RuleViolated", type text},
        {"Severity", type text},
        {"Disposition", type text},
        {"Description", type text},
        {"RawPayload", type text}
    })
in
    #"Changed Type";
