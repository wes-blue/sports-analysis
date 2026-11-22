// PlayerGames: the finished table the pipeline publishes (one row per player-game, newest first).
// No scoring happens here: the FF_ columns are already in the file. This query only downloads, reads and types.
let
    Source = Csv.Document(
        Web.Contents("https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-PlayerGames.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    AllColumns = Table.ColumnNames(Promoted),
    WholeColumns = List.Intersect({AllColumns, {"season", "week"}}),
    TextColumns = List.Intersect({AllColumns, {"season_type", "player_display_name", "position", "team", "opponent_team", "player_id", "position_group", "player_name", "headshot_url", "game_id", "fg_made_list", "fg_missed_list", "fg_blocked_list"}}),
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
