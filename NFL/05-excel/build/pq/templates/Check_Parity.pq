/*
  Check_Parity                                                      version 2.001
  Purpose:  per league, compares the workbook's scores (Stats_Scored) with the pipeline's own scores (Pipeline_Scored) on the
            key season, week, season_type, player_id. Different weights in the workbook legitimately give different scores,
            so the status informs rather than alarms; Check_Rules_Drift lists the rule differences that explain it.
  Inputs:   Stats_Scored, Pipeline_Scored, Scoring_Weights (queries only).
  Output:   League | Rows_Compared | Rows_Equal | Rows_Different | Largest_Difference | Only_In_Workbook | Only_In_Pipeline
            | Status | Example
            Status values: matches pipeline
                         | differs: workbook rules changed? (see Check_Rules_Drift)
                         | differs: blank scores on one side: refresh again
                         | same scores, but the row sets differ: refresh again
                         | not in pipeline: league added or renamed in the workbook? (see Check_Rules_Drift)
                         | not scored in workbook: league inactive or renamed here? (see Check_Rules_Drift)
                         | no rows to compare
            Two scores are equal when both are blank or |difference| <= 0.000001 (both sides are already rounded).
  Load:     table on the Checks sheet (see WORKBOOK-REQUIREMENTS.md).
  Method:   one hash join for all leagues (Table.Join, full outer), buffered once; per league the two score columns are
            compared as lists (List.Zip) rather than with per-row record functions.
  Firewall: references only other queries (Stats_Scored, Pipeline_Scored, Scoring_Weights) (D-009).
*/
let
    Tolerance = 0.000001,
    Keys = {"season", "week", "season_type", "player_id"},
    PipeKeys = List.Transform(Keys, each "Pipe_" & _),

    // 1. Leagues on each side
    WorkbookLeagues = Scoring_Weights[League],
    PipelineLeagues = List.Transform(List.Select(Table.ColumnNames(Pipeline_Scored), each Text.StartsWith(_, "FF_")), each Text.Middle(_, 3)),
    Common = List.Select(WorkbookLeagues, each List.Contains(PipelineLeagues, _)),
    WorkbookOnly = List.Select(WorkbookLeagues, each not List.Contains(PipelineLeagues, _)),
    PipelineOnly = List.Select(PipelineLeagues, each not List.Contains(WorkbookLeagues, _)),
    CommonColumns = List.Transform(Common, each "FF_" & _),

    // 2. Slim both sides to keys + common FF columns; rename the pipeline side; one full outer join
    Left = Table.SelectColumns(Stats_Scored, Keys & {"player_display_name"} & CommonColumns),
    Right = Table.RenameColumns(
        Table.SelectColumns(Pipeline_Scored, Keys & CommonColumns),
        List.Transform(Keys & CommonColumns, each {_, "Pipe_" & _})
    ),
    Joined = Table.Join(Left, Keys, Right, PipeKeys, JoinKind.FullOuter),
    OnlyInWorkbook = Table.RowCount(Table.SelectRows(Joined, each [Pipe_player_id] = null)),
    OnlyInPipeline = Table.RowCount(Table.SelectRows(Joined, each [player_id] = null)),
    Both = Table.Buffer(Table.SelectRows(Joined, each [player_id] <> null and [Pipe_player_id] <> null)),
    RowsCompared = Table.RowCount(Both),

    ShowScore = (v) => if v = null then "(blank)" else Text.From(v, "en-US"),

    // 3. Compare one league: |workbook - pipeline| per row as a list (null = one side blank)
    CompareLeague = (league as text) as record =>
        let
            Ours = Table.Column(Both, "FF_" & league),
            Theirs = Table.Column(Both, "Pipe_FF_" & league),
            Diffs = List.Buffer(List.Transform(
                List.Zip({Ours, Theirs}),
                (p) => if p{0} = null and p{1} = null then 0 else if p{0} = null or p{1} = null then null else Number.Abs(p{0} - p{1})
            )),
            Blank = List.Count(List.Select(Diffs, each _ = null)),
            Different = Blank + List.Count(List.Select(Diffs, each _ <> null and _ > Tolerance)),
            Numeric = List.RemoveNulls(Diffs),
            RawLargest = if List.Count(Numeric) = 0 then null else List.Max(Numeric),
            Largest = if RawLargest = null then null else Number.Round(RawLargest, 6),
            // example row: the largest numeric difference, else the first row with a blank score on one side
            WorstPos = if RawLargest <> null and RawLargest > Tolerance then List.PositionOf(Diffs, RawLargest)
                       else if Blank > 0 then List.PositionOf(Diffs, null) else -1,
            Worst = if WorstPos < 0 then null else Both{WorstPos},
            Example =
                if Worst = null then ""
                else Text.From(Worst[season]) & " wk" & Text.From(Worst[week]) & " " & Worst[season_type] & " "
                    & Text.From(Worst[player_display_name]) & " (" & Worst[player_id] & "): workbook "
                    & ShowScore(Record.Field(Worst, "FF_" & league)) & " vs pipeline "
                    & ShowScore(Record.Field(Worst, "Pipe_FF_" & league)),
            Status =
                if RowsCompared = 0 then "no rows to compare"
                else if Different > Blank then "differs: workbook rules changed? (see Check_Rules_Drift)"
                else if Blank > 0 then "differs: blank scores on one side: refresh again"
                else if OnlyInWorkbook + OnlyInPipeline > 0 then "same scores, but the row sets differ: refresh again"
                else "matches pipeline"
        in
            [League = league, Rows_Compared = RowsCompared, Rows_Equal = RowsCompared - Different, Rows_Different = Different,
             Largest_Difference = Largest, Only_In_Workbook = OnlyInWorkbook, Only_In_Pipeline = OnlyInPipeline,
             Status = Status, Example = Example],
    OneSided = (league as text, status as text) as record =>
        [League = league, Rows_Compared = 0, Rows_Equal = 0, Rows_Different = 0, Largest_Difference = null,
         Only_In_Workbook = null, Only_In_Pipeline = null, Status = status, Example = ""]
in
    Table.FromRecords(
        List.Transform(Common, CompareLeague)
            & List.Transform(WorkbookOnly, each OneSided(_, "not in pipeline: league added or renamed in the workbook? (see Check_Rules_Drift)"))
            & List.Transform(PipelineOnly, each OneSided(_, "not scored in workbook: league inactive or renamed here? (see Check_Rules_Drift)")),
        type table [League = text, Rows_Compared = Int64.Type, Rows_Equal = Int64.Type, Rows_Different = Int64.Type,
                    Largest_Difference = nullable number, Only_In_Workbook = nullable number, Only_In_Pipeline = nullable number,
                    Status = text, Example = text]
    )
