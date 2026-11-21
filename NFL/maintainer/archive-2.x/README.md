# Archive: the Power Query workbook (2.x)

**This folder is not maintained.** The workbook to use is the one the pipeline builds on GitHub; see [`NFL/05-excel/README.md`](../../05-excel/README.md).

## What this was

Design generation 2.x (`NFL-Analysis-2.001`): an Excel workbook whose Power Query read the published CSV files from the web, re-scored them with the workbook's own scoring tables and loaded the result into the Data Model. This folder holds everything of that route:

| Item | What it is |
|---|---|
| `NFL-Analysis-2.001.xlsx` | The paste-ready 2.001 workbook (the queries are added by hand in Excel). A copy; the released, immutable file is [`../releases/NFL-Analysis-2.001.xlsx`](../releases/NFL-Analysis-2.001.xlsx). |
| `NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx` | The same queries already installed. Experimental, never a release. |
| `powerquery/` | The 15 queries as `.pq` files, `manifest.json` and the runbook. |
| `build/` | The generator of the paste-ready workbook and the Power Query generator. |
| `experimental/` | The script and checks that built the experimental workbook. |

## Why it was retired

The owner opened the experimental workbook: it opened without a problem, but Refresh All was still running after five minutes, which was too long, and the owner asked for Python on GitHub to build the Excel workbook instead (decision D-041). Keeping two routes would double the maintenance and the instructions, so the Power Query route was retired (decision D-043). From version 3.001 the pipeline builds a finished, values-only workbook after every publish (`../../CONTRACTS.md` section 13).

## State of the files

- Nothing here is maintained or tested any more. The 2.001 workbooks were never opened in Excel by a tester other than the owner's single trial above.
- The scripts were moved here with `git mv` and their folder paths adjusted, but they were not run again after the move.
- Nothing was deleted; the files are also in the repository's git history.
- Whether to keep the route available at all is a question to the owner: `NFL/maintainer/BLOCKERS.csv` Q-023 (default: retired).

The scripts in `build/` and `experimental/` still use the old folder paths of the layout they were written in, so they are kept as a record and are not run.
