/*
  Pipeline_Scored                                                   version 2.001
  Purpose:  the pipeline's own scores (scored_<season>.csv) for the same season window and season type(s) as Stats_Raw,
            so Check_Parity can compare the workbook's FF_<League> columns with them.
  Inputs:   tblConfig (StartSeason, EndSeason, SeasonTypes, DataLocation), named cell WorkbookFolder,
            <data>/seasons.csv and <data>/scored/scored_<season>.csv (CONTRACTS.md 5.2, 5.4).
  Output:   season, week (whole numbers); season_type, player_id, player_display_name, position, team (text);
            fantasy_points, fantasy_points_ppr and one FF_<League> per league the pipeline scored (numbers, blank = null).
  Load:     connection only. Not added to the Data Model: it only feeds Check_Parity, and a second 180,000-row copy of
            the scores in the Data Model would add size and refresh time without adding anything to the pivots.
  Firewall: reads tblConfig, WorkbookFolder and the data files; references NO other query (D-009).
*/
let
//@@RESOLVER@@
//@@WINDOW@@
    // 1. One file per published season in the window, combined
    Files = List.Transform(W_Seasons, each ReadCsv("scored/scored_" & W_SeasonText(_) & ".csv")),
    Combined = Table.Combine(Files),

    // 2. Required columns (CONTRACTS.md 5.2)
    IdentityWhole = {"season", "week"},
    IdentityText = {"season_type", "player_id", "player_display_name", "position", "team"},
    AllColumns = Table.ColumnNames(Combined),
    MissingIdentity = List.Difference(IdentityWhole & IdentityText, AllColumns),
    Checked =
        if List.Count(MissingIdentity) > 0
        then error Error.Record("DataSource.Error", "scored files lack column(s) " & Text.Combine(MissingIdentity, ", ") & ": the data does not follow data contract version 1 (see Pipeline_Status)")
        else Combined,

    // 3. Season types, blanks to null, typing (en-US), as in Stats_Raw
    Filtered = Table.SelectRows(Checked, each List.Contains(W_Types, [season_type])),
    BlankToNull = Table.ReplaceValue(Filtered, "", null, Replacer.ReplaceValue, AllColumns),
    NumericColumns = List.Difference(AllColumns, IdentityText & IdentityWhole),
    Typed = Table.TransformColumnTypes(
        BlankToNull,
        List.Transform(IdentityWhole, each {_, Int64.Type})
            & List.Transform(IdentityText, each {_, type text})
            & List.Transform(NumericColumns, each {_, type number}),
        "en-US"
    ),
    Result = Table.ReplaceErrorValues(Typed, List.Transform(NumericColumns, each {_, null}))
in
    Result
