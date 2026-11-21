/*
  Check_Rules_Drift                                                 version 2.001
  Purpose:  lists every scoring rule in which the workbook differs from the rules the pipeline used for the published data,
            per league, so a Check_Parity difference can be explained. Compared: which leagues are active, each league's
            weight per metric (blank = 0), each metric's position gate (Applies_To), each league's bonus bands (identical
            bands are summed, because overlapping bands stack), and RoundDecimals.
  Inputs:   tblConfig, named cell WorkbookFolder, tblLeagues, tblScoring, tblBonus (optional) and the published copies
            <data>/config/leagues.csv, config/scoring_weights.csv, config/bonus_rules.csv, config/pipeline_config.csv (CONTRACTS.md 5.4).
  Output:   League | Kind (Setting | League | Weight | Gate | Band) | Item | Workbook | Pipeline | Status
            Status values: changed | only in workbook | only in pipeline | same (one summary row when nothing differs)
  Load:     table on the Checks sheet (see WORKBOOK-REQUIREMENTS.md).
  Firewall: reads workbook tables and data files only; references NO other query (D-009). It therefore parses tblScoring and
            tblBonus itself instead of using Scoring_Weights / Bonus_Rules, and it never raises an error on a bad cell:
            a value that is not a number is shown as text and reported as changed.
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
    // 1. Helpers: culture-independent numbers and text
    Clean = (v as any) as text => if v = null then "" else if v is number then Text.From(v, "en-US") else Text.Trim(Text.From(v)),
    ToNum = (v as any) as nullable number =>
        if v = null then null else if v is number then v
        else let t = Text.Trim(Text.From(v)) in if t = "" then null else try Number.From(t, "en-US") otherwise null,
    // display form of a cell; blank shown as given by 'blank'
    Show = (v as any, blank as text) as text => let t = Clean(v) in if t = "" then blank else (let n = ToNum(v) in if n = null then t else Text.From(n, "en-US")),
    // equal as numbers when both are numbers, else as trimmed text
    Same = (a as any, b as any, blankAsZero as logical) as logical =>
        let
            na = if blankAsZero and Clean(a) = "" then 0 else ToNum(a),
            nb = if blankAsZero and Clean(b) = "" then 0 else ToNum(b)
        in
            if na <> null and nb <> null then Number.Abs(na - nb) <= 0.000000001 else Clean(a) = Clean(b),
    NormGate = (v as any) as text =>
        Text.Combine(List.Sort(List.Distinct(List.Select(Text.Split(Text.Upper(Text.Remove(Clean(v), {" ", Character.FromNumber(160)})), ","), each _ <> ""))), ","),
    IsActive = (v as any) as logical => Text.Upper(Clean(v)) = "YES",
    Row = (league as text, kind as text, item as text, wb as text, pipe as text, status as text) as record =>
        [League = league, Kind = kind, Item = item, Workbook = wb, Pipeline = pipe, Status = status],

    // 2. The two rule sets
    WbLeagues = Table.SelectRows(Excel.CurrentWorkbook(){[Name = "tblLeagues"]}[Content], each Clean([League]) <> ""),
    WbScoring = Table.SelectRows(Excel.CurrentWorkbook(){[Name = "tblScoring"]}[Content], each Clean([Metric]) <> ""),
    WbBonusSource = try Excel.CurrentWorkbook(){[Name = "tblBonus"]}[Content] otherwise null,
    WbBonus = if WbBonusSource = null then {} else List.Select(Table.ToRecords(WbBonusSource), each Clean([League]) <> "" or Clean([Metric]) <> ""),
    PipeLeagues = Table.SelectRows(ReadCsv("config/leagues.csv"), each Clean([League]) <> ""),
    PipeScoring = Table.SelectRows(ReadCsv("config/scoring_weights.csv"), each Clean([Metric]) <> ""),
    PipeBonus = List.Select(Table.ToRecords(ReadCsv("config/bonus_rules.csv")), each Clean([League]) <> "" or Clean([Metric]) <> ""),
    PipeConfig = Table.SelectRows(ReadCsv("config/pipeline_config.csv"), each Clean([Setting]) <> ""),

    // 3. RoundDecimals
    WbRound = Record.FieldOrDefault(DL_Config, "RoundDecimals", null),
    PipeRoundRows = Table.SelectRows(PipeConfig, each Clean([Setting]) = "RoundDecimals")[Value],
    PipeRound = if List.Count(PipeRoundRows) = 0 then null else PipeRoundRows{0},
    SettingRows = if Same(WbRound, PipeRound, false) then {} else {Row("(all leagues)", "Setting", "RoundDecimals", Show(WbRound, "(blank)"), Show(PipeRound, "(blank)"), "changed")},

    // 4. Leagues: compared when active on either side
    WbActive = List.Transform(List.Select(Table.ToRecords(WbLeagues), each IsActive([Active])), each Clean([League])),
    PipeActive = List.Transform(List.Select(Table.ToRecords(PipeLeagues), each IsActive([Active])), each Clean([League])),
    WbAll = List.Transform(WbLeagues[League], Clean),
    PipeAll = List.Transform(PipeLeagues[League], Clean),
    Leagues = List.Distinct(WbActive & PipeActive),
    State = (name as text, all as list, active as list) as text => if List.Contains(active, name) then "active" else if List.Contains(all, name) then "inactive" else "(absent)",
    LeagueRows = List.Transform(
        List.Select(Leagues, (l) => State(l, WbAll, WbActive) <> State(l, PipeAll, PipeActive)),
        (l) => Row(l, "League", "Active", State(l, WbAll, WbActive), State(l, PipeAll, PipeActive), "changed")
    ),

    // 5. Weights: one row per league and metric whose effective weight differs (a missing row or column counts as 0)
    WbMetrics = List.Transform(WbScoring[Metric], Clean),
    PipeMetrics = List.Transform(PipeScoring[Metric], Clean),
    AllMetrics = List.Distinct(WbMetrics & PipeMetrics),
    WbRecords = Table.ToRecords(WbScoring),
    PipeRecords = Table.ToRecords(PipeScoring),
    WbByMetric = Record.FromList(WbRecords, List.Transform(WbRecords, each Clean([Metric]))),
    PipeByMetric = Record.FromList(PipeRecords, List.Transform(PipeRecords, each Clean([Metric]))),
    Cell = (byMetric as record, metric as text, column as text) as any =>
        let r = Record.FieldOrDefault(byMetric, metric, null) in if r = null then null else Record.FieldOrDefault(r, column, null),
    Describe = (byMetric as record, metric as text, column as text, hasColumn as logical) as text =>
        if not Record.HasFields(byMetric, metric) then "(no row)"
        else if not hasColumn then "(no league column)"
        else Show(Cell(byMetric, metric, column), "0"),
    WeightRows = List.Combine(List.Transform(Leagues, (l) =>
        let
            WbHas = List.Contains(Table.ColumnNames(WbScoring), l),
            PipeHas = List.Contains(Table.ColumnNames(PipeScoring), l)
        in
            List.Transform(
                List.Select(AllMetrics, (m) => not Same(Cell(WbByMetric, m, l), Cell(PipeByMetric, m, l), true)),
                (m) => Row(l, "Weight", m, Describe(WbByMetric, m, l, WbHas), Describe(PipeByMetric, m, l, PipeHas),
                           if not Record.HasFields(PipeByMetric, m) or not PipeHas then "only in workbook"
                           else if not Record.HasFields(WbByMetric, m) or not WbHas then "only in pipeline"
                           else "changed")
            ))),

    // 6. Position gates (Applies_To), per metric present on both sides; order and case of the codes do not matter
    GateOf = (byMetric as record, metric as text) as text => NormGate(Cell(byMetric, metric, "Applies_To")),
    GateRows = List.Transform(
        List.Select(AllMetrics, (m) => Record.HasFields(WbByMetric, m) and Record.HasFields(PipeByMetric, m) and GateOf(WbByMetric, m) <> GateOf(PipeByMetric, m)),
        (m) => Row("(all leagues)", "Gate", m,
                   let g = GateOf(WbByMetric, m) in if g = "" then "(all players)" else g,
                   let g = GateOf(PipeByMetric, m) in if g = "" then "(all players)" else g, "changed")
    ),

    // 7. Bands: key = league | metric | lower | upper | gate; identical bands are summed (they stack)
    BandKey = (r as record) as text =>
        Clean(r[League]) & "|" & Clean(r[Metric]) & "|" & Show(Record.FieldOrDefault(r, "Lower", null), "") & "|"
            & Show(Record.FieldOrDefault(r, "Upper", null), "") & "|" & NormGate(Record.FieldOrDefault(r, "Applies_To", null)),
    BandTable = (rules as list) as table =>
        let
            Keyed = Table.FromRecords(
                List.Transform(rules, (r) => [Key = BandKey(r), Points = ToNum(Record.FieldOrDefault(r, "Points", null)), PointsText = Clean(Record.FieldOrDefault(r, "Points", null))]),
                type table [Key = text, Points = nullable number, PointsText = text]
            )
        in
            Table.Group(Keyed, {"Key"}, {
                {"Points", (t) => if List.Contains(t[Points], null) then null else List.Sum(t[Points]), type nullable number},
                {"PointsText", (t) => Text.Combine(t[PointsText], " + "), type text}
            }),
    WbBands = BandTable(WbBonus),
    PipeBands = BandTable(PipeBonus),
    WbBandMap = Record.FromList(Table.ToRecords(WbBands), WbBands[Key]),
    PipeBandMap = Record.FromList(Table.ToRecords(PipeBands), PipeBands[Key]),
    BandKeys = List.Distinct(WbBands[Key] & PipeBands[Key]),
    BandLabel = (key as text) as text =>
        let p = Text.Split(key, "|")
        in p{1} & " " & (if p{2} = "" then "(no min)" else p{2}) & " to " & (if p{3} = "" then "(no max)" else p{3})
            & (if p{4} = "" then "" else " [" & p{4} & "]"),
    BandShow = (b as nullable record) as text =>
        if b = null then "(no band)" else if b[Points] = null then b[PointsText] else Text.From(b[Points], "en-US") & " pts",
    BandRows = List.Transform(
        List.Select(BandKeys, (k) =>
            let a = Record.FieldOrDefault(WbBandMap, k, null), b = Record.FieldOrDefault(PipeBandMap, k, null)
            in a = null or b = null or a[Points] = null or b[Points] = null or Number.Abs(a[Points] - b[Points]) > 0.000000001),
        (k) =>
            let a = Record.FieldOrDefault(WbBandMap, k, null), b = Record.FieldOrDefault(PipeBandMap, k, null)
            in Row(Text.BeforeDelimiter(k, "|"), "Band", BandLabel(k), BandShow(a), BandShow(b),
                   if b = null then "only in workbook" else if a = null then "only in pipeline" else "changed")
    ),

    // 8. Result (one "same" row when there is no difference at all)
    AllRows = SettingRows & LeagueRows & WeightRows & GateRows & BandRows,
    Final = if List.Count(AllRows) = 0
        then {Row("(all leagues)", "Summary", "Workbook rules equal the rules of the published data", "", "", "same")}
        else AllRows
in
    Table.FromRecords(
        Final,
        type table [League = text, Kind = text, Item = text, Workbook = text, Pipeline = text, Status = text]
    )
