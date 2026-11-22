    // ===== Season window 1.006: IDENTICAL in Stats_Raw, Pipeline_Scored and Published_Seasons. Never edit one copy alone. =====
    // "Latest" = the newest season in the published seasons.csv; Latest-N counts back from it.
    W_ReadText = (name as text) as text =>
        let v = Record.FieldOrDefault(DL_Config, name, null)
        in if v = null or Text.Trim(Text.From(v)) = ""
           then error Error.Record("Config.Error", "tblConfig: setting '" & name & "' is missing or blank")
           else Text.Trim(Text.From(v)),
    W_Index = Table.TransformColumnTypes(
        Table.SelectColumns(ReadCsv("seasons.csv"), {"season", "season_type", "player_rows", "dst_rows", "max_week", "season_status", "refreshed_utc"}),
        {{"season", Int64.Type}, {"season_type", type text}, {"player_rows", Int64.Type}, {"dst_rows", Int64.Type},
         {"max_week", Int64.Type}, {"season_status", type text}, {"refreshed_utc", type text}},
        "en-US"
    ),
    W_Published = List.Sort(List.Distinct(List.RemoveNulls(W_Index[season]))),
    W_Latest =
        if List.Count(W_Published) = 0
        then error Error.Record("DataSource.Error", "seasons.csv in the data folder lists no season: the pipeline has not published any data yet")
        else List.Max(W_Published),
    W_SeasonText = (season as number) as text => Number.ToText(Number.Round(season, 0), "0", "en-US"),
    // Year, Latest or Latest-N (N = 0..30; case-insensitive; spaces and non-breaking spaces ignored)
    W_Resolve = (name as text) as number =>
        let
            Raw = W_ReadText(name),
            U = Text.Upper(Text.Replace(Text.Replace(Raw, " ", ""), Character.FromNumber(160), "")),
            Digits = (t as text) as logical => t <> "" and Text.Select(t, {"0".."9"}) = t,
            Bad = error Error.Record("Config.Error", "tblConfig: setting '" & name & "' must be a year such as 2017, Latest, or Latest-N with N from 0 to 30 (found: " & Raw & ")"),
            Offset = if Text.StartsWith(U, "LATEST-") then Text.Middle(U, 7) else null,
            Resolved =
                if U = "LATEST" then W_Latest
                else if Offset <> null then
                    (if Digits(Offset) and Number.From(Offset) <= 30 then W_Latest - Number.From(Offset) else Bad)
                else if Digits(U) then Number.From(U)
                else Bad
        in
            if Resolved < 1999
            then error Error.Record("Config.Error", "tblConfig: setting '" & name & "' resolves to " & W_SeasonText(Resolved) & ", but nflverse weekly player stats start in 1999")
            else Resolved,
    W_Start = W_Resolve("StartSeason"),
    W_End = W_Resolve("EndSeason"),
    W_TypesSetting = Text.Upper(Text.Remove(W_ReadText("SeasonTypes"), {" ", Character.FromNumber(160)})),
    W_Types =
        if W_TypesSetting = "REG" then {"REG"}
        else if W_TypesSetting = "POST" then {"POST"}
        else if W_TypesSetting = "REG+POST" then {"REG", "POST"}
        else error Error.Record("Config.Error", "tblConfig: SeasonTypes must be REG, POST or REG+POST (found: " & W_TypesSetting & ")"),
    // Published seasons inside the window (a season is read only if seasons.csv lists it)
    W_Seasons =
        if W_Start > W_End
        then error Error.Record("Config.Error", "tblConfig: StartSeason (" & W_SeasonText(W_Start) & ") is after EndSeason (" & W_SeasonText(W_End) & ")")
        else
            let InWindow = List.Select(W_Published, each _ >= W_Start and _ <= W_End)
            in if List.Count(InWindow) = 0
               then error Error.Record("Config.Error", "No published season between " & W_SeasonText(W_Start) & " and " & W_SeasonText(W_End)
                    & ". The pipeline has published " & W_SeasonText(List.Min(W_Published)) & " to " & W_SeasonText(W_Latest) & ": change StartSeason / EndSeason on the Config sheet.")
               else InWindow,
    // ===== end of season window =====
