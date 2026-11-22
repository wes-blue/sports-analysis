# NFL-Analysis workbook (Excel)

The NFL workbook is built for you on GitHub. You download it and open it; there is nothing to refresh, install or paste.

## Get the workbook

**[Download NFL-Analysis.xlsx](https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx)**

`https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx`

The link stays the same: every rebuild replaces the file behind it. The file is **not in this folder or anywhere in the repository's files**: it is about 8 MB and is rebuilt on every publish. It is a release asset, and the release page is <https://github.com/wes-blue/sports-analysis/releases/tag/nfl-workbook>.

**Opening it.** The file is about 8 MB but holds about 17 million cells, so Excel takes about a minute to open it; it opened in desktop Excel with no repair message. Excel opens a downloaded file in Protected View: click **Enable Editing** so that sorting and filtering work. The newest games are at the top of `PlayerGames`, with your league columns (`FF_<League>`) right after the player's name.

**If the link answers "not found".** The workbook is being replaced or has not been built yet. Wait two minutes and try again. If it still answers "not found", open the repository's **Actions** tab, choose **nfl-pipeline-weekly**, click **Run workflow**, tick **workbook_only** and run it; the link works when that run is green. [`../03-pipeline/AUTOMATION.md`](../03-pipeline/AUTOMATION.md) has the details.

## What is in the workbook

The workbook holds values only: no Power Query, no formulas, no connections and no macros. It has these sheets, in this order (the full specification is [`../CONTRACTS.md`](../CONTRACTS.md) section 13):

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

After every successful data publish by the pipeline: in season on Tuesday, Wednesday and Thursday, on the 1st of every month, and whenever a scoring file is changed on GitHub (details in [`../03-pipeline/AUTOMATION.md`](../03-pipeline/AUTOMATION.md)). The file you downloaded is a snapshot; the `About` sheet says which data it holds. Download it again to get newer data.

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
