# sports-analysis

Fantasy-sports data that builds and checks itself on GitHub, and a finished Excel workbook built from it.

For each sport, a pipeline downloads public statistics, scores them for one or more fantasy leagues, checks the result, publishes plain CSV files in this repository and builds an Excel workbook from them. GitHub Actions runs the pipeline on a schedule. A reader needs only Excel to use the workbook: no Python, no git, no copy of the repository, and nothing to refresh.

## Download the NFL workbook

**[Download NFL-Analysis.xlsx](https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx)**, the finished workbook. Open it in Excel; its `About` sheet says which data it holds. The link never changes: every rebuild replaces the file behind it. [`NFL/05-excel/README.md`](NFL/05-excel/README.md) says what is in it.

The file is about 38 MB, so allow a little time for the download and for Excel to open it (about a minute to open in Excel). Excel opens a downloaded file in Protected View: click **Enable Editing** so that sorting and filtering work.

If the link answers "not found": the workbook is being replaced or has not been built yet. Wait two minutes and try again. If it still answers "not found", open the repository's **Actions** tab, choose **nfl-pipeline-weekly**, click **Run workflow**, tick **workbook_only** and run it; the link works when that run is green. [`NFL/03-pipeline/AUTOMATION.md`](NFL/03-pipeline/AUTOMATION.md) explains the runs. [`NFL/08-releases/RELEASES.md`](NFL/08-releases/RELEASES.md) lists the releases.

## Sports

| Sport | Folder | What it covers | Workbook | Status |
|---|---|---|---|---|
| NFL | [`NFL/`](NFL/README.md) | Weekly player stats for a rolling 10 seasons (regular season and playoffs), team defense and special teams (D/ST) rows, long-touchdown counts, and fantasy points for several scoring systems, including one ESPN league | `NFL-Analysis` 3.001 | Moved here on 2026-11-20. Version 3.001, the workbook built on GitHub, was released on 2026-11-21; version 2.001 (Power Query) is retired; [`NFL/08-releases/RELEASES.md`](NFL/08-releases/RELEASES.md) shows the releases. |

NFL is the only sport for now. The structure allows more.

## How a sport is laid out

Every sport has its own top-level folder with the same numbered subfolders:

| Subfolder | Holds |
|---|---|
| `01-plan/` | `plan.json`: the plan, requirements, risks and roadmap (rendered to `PLAN.md`) |
| `02-config/` | The CSV files a person edits: leagues, scoring weights, bonus bands, settings |
| `03-pipeline/` | The code that downloads, scores, checks and publishes, with its tests |
| `04-data/` | The published CSV files. Written only by the pipeline. |
| `05-excel/` | Where to get the workbook, and the archive of the retired Power Query workbook |
| `06-qa/` | QA reports, evidence and test fixtures |
| `07-research/` | Design notes |
| `08-releases/` | The release register |

Each sport also has a `README.md`, a `PLAN.md` and a `CONTRACTS.md` that defines every file format. Shared across sports: `00-Governance/` (charter, versioning policy, decision log), `BLOCKERS.csv` (questions waiting on the owner) and `.github/workflows/` (one set of workflows per sport, named `<sport>-pipeline-*.yml`). [`_Sport-Template/`](_Sport-Template/README.md) is the skeleton and checklist for adding a sport.

## Use the NFL workbook

1. Download it with the link above and open it in Excel; click **Enable Editing** if Excel shows the Protected View bar. There is no query to add and nothing to refresh.
2. To get newer data, download it again. It is rebuilt after every pipeline publish, in season on Tuesday, Wednesday and Thursday.
3. To change the scoring, edit a file in [`NFL/02-config/`](NFL/02-config/README.md) on GitHub. Saving it reruns the pipeline, which rebuilds the workbook; download it again once the run on the Actions tab is green (usually within about ten minutes). [`NFL/03-pipeline/AUTOMATION.md`](NFL/03-pipeline/AUTOMATION.md) has the steps.

The Power Query workbooks of version 2.001 are retired; see [`NFL/05-excel/archive-2.x/README.md`](NFL/05-excel/archive-2.x/README.md).

## Read the published NFL data

Every file in `NFL/04-data/` can be read by anyone, from a browser, Excel, Python, R or any other tool, at:

```
https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/<path>
```

For example, `.../NFL/04-data/scored/scored_2025.csv` holds every player-game of 2025 with its fantasy points per league. These addresses serve the files on the `main` branch. [`NFL/04-data/README.md`](NFL/04-data/README.md) lists the files, and [`NFL/CONTRACTS.md`](NFL/CONTRACTS.md) §5 defines every column.

## It updates itself

The NFL workflows in `.github/workflows/` run the pipeline and rebuild the workbook during the season on Tuesday, Wednesday and Thursday, on the 1st of every month, and whenever a scoring file in `NFL/02-config/` is changed on `main`. A run publishes only when every blocking check passes; otherwise the last good data stays in place. The pipeline first published data on GitHub on 2026-11-20, and the first workbook was built and uploaded on 2026-11-21 by the run that the 3.001 merge started.

When the data looks out of date:

1. Open [`NFL/04-data/status.csv`](NFL/04-data/status.csv): `generated_utc` is when the data was last published, and `latest_season` and `latest_week` are what it covers.
2. Look at the repository's **Issues** for an open issue labelled `nfl-pipeline-alert-*`: a failed or stale run opens one and says what went wrong.
3. Look at the **Actions** tab for the latest `nfl-pipeline-*` runs.

`NFL/03-pipeline/AUTOMATION.md` explains each workflow, what an alert means and how to start a run by hand.

## Licence and attribution

- **Code and documentation:** MIT licence, see [`LICENSE`](LICENSE).
- **Data:** derived from [nflverse](https://github.com/nflverse/nflverse-data) data, licensed CC BY 4.0. See [`DATA-LICENSE.md`](DATA-LICENSE.md).

This project is not affiliated with or endorsed by nflverse, the NFL or ESPN.
