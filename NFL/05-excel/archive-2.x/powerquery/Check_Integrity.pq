/*
  Check_Integrity                                                   version 2.001
  Purpose:  structural controls on the workbook's own data: scoring keeps every row (Stats_Scored = Stats_Raw), the key
            season, week, season_type, player_id is unique (the workbook's view of the pipeline's G-GRAIN gate), and the
            team D/ST rows are reported for information.
  Inputs:   Stats_Raw, Stats_Scored (queries only).
  Output:   Check | Expected | Actual | Status        Status values: PASS | FAIL | INFO
  Load:     table on the Checks sheet (see WORKBOOK-REQUIREMENTS.md).
  Changed from 1.x (1.005): Stats_Scored no longer appends D/ST rows, so the first check compares all rows; the key
            uniqueness check is new.
  Firewall: references only other queries (Stats_Raw, Stats_Scored); no direct data-source access (D-009).
*/
let
    // 1. Counts
    Keys = {"season", "week", "season_type", "player_id"},
    RawRows = Table.RowCount(Stats_Raw),
    ScoredRows = Table.RowCount(Stats_Scored),
    DistinctKeys = Table.RowCount(Table.Distinct(Table.SelectColumns(Stats_Raw, Keys))),
    DstRows = Table.RowCount(Table.SelectRows(Stats_Raw, each [position] = "DST")),

    // 2. One row per check
    Rows = {
        [Check = "Rows: Stats_Scored = Stats_Raw (scoring keeps every row)", Expected = RawRows, Actual = ScoredRows,
         Status = if RawRows = ScoredRows then "PASS" else "FAIL"],
        [Check = "Unique key (season, week, season_type, player_id) in Stats_Raw", Expected = RawRows, Actual = DistinctKeys,
         Status = if RawRows = DistinctKeys then "PASS" else "FAIL"],
        [Check = "Team D/ST rows in Stats_Raw (information)", Expected = null, Actual = DstRows, Status = "INFO"]
    }
in
    Table.FromRecords(
        Rows,
        type table [Check = text, Expected = nullable number, Actual = Int64.Type, Status = text]
    )
