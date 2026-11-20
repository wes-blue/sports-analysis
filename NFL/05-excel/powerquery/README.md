# Power Query for the pipeline-fed workbook (version 2.001)

The Python pipeline runs on GitHub. It downloads nflverse, builds long-TD counts and team D/ST rows, scores every league, and publishes plain CSV files to `NFL/04-data/` on the `main` branch of `wes-blue/sports-analysis` (contract: `../../CONTRACTS.md` §5). The workbook's Power Query:

1. reads those CSV files **from the web** by default, at `https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/` (decision D-037), so your PC needs no copy of the repository, no git and no Python;
2. **re-scores every league with the weights on your own Scoring and Bonus sheets**, so you can still change points per league in Excel;
3. checks itself against the pipeline's scores (`Check_Parity`) and rules (`Check_Rules_Drift`).

Status: **not yet run in Excel.** All 15 files pass Microsoft's M parser and a scope and firewall lint (`05-excel/build/pq/lint.js`). The logic was reproduced in Python on 10 seasons of published data read from a local folder (`05-excel/build/pq/emulate.py`): the workbook's scores equal the pipeline's on all 180,233 rows for all 5 leagues. The web reading itself cannot run outside Excel. It uses the same Power Query function (`Web.Contents` with a fixed site plus `RelativePath`) that read nflverse from github.com in real Excel in versions 1.003 and 1.004.

**Two ways to get a working workbook** (`05-excel/README.md` has the order): try the experimental workbook with the queries already installed first (`05-excel/experimental/README.md`; not yet opened in Excel). The paste-ready workbook with the steps below is the fallback; adding the 15 queries by hand takes **about 30 minutes**, once.

**Do not edit the M inside Excel.** The `.pq` files here are the source of truth. If something must change, ask for a new `.pq` and paste it again.

## 1. Where the data is read from

Every query that reads data starts with the same "DataLocation resolver" block, which reads the setting `DataLocation` (Config sheet, table `tblConfig`, column `Value`):

| `DataLocation` value | What happens |
|---|---|
| `https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/` (**as shipped**) | Reads each file from GitHub over the web: about 25 files and 45 MB at the first refresh. |
| another web address starting with `http` | The same, from that address (for example a fork). It must be the address of the folder that holds `status.csv`. |
| a folder path, for example `D:\nfl\04-data\` | Reads from that folder on your PC (trailing `\` optional; `/` is accepted). |
| blank | Automatic local search: the `04-data` folder next to the workbook's folder (right when the workbook sits in `NFL\05-excel` or `NFL\08-releases` of a copy of the repository), then a `04-data` folder inside the workbook's folder. The workbook must have been saved, because the named cell `WorkbookFolder` (Config sheet, B2) supplies its folder. |

**How the web reading works.** The address is split into the site (`https://raw.githubusercontent.com`) and the rest. Every file is read as `Web.Contents(site, [RelativePath = rest + file])`, so Excel sees one data source, the site, and asks for credentials and the privacy level once. A failed read is reported by HTTP status, with what to do:

| GitHub answers | What you see | Meaning |
|---|---|---|
| 200 | data | The file exists. GitHub's raw server sends it as `text/plain; charset=utf-8`, compressed in transit; Power Query unpacks it. |
| 404 | `DataLocation.Error: HTTP 404 reading https://.../status.csv. Nothing is published at that address. If you are setting the workbook up ...` | The data is not on `main` yet (the pull request is not merged), the address is wrong, or the repository is private: GitHub answers all three the same way. |
| 401 or 403 | `DataLocation.Error: HTTP 403 ... GitHub refused the request ...` | A login is needed, or GitHub is limiting requests. |
| 408, 429, 5xx | `... GitHub is busy or limiting requests. Wait a few minutes and Refresh All again.` | Temporary. |

Checked on 2026-11-20 by fetching real files from `raw.githubusercontent.com` with the same kind of request the queries make: an existing file answers 200 with no redirect; a missing file, a missing branch and a missing repository all answer 404 with the 14-byte body `404: Not Found`; a plain `http://` address is redirected (301) to `https://`. The shipped address answered 404 that day, because the data was not yet on `main`.

**GitHub's cache.** The raw server lets copies be kept for 5 minutes (`Cache-Control: max-age=300`). For up to 5 minutes after the pipeline publishes, a refresh can still get the previous files, or a mix of old and new ones. If new data was published within the last few minutes and a check is amber or red, wait 5 minutes and Refresh All again.

## 2. Prerequisites

- Windows desktop Excel for Microsoft 365 (the Data Model is needed for `Stats_Scored`). Not Excel for Mac or Excel for the web.
- The workbook, downloaded from the repository's web page (`05-excel/README.md`). Nothing else is downloaded.
- The published data on `main`. Until the pull request that brings this project to `main` is merged (`BLOCKERS.csv` Q-015), the shipped address answers 404 (section 1).
- An internet connection when you refresh.

## 3. What Excel asks the first time, and what to answer

**a. Opening a downloaded file.** Excel opens files from the internet in Protected View: click **Enable Editing**. If a yellow bar says *External Data Connections have been disabled* (or *Data connections have been disabled*), click **Enable Content**.

**b. Credentials for the web site** (at the first refresh; in the Power Query window it is a yellow bar *Please specify how to connect* › **Edit Credentials**). The dialog is called **Access Web content**:
1. Choose **Anonymous** on the left (it is usually already selected).
2. In *Select which level to apply these settings to*, choose `https://raw.githubusercontent.com/` (the shortest entry).
3. Click **Connect**.

Do not choose Windows, Basic or Organizational account: the data is public, and a login would be refused.

**c. Privacy levels** (*Information is required about data privacy*; in the Power Query window click **Continue**). Excel asks because the workbook's own settings (`DataLocation`, the season window) decide which files are read.
1. Set **Current Workbook** to **Public**.
2. Set `https://raw.githubusercontent.com/` to **Public**. Click **Save**.

Nothing private leaves the workbook: only file names and season years go into the web addresses, and the data itself is public. The same answer (Public) was used in real Excel in 1.003 for `https://github.com`.

Later changes: Data › Get Data › **Data Source Settings** › select the site (or Current Workbook) › **Edit Permissions** (credentials and privacy level) or **Clear Permissions** (Excel then asks again at the next refresh).

**Fallback, only if a privacy or Formula.Firewall message keeps coming back:** Data › Get Data › Query Options › Current Workbook › Privacy › **Ignore the Privacy Levels and potentially improve performance** › OK, then Refresh All. Harmless for this workbook, but it applies to every query you add to it later.

**Reading a local folder instead** (`DataLocation` = a path or blank): no credentials are asked. The privacy prompt lists the folder: choose the folder itself (the entry ending in `\04-data\`, not a single file) and set it to Public, with Current Workbook Public.

Firewall rule D-009 (proven in Excel in 1.003): a query that reads a workbook table, a file or the web never references another query, and a query that combines other queries reads no source. That is why the resolver block is repeated, identically, in `Stats_Raw`, `Pipeline_Scored`, `Published_Seasons`, `Pipeline_Status` and `Check_Rules_Drift`, and why `Published_Seasons` exists (so `Check_RowCounts` can compare with `seasons.csv` without reading it).

## 4. Add the queries, in this order (paste-ready workbook only)

The experimental workbook has them installed already. For the paste-ready workbook, for each query: **Data › Get Data › From Other Sources › Blank Query › Home › Advanced Editor**, select all, delete, paste the query's code (in the workbook: choose its `PQ_` name in the Name Box on the M_Code sheet and press Ctrl+C), **Done**, rename the query to exactly the name shown (Query Settings › Name), then **Home › Close & Load To…** with the setting shown. Tip: switch off background refresh while adding (right-click a query › Properties › untick Enable background refresh), because each Close & Load may refresh what it depends on.

| # | Query name | File | Close & Load To… |
|---|---|---|---|
| 1 | `Stats_Raw` | `Stats_Raw.pq` | Only Create Connection |
| 2 | `Scoring_Weights` | `Scoring_Weights.pq` | Only Create Connection |
| 3 | `Bonus_Rules` | `Bonus_Rules.pq` | Only Create Connection |
| 4 | `Pipeline_Scored` | `Pipeline_Scored.pq` | Only Create Connection |
| 5 | `Published_Seasons` | `Published_Seasons.pq` | Only Create Connection |
| 6 | `Golden_Keys` | `Golden_Keys.pq` | Only Create Connection |
| 7 | `Stats_Scored` | `Stats_Scored.pq` | Only Create Connection **and** tick **Add this data to the Data Model** |
| 8 | `Pipeline_Status` | `Pipeline_Status.pq` | Table › Existing worksheet › `=Checks!$A$5` (5 columns, A–E) |
| 9 | `Check_Parity` | `Check_Parity.pq` | Table › Existing worksheet › `=Checks!$G$5` (9 columns, G–O) |
| 10 | `Check_Rules_Drift` | `Check_Rules_Drift.pq` | Table › Existing worksheet › `=Checks!$Q$5` (6 columns, Q–V) |
| 11 | `Check_Metrics` | `Check_Metrics.pq` | Table › Existing worksheet › `=Checks!$X$5` (5 columns, X–AB) |
| 12 | `Check_Reconciliation` | `Check_Reconciliation.pq` | Table › Existing worksheet › `=Checks!$AD$5` (7 columns, AD–AJ) |
| 13 | `Check_RowCounts` | `Check_RowCounts.pq` | Table › Existing worksheet › `=Checks!$AL$5` (9 columns, AL–AT) |
| 14 | `Check_Golden` | `Check_Golden.pq` | Table › Existing worksheet › `=Checks!$AV$5` (6 columns, AV–BA) |
| 15 | `Check_Integrity` | `Check_Integrity.pq` | Table › Existing worksheet › `=Checks!$BC$5` (4 columns, BC–BF) |

The same order, dependencies and load settings are in `manifest.json`. Every query comes after the queries it depends on (`Check_Reconciliation` and `Check_Golden` also read `Pipeline_Status` and `Check_Rules_Drift`, numbers 8 and 10). Every Checks table grows downward only and has a blank column on its right, so tables never overlap.

## 5. First refresh and what you should see

**Data › Refresh All.** The first refresh downloads the data and scores about 180,000 rows for every league (row by row, as in 1.x). How long it takes in Excel has not been measured: allow several minutes, and note the time. Each loaded check is evaluated on its own; whether Excel then downloads a file once per refresh or once per check that needs it is not known yet (only Excel can show it).

Expected with the default settings (Latest-9 to Latest, REG+POST) on the data published 2026-11-20 by pipeline 1.2.0 (seasons 2017–2026, 2026 through REG week 10). Numbers grow each week.

**What each status means** (the same legend is on the workbook's Start_Here sheet, section 6, which also explains each check): Green = good: `PASS`, `OK`, `same`, `matches pipeline`. Amber = read the row; often expected after you change a rule: `NOT APPLICABLE`, `RULES CHANGED`, `DECIMALS CHANGED`, `NO TEST VALUES`, `WARN`, `CHECK`, `changed`, `differs`, `only in workbook`, `only in pipeline`, `not in pipeline`, `not scored in workbook`, `NOT PUBLISHED`, `NO ROWS`, `MISSING (zero weight everywhere)`. Red = act: `FAIL`, `MISSING`, `MISSING COLUMN`, `NOT NUMERIC`, `UNSUPPORTED`. `INFO` = information only.

| Where | Expected |
|---|---|
| `Stats_Raw` | 180,233 rows (174,945 player rows + 5,288 team D/ST rows), 93 columns on that data (9 identity + 82 metrics, including `dst_points_allowed_excl_def` (D-038), + 2 nflverse fantasy columns) |
| `Stats_Scored` | Same rows, plus `FF_Standard`, `FF_Half_PPR`, `FF_PPR`, `FF_League_1`, `FF_ESPN_League` |
| `Pipeline_Status` | First row `Data read from` = the web address; Data contract version `1` / `OK`; Data through `2026 REG week 10`; every league contract `OK`; every gate `PASS` |
| `Check_Parity` | 5 rows, each `matches pipeline`, Rows_Compared 180,233, Rows_Different 0 |
| `Check_Rules_Drift` | One row: `Workbook rules equal the rules of the published data` / `same` |
| `Check_Metrics` | One row per metric in tblScoring and tblBonus, every Status `OK` |
| `Check_Reconciliation` | Standard and PPR `PASS`, 100% (174,945 player rows; D/ST rows excluded) |
| `Check_RowCounts` | 19 rows (2017–2025 REG and POST, 2026 REG), every Status `PASS`; 2026 shows `in_progress` |
| `Check_Golden` | 5 leagues, each 25 of 25 matched, `PASS` |
| `Check_Integrity` | `PASS`, `PASS`, then `INFO` with 5,288 D/ST rows |

If the workbook's rules differ from the rules of the published data (for example while a scoring change is on its way through the pipeline), `Check_Parity`, `Check_Rules_Drift`, `Check_Golden` and `Check_Reconciliation` show amber for that league instead: section 8.

## 6. Each week

1. Open the workbook, **Data › Refresh All**. Nothing else: GitHub runs the pipeline and publishes new data Tuesday to Thursday in season (`03-pipeline/AUTOMATION.md`).
2. Look at the Checks sheet: `Pipeline_Status` shows how far the data goes (`Data through`); everything should be green unless you changed rules on purpose.

Optional: Data › Queries & Connections › right-click `Stats_Scored` › Properties › **Refresh data when opening the file**.

## 7. Point the workbook at a different address or a folder

Config sheet, `tblConfig`, row `DataLocation`, column `Value`:
- the published data (as shipped): `https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/`;
- another web address: the address of the folder that holds `status.csv`, ending with `/`. Excel asks again for credentials and privacy only if the site is different (section 3);
- a folder on your PC: its full path, for example `D:\Data\04-data\`. Excel may ask for the folder's privacy level (section 3);
- blank: the automatic local search (section 1).

## 8. Change scoring, and what the checks then show

There are two places to change scoring, and they can be used together.

**A. In the workbook** (yours alone, at once): edit the yellow cells in `tblScoring` (Scoring sheet) or `tblBonus` (Bonus sheet), then Refresh All. `Stats_Scored` uses your numbers at once; the published data does not change. On the Checks sheet you then see, as expected:
- `Check_Parity` for that league: `differs: workbook rules changed? (see Check_Rules_Drift)`, with the number of rows that differ, the largest difference and one example player-game. Information, not an error.
- `Check_Rules_Drift`: one row per change, for example `ESPN_League | Weight | receptions | 0.5 | 1 | changed`.
- `Check_Golden` for that league: `NOT APPLICABLE` (its 25 expected values were made with other rules), with the reason in Worst_Examples. A control league (`Standard`, `PPR`) also shows `NOT APPLICABLE` in `Check_Reconciliation`, because it no longer follows nflverse's own scoring.

**B. On GitHub** (the published scores change): edit the file in `NFL/02-config/` on GitHub (`scoring_weights.csv`, `bonus_rules.csv`, or `pipeline_config.csv` for `RoundDecimals`). Saving it there starts the pipeline, which publishes new data a few minutes later. `03-pipeline/AUTOMATION.md` explains this side; `02-config/README.md` explains the files.
- **What the pipeline reports.** It still publishes. For the league you changed, the stored test values (25 hand-checked player-games, and your ESPN week 8 lineup for `ESPN_League`) no longer apply, so the gate `G-GOLDEN` (also `G-ESPN` for `ESPN_League`, and `G-RECON` for a control league) reports `WARN` "not applicable: rules for <League> changed since the expected values were made". Leagues you did not change keep their tests (`BLOCKERS.csv` Q-013). A mistake in the file (for example a misspelt statistic) stops the publish with `G-CONFIG` `FAIL`: nothing is published and the workbook keeps reading the previous data.
- **What the workbook shows at the next Refresh All.** `Pipeline_Status` shows those gates in amber (`WARN`) and that league's contract row as `RULES CHANGED`. `Check_Golden` (and `Check_Reconciliation` for a control league) show `NOT APPLICABLE` for it: the same verdict as the pipeline's gates. If you did not make the same change in the workbook, `Check_Parity` says `differs` and `Check_Rules_Drift` lists the pipeline's new rules (its Pipeline column holds each new value): copy them into `tblScoring` or `tblBonus` and Refresh All, and both return to `matches pipeline` and `same`.

**Changes that touch every league.** `RoundDecimals`: with 0 or 1 decimals, `Check_Golden` shows `NOT APPLICABLE` for every league (the expected values have 2 decimals), and `Check_Reconciliation` widens its tolerance to half a unit of the last decimal (0.5 or 0.05), as the pipeline's `G-RECON` gate does, so it stays `PASS`. A position gate (`Applies_To`) changed in the workbook counts as a change to every league.

The workbook and the pipeline decide "changed on purpose" the same way. The pipeline compares each league's rules with those recorded beside the expected values (`06-qa/fixtures/fixture_contracts.csv`). The workbook holds a copy of that record in `tblGoldenRules` (Validation sheet), compares it with the published rules (`Pipeline_Status`), and compares its own tables with the published rules (`Check_Rules_Drift`). Do not edit `tblGoldenRules`.

**Add a league:**
1. `tblLeagues`: new row, `League` = a name with letters, digits and underscores starting with a letter (for example `My_League`), `Active` = `Yes`, `Reconcile_To` blank.
2. `tblScoring`: insert a column before `Notes` with exactly the same header, and fill a weight for each metric (blank = 0).
3. Optional: `tblBonus` rows with that `League` name.
4. Refresh All. `Stats_Scored` gets `FF_My_League` without any M change.
- `Check_Parity`: `My_League | not in pipeline: league added or renamed in the workbook?`.
- `Check_Rules_Drift`: `My_League | League | Active | active | (absent)`, then one `only in workbook` row per non-zero weight and band.
- `Check_Golden` does not list it (no expected values exist for it).

**Switch a league off** (`Active` = `No`): `Check_Parity` shows `not scored in workbook: league inactive or renamed here?` and the drift check shows `inactive` vs `active`.

**Score a new statistic:** add a row to `tblScoring` with the exact column name from the Data_Dictionary sheet. If `player_week` does not contain that column, `Check_Metrics` says `MISSING COLUMN`: add the metric to `02-config/scoring_weights.csv` on GitHub (or to `PublishExtraColumns` in `pipeline_config.csv`) so the pipeline publishes it.

## 9. Troubleshooting

| What you see | Why | Fix |
|---|---|---|
| `DataLocation.Error: HTTP 404 reading https://raw.githubusercontent.com/.../status.csv ...` (or `seasons.csv`) | Nothing is published at that address: the pull request is not merged yet, the address in `DataLocation` is wrong, or the repository is private. | If you are just setting up: wait for the merge (`BLOCKERS.csv` Q-015), then Refresh All. Otherwise put the shipped address back into `DataLocation` (section 7). |
| The same 404 for one season file only (for example `player_week/player_week_2025.csv`) | `seasons.csv` lists a season whose file is missing: a publish in progress, or GitHub's 5-minute cache (section 1). | Wait 5 minutes and Refresh All again. If it stays, tell Claude. |
| `DataLocation.Error: HTTP 403` or `401` | GitHub refused: a login is needed (private repository) or requests are being limited. | Wait a few minutes and Refresh All. If it stays, check `DataLocation`. |
| `DataLocation.Error: HTTP 429` or `5xx`, or the refresh times out | GitHub is busy or limiting requests, or the connection dropped. | Wait a few minutes and Refresh All again. |
| `We couldn't authenticate with the credentials provided` | A login type other than Anonymous was chosen for the site. | Data › Get Data › Data Source Settings › `https://raw.githubusercontent.com/` › Edit Permissions › Credentials › Edit › **Anonymous** › Save, then Refresh All. |
| `DataSource.Error: The remote name could not be resolved` or `Unable to connect` | No internet connection, or a proxy or firewall blocks `raw.githubusercontent.com`. | Connect and Refresh All again. To work offline, download the `NFL/04-data` folder and set `DataLocation` to its path (section 7). |
| `Formula.Firewall: ... has privacy levels which cannot be used together` or a privacy prompt that keeps returning | Current Workbook and the site have incompatible privacy levels. | Set both to Public (section 3), or Ignore the Privacy Levels for this workbook. |
| `Formula.Firewall: Query 'X' (step 'Y') references other queries or steps, so it may not directly access a data source` | The M was edited in Excel, or a query was pasted under the wrong name. | Paste the original `.pq` again under the exact name. |
| `DataLocation.Error: ... starts with http but is not a web address` | A typing error in `DataLocation`. | Put the shipped address back (section 7). |
| `DataLocation.Error: No published pipeline data (status.csv) found in: ...` | `DataLocation` is blank or a folder, and no folder tried holds `status.csv`. The message names the folders tried. | Set `DataLocation` to the shipped web address, or to the folder that contains `status.csv`. |
| The same message, **but the folder it names does contain `status.csv`**, and Excel never asked about privacy | Probably a privacy question that Excel raised while the queries were testing the folder: the test treats any failed read as "not found". Not yet seen in Excel. | Data › Get Data › Data Source Settings › the `04-data` folder (and Current Workbook) › Edit Permissions › Privacy Level **Public**, then Refresh All. If it stays: Ignore the Privacy Levels (section 3). |
| `DataLocation.Error: ... Excel reports this workbook's folder as a web address ...` | `DataLocation` is blank and the workbook is in a OneDrive or SharePoint folder. | Set `DataLocation` to the shipped web address (section 7). |
| `DataLocation.Error: ... the named cell WorkbookFolder is blank or shows an error ...` | `DataLocation` is blank and the workbook was never saved. | Set `DataLocation` to the shipped web address, or save the workbook. |
| `Config.Error: tblConfig: setting 'StartSeason' ...` | Blank or unreadable season setting. | Use a year (for example `2017`), `Latest` or `Latest-N` (N 0–30). |
| `Config.Error: No published season between 2010 and 2012` | The window has no published season. | Change StartSeason / EndSeason; `Pipeline_Status` shows the pipeline's window. |
| `Check_RowCounts` shows `NOT PUBLISHED` rows | The window asks for seasons the pipeline did not publish. | Narrow the window, or widen the pipeline's window in `02-config/pipeline_config.csv`. |
| `Check_RowCounts` shows `FAIL`, or `Check_Parity` says `blank scores on one side` or `row sets differ` | Files from two different publishes were read (GitHub's 5-minute cache, section 1), or, for a local folder, a partial copy. | Wait 5 minutes and Refresh All again. |
| `Expression.Error: The key didn't match any rows in the table` | A table (`tblConfig`, `tblLeagues`, `tblScoring`, `tblGolden`) is missing or renamed. | Restore the table name (Table Design › Table Name). |
| `Scoring.Error: tblScoring has no column named 'X'` | A league in `tblLeagues` has no weights column. | Add the column with exactly that header, or set the league inactive. |
| `Bonus.Error: tblBonus row (...)` | A band has no league, no metric, no points, no bound, Lower > Upper, or a league not in `tblLeagues`. | Fix that row on the Bonus sheet. |
| `DataSource.Error: player_week files lack column(s) season, ...` or `Pipeline_Status` shows `UNSUPPORTED` | The data uses another data contract version. | Ask for queries that match the new version. |
| `Check_Parity` says `differs` and you changed nothing | The pipeline published new rules (someone changed `02-config`). | Read `Check_Rules_Drift`; copy the pipeline's rules into the tables, or change `02-config` back. |
| `Check_Golden` or `Check_Reconciliation` shows `NOT APPLICABLE` | That league's rules were changed on purpose, in the workbook or on GitHub (section 8). Worst_Examples says which. | Nothing to fix. |
| Refresh is slow | Each loaded check evaluates `Stats_Scored` again (Excel does not share results between queries), and the data comes over the web. | Narrow the window, or refresh only `Stats_Scored` routinely and run the checks weekly. |

## 10. Known limitations

- Not yet executed in Excel; see `manifest.json` for each query's status.
- Scoring is row by row (Table.AddColumn with a record function per league), kept as proven in 1.x. `Check_Parity` and the row-count and integrity checks are column- or list-based.
- A non-numeric value in a metric column becomes null (scored as 0), as in 1.x; blank cells are turned into null before typing, so no conversion errors are raised for them.
- `Check_Golden` and `Check_Reconciliation` follow the pipeline's "changed on purpose" rule per league, with two simplifications: a position gate changed in the workbook counts for every league, and a league renamed without other changes shows as `SKIPPED (column not in Stats_Scored)` in `Check_Golden`, where the pipeline checks it under its new name.
- `Check_Rules_Drift` compares effective weights (a missing row or column counts as 0), gates as sets of codes (order and case ignored) and bands after summing identical bands (they stack). It does not compare `Description`, `Notes` or `Reconcile_To`.
- Up to 5 minutes after a publish, GitHub's cache can serve the previous files (section 1).
