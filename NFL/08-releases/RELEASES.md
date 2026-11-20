# Release Register: NFL-Analysis workbook

This is the release register for the NFL workbook in `wes-blue/sports-analysis`. The versioning policy is in [`/00-Governance/VERSIONING.md`](../../00-Governance/VERSIONING.md): the first digit names the design generation (decision D-035), released files are immutable, fixes ship as the next version, and a version's status changes only here, never inside a released file.

## Releases in this repository (2.x)

The 2.x line is the workbook fed by the pipeline in this repository, reading the published data from the web.

| Version | Date | Status | Scope | Gates | SHA-256 | File |
|---|---|---|---|---|---|---|
| 2.001 | 2026-11-20 | **Released** (generated; paste-ready) | Public repository, GitHub-only (see below) | G1 ✔ G2 ✔ G3 ✔ G4 ✔ G5 ✔ | `ac72364839f46e35b68a2594ffcfcf50960081e12cdb08590da897eb7899da87` | [`NFL-Analysis-2.001.xlsx`](NFL-Analysis-2.001.xlsx) (the working copy, byte-identical, is [`../05-excel/NFL-Analysis-2.001.xlsx`](../05-excel/NFL-Analysis-2.001.xlsx)) |

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
| Workbook 2.001 | `NFL-Analysis-2.001.xlsx` here and in `../05-excel/` | Paste-ready: 18 sheets, the M text of all 15 queries, a Start_Here guide. The queries are added once in Excel. **Not yet run in Excel.** |
| Experimental workbook | `../05-excel/NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx` | The owner's own Excel-built workbook with the 15 queries installed and personal data removed. Version `2.001-experimental`; **not a release; never opened in Excel.** SHA-256 `5a254114540a7d5648b30e3bc8d959422eadf7bc169cbb74bd688b5cd0128d1b`. |
| Power Query | `../05-excel/powerquery/` | 15 queries with a runbook. Parse and lint clean. |
| Published data | `../04-data/` | 174,945 player rows plus 5,288 D/ST rows, 2017–2026 through week 10. All 13 gates pass. |
| Pipeline | `../03-pipeline/` (version 1.2.0) | 377 tests, passing on Python 3.11 and 3.13. |
| Workflows | `/.github/workflows/` | Weekly, monthly, watchdog and CI. Lint clean; their logic was executed locally. **Never run on GitHub.** |

**Verification.**

| Gate | Result |
|---|---|
| G1 Source | Pass. Live nflverse files and column names checked. |
| G2 Code | Pass. 377 tests on Python 3.11 and 3.13; 15 of 15 queries parse with Microsoft's M parser and pass the firewall lint; actionlint clean; pinned action versions match their tags. |
| G3 Workbook | Pass. 284 structural checks; LibreOffice recalculation of 262 formulas with 0 errors; M text identical to the `.pq` files; a rebuild gives the same SHA-256. |
| G4 Release | Pass. 2.001 in the file name, Cover, file properties, Version_Log and this register. |
| G5 Data | Pass. `check` passes. An independent reviewer recomputed all 901,165 league scores with its own scorer (0 mismatches) and rebuilt the new points-allowed metric from play-by-play for all 5,288 team-games (0 mismatches). ESPN evidence: 25 of 25 values reproduced (23 exact, 2 within 1 point), and all 70 of ESPN's D/ST stat cells match. |

**QA.** Independent review [`../06-qa/qa-report-2.001.md`](../06-qa/qa-report-2.001.md): safe to publish; 0 critical, 1 major and 12 minor findings. Dispositions: [`../06-qa/qa-disposition-2.001.md`](../06-qa/qa-disposition-2.001.md). The review included a search of every file and every part of both workbooks for personal data: none found.

**Known limits.**
- Neither workbook has run in Excel. The first refresh by the owner is the first real test (roadmap 2.002; `/BLOCKERS.csv` Q-020).
- The workflows have never run on GitHub. The first run starts when the pull request is merged (roadmap 2.003).
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
