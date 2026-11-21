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
    EndTime TIME NOT NULL
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
    FOREIGN KEY (LineKey) REFERENCES DimLine(LineKey)
);

CREATE TABLE DimProduct (
    ProductKey INTEGER PRIMARY KEY,
    ProductId TEXT NOT NULL,
    ProductFamily TEXT NOT NULL,
    ProductName TEXT NOT NULL
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
    FOREIGN KEY (DateKey) REFERENCES DimDate(DateKey),
    FOREIGN KEY (MachineKey) REFERENCES DimMachine(MachineKey)
);

CREATE TABLE FactDQExceptions (
    ExceptionKey INTEGER PRIMARY KEY,
    SourceTable TEXT NOT NULL,
    RecordIdentifier TEXT NOT NULL,
    RuleViolated TEXT NOT NULL,
    Severity TEXT NOT NULL,
    Disposition TEXT NOT NULL,
    Description TEXT
);

-- End of schema
