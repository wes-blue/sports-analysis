/*
  Stats_Raw                                                         version 2.001
  Purpose:  the pipeline's scoring-ready player_week rows (player-games plus team D/ST games, long-TD and dst_* metrics
            already merged) for the season window and season type(s) set in tblConfig, combined and typed.
  Inputs:   tblConfig (StartSeason, EndSeason, SeasonTypes, DataLocation), named cell WorkbookFolder,
            <data>/seasons.csv and <data>/player_week/player_week_<season>.csv (CONTRACTS.md 5.1, 5.4).
  Output:   season, week (whole numbers); season_type, player_id, player_display_name, position, position_group, team,
            opponent_team (text); every other column a number, blank = null.
  Load:     connection only.
  Firewall: reads tblConfig, WorkbookFolder and the data files; references NO other query (D-009).
  Notes:    "Latest" / "Latest-N" count from the newest season in seasons.csv. Blank fields become null column-wise
            (one Table.ReplaceValue over all columns) BEFORE typing, so no per-cell conversion errors are raised;
            any other non-numeric text in a metric column becomes null (as in 1.x).
*/
let
//@@RESOLVER@@
//@@WINDOW@@
    // 1. One file per published season in the window, combined (columns are unioned by name)
    Files = List.Transform(W_Seasons, each ReadCsv("player_week/player_week_" & W_SeasonText(_) & ".csv")),
    Combined = Table.Combine(Files),

    // 2. The nine identity columns are required (CONTRACTS.md 5.1)
    IdentityWhole = {"season", "week"},
    IdentityText = {"season_type", "player_id", "player_display_name", "position", "position_group", "team", "opponent_team"},
    AllColumns = Table.ColumnNames(Combined),
    MissingIdentity = List.Difference(IdentityWhole & IdentityText, AllColumns),
    Checked =
        if List.Count(MissingIdentity) > 0
        then error Error.Record("DataSource.Error", "player_week files lack column(s) " & Text.Combine(MissingIdentity, ", ") & ": the data does not follow data contract version 1 (see Pipeline_Status)")
        else Combined,

    // 3. Keep the requested season types (before typing: fewer rows to convert)
    Filtered = Table.SelectRows(Checked, each List.Contains(W_Types, [season_type])),

    // 4. Blank means null (CONTRACTS.md 5): one column-wise replace over every column
    BlankToNull = Table.ReplaceValue(Filtered, "", null, Replacer.ReplaceValue, AllColumns),

    // 5. Typing, independent of the PC's regional settings (en-US: "." is the decimal mark).
    //    Text: identity columns plus the nflverse text columns PublishExtraColumns may add. Everything else is a number.
    ExtraText = {"player_name", "headshot_url", "game_id", "fg_made_list", "fg_missed_list", "fg_blocked_list"},
    TextPresent = List.Select(IdentityText & ExtraText, each List.Contains(AllColumns, _)),
    NumericColumns = List.Difference(AllColumns, TextPresent & IdentityWhole),
    Typed = Table.TransformColumnTypes(
        BlankToNull,
        List.Transform(IdentityWhole, each {_, Int64.Type})
            & List.Transform(TextPresent, each {_, type text})
            & List.Transform(NumericColumns, each {_, type number}),
        "en-US"
    ),

    // 6. Error safety (as in 1.x): a metric value that is not a number becomes null; scoring counts null as 0
    Result = Table.ReplaceErrorValues(Typed, List.Transform(NumericColumns, each {_, null}))
in
    Result
