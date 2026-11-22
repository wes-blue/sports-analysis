/*
  Pipeline_Status                                                   version 2.001
  Purpose:  one table for the Checks sheet saying what data the workbook is reading: when the pipeline generated it, through
            which season and week, the pipeline and data contract versions, the run outcome and the result of each gate.
            A data_contract_version other than 1 is flagged: these queries are written for version 1.
            Each league contract row says whether the pipeline still uses the rules (and RoundDecimals) that the expected
            values on the Validation sheet were made with, the same test the pipeline's G-GOLDEN, G-ESPN and G-RECON gates make.
  Inputs:   tblConfig (DataLocation), named cell WorkbookFolder, tblGoldenRules (optional), <data>/status.csv,
            <data>/checks/gates.csv and <data>/config/pipeline_config.csv (CONTRACTS.md 5.4, 5.5).
  Output:   Section (Run | League contract | Gate) | Item | Value | Result | Detail
            Result values: OK | CHECK | UNSUPPORTED | MISSING for run rows; OK | RULES CHANGED | DECIMALS CHANGED |
            NO TEST VALUES for league contract rows; PASS | WARN | FAIL for gates.
            Check_Golden and Check_Reconciliation read the league contract rows (QA finding N-1).
  Changed in 2.001: league contract rows compared with tblGoldenRules; the first row is "Data read from" (web or folder).
  Load:     table on the Checks sheet (see WORKBOOK-REQUIREMENTS.md).
  Firewall: reads tblConfig, WorkbookFolder and the data files; references NO other query (D-009).
*/
let
//@@RESOLVER@@
    // 1. status.csv as a record [key = value]
    StatusTable = Table.SelectRows(ReadCsv("status.csv"), each [key] <> null and Text.Trim([key]) <> ""),
    Status = Record.FromList(List.Transform(StatusTable[value], each if _ = null then "" else Text.Trim(_)), List.Transform(StatusTable[key], Text.Trim)),
    Get = (k as text) as nullable text => let v = Record.FieldOrDefault(Status, k, null) in if v = null or v = "" then null else v,
    Present = (k as text) as text => if Get(k) = null then "MISSING" else "OK",
    Location = if DL_IsWeb then DL_WebBase else DL_Folder,

    // 2. Run rows, in reading order
    ContractVersion = Get("data_contract_version"),
    GatesFail = Get("gates_fail"),
    RunRows = {
        [Section = "Run", Item = "Data read from", Value = Location, Result = "OK", Detail = (if DL_IsWeb then "the web address in DataLocation (Config sheet)" else "a folder on this PC (DataLocation on the Config sheet; blank = automatic)")],
        [Section = "Run", Item = "Data generated (UTC)", Value = Get("generated_utc"), Result = Present("generated_utc"), Detail = "run " & (if Get("run_id") = null then "?" else Get("run_id"))],
        [Section = "Run", Item = "Data through",
         Value = if Get("latest_season") = null then null else Get("latest_season") & " " & (if Get("latest_season_type") = null then "" else Get("latest_season_type")) & " week " & (if Get("latest_week") = null then "?" else Get("latest_week")),
         Result = Present("latest_season"), Detail = "newest season, season type and week in the published data"],
        [Section = "Run", Item = "Pipeline version", Value = Get("pipeline_version"), Result = Present("pipeline_version"), Detail = ""],
        [Section = "Run", Item = "Data contract version", Value = ContractVersion,
         Result = if ContractVersion = null then "MISSING" else if ContractVersion = "1" then "OK" else "UNSUPPORTED",
         Detail = if ContractVersion = "1" then "these queries are written for version 1"
                  else "these queries are written for version 1: ask for queries that match version " & (if ContractVersion = null then "?" else ContractVersion) & " before trusting the checks"],
        [Section = "Run", Item = "Outcome", Value = Get("outcome"), Result = Present("outcome"), Detail = ""],
        [Section = "Run", Item = "Pipeline season window",
         Value = (if Get("window_start") = null then "?" else Get("window_start")) & " to " & (if Get("window_end") = null then "?" else Get("window_end")) & " " & (if Get("season_types") = null then "" else Get("season_types")),
         Result = Present("window_start"), Detail = "the workbook can only read seasons inside this window"],
        [Section = "Run", Item = "Gates pass / warn / fail",
         Value = (if Get("gates_pass") = null then "?" else Get("gates_pass")) & " / " & (if Get("gates_warn") = null then "?" else Get("gates_warn")) & " / " & (if GatesFail = null then "?" else GatesFail),
         Result = if GatesFail = null then "MISSING" else if GatesFail = "0" then "OK" else "CHECK", Detail = "details in the Gate rows below"],
        [Section = "Run", Item = "Upstream last modified (UTC)", Value = Get("upstream_last_modified_max"), Result = Present("upstream_last_modified_max"), Detail = "newest nflverse file the run used"],
        [Section = "Run", Item = "Seasons refreshed", Value = Get("seasons_refreshed"), Result = "OK", Detail = "seasons rebuilt by the last run"],
        [Section = "Run", Item = "Config hash", Value = Get("config_sha256"), Result = Present("config_sha256"), Detail = "changes when 02-config changes"]
    },

    // 3. One row per league contract hash (contract_<League>), compared with tblGoldenRules (League | Rules_SHA256 |
    //    RoundDecimals, seeded from 06-qa/fixtures/fixture_contracts.csv): the rules the expected values were made with.
    //    Without tblGoldenRules every row is OK, as in 1.006.
    ExpectedSource = try Excel.CurrentWorkbook(){[Name = "tblGoldenRules"]}[Content] otherwise null,
    ExpectedRows = if ExpectedSource = null then {}
        else List.Select(Table.ToRecords(ExpectedSource), each Record.FieldOrDefault(_, "League", null) <> null and Text.Trim(Text.From([League])) <> ""),
    ExpectedFor = (league as text) as nullable record =>
        let m = List.Select(ExpectedRows, each Text.Trim(Text.From([League])) = league) in if List.Count(m) = 0 then null else m{0},
    AsText = (v as any) as text => if v = null then "" else Text.Lower(Text.Trim(Text.From(v, "en-US"))),
    AsNumber = (v as any) as nullable number => if v = null then null else try Number.From(Text.Trim(Text.From(v, "en-US")), "en-US") otherwise null,
    PipeConfig = try Table.Buffer(ReadCsv("config/pipeline_config.csv")) otherwise null,
    PipeRoundRows = if PipeConfig = null then {} else Table.SelectRows(PipeConfig, each [Setting] <> null and Text.Trim([Setting]) = "RoundDecimals")[Value],
    PipeRound = if List.Count(PipeRoundRows) = 0 then null else AsNumber(PipeRoundRows{0}),
    ContractKeys = List.Select(Record.FieldNames(Status), each Text.StartsWith(_, "contract_")),
    ContractRows = List.Transform(ContractKeys, (k) =>
        let
            LeagueName = Text.Middle(k, 9),
            Exp = ExpectedFor(LeagueName),
            RulesSame = Exp <> null and AsText(Record.FieldOrDefault(Exp, "Rules_SHA256", null)) = AsText(Get(k)),
            ExpRound = if Exp = null then null else AsNumber(Record.FieldOrDefault(Exp, "RoundDecimals", null)),
            RoundSame = ExpRound <> null and PipeRound <> null and ExpRound = PipeRound,
            ContractResult =
                if ExpectedSource = null then "OK"
                else if Exp = null then "NO TEST VALUES"
                else if not RulesSame then "RULES CHANGED"
                else if not RoundSame then "DECIMALS CHANGED"
                else "OK",
            ContractDetail =
                if ExpectedSource = null then "hash of the league's weights and bands in the pipeline"
                else if ContractResult = "NO TEST VALUES" then "no expected values exist for this league (a new league?), so Check_Golden does not test it"
                else if ContractResult = "RULES CHANGED" then "the pipeline's rules for this league differ from the rules its expected values were made with (02-config was changed): Check_Golden, and Check_Reconciliation for a control league, show NOT APPLICABLE, as the pipeline's gates do. Expected after a deliberate change"
                else if ContractResult = "DECIMALS CHANGED" then "the pipeline rounds to " & (if PipeRound = null then "?" else Number.ToText(PipeRound)) & " decimals but the expected values were made with " & (if ExpRound = null then "?" else Number.ToText(ExpRound)) & ": Check_Golden shows NOT APPLICABLE, as the pipeline's gates do"
                else "same rules and RoundDecimals as the league's expected values (Validation sheet), so Check_Golden tests it"
        in
            [Section = "League contract", Item = LeagueName, Value = Get(k), Result = ContractResult, Detail = ContractDetail]),

    // 4. Gates (checks/gates.csv); a missing file becomes one MISSING row instead of an error
    GatesTable = try Table.Buffer(ReadCsv("checks/gates.csv")) otherwise null,
    GateRows =
        if GatesTable = null then {[Section = "Gate", Item = "checks/gates.csv", Value = null, Result = "MISSING", Detail = "file not found in the data folder"]}
        else List.Transform(
            List.Select(Table.ToRecords(GatesTable), each [gate_id] <> null and Text.Trim([gate_id]) <> ""),
            (g) => [Section = "Gate", Item = Text.Trim(g[gate_id]) & " " & g[gate], Value = g[severity], Result = g[result],
                    Detail = (if g[detail] = null then "" else g[detail]) & (if g[checked_utc] = null or g[checked_utc] = "" then "" else " (checked " & g[checked_utc] & ")")]
        )
in
    Table.FromRecords(
        RunRows & ContractRows & GateRows,
        type table [Section = text, Item = text, Value = nullable text, Result = nullable text, Detail = text]
    )
