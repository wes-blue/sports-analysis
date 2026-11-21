/*
  Published_Seasons                                                 version 2.001
  Purpose:  the pipeline's season index (seasons.csv) for the workbook's season window and season type(s), plus one row
            per season and type the window asks for but the pipeline has not published. Feeds Check_RowCounts, which
            cannot read the file itself (firewall rule D-009).
  Inputs:   tblConfig (StartSeason, EndSeason, SeasonTypes, DataLocation), named cell WorkbookFolder, <data>/seasons.csv.
  Output:   season (whole number), season_type, player_rows, dst_rows, max_week (whole numbers, null when not published),
            season_status (complete | in_progress | not published), refreshed_utc.
  Load:     connection only.
  Firewall: reads tblConfig, WorkbookFolder and seasons.csv; references NO other query (D-009).
*/
let
//@@RESOLVER@@
//@@WINDOW@@
    // 1. Published rows inside the window and season types
    InWindow = Table.SelectRows(W_Index, each List.Contains(W_Seasons, [season]) and List.Contains(W_Types, [season_type])),

    // 2. Seasons the window asks for that seasons.csv does not list at all
    NotPublished = if List.Count(W_Seasons) = 0 then {} else List.Select(List.Numbers(W_Start, W_End - W_Start + 1), each not List.Contains(W_Published, _)),
    MissingRows = Table.FromRecords(
        List.Combine(List.Transform(NotPublished, (s) => List.Transform(W_Types, (t) =>
            [season = s, season_type = t, player_rows = null, dst_rows = null, max_week = null, season_status = "not published", refreshed_utc = null]))),
        type table [season = Int64.Type, season_type = text, player_rows = nullable number, dst_rows = nullable number,
                    max_week = nullable number, season_status = text, refreshed_utc = nullable text]
    ),
    Result = Table.Sort(Table.Combine({InWindow, MissingRows}), {{"season", Order.Ascending}, {"season_type", Order.Descending}})
in
    Result
