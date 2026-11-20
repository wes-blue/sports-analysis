/*
  Golden_Keys                                                       version 2.001
  Purpose:  the golden-sample keys (season, week, season_type, player_id) plus the expected FF_<League> values,
            read from the workbook table tblGolden. Feeds Check_Golden.
  Inputs:   tblGolden (seeded from 06-qa/fixtures/golden_sample.csv).
  Output:   season, week, season_type, player_id, player_display_name, FF_<League>... (expected values)
  Load:     connection only.
  Changed from 1.x (1.004): header only. season and week stay type number; M compares numbers by value, so they join
            with Stats_Scored's whole-number keys.
  Firewall: reads ONE source (the workbook table tblGolden) and references no other query (D-009).
*/
let
    // 1. Golden table as typed in the workbook (headers are lower-case keys plus FF_<League> expected columns)
    Source = Excel.CurrentWorkbook(){[Name = "tblGolden"]}[Content],

    // 2. Keep only rows that have a player_id (ignores empty table rows)
    Filled = Table.SelectRows(Source, each [player_id] <> null and Text.Trim(Text.From([player_id])) <> ""),

    // 3. Columns to keep: the four keys, the display name (for readable examples) and every FF_<League> column
    KeyColumns = {"season", "week", "season_type", "player_id"},
    FFColumns = List.Select(Table.ColumnNames(Filled), each Text.StartsWith(_, "FF_")),
    Kept = Table.SelectColumns(Filled, KeyColumns & {"player_display_name"} & FFColumns),

    // 4. Types: keys must match Stats_Scored's types exactly so the join works
    Typed = Table.TransformColumnTypes(
        Kept,
        {{"season", type number}, {"week", type number}, {"season_type", type text}, {"player_id", type text}, {"player_display_name", type text}}
            & List.Transform(FFColumns, each {_, type number}),
        "en-US"
    )
in
    Typed
