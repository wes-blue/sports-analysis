# Release Register: NFL-Analysis workbook

This is the release register for the NFL workbook in `wes-blue/sports-analysis`. The versioning policy is in [`/00-Governance/VERSIONING.md`](../../00-Governance/VERSIONING.md): the first digit names the design generation (decision D-035), released files are immutable, fixes ship as the next version, and a version's status changes only here, never inside a released file.

## Releases in this repository

### 3.x: the workbook built on GitHub

From 3.001 the pipeline builds the finished, values-only workbook after every data publish and uploads it as a GitHub Release asset, not as a file in git (decisions D-041, D-042; `../CONTRACTS.md` section 13; policy in [`/00-Governance/VERSIONING.md`](../../00-Governance/VERSIONING.md)). One row per released roadmap version is written here when it is released; it says which workbook design version the file shows. The file at the stable address is rebuilt with new data on every publish, so the SHA-256 below is that of the file as first published for the version.

Stable download address: <https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx>

| Version | Date | Status | Scope | Gates | SHA-256 | Where |
|---|---|---|---|---|---|---|
| 3.002 | 2026-11-21 | **Released** (D-049). Published at 20:37 UTC by `nfl-pipeline-weekly` run [44947234464](https://github.com/wes-blue/sports-analysis/actions/runs/44947234464), started by the merge: it replaced the 3.001 file at the link (the first real replacement). Opened cleanly in desktop Excel by the owner before the merge (Q-025, D-048). | Smaller workbook: the same cells as 3.001, with the cell reference left out where a cell follows the previous one (`../CONTRACTS.md` section 13.3); design version 3.002 | G1 ✔ G2 ✔ G3 ✔ G4 ✔ G5 ✔ (QA: [`../06-qa/qa-disposition-3.002.md`](../06-qa/qa-disposition-3.002.md)) | As first published (identical to the tested copy), from data run `20261120T233201Z-gh44837469898`: `eb33017ce791d4ba11216bd348175b5453720d7b3cbd29799a7b029f2cadd9ed`, 8,432,121 bytes. | Published at the same address by the first run after the merge: <https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx> |
| 3.001 | 2026-11-21 | **Superseded by 3.002** on 2026-11-21 (D-049). Released (D-045). Published at 02:03 UTC by `nfl-pipeline-weekly` run [44853664413](https://github.com/wes-blue/sports-analysis/actions/runs/44853664413), started by the merge of pull request #3 (green in 36 seconds: pipeline SKIP, workbook built in 12 seconds, uploaded and renamed in 9). The owner opened it in desktop Excel the same day: no repair message, about a minute to open, ESPN points spot check matched (`/BLOCKERS.csv` Q-024, D-046). | Workbook built on GitHub: `python -m nflpipe export`, values only, newest games first with the league columns next to the player, uploaded after every publish (`../CONTRACTS.md` section 13) | G1 ✔ G2 ✔ G3 ✔ G4 ✔ G5 ✔ (QA: [`../06-qa/qa-disposition-3.001.md`](../06-qa/qa-disposition-3.001.md)) | As first published, from data run `20261120T233201Z-gh44837469898` (data through 2026 week 11, REG): `66d6e26abc6d64c040ac8a413a2e1c89bb3d3bba955f4ded197d77d936fba2f2`, 40,018,688 bytes. The same bytes as the local builds on Python 3.11 and 3.13 (the runner used 3.12). Later rebuilds have their own; the release notes name the data run each holds. | Release asset `NFL-Analysis.xlsx`, tag `nfl-workbook` (a pre-release, never marked Latest): <https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx> |

### 2.x: Power Query workbook (retired)

The 2.x line was the workbook fed by the pipeline in this repository, reading the published data from the web with Power Query. It is retired (decisions D-041, D-043).

| Version | Date | Status | Scope | Gates | SHA-256 | File |
|---|---|---|---|---|---|---|
| 2.001 | 2026-11-20 | **Superseded by 3.001** (decision D-043; the Power Query route is retired; 3.001 was released on 2026-11-21). Released as generated, paste-ready. | Public repository, GitHub-only (see below) | G1 ✔ G2 ✔ G3 ✔ G4 ✔ G5 ✔ | `ac72364839f46e35b68a2594ffcfcf50960081e12cdb08590da897eb7899da87` | [`NFL-Analysis-2.001.xlsx`](NFL-Analysis-2.001.xlsx), immutable and unchanged. A copy of it is [`../05-excel/archive-2.x/NFL-Analysis-2.001.xlsx`](../05-excel/archive-2.x/NFL-Analysis-2.001.xlsx). |

## 2.001: public repository, GitHub-only (released 2026-11-20)

**What changed since 1.006.**
- The project moved to this public repository, one folder per sport (decision D-033).
- The workflows are installed at `.github/workflows/` and are the only way the pipeline runs. A scoring change committed on GitHub starts the pipeline by itself (D-036).
- The workbook reads the published data from the web address by default, so nothing has to be cloned, synced or installed (D-037).
- ESPN points allowed now leave out points scored by the opposing defense, proven against the owner's ESPN game log for the Arizona D/ST (D-038). Only D/ST scores in the ESPN league changed: 300 team-games since 2017, all upward.
- The workbook's reconciliation and golden checks now give the same verdict as the pipeline after a deliberate rule change.

**What is in the release.**

| Part | Where | State |
|---|---|---|
| Workbook 2.001 | `NFL-Analysis-2.001.xlsx` here (a copy is in `../05-excel/archive-2.x/`) | Paste-ready: 18 sheets, the M text of all 15 queries, a Start_Here guide. The queries are added once in Excel. **Not yet run in Excel.** |
| Experimental workbook | `../05-excel/archive-2.x/NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx` | The owner's own Excel-built workbook with the 15 queries installed and personal data removed. Version `2.001-experimental`; **not a release; never opened in Excel.** SHA-256 `5a254114540a7d5648b30e3bc8d959422eadf7bc169cbb74bd688b5cd0128d1b`. |
| Power Query | `../05-excel/archive-2.x/powerquery/` | 15 queries with a runbook. Parse and lint clean. |
| Published data | `../04-data/` | 174,945 player rows plus 5,288 D/ST rows, 2017–2026 through week 10. All 13 gates pass. |
| Pipeline | `../03-pipeline/` (version 1.2.1) | 381 tests, passing on Python 3.11 and 3.13, here and on GitHub's runners. |
| Workflows | `/.github/workflows/` | Weekly, monthly, watchdog and CI. Lint clean; their logic was executed locally. **Never run on GitHub.** |

**Verification.**

| Gate | Result |
|---|---|
| G1 Source | Pass. Live nflverse files and column names checked. |
| G2 Code | Pass. 381 tests on Python 3.11 and 3.13; 15 of 15 queries parse with Microsoft's M parser and pass the firewall lint; actionlint clean; pinned action versions match their tags. |
| G3 Workbook | Pass. 284 structural checks; LibreOffice recalculation of 262 formulas with 0 errors; M text identical to the `.pq` files; a rebuild gives the same SHA-256. |
| G4 Release | Pass. 2.001 in the file name, Cover, file properties, Version_Log and this register. |
| G5 Data | Pass. `check` passes. An independent reviewer recomputed all 901,165 league scores with its own scorer (0 mismatches) and rebuilt the new points-allowed metric from play-by-play for all 5,288 team-games (0 mismatches). ESPN evidence: 25 of 25 values reproduced (23 exact, 2 within 1 point), and all 70 of ESPN's D/ST stat cells match. |

**QA.** Independent review [`../06-qa/qa-report-2.001.md`](../06-qa/qa-report-2.001.md): safe to publish; 0 critical, 1 major and 12 minor findings. Dispositions: [`../06-qa/qa-disposition-2.001.md`](../06-qa/qa-disposition-2.001.md). The review included a search of every file and every part of both workbooks for personal data: none found.

**After the release (2026-11-21).** The owner opened the experimental workbook: it opened without a problem, but Refresh All was still running after five minutes, which was too long (`/BLOCKERS.csv` Q-020). That led to decisions D-041 to D-043: the pipeline builds the workbook itself from 3.001, and the Power Query route is retired. The "Known limits" below are as written at release.

**Known limits.**
- Neither workbook has run in Excel. The first refresh by the owner is the first real test (roadmap 2.002; `/BLOCKERS.csv` Q-020).
- Of the workflows, only the test workflow has run on GitHub (on the pull request). It caught one defect before the merge: the download code looked for a certificate file at a path that exists only in the build environment, which GitHub's runners refuse to read. Fixed in pipeline 1.2.1. The scheduled workflows first run when the pull request is merged (roadmap 2.003).
- Three rarer D/ST cases and two player rules are scored on assumptions until the owner supplies ESPN game logs (`/BLOCKERS.csv` Q-016, Q-017, Q-019).
- Whether the off-season heartbeat commit counts as repository activity for GitHub is unverified.

## History: the 1.x line (private repository)

Versions 1.001 to 1.006 were built and released in the owner's private repository, before the project moved here on 2026-11-20 (decision D-033). Their files and full release records are kept there and are not part of this repository. They are listed for the record only.

| Version | Date | Scope | Where |
|---|---|---|---|
| 1.001 | 2026-11-14 | Plan and foundation: plan, configuration and scoring tables, data dictionary, Power Query as text; no data connection | Private repository |
| 1.002 | 2026-11-14 | Decisions applied and paste-ready: rolling season window, playoffs included, single-session query runbook | Private repository |
| 1.003 | 2026-11-15 | Guided Excel build: the queries added and refreshed in Excel by the owner | Private repository |
| 1.004 | 2026-11-15 | Your leagues: the ESPN league, the position gate, the golden-sample check | Private repository |
| 1.005 | none | Withdrawn, never released (decision D-028); 1.006 carried its scope; the number is not reused | Private repository |
| 1.006 | 2026-11-19 | Pipeline and paste-ready workbook: the Python pipeline, published CSV data, workflow files stored inactive, a workbook reading a local data folder; the last 1.x release | Private repository |

The independent QA records of 1.006 are kept in the private repository; [`../06-qa/README.md`](../06-qa/README.md) summarizes them.
