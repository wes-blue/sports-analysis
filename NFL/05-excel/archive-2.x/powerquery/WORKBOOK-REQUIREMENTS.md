# Workbook requirements for the 2.001 Power Query

For the workbook builder (E1). Everything the queries in this folder read, and where each loaded query lands. Names are case-sensitive and must match exactly. Paths are relative to `NFL/` in `wes-blue/sports-analysis`.

## 1. Layout rule (no overlap as rows grow)

- **No table may sit below another table on the same sheet.** Tables grow downward when rows are added.
- Two tables may sit side by side only if the left one has a fixed set of columns. The table that can gain columns (`tblScoring`, which gains one column per league) is the **rightmost** table on its sheet.
- Leave at least one empty column between neighbouring tables.
- Rows 1 to 3 of each sheet are free for a title and notes; tables start at row 4 (input tables) or row 5 (query outputs, with a label in row 4).

## 2. Named cell

| Name | Sheet and cell | Content | Used by |
|---|---|---|---|
| `WorkbookFolder` | `Config!$B$2` (label `Workbook folder` in `Config!$A$2`) | Formula `=LEFT(CELL("filename",$A$1),FIND("[",CELL("filename",$A$1))-1)`, which returns the workbook's folder with a trailing `\` (e.g. `C:\...\NFL\05-excel\`). Scope: Workbook. A single cell, not a table. | The DataLocation resolver in `Stats_Raw`, `Pipeline_Scored`, `Published_Seasons`, `Pipeline_Status`, `Check_Rules_Drift` |

Used only when `DataLocation` is blank (automatic local search). The cell is blank or `#VALUE!` until the workbook is saved; the queries then say so. In a OneDrive folder it returns a web address; the queries stop with a message telling the user to set `DataLocation`.

## 3. Input tables

### `tblConfig`: sheet `Config`, anchor `A4`

Columns: `Setting | Value | Allowed_Values | Description` (seeded from `02-config/pipeline_config.csv`, plus the `DataLocation` row). Format the `Value` column as **Text** so `2017`, `Latest-9` and paths are kept as typed (the queries also accept numbers).

| Setting | Default | Allowed values | Read by |
|---|---|---|---|
| `StartSeason` | `Latest-9` | A year (1999 or later) \| `Latest` \| `Latest-N` (N 0–30) | `Stats_Raw`, `Pipeline_Scored`, `Published_Seasons` |
| `EndSeason` | `Latest` | Same | same |
| `SeasonTypes` | `REG+POST` | `REG` \| `POST` \| `REG+POST` | same |
| `RoundDecimals` | `2` | Whole number 0–6 | `Scoring_Weights`, `Check_Rules_Drift` |
| `ReconcileTolerance` | `0.005` | 0 or a small positive number (blank = 0.005) | `Scoring_Weights` (for `Check_Reconciliation`) |
| `DataLocation` | `https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/` | a web address starting with `http` \| a folder path \| blank = automatic local search | the DataLocation resolver (D-037: the shipped value reads the published data from the web) |
| `PublishExtraColumns` | *(blank)* | Pipeline-only setting; may be kept for reference; the workbook ignores it | none |

`Latest` means the newest season in the published `seasons.csv`. Suggested Description for `DataLocation`: "Where the pipeline's CSV files are. As shipped: the published data on GitHub (read from the web). Or the full path of a folder that contains status.csv. Blank = the 04-data folder next to the workbook's folder."

Setting names must be unique; rows with a blank `Setting` are ignored.

### `tblLeagues`: sheet `Scoring`, anchor `A4`

Columns: `League | Description | Active | Reconcile_To | Notes` (seeded from `02-config/leagues.csv`). Extra columns to the right (e.g. a `Column_Check` formula) are ignored by the queries. Fixed columns: it may sit left of `tblScoring`. Occupies `A:E` (or `A:F` with `Column_Check`).

### `tblScoring`: sheet `Scoring`, anchor `H4` (rightmost table on the sheet)

Columns: `Metric | Category | Description | <one column per League, same names and order as tblLeagues> | Notes | Applies_To` (seeded from `02-config/scoring_weights.csv`, same column order as the file). Columns are found by name, so extra columns (e.g. `Metric_Check`) are allowed at the right end. One row per metric in `scoring_weights.csv`. League names may not be `Metric`, `Category`, `Description`, `Notes`, `Metric_Check` or `Applies_To`.

### `tblBonus`: sheet `Bonus`, anchor `A4`

Columns: `League | Metric | Lower | Upper | Points | Applies_To | Notes` (seeded from `02-config/bonus_rules.csv`, one row per band). Optional for `Bonus_Rules` (absent = no bands), but `Check_Rules_Drift` would then report every pipeline band as `only in pipeline`.

### `tblGolden`: sheet `Validation`, anchor `A4`

Columns: exactly the header of `06-qa/fixtures/golden_sample.csv` (25 rows), seeded from that file:
`season, week, season_type, player_id, player_display_name, position, team,` the stat columns of the fixture, `fantasy_points, fantasy_points_ppr, FF_Standard, FF_Half_PPR, FF_PPR, FF_League_1, FF_ESPN_League`.
`Golden_Keys` reads only `season, week, season_type, player_id, player_display_name` and every column whose name starts with `FF_`. Store `season`, `week` and the `FF_` values as numbers.

### `tblGoldenRules`: sheet `Validation`, to the right of `tblGolden` (one empty column between them), row 4

Columns: `League | Rules_SHA256 | RoundDecimals`, seeded from `06-qa/fixtures/fixture_contracts.csv` (`league`, `rules_sha256`, `round_decimals`): the rules each league's expected values were made with. Read by `Pipeline_Status` (optional: without it every league contract row is `OK`, as in 1.006). Fixed columns; `tblGolden` to its left has a fixed column set too. Store `Rules_SHA256` as text and `RoundDecimals` as a number. The owner does not edit it.

`tblBaseline` (1.x) is **no longer needed**: `Check_RowCounts` compares with the published `seasons.csv`.

## 4. Query outputs

Only-connection queries: `Stats_Raw`, `Scoring_Weights`, `Bonus_Rules`, `Pipeline_Scored`, `Published_Seasons`, `Golden_Keys`. `Stats_Scored` is connection only plus Data Model (no sheet).

All loaded tables go on one sheet, **`Checks`**, at row 5, side by side, each with a fixed column set and a blank column to its right. Put a label (the query name) in row 4 above each anchor.

| Query | Anchor | Columns (in order) | Span |
|---|---|---|---|
| `Pipeline_Status` | `Checks!A5` | `Section, Item, Value, Result, Detail` | A–E |
| `Check_Parity` | `Checks!G5` | `League, Rows_Compared, Rows_Equal, Rows_Different, Largest_Difference, Only_In_Workbook, Only_In_Pipeline, Status, Example` | G–O |
| `Check_Rules_Drift` | `Checks!Q5` | `League, Kind, Item, Workbook, Pipeline, Status` | Q–V |
| `Check_Metrics` | `Checks!X5` | `Metric, In_Stats_Raw, Is_Numeric, Used_By_Leagues, Status` | X–AB |
| `Check_Reconciliation` | `Checks!AD5` | `League, Reconcile_To, Rows_Compared, Rows_Mismatched, Match_Pct, Status, Worst_Examples` | AD–AJ |
| `Check_RowCounts` | `Checks!AL5` | `season, season_type, Season_Status, Max_Week, Published_Player_Rows, Workbook_Player_Rows, Published_DST_Rows, Workbook_DST_Rows, Status` | AL–AT |
| `Check_Golden` | `Checks!AV5` | `League, Golden_Rows, Matched, Mismatched, Status, Worst_Examples` | AV–BA |
| `Check_Integrity` | `Checks!BC5` | `Check, Expected, Actual, Status` | BC–BF |

Gap columns: F, P, W, AC, AK, AU, BB. Expected row counts on 2026-11-19 data: Pipeline_Status 29 (11 run rows + 5 league contracts + 1 row per gate in checks/gates.csv, 13 on that data), Check_Parity 5, Check_Rules_Drift 1, Check_Metrics 81, Check_Reconciliation 2, Check_RowCounts 19, Check_Golden 5, Check_Integrity 3. Pipeline_Status, Check_Rules_Drift and Check_RowCounts vary the most; all grow downward only.

Suggested formats: `Check_Reconciliation[Match_Pct]` as percentage; `Check_Parity[Largest_Difference]` with 2 decimals; conditional formatting on the `Status` / `Result` columns (`PASS`, `OK`, `matches pipeline`, `same` = green; `FAIL`, `MISSING`, `UNSUPPORTED` = red; `differs...`, `changed`, `only in ...`, `NOT PUBLISHED`, `NOT APPLICABLE`, `RULES CHANGED`, `DECIMALS CHANGED`, `NO TEST VALUES`, `WARN`, `CHECK` = amber).

## 5. Sheets summary

| Sheet | Contents |
|---|---|
| `Config` | `WorkbookFolder` (B2), `tblConfig` (A4) |
| `Scoring` | `tblLeagues` (A4), `tblScoring` (H4, rightmost) |
| `Bonus` | `tblBonus` (A4) |
| `Validation` | `tblGolden` (A4), `tblGoldenRules` (row 4, right of `tblGolden`) |
| `Checks` | the eight loaded query tables at row 5 (section 4) |

The M text of every query is in the `.pq` files; `manifest.json` gives the paste order and load settings.
