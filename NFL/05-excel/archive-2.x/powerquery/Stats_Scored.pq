/*
  Stats_Scored                                                      version 2.001
  Purpose:  Stats_Raw plus one FF_<League> column per active league = SUM(weight x stat) + band bonuses, missing/blank stat = 0
            in the weighted sum, rounded half away from zero to RoundDecimals (CONTRACTS.md 4).
            Position gate: a metric with an Applies_To list (carried in Scoring_Weights[Gates]) only counts for rows whose
            position OR position_group is in that list; no list = all players.
            Band bonuses (Bonus_Rules): a rule adds Points when Lower <= stat <= Upper (inclusive; a null stat earns nothing),
            subject to the rule's own position gate. Bands are independent: disjoint bands give one bonus, overlapping bands stack.
  Inputs:   Stats_Raw, Scoring_Weights, Bonus_Rules (queries only).
  Output:   every Stats_Raw column, then FF_<League> (number) for each active league in tblLeagues order.
  Load:     connection only + Data Model (build PivotTables from the Data Model).
  Changed from 1.x (1.005): the LongTD join and the Team_DST append are gone, because player_week already carries the
            long-TD columns and the D/ST rows; the FF_<League>_Bonus helper column is dropped (the contract output is
            FF_<League> only). ScoreRow, BonusRow, the gate test and the band test are unchanged; RoundIt first rounds to 9 decimals (QA m-02).
            Scoring is row by row (Table.AddColumn with a record function), as proven in 1.x; it is kept deliberately.
  Firewall: references only other queries (Stats_Raw, Scoring_Weights, Bonus_Rules); no direct data-source access (D-009).
*/
let
    // 1. Inputs
    Raw = Stats_Raw,
    Weights = Scoring_Weights,
    Rules = Bonus_Rules,

    // 1b. (1.006) player_week already holds the long-TD columns and the team D/ST rows: no join, no append
    Combined = Raw,
    Decimals = if Table.RowCount(Weights) = 0 then 2 else Weights{0}[RoundDecimals],

    // 2. Weighted sum for one row and one league. Metrics absent from the data count as 0
    //    (Check_Metrics reports them, so a typo does not stay silent).
    ScoreRow = (row as record, weights as record, gates as record) as number =>
        let
            // the row's position codes, upper case ("" when missing)
            Pos = let p = Record.FieldOrDefault(row, "position", null) in if p = null then "" else Text.Upper(p),
            Grp = let g = Record.FieldOrDefault(row, "position_group", null) in if g = null then "" else Text.Upper(g),
            // gate test: no gate for the metric, or the row's position / group is listed
            Allowed = (metric as text) as logical =>
                let gate = Record.FieldOrDefault(gates, metric, null)
                in gate = null or List.Contains(gate, Pos) or List.Contains(gate, Grp),
            Terms = List.Transform(
                Record.FieldNames(weights),
                (metric) =>
                    let
                        stat = Record.FieldOrDefault(row, metric, null),
                        value = if stat = null or not Allowed(metric) then 0 else stat
                    in
                        value * Record.Field(weights, metric)
            )
        in
            if List.Count(Terms) = 0 then 0 else List.Sum(Terms),

    // 2b. Band-bonus points for one row and one league (rules = list of records from Bonus_Rules)
    BonusRow = (row as record, rules as list) as number =>
        let
            Pos = let p = Record.FieldOrDefault(row, "position", null) in if p = null then "" else Text.Upper(p),
            Grp = let g = Record.FieldOrDefault(row, "position_group", null) in if g = null then "" else Text.Upper(g),
            Awarded = List.Transform(
                rules,
                (rule) =>
                    let
                        stat = Record.FieldOrDefault(row, rule[Metric], null),
                        InBand = stat <> null
                            and (rule[Lower] = null or stat >= rule[Lower])
                            and (rule[Upper] = null or stat <= rule[Upper]),
                        InGate = rule[Gate] = null or List.Contains(rule[Gate], Pos) or List.Contains(rule[Gate], Grp)
                    in
                        if InBand and InGate then rule[Points] else 0
            )
        in
            if List.Count(Awarded) = 0 then 0 else List.Sum(Awarded),

    // 3. Add FF_<League> for every active league, in tblLeagues order
    Scored = List.Accumulate(
        Weights[League],
        Combined,
        (state, leagueName) =>
            let
                LeagueWeights = Weights{[League = leagueName]}[Weights],
                LeagueGates = Weights{[League = leagueName]}[Gates],
                LeagueRules = List.Buffer(Table.ToRecords(Table.SelectRows(Rules, each [League] = leagueName))),
                RoundIt = (x as number) as number => Number.Round(Number.Round(x, 9, RoundingMode.AwayFromZero), Decimals, RoundingMode.AwayFromZero),
                // no rules: exactly the pre-1.005 behaviour (one column)
                NoBonus = Table.AddColumn(state, "FF_" & leagueName, (row) => RoundIt(ScoreRow(row, LeagueWeights, LeagueGates)), type number),
                // rules: FF = weighted sum + band points (1.006: the separate FF_<League>_Bonus column is no longer added)
                WithBonus = Table.AddColumn(
                    state,
                    "FF_" & leagueName,
                    (row) => RoundIt(ScoreRow(row, LeagueWeights, LeagueGates) + BonusRow(row, LeagueRules)),
                    type number
                )
            in
                if List.Count(LeagueRules) = 0 then NoBonus else WithBonus
    )
in
    Scored
