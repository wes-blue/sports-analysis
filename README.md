# sports-analysis

Fantasy-sports data that builds and checks itself on GitHub, and Excel workbooks that read it straight from the web.

For each sport, a pipeline downloads public statistics, scores them for one or more fantasy leagues, checks the result, and publishes plain CSV files in this repository. GitHub Actions runs the pipeline on a schedule. An Excel workbook reads the published files from their web address, so a reader needs only Excel: no Python, no git and no copy of the repository.

## Sports

| Sport | Folder | What it covers | Workbook | Status |
|---|---|---|---|---|
| NFL | [`NFL/`](NFL/README.md) | Weekly player stats for a rolling 10 seasons (regular season and playoffs), team defense and special teams (D/ST) rows, long-touchdown counts, and fantasy points for several scoring systems, including one ESPN league | `NFL-Analysis-2.xxx` | Moved here on 2026-11-20. Version 2.001 is in preparation; [`NFL/08-releases/RELEASES.md`](NFL/08-releases/RELEASES.md) shows the latest release. |

NFL is the only sport for now. The structure allows more.

## How a sport is laid out

Every sport has its own top-level folder with the same numbered subfolders:

| Subfolder | Holds |
|---|---|
| `01-plan/` | `plan.json`: the plan, requirements, risks and roadmap (rendered to `PLAN.md`) |
| `02-config/` | The CSV files a person edits: leagues, scoring weights, bonus bands, settings |
| `03-pipeline/` | The code that downloads, scores, checks and publishes, with its tests |
| `04-data/` | The published CSV files. Written only by the pipeline. |
| `05-excel/` | The workbook and its Power Query |
| `06-qa/` | QA reports, evidence and test fixtures |
| `07-research/` | Design notes |
| `08-releases/` | The release register |

Each sport also has a `README.md`, a `PLAN.md` and a `CONTRACTS.md` that defines every file format. Shared across sports: `00-Governance/` (charter, versioning policy, decision log), `BLOCKERS.csv` (questions waiting on the owner) and `.github/workflows/` (one set of workflows per sport, named `<sport>-pipeline-*.yml`). [`_Sport-Template/`](_Sport-Template/README.md) is the skeleton and checklist for adding a sport.

## Use the NFL workbook

1. You need **Excel for Windows (Microsoft 365)**. The workbook uses the Data Model, which Excel for Mac and Excel on the web do not offer.
2. Open [`NFL/05-excel/`](NFL/05-excel/README.md) on GitHub, click the workbook file, and use **Download raw file**. There are two:
   - `NFL-Analysis-2.001.xlsx`: every table and setting is in place, and the 15 Power Query queries are inside it as text. You add them once in Excel by following its Start_Here sheet (about 30 minutes).
   - `NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx`: the same queries already installed. It has not yet been opened in Excel, so it is labelled experimental and is not a release.
3. Open the file, follow its Start_Here sheet, and press **Data › Refresh All**. The workbook reads the published data from the web address below.

[`NFL/05-excel/README.md`](NFL/05-excel/README.md) has the full steps and what the Checks sheet should show.

## Read the published NFL data

Every file in `NFL/04-data/` can be read by anyone, from Excel, a browser, Python, R or any other tool, at:

```
https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/<path>
```

For example, `.../NFL/04-data/scored/scored_2025.csv` holds every player-game of 2025 with its fantasy points per league. These addresses serve the files on the `main` branch. [`NFL/04-data/README.md`](NFL/04-data/README.md) lists the files, and [`NFL/CONTRACTS.md`](NFL/CONTRACTS.md) §5 defines every column.

## It updates itself

The NFL workflows in `.github/workflows/` run the pipeline during the season on Tuesday, Wednesday and Thursday, on the 1st of every month, and whenever a scoring file in `NFL/02-config/` is changed on `main`. A run publishes only when every blocking check passes; otherwise the last good data stays in place. As of 2026-11-20 the workflows are installed but have not yet run on GitHub.

When the data looks out of date:

1. Open [`NFL/04-data/status.csv`](NFL/04-data/status.csv): `generated_utc` is when the data was last published, and `latest_season` and `latest_week` are what it covers.
2. Look at the repository's **Issues** for an open issue labelled `nfl-pipeline-alert-*`: a failed or stale run opens one and says what went wrong.
3. Look at the **Actions** tab for the latest `nfl-pipeline-*` runs.

`NFL/03-pipeline/AUTOMATION.md` explains each workflow, what an alert means and how to start a run by hand.

## Licence and attribution

- **Code and documentation:** MIT licence, see [`LICENSE`](LICENSE).
- **Data:** derived from [nflverse](https://github.com/nflverse/nflverse-data) data, licensed CC BY 4.0. See [`DATA-LICENSE.md`](DATA-LICENSE.md).

This project is not affiliated with or endorsed by nflverse, the NFL or ESPN.
