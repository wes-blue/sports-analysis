/*
  Check_Reconciliation                                              version 2.001
  Purpose:  for each league with Reconcile_To set (e.g. Standard -> fantasy_points), compare FF_<League> with the
            nflverse column row by row; a row mismatches when |difference| > the tolerance. D/ST rows are excluded.
            Tolerance = ReconcileTolerance, widened to half a unit of RoundDecimals when fewer than 2 decimals are kept
            (0.5 for 0, 0.05 for 1): the same rule as the pipeline's G-RECON gate.
            NOT APPLICABLE (instead of PASS/FAIL) when the league no longer follows nflverse's scoring on purpose, as
            G-RECON does: its rules in the pipeline changed since the expected values were made (Pipeline_Status league
            contract row RULES CHANGED), or you changed its weights, bands, gates or Active flag in the workbook
            (a Check_Rules_Drift row for the league or for all leagues). The counts are still shown.
  Inputs:   Scoring_Weights, Stats_Scored, Pipeline_Status, Check_Rules_Drift (queries only).
  Output:   League | Reconcile_To | Rows_Compared | Rows_Mismatched | Match_Pct | Status | Worst_Examples
  Load:     table on the Checks sheet (see WORKBOOK-REQUIREMENTS.md).
  Changed from 1.x (1.005): the tolerance is tblConfig ReconcileTolerance (via Scoring_Weights, default 0.005, the same
            value as the pipeline's G-RECON gate) instead of a fixed 0.011.
  Changed in 2.001 (QA finding N-1): widened tolerance for RoundDecimals 0 or 1, and NOT APPLICABLE for a league whose
            rules were changed on purpose, so the workbook and the pipeline tell you the same thing.
  Firewall: references only other queries (Scoring_Weights, Stats_Scored, Pipeline_Status, Check_Rules_Drift) (D-009).
*/
let
    // 1. Inputs
    Weights = Scoring_Weights,
    BaseTolerance = if Table.RowCount(Weights) = 0 then 0.005 else Weights{0}[ReconcileTolerance],
    Decimals = if Table.RowCount(Weights) = 0 then 2 else Weights{0}[RoundDecimals],
    Tolerance = if Decimals < 2 then List.Max({BaseTolerance, 0.5 * Number.Power(10, -Decimals)}) else BaseTolerance,
    ToleranceNote = if Tolerance > BaseTolerance then "tolerance " & Number.ToText(Tolerance, "G", "en-US") & " because RoundDecimals is " & Number.ToText(Decimals, "G", "en-US") else "",
    // Leagues changed on purpose (N-1): pipeline rules changed (Pipeline_Status) or workbook rules edited (Check_Rules_Drift)
    ContractRows = try Table.ToRecords(Table.SelectRows(Pipeline_Status, each [Section] = "League contract")) otherwise {},
    DriftRows = try Table.ToRecords(Table.SelectRows(Check_Rules_Drift, each [Status] <> "same" and [Kind] <> "Setting")) otherwise {},
    NotApplicable = (league as text) as text =>
        let
            Pipe = List.Select(ContractRows, each [Item] = league and [Result] = "RULES CHANGED"),
            Edits = List.Select(DriftRows, each [League] = league or [League] = "(all leagues)")
        in
            if List.Count(Pipe) > 0 then "NOT APPLICABLE: the pipeline's rules for " & league & " changed since the expected values were made (Pipeline_Status), so it no longer follows nflverse's scoring; expected after a deliberate change, as the pipeline's G-RECON says"
            else if List.Count(Edits) > 0 then "NOT APPLICABLE: you changed " & league & "'s rules in the workbook (" & Number.ToText(List.Count(Edits)) & " row(s) in Check_Rules_Drift), so it no longer follows nflverse's scoring; expected"
            else "",
    Scored = Stats_Scored,
    ScoredColumns = Table.ColumnNames(Scored),
    ToCheck = Table.ToRecords(Table.SelectRows(Weights, each [Reconcile_To] <> null)),

    // 2. Check one league
    CheckLeague = (rec as record) as record =>
        let
            LeagueName = rec[League],
            Target = rec[Reconcile_To],
            OurColumn = "FF_" & LeagueName,
            TargetFound = List.Contains(ScoredColumns, Target),
            Result =
                if not TargetFound then
                    [League = LeagueName, Reconcile_To = Target, Rows_Compared = 0, Rows_Mismatched = 0, Match_Pct = null,
                     Status = "TARGET COLUMN MISSING", Worst_Examples = ""]
                else
                    let
                        // Only the columns needed, buffered because they are read three times below
                        Slim = Table.Buffer(
                            Table.SelectColumns(Scored, {"season", "week", "season_type", "player_display_name", "position", OurColumn, Target})
                        ),
                        // Rows where nflverse has a value; our blank counts as 0
                        Compared = Table.SelectRows(Slim, each [position] <> "DST" and Record.Field(_, Target) <> null),   // D/ST rows have no nflverse fantasy_points
                        WithDiff = Table.AddColumn(
                            Compared, "Diff",
                            each (if Record.Field(_, OurColumn) = null then 0 else Record.Field(_, OurColumn)) - Record.Field(_, Target),
                            type number
                        ),
                        Mismatched = Table.SelectRows(WithDiff, each Number.Abs([Diff]) > Tolerance),
                        RowsCompared = Table.RowCount(WithDiff),
                        RowsMismatched = Table.RowCount(Mismatched),
                        WithAbs = Table.AddColumn(Mismatched, "AbsDiff", each Number.Abs([Diff]), type number),
                        WorstSorted = Table.FirstN(Table.Sort(WithAbs, {{"AbsDiff", Order.Descending}}), 3),
                        Examples = Text.Combine(
                            List.Transform(
                                Table.ToRecords(WorstSorted),
                                (r) => Text.From(r[season]) & " wk" & Text.From(r[week]) & " " & Text.From(r[player_display_name])
                                    & ": ours " & Text.From(Record.Field(r, OurColumn)) & " vs nflverse " & Text.From(Record.Field(r, Target))
                            ),
                            "; "
                        )
                    in
                        [
                            League = LeagueName,
                            Reconcile_To = Target,
                            Rows_Compared = RowsCompared,
                            Rows_Mismatched = RowsMismatched,
                            Match_Pct = if RowsCompared = 0 then null else (RowsCompared - RowsMismatched) / RowsCompared,
                            Status = if RowsCompared = 0 then "NO ROWS" else if NotApplicable(LeagueName) <> "" then "NOT APPLICABLE" else if RowsMismatched = 0 then "PASS" else "FAIL",
                            Worst_Examples = Text.Combine(List.Select({NotApplicable(LeagueName), ToleranceNote, Examples}, each _ <> ""), "; ")
                        ]
        in
            Result
in
    Table.FromRecords(
        List.Transform(ToCheck, CheckLeague),
        type table [League = text, Reconcile_To = text, Rows_Compared = Int64.Type, Rows_Mismatched = Int64.Type, Match_Pct = nullable number, Status = text, Worst_Examples = text]
    )
