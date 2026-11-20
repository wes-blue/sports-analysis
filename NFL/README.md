# NFL

Scored NFL fantasy-football data and an Excel workbook that reads it. A Python pipeline turns public [nflverse](https://github.com/nflverse/nflverse-data) data into scored CSV files, GitHub Actions runs it, and the workbook's Power Query reads the published files from the web and lets you set your own points per league.

Everything runs on GitHub. Nothing needs your computer to be on, and you need only Excel to use the result.

**Status (2026-11-20).** The project moved here from a private repository today. Version 2.001 is in preparation: [`08-releases/RELEASES.md`](08-releases/RELEASES.md) shows the latest release, and [`PLAN.md`](PLAN.md) the roadmap. The work is on a branch with a pull request into `main`. Until it is merged, the data's web address and the scheduled runs do not work yet ([`/BLOCKERS.csv`](../BLOCKERS.csv) Q-015).

## Start here

| To | Read |
|---|---|
| Use the workbook | [`05-excel/README.md`](05-excel/README.md): which file to download, how to open it, what the Checks sheet should show |
| Change the scoring | [`02-config/README.md`](02-config/README.md): edit a file on GitHub; saving it on `main` publishes new scores |
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
05-excel/          NFL-Analysis-<version>.xlsx: Power Query reads 04-data from that address,
                   re-scores with the workbook's own Scoring sheet and checks itself against the pipeline
```

## Folders

| Folder | Holds |
|---|---|
| `01-plan/` | `plan.json`, the single source of the plan, requirements, RAID log and roadmap; `PLAN.md` is rendered from it |
| `02-config/` | The CSV files you edit to change the scoring |
| `03-pipeline/` | The `nflpipe` Python package, its tests, and `AUTOMATION.md`, the guide to the workflows |
| `04-data/` | What the pipeline publishes. Never edited by hand. |
| `05-excel/` | The workbooks, their Power Query and the workbook generators |
| `06-qa/` | QA reports, evidence from your ESPN league, and test fixtures |
| `07-research/` | Design notes |
| `08-releases/` | The release register, `RELEASES.md` |

The workflow files themselves are at the repository root, in [`/.github/workflows/`](../.github/workflows/), because GitHub runs workflows only from there.

## Running the pipeline by hand (optional)

You never need to: GitHub runs it. A developer with Python 3.11 or later can run it on any computer with the commands in [`03-pipeline/README.md`](03-pipeline/README.md).

## Licence

Code: MIT ([`/LICENSE`](../LICENSE)). Data: derived from nflverse, CC BY 4.0 ([`/DATA-LICENSE.md`](../DATA-LICENSE.md)).
