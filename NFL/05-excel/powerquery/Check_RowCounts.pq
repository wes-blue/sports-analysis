/*
  Check_RowCounts                                                   version 2.001
  Purpose:  rows per season x season_type in Stats_Raw compared with what the pipeline says it published (seasons.csv,
            via Published_Seasons), split into player rows and team D/ST rows. Replaces the baked-in 1.x baseline.
  Inputs:   Stats_Raw, Published_Seasons (queries only).
  Output:   season | season_type | Season_Status | Max_Week | Published_Player_Rows | Workbook_Player_Rows
            | Published_DST_Rows | Workbook_DST_Rows | Status
            Status values: PASS | FAIL (counts differ: refresh again; if it persists the data folder is incomplete)
                           | NOT PUBLISHED (the window asks for a season the pipeline has not published)
                           | NOT IN seasons.csv (rows the index does not list)
  Load:     table on the Checks sheet (see WORKBOOK-REQUIREMENTS.md).
  Firewall: references only other queries (Stats_Raw, Published_Seasons) (D-009).
*/
let
    Keys = {"season", "season_type"},

    // 1. Workbook counts per season and season type (D/ST rows have position "DST", CONTRACTS.md 3)
    Counted = Table.Group(
        Stats_Raw,
        Keys,
        {
            {"Workbook_Player_Rows", (t) => Table.RowCount(Table.SelectRows(t, each [position] <> "DST")), Int64.Type},
            {"Workbook_DST_Rows", (t) => Table.RowCount(Table.SelectRows(t, each [position] = "DST")), Int64.Type}
        }
    ),

    // 2. Every published (or requested but unpublished) season row, with the workbook counts joined on
    Joined = Table.ExpandTableColumn(
        Table.NestedJoin(Published_Seasons, Keys, Counted, Keys, "W", JoinKind.LeftOuter),
        "W", {"Workbook_Player_Rows", "Workbook_DST_Rows"}
    ),
    Zero = (n) => if n = null then 0 else n,
    Compared = Table.FromRecords(
        List.Transform(Table.ToRecords(Joined), (r) =>
            [
                season = r[season],
                season_type = r[season_type],
                Season_Status = r[season_status],
                Max_Week = r[max_week],
                Published_Player_Rows = r[player_rows],
                Workbook_Player_Rows = Zero(r[Workbook_Player_Rows]),
                Published_DST_Rows = r[dst_rows],
                Workbook_DST_Rows = Zero(r[Workbook_DST_Rows]),
                Status =
                    if r[season_status] = "not published" then "NOT PUBLISHED"
                    else if Zero(r[player_rows]) = Zero(r[Workbook_Player_Rows]) and Zero(r[dst_rows]) = Zero(r[Workbook_DST_Rows]) then "PASS"
                    else "FAIL"
            ]),
        type table [season = Int64.Type, season_type = text, Season_Status = nullable text, Max_Week = nullable number,
                    Published_Player_Rows = nullable number, Workbook_Player_Rows = Int64.Type,
                    Published_DST_Rows = nullable number, Workbook_DST_Rows = Int64.Type, Status = text]
    ),

    // 3. Workbook rows for a season / type that seasons.csv does not list (should never happen)
    Unlisted = Table.NestedJoin(Counted, Keys, Published_Seasons, Keys, "P", JoinKind.LeftAnti),
    UnlistedRows = Table.FromRecords(
        List.Transform(Table.ToRecords(Unlisted), (r) =>
            [season = r[season], season_type = r[season_type], Season_Status = null, Max_Week = null,
             Published_Player_Rows = null, Workbook_Player_Rows = r[Workbook_Player_Rows],
             Published_DST_Rows = null, Workbook_DST_Rows = r[Workbook_DST_Rows], Status = "NOT IN seasons.csv"]),
        Value.Type(Compared)
    ),
    Result = Table.Sort(Table.Combine({Compared, UnlistedRows}), {{"season", Order.Ascending}, {"season_type", Order.Descending}})
in
    Result
