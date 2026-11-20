# NFL-Analysis workbook (Excel)

This folder holds the Excel workbook for NFL-Analysis: every NFL player's game-by-game stats for a rolling 10 seasons, team defense and special teams (D/ST) rows, and fantasy points for each of your leagues. A pipeline on GitHub publishes the data every week in season; the workbook **reads it from the web**. You need Windows desktop Excel for Microsoft 365 and a browser. Nothing has to be installed, copied or kept in step on your laptop.

The data is derived from nflverse (github.com/nflverse/nflverse-data), licensed CC BY 4.0; see `DATA-LICENSE.md` at the root of the repository.

## The two workbooks

| File | What it is |
|---|---|
| `NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx` | **Try this one first.** Your own 1.004 workbook with all 15 queries of 2.001 already installed, so there is nothing to paste. Its version reads `2.001-experimental`: it is **not a release** and has **never been opened in Excel**, so it may not work. `experimental/README.md` says exactly what to do, what you should see and what to report. |
| `NFL-Analysis-2.001.xlsx` | The release 2.001, **paste-ready**: every table, setting and check location is in place, and the 15 queries are inside it as text (M_Code sheet). You add them once (about 30 minutes); its **Start_Here** sheet walks you through it. Use it if the experimental file does not work. |

Both read the published data from `https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/` (setting `DataLocation` on the Config sheet).

## Do this, in this order

1. **The data must be on `main`.** Until the pull request that brings this project to `main` is merged (`BLOCKERS.csv` Q-015), the web address answers "404" and the first refresh stops with a message saying so.
2. **Download the experimental workbook**: click its name in the list of files above, then the **Download raw file** button (the arrow pointing down, at the top right of the file view). Save it anywhere, for example in Documents.
3. **Open it** in Excel. Protected View: **Enable Editing**; a yellow bar about data connections: **Enable Content**. If Excel offers to repair the file, click **No** and go to step 6.
4. **Data › Refresh All**, and answer Excel's two questions once:
   - *Access Web content*: **Anonymous**, level `https://raw.githubusercontent.com/`, **Connect**;
   - *Information is required about data privacy*: **Current Workbook** = **Public**, `https://raw.githubusercontent.com/` = **Public**, **Save**.
5. **Follow `experimental/README.md`** from its section 3: what the Checks sheet should show, four checks to load with a few clicks each, one look at the Data Model, and what to tell Claude.
6. **If the experimental file does not work**, download `NFL-Analysis-2.001.xlsx` the same way and follow its Start_Here sheet (add the 15 queries once, then refresh).

## Each week

Open the workbook and click **Data › Refresh All**. That is all: GitHub runs the pipeline and publishes new data Tuesday to Thursday in season (`../03-pipeline/AUTOMATION.md` explains the schedule, the alerts and how to start a run by hand). If new data was published only minutes ago and a check is amber or red, wait 5 minutes and refresh again: GitHub keeps copies of the files for up to 5 minutes.

## Changing scoring

- **In the workbook** (yours alone, at once): edit the yellow cells on the Scoring and Bonus sheets and refresh. The Checks sheet then shows how your scores differ from the published ones (`Check_Parity`, `Check_Rules_Drift`), and `Check_Golden` shows `NOT APPLICABLE` for that league, because its stored test values were made with other rules.
- **On GitHub** (changes the published scores): edit the file in `NFL/02-config/` on GitHub. Saving it there starts the pipeline, which publishes new scores a few minutes later; `../03-pipeline/AUTOMATION.md` explains how, and `../02-config/README.md` explains the files.

The runbook, `powerquery/README.md` section 8, says what each check shows after either kind of change; the workbook and the pipeline give the same verdict.

## What else is here

| Item | What it is |
|---|---|
| `powerquery/` | The 15 queries as `.pq` files (the source of truth), `manifest.json` (paste order and load settings), `README.md` (**the runbook**: Excel's questions, what each check means, expected results, changing scoring, every error message and its fix) and `WORKBOOK-REQUIREMENTS.md` (what the workbook must contain). |
| `experimental/` | The guide to the experimental workbook (`README.md`), the script that builds it from the owner's private Excel file, and its two verification scripts. |
| `build/` | The generator of the paste-ready workbook (`build_workbook.py`), the personal-data scan run on every workbook before it is published (`pii_scan.py`), the Power Query generator and its Python emulation (`pq/`), and `version_history.csv`. You do not need any of it to use the workbook. |

## Questions waiting on you

The workbook's Open_Questions sheet lists them; the full list is `BLOCKERS.csv` at the root of the repository (fill in the Answer column on GitHub, or tell Claude in chat). For this folder: merging the pull request (Q-015) and how the experimental workbook went (Q-020).
