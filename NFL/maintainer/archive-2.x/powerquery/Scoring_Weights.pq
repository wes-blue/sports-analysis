/*
  Scoring_Weights                                                   version 2.001
  Purpose:  one row per ACTIVE league with a record of its non-zero weights, e.g. [passing_yards = 0.04, ...], its
            position gates, and the settings downstream queries need (they may not read workbook tables themselves).
  Inputs:   tblConfig (RoundDecimals, ReconcileTolerance), tblLeagues, tblScoring.
  Output:   League | Reconcile_To | RoundDecimals | ReconcileTolerance | Weights (record, non-zero only) | Gates (record)
            | AllMetrics (list of every tblScoring metric)
  Load:     connection only.
  Changed from 1.x (1.004): adds ReconcileTolerance (tblConfig; blank or missing = 0.005, the pipeline default), so
            Check_Reconciliation uses the same tolerance as the pipeline's G-RECON gate. Everything else is unchanged.
  Gates: for the metrics in Weights that have a non-blank Applies_To in tblScoring, the list of allowed position / position_group codes
         (upper case, e.g. [def_sacks = {"DL", "LB", "DB"}]). A metric without an entry applies to all players. Applies_To is optional:
         if tblScoring has no such column, nothing is gated.
  Firewall: reads only workbook tables (tblConfig, tblLeagues, tblScoring); references no other query (D-009).
  Extra columns in tblLeagues / tblScoring (e.g. Column_Check, Metric_Check, Notes) are ignored:
  league columns are selected by NAME from tblLeagues.
*/
let
    // 1. Parameter tables
    Leagues = Excel.CurrentWorkbook(){[Name = "tblLeagues"]}[Content],
    Scoring = Excel.CurrentWorkbook(){[Name = "tblScoring"]}[Content],
    ConfigTable = Excel.CurrentWorkbook(){[Name = "tblConfig"]}[Content],
    Config = Record.FromList(ConfigTable[Value], List.Transform(ConfigTable[Setting], each Text.Trim(Text.From(_)))),

    // 2. Rounding setting (0-6): readable Config.Error if blank / non-numeric / out of range
    RoundText = let v = Record.FieldOrDefault(Config, "RoundDecimals", null) in if v = null then "" else Text.Trim(Text.From(v)),
    RoundDecimals =
        if RoundText = "" then error Error.Record("Config.Error", "tblConfig: setting 'RoundDecimals' is missing or blank")
        else
            let n = try Number.Round(Number.From(RoundText, "en-US"), 0) otherwise null
            in if n = null or n < 0 or n > 6
               then error Error.Record("Config.Error", "tblConfig: setting 'RoundDecimals' must be a whole number from 0 to 6 (found: " & RoundText & ")")
               else n,

    // 2b. Reconciliation tolerance (1.006): blank or missing = 0.005 (pipeline default); readable Config.Error if not a number >= 0
    TolText = let v = Record.FieldOrDefault(Config, "ReconcileTolerance", null) in if v = null then "" else Text.Trim(Text.From(v, "en-US")),
    ReconcileTolerance =
        if TolText = "" then 0.005
        else
            let n = try Number.From(TolText, "en-US") otherwise null
            in if n = null or n < 0
               then error Error.Record("Config.Error", "tblConfig: setting 'ReconcileTolerance' must be 0 or a small positive number (found: " & TolText & ")")
               else n,

    // 3. Active leagues: Active = Yes, League not blank
    ActiveLeagues = Table.SelectRows(
        Leagues,
        each [League] <> null
            and Text.Trim(Text.From([League])) <> ""
            and Text.Upper(Text.Trim(if [Active] = null then "" else Text.From([Active]))) = "YES"
    ),
    LeagueRows = Table.ToRecords(ActiveLeagues),
    CheckHasLeague = if List.Count(LeagueRows) = 0 then error Error.Record("Scoring.Error", "tblLeagues has no row with Active = Yes") else true,

    // 3b. An active league may not be named like a tblScoring descriptive column (it would be read as weights)
    ReservedColumns = {"metric", "category", "description", "notes", "metric_check", "applies_to"},
    ReservedUsed = List.Select(
        List.Transform(LeagueRows, each Text.Trim(Text.From([League]))),
        (n) => List.Contains(ReservedColumns, Text.Lower(n))
    ),
    CheckReserved =
        if List.Count(ReservedUsed) > 0
        then error Error.Record("Scoring.Error", "tblLeagues: league name(s) reserved for tblScoring columns: " & Text.Combine(ReservedUsed, ", ") & " (Metric, Category, Description, Notes, Metric_Check, Applies_To cannot be league names)")
        else true,

    // 4. Metrics: tblScoring rows with a non-blank Metric; duplicates are an error (Record.FromList would fail obscurely)
    ScoringRows = Table.SelectRows(Scoring, each [Metric] <> null and Text.Trim(Text.From([Metric])) <> ""),
    Metrics = List.Transform(ScoringRows[Metric], each Text.Trim(Text.From(_))),
    Duplicates = List.Select(List.Distinct(Metrics), (m) => List.Count(List.Select(Metrics, (x) => x = m)) > 1),
    CheckDuplicates =
        if List.Count(Duplicates) > 0
        then error Error.Record("Scoring.Error", "tblScoring: duplicate Metric rows: " & Text.Combine(Duplicates, ", "))
        else true,

    // 5. Weight lookup for one league: non-zero weights only, blank = 0, non-numeric = readable error
    WeightsFor = (leagueName as text) as record =>
        let
            ColumnPresent = List.Contains(Table.ColumnNames(ScoringRows), leagueName),
            Values = if ColumnPresent
                then List.Transform(Table.Column(ScoringRows, leagueName), (v) => v)
                else error Error.Record("Scoring.Error", "tblScoring has no column named '" & leagueName & "' (League names in tblLeagues must match tblScoring column headers exactly)"),
            Numbers = List.Transform(
                List.Positions(Values),
                (i) =>
                    let v = Values{i}
                    in if v = null or (v is text and Text.Trim(v) = "") then 0
                       else try Number.From(v, "en-US") otherwise error Error.Record("Scoring.Error", "tblScoring: weight for metric '" & Metrics{i} & "' in league '" & leagueName & "' is not a number: " & Text.From(v))
            ),
            NonZeroPositions = List.Select(List.Positions(Numbers), (i) => Numbers{i} <> 0)
        in
            Record.FromList(
                List.Transform(NonZeroPositions, (i) => Numbers{i}),
                List.Transform(NonZeroPositions, (i) => Metrics{i})
            ),

    // 5b. Position gates: Applies_To = comma-separated position / position_group codes, blank = all players
    ParseGate = (v as any) as nullable list =>
        if v = null then null
        else
            let
                Cleaned = Text.Upper(Text.Remove(Text.From(v), {" ", Character.FromNumber(160)})),
                Parts = List.Select(Text.Split(Cleaned, ","), each _ <> "")
            in
                if List.Count(Parts) = 0 then null else Parts,
    GateValues = if List.Contains(Table.ColumnNames(ScoringRows), "Applies_To") then Table.Column(ScoringRows, "Applies_To") else List.Repeat({null}, List.Count(Metrics)),
    GatedPositions = List.Select(List.Positions(Metrics), (i) => ParseGate(GateValues{i}) <> null),
    GateMap = Record.FromList(
        List.Transform(GatedPositions, (i) => ParseGate(GateValues{i})),
        List.Transform(GatedPositions, (i) => Metrics{i})
    ),
    GatesFor = (weights as record) as record =>
        Record.SelectFields(GateMap, List.Select(Record.FieldNames(GateMap), (m) => Record.HasFields(weights, m))),

    // 6. One output record per active league
    Output = List.Transform(
        if CheckHasLeague and CheckDuplicates and CheckReserved then LeagueRows else {},
        (row) =>
            let
                LeagueName = Text.Trim(Text.From(row[League])),
                Reconcile = if row[Reconcile_To] = null or Text.Trim(Text.From(row[Reconcile_To])) = "" then null else Text.Trim(Text.From(row[Reconcile_To]))
            in
                [
                    League = LeagueName,
                    Reconcile_To = Reconcile,
                    RoundDecimals = RoundDecimals,
                    ReconcileTolerance = ReconcileTolerance,
                    Weights = WeightsFor(LeagueName),
                    Gates = GatesFor(WeightsFor(LeagueName)),
                    AllMetrics = Metrics
                ]
    ),
    Result = Table.FromRecords(
        Output,
        type table [League = text, Reconcile_To = nullable text, RoundDecimals = number, ReconcileTolerance = number, Weights = record, Gates = record, AllMetrics = list]
    )
in
    Result
