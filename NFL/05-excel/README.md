# NFL-Analysis workbook (Excel)

The NFL workbook is built for you on GitHub, from public nflverse statistics. The same data is also published as two plain CSV files.

## Two ways to use it

1. **Download the finished workbook.** Nothing to install or refresh. This is the easiest way and the one that works on every device.
2. **Refresh from Excel.** Load two CSV files into desktop Excel with Get Data, From Web, and press Refresh whenever you want the newest data.

### 1. Download the finished workbook

**[Download NFL-Analysis.xlsx](https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx)**

`https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx`

The link stays the same: every rebuild replaces the file behind it. For about a second during each replacement the link answers "not found"; if a download fails, try again. The file is **not in this folder or anywhere in the repository's files**: it is about 8 MB and is rebuilt on every publish. It is a release asset, and the release page is <https://github.com/wes-blue/sports-analysis/releases/tag/nfl-workbook>.

**Opening it.** The file is about 8 MB but holds about 17 million cells, so Excel takes about a minute to open it; it opened in desktop Excel with no repair message. Excel opens a downloaded file in Protected View: click **Enable Editing** so that sorting and filtering work. The newest games are at the top of `PlayerGames`, with your league columns (`FF_<League>`) right after the player's name.

**If the link answers "not found".** The workbook is being replaced or has not been built yet. Wait two minutes and try again. If it still answers "not found", open the repository's **Actions** tab, choose **nfl-pipeline-weekly**, click **Run workflow**, tick **workbook_only** and run it; the link works when that run is green. [`../03-pipeline/AUTOMATION.md`](../03-pipeline/AUTOMATION.md) has the details.

### 2. Refresh from Excel

The same two tables as the workbook's `PlayerGames` and `SeasonTotals` sheets are published as plain files. They are scored already, so Excel only downloads and reads them. It does not calculate any points.

| File | What it holds | Size | Link |
|---|---|---|---|
| `NFL-PlayerGames.csv` | One row per player per game, newest first (about 180,000 rows, 98 columns today) | about 38 MB | [download](https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-PlayerGames.csv) |
| `NFL-SeasonTotals.csv` | One row per player per season and season type (about 24,000 rows, 17 columns today) | about 2 MB | [download](https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-SeasonTotals.csv) |

The columns are the ones in the finished workbook, so a league you add is a new `FF_<League>` column in both files.

**Coming: a ready-made refresh workbook.** A small workbook with no data in it, whose two queries read the two files above, is coming once it has been confirmed in Excel. Until then, use the steps below: they build the same two queries yourself.

**The steps: Get Data, From Web.** Do these in a new, empty workbook in desktop Excel (Microsoft 365 or Excel 2019 or newer). The steps were written for desktop Excel on Windows. On a Mac the menu names differ (look for **Get Data (Power Query)**), and these steps are not tested there.

1. On the **Data** tab, choose **Get Data**, then **From Other Sources**, then **From Web**.
2. Paste the link `https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-PlayerGames.csv` and click **OK**.
3. If Excel asks how to connect, choose **Anonymous** and click **Connect**. (The files are public. If it offers to apply the setting to a level, keep `https://github.com/`. Excel may ask once more for a second address that ends in `githubusercontent.com`: choose **Anonymous** there too.)
4. If Excel asks about **privacy levels**, choose **Public** for this address.
5. In the preview window, click **Transform Data** (not Load). The Power Query window opens. On its **Home** tab, click **Advanced Editor**.
6. Select everything in the box, delete it, paste the `PlayerGames` code below, and click **Done**. If a yellow bar asks for credentials, click **Edit Credentials**, then **Anonymous**, then **Connect**.
7. On the **Home** tab, click **Close & Load**. Then do the same, from step 1, for `https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-SeasonTotals.csv` with the `SeasonTotals` code. To get new data later, choose **Data**, **Refresh All**.

`PlayerGames`:

```
let
    Source = Csv.Document(
        Web.Contents(
            "https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-PlayerGames.csv",
            [Timeout = #duration(0, 0, 10, 0)]
        ),
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
```

`SeasonTotals`:

```
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
```

The code names the columns that are whole numbers or text and treats every other column as a number, so a new statistic or league column needs no change. `en-US` makes the decimal point a full stop whatever your computer's regional settings are.

**Good to know.**

- A refresh may take about a minute or two (an estimate; not yet measured): Excel downloads about 40 MB and writes about 17 million cells.
- **Excel for the web may not be able to refresh these queries** (not tested). Use desktop Excel.
- **On a phone or tablet, use the finished workbook** (way 1). It opens there, and there is nothing to refresh.
- Refreshing reads the newest published files, which are the same data the finished workbook holds. The data is rebuilt after every publish (see "How often it is rebuilt").

**Other tools.** The two CSV files are plain text: UTF-8 (no byte-order mark), comma-separated, one header row, a full stop as the decimal mark, an empty field for "no value". Read the link straight into R (`read.csv(url)`), Python (`pandas.read_csv(url)`) or any tool that reads CSV. In Excel, load them with **Data**, **From Text/CSV** (keep the file origin on **65001: Unicode (UTF-8)**) or with the steps above, never by double-clicking the file, for two reasons: a double-clicked file makes Excel guess the encoding (accents such as in a player's name can come out garbled), and it treats a text cell that starts with `=`, `+`, `-` or `@` as a formula. No such cell is in the files today. Google Sheets cannot open `NFL-PlayerGames.csv`: it has about 17 million cells, more than a Google Sheet holds. `NFL-SeasonTotals.csv` fits.

**Data credit.** The data comes from [nflverse](https://github.com/nflverse), licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), and has been modified (scored for fantasy-football leagues and combined). See [`/DATA-LICENSE.md`](../../DATA-LICENSE.md).

## What is in the workbook

The finished workbook holds values only: no queries, no formulas, no connections and no macros. It has these sheets, in this order (the full specification is [`../CONTRACTS.md`](../CONTRACTS.md) section 13):

| Sheet | What it holds |
|---|---|
| `About` | The workbook version, the season and week the data runs through, when it was built, the pipeline and data versions, how many checks passed, where the data comes from and its licence, where to find the latest file, how to change scoring, and one line about each sheet. Start here. |
| `PlayerGames` | One row per player per game for the last ten seasons, with each league's fantasy points (`FF_<League>`), the Standard and PPR points from nflverse, and every statistic column. Team defense and special teams (D/ST) rows are included. |
| `SeasonTotals` | One row per player per season and season type: games played and, for each league, the total and the average fantasy points. |
| `Leagues`, `Scoring`, `Bonus` | The league list, the points per statistic and the bonus bands that were used to score the data. You read them here; you change them on GitHub (below). |
| `Checks` | The pipeline's data checks and their results. |
| `Dictionary` | What each column means. |

Every table has a header row, a filter and a frozen header, so you can sort and filter at once, and make your own PivotTables from them.

## How often it is rebuilt

After every successful data publish by the pipeline: in season on Tuesday, Wednesday and Thursday, on the 1st of every month, and whenever a scoring file is changed on GitHub (details in [`../03-pipeline/AUTOMATION.md`](../03-pipeline/AUTOMATION.md)). The file you downloaded is a snapshot; the `About` sheet says which data it holds. Download it again to get newer data, or refresh from Excel (way 2).

## Changing scoring

Edit the file in `NFL/02-config/` on GitHub. Saving it there reruns the pipeline, which rescores the data and replaces the workbook when the run on the Actions tab is green (usually within about ten minutes). Then download it again. [`../03-pipeline/AUTOMATION.md`](../03-pipeline/AUTOMATION.md) explains how, what to do when a run fails and how to start a run by hand; [`../02-config/README.md`](../02-config/README.md) explains the files. Changes made inside the downloaded workbook affect only that copy and are lost at the next download.

## Version history

| Version | Released | Notes |
|---|---|---|
| **3.002** (current) | 2026-11-21 | The same cells as 3.001 in a file of about 8 MB (8,432,121 bytes) instead of about 38 MB. Opens in desktop Excel with no repair message, in about a minute. |
| 3.001 | 2026-11-21 | The first workbook built on GitHub: values only, nothing to refresh. About 38 MB. |
| 2.001 | 2026-11-20 | Power Query workbook that refreshed itself in Excel. Retired: re-scoring 180,000 rows in Excel was too slow. It is no longer published here; its files are archived in `NFL/maintainer/archive-2.x/`. |

Only the current version is at the download link; it is rebuilt after every publish, and the `About` sheet inside says which data it holds.

The data is derived from nflverse, licensed CC BY 4.0; see [`/DATA-LICENSE.md`](../../DATA-LICENSE.md).
