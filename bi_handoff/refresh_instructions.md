# FactoryPulse 360 — Power BI & Excel Refresh & Ingestion Guide

## Executive Summary
This document provides complete, reproducible step-by-step instructions for manufacturing analytics authors to import, configure, and refresh the FactoryPulse 360 semantic data model within **Microsoft Power BI Desktop / Power BI Service** and **Microsoft Excel Power Pivot**.

---

## 1. Architecture & Ingestion Paths
Downstream authors can ingest FactoryPulse 360 data via two supported methods:
1. **Option A (Recommended for Portability)**: Ingest cleaned dimension and fact CSVs directly from `bi_handoff/dimensions/`, `bi_handoff/facts/`, and `bi_handoff/exceptions/`.
2. **Option B (Direct Warehouse Connection)**: Connect directly to the SQLite curated data warehouse (`data/factorypulse.db`) via the SQLite ODBC Driver.

---

## 2. Power BI Setup Instructions (Option A: Portable CSV Package)

### Step 1: Define Environment Parameters
1. Open **Power BI Desktop**.
2. Navigate to **Home** > **Transform Data** (opens Power Query Editor).
3. In Power Query, click **Home** > **Manage Parameters** > **New Parameter**:
   - **Name**: `DataRootPath`
   - **Type**: `Text`
   - **Current Value**: `E:\FactoryPulse-360\bi_handoff` (or your local repo folder path).

### Step 2: Ingest Dimensions
For each dimension CSV in `dimensions/` (`DimDate.csv`, `DimShift.csv`, `DimLine.csv`, `DimMachine.csv`, `DimProduct.csv`, `DimReason.csv`):
1. In Power Query, select **New Source** > **CSV** (or **Blank Query** using parameter M script in `power_query/transformations.m`).
2. Point source to `DataRootPath & "\dimensions\" & "<TableName>.csv"`.
3. Set data types explicitly:
   - All `*Key` columns: Whole Number (`Int64.Type`).
   - `Date`: Date (`type date`).
   - Continuous duration / intensity columns: Decimal Number (`type number`).
   - Names / Codes: Text (`type text`).

### Step 3: Ingest Fact Tables
For each fact CSV in `facts/` (`FactProduction.csv`, `FactDowntime.csv`, `FactQuality.csv`, `FactEnergy.csv`, `FactSensor.csv`):
1. Create query pointing to `DataRootPath & "\facts\" & "<TableName>.csv"`.
2. Ensure surrogate keys are mapped as Whole Number (`Int64.Type`).
3. For `FactSensor`, note that `SensorValue` is continuous Decimal (`type number`), and `is_external` is Whole Number (`Int64.Type`).

### Step 4: Ingest Exception Register
1. Create query pointing to `DataRootPath & "\exceptions\FactDQExceptions.csv"`.
2. Keep this table isolated (disconnected from relationships) to serve as a data governance / audit page.

### Step 5: Configure Semantic Model & Relationships
1. Click **Close & Apply** in Power Query.
2. In Power BI, switch to the **Model View** tab.
3. Configure the relationships as specified in `model_relationships.md`:
   - All relationships: **Many to One (`*:1`)**, **Single** cross-filter direction.
   - Verify zero many-to-many relationships.
4. Mark `DimDate` as an official Date Table:
   - Right-click `DimDate` in data pane > **Mark as date table** > select `Date` column.

### Step 6: Import DAX Measures
1. Create a dedicated measure table: **Home** > **Enter Data** > Name table `_Measures`.
2. Copy and paste the validated DAX measures from `bi_handoff/dax/measures.dax` into the `_Measures` table.
3. Validate overall KPI cards against `bi_handoff/kpi_reference.csv`:
   - **Availability**: 99.42%
   - **Performance**: 19.51%
   - **Quality**: 95.25%
   - **OEE**: 18.48%
   - **Energy Intensity**: 0.7306 kWh/unit

---

## 3. Microsoft Excel Power Pivot Setup Instructions

### Step 1: Enable Power Pivot
1. Open **Microsoft Excel** (Excel 2016, 2019, 2021, or Microsoft 365).
2. Go to **File** > **Options** > **Add-ins**.
3. Under **Manage**, select **COM Add-ins** > click **Go**.
4. Check **Microsoft Power Pivot for Excel** and click **OK**.

### Step 2: Load Data into Data Model
1. In Excel, go to the **Data** tab > **Get Data** > **From File** > **From Folder** (or **From Text/CSV**).
2. Select `bi_handoff/dimensions` and `bi_handoff/facts`.
3. In the Load dialog, select **Load To...** > choose **Only Create Connection** and check **Add this data to the Data Model**.

### Step 3: Configure Diagram View in Power Pivot
1. Click the **Power Pivot** tab > **Manage** (opens Power Pivot window).
2. Click **Diagram View**.
3. Drag foreign keys from fact tables to primary keys in dimension tables to establish the exact 1-to-many relationships defined in `model_relationships.md`.
4. In the calculation area below any fact table, enter the standard DAX formulas provided in `dax/measures.dax`.

---

## 4. Scheduled Refresh & Operational Cadence
- **Local Desktop Refresh**: Click **Home** > **Refresh** in Power BI Desktop or **Data** > **Refresh All** in Excel.
- **Power BI Service (Automated Refresh)**:
  - If deploying to Power BI Service via OneDrive/SharePoint, set `DataRootPath` to the SharePoint folder URL.
  - If hosting on local file servers or on-premise SQLite warehouse, install the **On-premises Data Gateway (Standard Mode)**, register the data source, and configure scheduled refresh (e.g. daily at 06:00 UTC).
- **Data Pipeline Trigger**:
  - Whenever the upstream data pipeline generates new curated data (`python -m src.run_pipeline`), re-run `scratch/populate_bi_handoff.py` to sync `bi_handoff/` CSVs, and trigger a Power BI refresh.
