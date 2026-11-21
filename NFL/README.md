# NFL

Scored NFL fantasy-football data and a finished Excel workbook built from it. A Python pipeline turns public [nflverse](https://github.com/nflverse/nflverse-data) data into scored CSV files and into an Excel workbook, and GitHub Actions runs it.

**Download the workbook:** <https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx>. Open it in Excel; there is nothing to refresh. The link never changes, and the file behind it is replaced after every publish.

Everything runs on GitHub. Nothing needs your computer to be on, and you need only Excel to use the result.

**Status (2026-11-21).** The project moved here from a private repository on 2026-11-20 and the pull request was merged; the pipeline has published on GitHub. Version 3.001 (the workbook built on GitHub) is in preparation: the exporter and the upload step are not yet running, so the download link answers "not found" until the first upload. [`08-releases/RELEASES.md`](08-releases/RELEASES.md) shows the releases, and [`PLAN.md`](PLAN.md) the roadmap.

## Start here

| To | Read |
|---|---|
| Use the workbook | [`05-excel/README.md`](05-excel/README.md): the download link and what is in the workbook |
| Change the scoring | [`02-config/README.md`](02-config/README.md): edit a file on GitHub; saving it on `main` publishes new scores and rebuilds the workbook |
| Understand the automation, or see why data is late | [`03-pipeline/AUTOMATION.md`](03-pipeline/AUTOMATION.md) |
| Read the data from another tool | [`04-data/README.md`](04-data/README.md) |
| See every file format and command | [`CONTRACTS.md`](CONTRACTS.md) |
| Answer the questions waiting on you | [`/BLOCKERS.csv`](../BLOCKERS.csv) (fill in the `Answer` column) |

## How the parts connect

```
02-config/*.csv    leagues, scoring weights, bonus bands, settings
       |           (edited on GitHub; a change on main starts the pipeline)
       v
GitHub Actions     /.github/workflows/nfl-pipeline-*.yml
       |           in season Tue-Thu, the 1st of each month, and on a config change
       v
03-pipeline/       nflpipe (Python): download -> derive -> score -> gates -> publish
       |           publishes only when every blocking gate passes
       v
04-data/*.csv      committed by the workflow, public at
       |           https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/
       v
nflpipe export     builds NFL-Analysis.xlsx (values only) from 04-data; the workflow uploads it as a
                   release asset at https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx
                   (not committed to git; the 05-excel/ folder only says where it is)
```

## Folders

| Folder | Holds |
|---|---|
| `01-plan/` | `plan.json`, the single source of the plan, requirements, RAID log and roadmap; `PLAN.md` is rendered from it |
| `02-config/` | The CSV files you edit to change the scoring |
| `03-pipeline/` | The `nflpipe` Python package, its tests, and `AUTOMATION.md`, the guide to the workflows |
| `04-data/` | What the pipeline publishes. Never edited by hand. |
| `05-excel/` | Where to get the workbook, and `archive-2.x/`, the retired Power Query workbook |
| `06-qa/` | QA reports, evidence from your ESPN league, and test fixtures |
| `07-research/` | Design notes |
| `08-releases/` | The release register, `RELEASES.md` |

The workbook design is specified in [`CONTRACTS.md`](CONTRACTS.md) section 13.

The workflow files themselves are at the repository root, in [`/.github/workflows/`](../.github/workflows/), because GitHub runs workflows only from there.

## Running the pipeline by hand (optional)

You never need to: GitHub runs it. A developer with Python 3.11 or later can run it on any computer with the commands in [`03-pipeline/README.md`](03-pipeline/README.md).

## Licence

Code: MIT ([`/LICENSE`](../LICENSE)). Data: derived from nflverse, CC BY 4.0 ([`/DATA-LICENSE.md`](../DATA-LICENSE.md)).
