// SeasonTotals: the finished table the pipeline publishes (one row per player, season and season type).
let
    Source = Csv.Document(
        Web.Contents(
            "https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-SeasonTotals.csv",
            [Timeout = #duration(0, 0, 10, 0)]
        ),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    AllColumns = Table.ColumnNames(Promoted),
    WholeColumns = List.Intersect({AllColumns, {"season", "games"}}),
    TextColumns = List.Intersect({AllColumns, {"season_type", "player_display_name", "position", "team", "player_id"}}),
    NumberColumns = List.Difference(AllColumns, WholeColumns & TextColumns),
    BlankToNull = Table.ReplaceValue(Promoted, "", null, Replacer.ReplaceValue, AllColumns),
    Typed = Table.TransformColumnTypes(
        BlankToNull,
        List.Transform(WholeColumns, each {_, Int64.Type})
            & List.Transform(TextColumns, each {_, type text})
            & List.Transform(NumberColumns, each {_, type number}),
        "en-US"
    )
in
    Typed
