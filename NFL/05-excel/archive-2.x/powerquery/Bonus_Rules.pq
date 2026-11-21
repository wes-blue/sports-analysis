/*
  Bonus_Rules                                                       version 2.001
  Purpose:  band-bonus rules from the workbook table tblBonus (League | Metric | Lower | Upper | Points | Applies_To | Notes).
            A rule awards Points when Lower <= value <= Upper (both inclusive). Blank Lower = no minimum, blank Upper = no maximum
            (at least one of the two is required). Applies_To uses the same position gate as tblScoring (blank = all players).
  Inputs:   tblBonus (optional), tblLeagues.
  Output:   League | Metric | Lower | Upper | Points | Gate (list of upper-case position / position_group codes, or null)
  Load:     connection only.
  Changed from 1.x (1.005): header only. If tblBonus does not exist or has no rules, the result is an empty table.
  Firewall: reads ONLY workbook tables (tblBonus, tblLeagues) and references no other query (D-009).
*/
let
    // 1. tblBonus may be absent (older workbooks): treat that as "no rules"
    Source = try Excel.CurrentWorkbook(){[Name = "tblBonus"]}[Content] otherwise null,
    Leagues = Excel.CurrentWorkbook(){[Name = "tblLeagues"]}[Content],
    LeagueNames = List.Transform(List.Select(Leagues[League], each _ <> null), each Text.Trim(Text.From(_))),

    // 2. Helpers: blank-safe text and numbers with readable errors
    Clean = (v as any) as text => if v = null then "" else Text.Trim(Text.From(v)),
    ToNumber = (v as any, what as text) as nullable number =>
        if Clean(v) = "" then null
        else try Number.From(v, "en-US") otherwise error Error.Record("Bonus.Error", "tblBonus: " & what & " is not a number: " & Text.From(v)),
    ParseGate = (v as any) as nullable list =>
        let
            Cleaned = Text.Upper(Text.Remove(Clean(v), {" ", Character.FromNumber(160)})),
            Parts = List.Select(Text.Split(Cleaned, ","), each _ <> "")
        in
            if List.Count(Parts) = 0 then null else Parts,

    // 3. Keep rows that are not completely empty
    Rows = if Source = null then {} else
        List.Select(
            Table.ToRecords(Source),
            each Clean([League]) <> "" or Clean([Metric]) <> "" or Clean([Points]) <> ""
        ),

    // 4. Validate and normalise each rule
    Rules = List.Transform(
        Rows,
        (r) =>
            let
                LeagueName = Clean(r[League]),
                MetricName = Clean(r[Metric]),
                Label = "tblBonus row (" & LeagueName & ", " & MetricName & ")",
                Lower = ToNumber(r[Lower], Label & " Lower"),
                Upper = ToNumber(r[Upper], Label & " Upper"),
                Points = ToNumber(r[Points], Label & " Points"),
                Checked =
                    if LeagueName = "" or MetricName = "" or Points = null
                    then error Error.Record("Bonus.Error", Label & ": League, Metric and Points are required")
                    else if not List.Contains(LeagueNames, LeagueName)
                    then error Error.Record("Bonus.Error", Label & ": league is not in tblLeagues")
                    else if Lower = null and Upper = null
                    then error Error.Record("Bonus.Error", Label & ": give Lower and/or Upper (a rule with neither would award every row)")
                    else if Lower <> null and Upper <> null and Lower > Upper
                    then error Error.Record("Bonus.Error", Label & ": Lower is greater than Upper")
                    else true
            in
                if Checked then
                    [League = LeagueName, Metric = MetricName, Lower = Lower, Upper = Upper, Points = Points, Gate = ParseGate(Record.FieldOrDefault(r, "Applies_To", null))]
                else null
    )
in
    Table.FromRecords(
        Rules,
        type table [League = text, Metric = text, Lower = nullable number, Upper = nullable number, Points = number, Gate = nullable list]
    )
