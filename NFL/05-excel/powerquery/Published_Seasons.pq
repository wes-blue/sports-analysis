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
    // ===== DataLocation resolver 2.001: IDENTICAL in every query that reads published CSVs. Never edit one copy alone. =====
    // tblConfig as a record [Setting = Value]; blank Setting rows are ignored.
    DL_ConfigTable = Table.SelectRows(
        Excel.CurrentWorkbook(){[Name = "tblConfig"]}[Content],
        each [Setting] <> null and Text.Trim(Text.From([Setting])) <> ""
    ),
    DL_Config = Record.FromList(DL_ConfigTable[Value], List.Transform(DL_ConfigTable[Setting], each Text.Trim(Text.From(_)))),
    // DataLocation: a web address starting with http (shipped: the published data on GitHub); a folder path; or blank = automatic local search
    DL_Setting = let v = Record.FieldOrDefault(DL_Config, "DataLocation", null) in if v = null then "" else Text.Trim(Text.From(v)),
    DL_IsWeb = Text.StartsWith(Text.Lower(DL_Setting), "http"),
    DL_Shipped = "https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/",
    // Named cell WorkbookFolder: the folder that holds this workbook (formula on the Config sheet); "" when unreadable
    DL_WorkbookFolder =
        let
            t = try Excel.CurrentWorkbook(){[Name = "WorkbookFolder"]}[Content] otherwise null,
            v = if t = null then null else (try Table.Column(t, Table.ColumnNames(t){0}){0} otherwise null)
        in
            if v = null then "" else Text.Trim(Text.From(v)),
    DL_AsFolder = (p as text) as text => let s = Text.Replace(p, "/", "\") in if Text.EndsWith(s, "\") then s else s & "\",
    DL_Parent = (folder as text) as text =>
        let f = Text.TrimEnd(Text.Replace(folder, "/", "\"), "\")
        in if Text.Contains(f, "\") then Text.BeforeDelimiter(f, "\", {0, RelativePosition.FromEnd}) & "\"
           else error Error.Record("DataLocation.Error", "Cannot work out the parent of the workbook folder '" & folder & "'. On the Config sheet, set DataLocation to " & DL_Shipped & " (the published data) or to the full path of a 04-data folder."),
    // Local search (DataLocation blank): the 04-data folder beside the workbook's folder (05-excel or 08-releases in a copy of NFL), or inside it
    DL_Candidates =
        if DL_IsWeb then {}
        else if DL_Setting <> "" then {DL_AsFolder(DL_Setting)}
        else if DL_WorkbookFolder = "" then
            error Error.Record("DataLocation.Error", "DataLocation on the Config sheet is blank, so the workbook looks for a 04-data folder on this PC, but the named cell WorkbookFolder is blank or shows an error (has the workbook been saved?). To read the published data from the web, set DataLocation to " & DL_Shipped & " ; to read a folder, save the workbook or type the folder's full path into DataLocation.")
        else if Text.StartsWith(Text.Lower(DL_WorkbookFolder), "http") then
            error Error.Record("DataLocation.Error", "DataLocation on the Config sheet is blank, so the workbook looks for a 04-data folder on this PC, but Excel reports this workbook's folder as a web address (" & DL_WorkbookFolder & "), as it does in a OneDrive or SharePoint folder. Set DataLocation to " & DL_Shipped & " to read the published data from the web, or to the LOCAL path of a 04-data folder.")
        else {DL_Parent(DL_WorkbookFolder) & "04-data\", DL_AsFolder(DL_WorkbookFolder) & "04-data\"},
    // A folder counts as found when it holds a non-empty status.csv (the pipeline always publishes it)
    DL_HasData = (folder as text) as logical => (try Binary.Length(File.Contents(folder & "status.csv")) otherwise 0) > 0,
    DL_Folder =
        if DL_IsWeb then null
        else
            let Found = List.Select(DL_Candidates, DL_HasData)
            in if List.Count(Found) > 0 then Found{0}
               else error Error.Record("DataLocation.Error", "No published pipeline data (status.csv) found in: " & Text.Combine(DL_Candidates, "  and  ") & ". On the Config sheet, set DataLocation to " & DL_Shipped & " (the published data, read from the web) or to the full path of a folder that holds status.csv."),
    // Web: a fixed site (scheme + host, e.g. https://raw.githubusercontent.com) plus RelativePath, so Excel asks for
    // credentials (Anonymous) and the privacy level once, for the site, whatever the rest of the address is.
    DL_WebBase = if Text.EndsWith(DL_Setting, "/") then DL_Setting else DL_Setting & "/",
    DL_WebRest = Text.AfterDelimiter(DL_WebBase, "://"),
    DL_WebSite =
        if not Text.Contains(DL_WebBase, "://") or Text.BeforeDelimiter(DL_WebRest, "/") = ""
        then error Error.Record("DataLocation.Error", "DataLocation on the Config sheet starts with http but is not a web address: '" & DL_Setting & "'. The published data is at " & DL_Shipped)
        else Text.BeforeDelimiter(DL_WebBase, "://") & "://" & Text.BeforeDelimiter(DL_WebRest, "/"),
    DL_WebPath = Text.AfterDelimiter(DL_WebRest, "/"),
    DL_WebAdvice = (status as number) as text =>
        if status = 404 then
            ". Nothing is published at that address. If you are setting the workbook up and this is the shipped address, the data is not on GitHub's main branch yet (the pull request has not been merged): Refresh All again once it is. Otherwise check DataLocation on the Config sheet: it must be the address of the folder that holds status.csv (shipped value " & DL_Shipped & "). A private repository also answers 404."
        else if status = 401 or status = 403 then
            ". GitHub refused the request: the address needs a login (a private repository cannot be read this way) or GitHub is limiting requests. Wait a few minutes and Refresh All again; if it stays, check DataLocation on the Config sheet."
        else if status = 408 or status = 429 or status >= 500 then
            ". GitHub is busy or limiting requests. Wait a few minutes and Refresh All again."
        else ". Check DataLocation on the Config sheet.",
    ReadData = (relativePath as text) as binary =>
        if DL_IsWeb then
            let
                Response = Web.Contents(DL_WebSite, [RelativePath = DL_WebPath & relativePath, ManualStatusHandling = {400, 401, 403, 404, 408, 429, 500, 502, 503, 504}]),
                Status = Value.Metadata(Response)[Response.Status]
            in
                if Status = 200 then Response
                else error Error.Record("DataLocation.Error", "HTTP " & Number.ToText(Status) & " reading " & DL_WebBase & relativePath & DL_WebAdvice(Status))
        else File.Contents(DL_Folder & Text.Replace(relativePath, "/", "\")),
    // Published CSV: UTF-8, comma, RFC 4180 quoting, header row; every value still text here
    ReadCsv = (relativePath as text) as table =>
        Table.PromoteHeaders(
            Csv.Document(ReadData(relativePath), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
            [PromoteAllScalars = true]
        ),
    // ===== end of DataLocation resolver =====
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
