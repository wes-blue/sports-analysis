# sports-analysis

Scored NFL fantasy-football data, rebuilt automatically on GitHub from public nflverse statistics, and a finished Excel workbook made from it.

## Download the workbook

**[Download NFL-Analysis.xlsx](https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx)** (about 8 MB; version 3.002)

The link never changes: every rebuild replaces the file behind it. Open it in Excel and click **Enable Editing** if Protected View appears. It takes about a minute to open. [`NFL/05-excel/README.md`](NFL/05-excel/README.md) has tips and the version history.

Prefer to refresh from Excel, or read the data in another tool? The same two tables are plain files: [`NFL-PlayerGames.csv`](https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-PlayerGames.csv) (about 38 MB) and [`NFL-SeasonTotals.csv`](https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-SeasonTotals.csv). For Excel there is also a ready-made [refresh workbook](https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis-Refresh.xlsx) (about 14 KB): open it, choose **Data**, **Refresh All**, and it loads both tables. [`NFL/05-excel/README.md`](NFL/05-excel/README.md) has the steps, including how to build the same queries yourself.

## What is in the workbook

- **About**: version, data-through date and where the data comes from. Start here.
- **PlayerGames**: about 180,000 player-games, newest first, with each league's fantasy points next to the player's name.
- **SeasonTotals**: one row per player per season, with totals and averages per league.
- **Leagues, Scoring, Bonus**: the scoring rules the numbers were built with.
- **Checks and Dictionary**: the pipeline's data checks and what every column means.
- Seasons 2017 to 2026, regular season and playoffs, plus team defense and special teams (D/ST) rows, scored for several leagues including one ESPN league.

## Read the data directly

Every published CSV is public at:

```
https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/<path>
```

For example, `.../NFL/04-data/scored/scored_2025.csv` holds every player-game of 2025 with its points per league. [`NFL/04-data/README.md`](NFL/04-data/README.md) lists the files and [`NFL/CONTRACTS.md`](NFL/CONTRACTS.md) defines every column.

## How and when it updates

GitHub Actions downloads the statistics, scores them, runs the checks, publishes the CSV files and rebuilds the workbook. It runs in season on Tuesday, Wednesday and Thursday, on the 1st of each month, and whenever a scoring file in [`NFL/02-config/`](NFL/02-config/README.md) changes on `main`. A run publishes only when every blocking check passes; otherwise the last good data stays. To see how fresh the data is, open [`NFL/04-data/status.csv`](NFL/04-data/status.csv). [`NFL/03-pipeline/AUTOMATION.md`](NFL/03-pipeline/AUTOMATION.md) explains the runs and alerts.

## What's in this repository

| Path | What it is | Ignore it? |
|---|---|---|
| [`NFL/`](NFL/README.md) | The NFL project and its guide | Start here for details |
| `NFL/02-config/` | Scoring rules, as CSV files | Only to change scoring |
| `NFL/03-pipeline/` | The Python code, its tests and the automation guide | Yes, unless you are a developer |
| `NFL/04-data/` | The published CSV files | No: this is the data |
| `NFL/05-excel/` | How to get the workbook | No |
| `NFL/06-qa/` | Test fixtures and evidence the checks read | Yes |
| `NFL/maintainer/` | How the project is run (plans, decisions, reviews). You can ignore it. | Yes |
| `.github/workflows/` | The scheduled workflows | Yes |
| `.claude/` | Instructions for Claude sessions | Yes |
| `LICENSE`, `DATA-LICENSE.md` | Licences and attribution | |

## Using the code yourself

See [`NFL/03-pipeline/README.md`](NFL/03-pipeline/README.md) for how to run the pipeline and its tests on your own computer (Python 3.11 or later).

## Questions and problems

Open an issue on this repository.

## Licence and attribution

- **Code and documentation:** MIT licence, see [`LICENSE`](LICENSE).
- **Data:** derived from [nflverse](https://github.com/nflverse/nflverse-data) data, licensed CC BY 4.0. See [`DATA-LICENSE.md`](DATA-LICENSE.md).

This project is not affiliated with or endorsed by nflverse, the NFL or ESPN.
