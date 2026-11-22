/*
  Check_Metrics                                                     version 2.001
  Purpose:  control that stops silent zeros: every metric listed in tblScoring, and every metric used by a tblBonus rule,
            must exist as a numeric column in the scored data (Stats_Scored = player_week columns + FF_<League>).
  Inputs:   Stats_Scored (schema only), Scoring_Weights, Bonus_Rules (queries only).
  Output:   Metric | In_Stats_Raw | Is_Numeric | Used_By_Leagues | Status
            Status values: OK | MISSING COLUMN (a league gives it weight, so scores would silently be too low)
                           | MISSING (zero weight everywhere) | NOT NUMERIC
  Load:     table on the Checks sheet (see WORKBOOK-REQUIREMENTS.md).
  Changed from 1.x (1.005): header only. The long-TD and dst_* columns now come from player_week itself, so a missing
            one means the pipeline did not publish it (add the metric to 02-config/scoring_weights.csv and re-run).
  Firewall: references only other queries (Stats_Scored, Scoring_Weights, Bonus_Rules) (D-009).
*/
let
    // 1. Inputs
    Weights = Scoring_Weights,
    BonusRules = Bonus_Rules,
    // tblScoring metrics plus any bonus-only metrics (e.g. long-TD counts)
    AllMetrics = List.Distinct((if Table.RowCount(Weights) = 0 then {} else Weights{0}[AllMetrics]) & BonusRules[Metric]),
    RawSchema = Table.Schema(Stats_Scored),
    RawColumns = RawSchema[Name],

    // 2. One row per metric
    Rows = List.Transform(
        AllMetrics,
        (metric) =>
            let
                Found = List.Contains(RawColumns, metric),
                TypeName = if Found then RawSchema{[Name = metric]}[TypeName] else null,
                IsNumeric = Found and TypeName <> null and Text.Contains(TypeName, "Number"),
                UsedBy = List.Distinct(
                    List.Select(Weights[League], (lg) => Record.HasFields(Weights{[League = lg]}[Weights], metric))
                    & Table.SelectRows(BonusRules, each [Metric] = metric)[League]
                ),
                Status =
                    if not Found then (if List.Count(UsedBy) > 0 then "MISSING COLUMN" else "MISSING (zero weight everywhere)")
                    else if not IsNumeric then "NOT NUMERIC"
                    else "OK"
            in
                [
                    Metric = metric,
                    In_Stats_Raw = if Found then "Yes" else "No",
                    Is_Numeric = if not Found then "n/a" else if IsNumeric then "Yes" else "No",
                    Used_By_Leagues = Text.Combine(UsedBy, ", "),
                    Status = Status
                ]
    )
in
    Table.FromRecords(
        Rows,
        type table [Metric = text, In_Stats_Raw = text, Is_Numeric = text, Used_By_Leagues = text, Status = text]
    )
