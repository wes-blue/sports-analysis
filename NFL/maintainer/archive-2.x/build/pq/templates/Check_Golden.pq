/*
  Check_Golden                                                      version 2.001
  Purpose:  control C-04. Joins the golden sample (Golden_Keys) to Stats_Scored on season, week, season_type, player_id
            and, for every FF_<League> column present in both, compares actual with expected at |diff| <= 0.011.
            A golden player-game that is missing from Stats_Scored counts as a mismatch and is named in Worst_Examples.
            A golden league column that Stats_Scored does not have is reported as SKIPPED (not silently ignored).
            The expected values were made with particular rules (tblGoldenRules). A league whose rules were changed on
            purpose shows NOT APPLICABLE instead of PASS/FAIL, as the pipeline's G-GOLDEN gate does: its rules or
            RoundDecimals in the pipeline changed since then (Pipeline_Status league contract row RULES CHANGED or
            DECIMALS CHANGED), or you changed its rules or RoundDecimals in the workbook (a Check_Rules_Drift row for the
            league or for all leagues). The counts are still shown.
  Inputs:   Stats_Scored, Golden_Keys, Pipeline_Status, Check_Rules_Drift (queries only).
  Output:   League | Golden_Rows | Matched | Mismatched | Status | Worst_Examples
  Load:     table on the Checks sheet (see WORKBOOK-REQUIREMENTS.md).
  Changed from 1.x (1.004): header only.
  Changed in 2.001 (QA finding N-1): NOT APPLICABLE for a league whose rules were changed on purpose, so the workbook
            and the pipeline tell you the same thing.
  Firewall: references only other queries (Stats_Scored, Golden_Keys, Pipeline_Status, Check_Rules_Drift); no direct
            data-source access (D-009).
*/
let
    // 1. Inputs
    Tolerance = 0.011,
    Golden = Golden_Keys,
    Scored = Stats_Scored,
    KeyColumns = {"season", "week", "season_type", "player_id"},
    GoldenLeagueColumns = List.Select(Table.ColumnNames(Golden), each Text.StartsWith(_, "FF_")),
    ScoredColumns = Table.ColumnNames(Scored),
    CommonColumns = List.Select(GoldenLeagueColumns, each List.Contains(ScoredColumns, _)),
    MissingColumns = List.Select(GoldenLeagueColumns, each not List.Contains(ScoredColumns, _)),
    // Leagues changed on purpose (N-1): pipeline rules changed (Pipeline_Status) or workbook rules edited (Check_Rules_Drift)
    ContractRows = try Table.ToRecords(Table.SelectRows(Pipeline_Status, each [Section] = "League contract")) otherwise {},
    DriftRows = try Table.ToRecords(Table.SelectRows(Check_Rules_Drift, each [Status] <> "same")) otherwise {},
    NotApplicable = (league as text) as text =>
        let
            Pipe = List.Select(ContractRows, each [Item] = league and ([Result] = "RULES CHANGED" or [Result] = "DECIMALS CHANGED")),
            Edits = List.Select(DriftRows, each [League] = league or [League] = "(all leagues)")
        in
            if List.Count(Pipe) > 0 then "NOT APPLICABLE: the pipeline's " & (if Pipe{0}[Result] = "DECIMALS CHANGED" then "RoundDecimals" else "rules for " & league) & " changed since the expected values were made (Pipeline_Status); expected after a deliberate change, as the pipeline's G-GOLDEN says"
            else if List.Count(Edits) > 0 then "NOT APPLICABLE: you changed " & league & "'s rules or RoundDecimals in the workbook (" & Number.ToText(List.Count(Edits)) & " row(s) in Check_Rules_Drift); expected"
            else "",

    // 2. Slim Stats_Scored (keys + common FF columns) and left-join the golden rows onto it
    Slim = Table.SelectColumns(Scored, KeyColumns & CommonColumns),
    Joined = Table.NestedJoin(Golden, KeyColumns, Slim, KeyColumns, "Actual", JoinKind.LeftOuter),
    Rows = List.Buffer(Table.ToRecords(Joined)),

    // 3. One result row per league
    CheckLeague = (col as text) as record =>
        let
            Evaluated = List.Transform(
                Rows,
                (r) =>
                    let
                        Found = Table.RowCount(r[Actual]) > 0,
                        Act = if Found then Record.Field(Table.First(r[Actual]), col) else null,
                        Exp = Record.Field(r, col),
                        Ok = Act <> null and Exp <> null and Number.Abs(Act - Exp) <= Tolerance,
                        Label = Text.From(r[season]) & " wk" & Text.From(r[week]) & " " & r[season_type] & " " & Text.From(r[player_display_name]) & " (" & r[player_id] & ")",
                        Example =
                            if not Found then "MISSING in Stats_Scored: " & Label
                            else Label & ": Excel " & Text.From(Act) & " vs golden " & Text.From(Exp)
                    in
                        [Ok = Ok, Example = Example]
            ),
            Bad = List.Select(Evaluated, each not [Ok]),
            Total = List.Count(Evaluated),
            Mismatched = List.Count(Bad),
            LeagueName = Text.AfterDelimiter(col, "FF_"),
            Reason = NotApplicable(LeagueName)
        in
            [
                League = LeagueName,
                Golden_Rows = Total,
                Matched = Total - Mismatched,
                Mismatched = Mismatched,
                Status = if Total = 0 then "NO ROWS" else if Reason <> "" then "NOT APPLICABLE" else if Mismatched = 0 then "PASS" else "FAIL",
                Worst_Examples = if Reason <> "" then Reason else Text.Combine(List.Transform(List.FirstN(Bad, 3), each [Example]), "; ")
            ],
    SkippedLeague = (col as text) as record =>
        [
            League = Text.AfterDelimiter(col, "FF_"),
            Golden_Rows = Table.RowCount(Golden),
            Matched = 0,
            Mismatched = Table.RowCount(Golden),
            Status = "SKIPPED (column not in Stats_Scored)",
            Worst_Examples = ""
        ]
in
    Table.FromRecords(
        List.Transform(CommonColumns, CheckLeague) & List.Transform(MissingColumns, SkippedLeague),
        type table [League = text, Golden_Rows = Int64.Type, Matched = Int64.Type, Mismatched = Int64.Type, Status = text, Worst_Examples = text]
    )
