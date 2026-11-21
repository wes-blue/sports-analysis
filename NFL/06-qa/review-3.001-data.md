# Review 3.001, R1: data correctness and contract conformance (`nflpipe export`)

Reviewer: R1 (Q1 QA Reviewer role), independent of the builder. Repository commit `dd05adb`, branch `agents/pensive-noether-dxfoz6`.
Scope: `NFL/03-pipeline/nflpipe/export_xlsx.py`, its wiring in `__main__.py`, `NFL/CONTRACTS.md` sections 4, 5 and 13.
Method: every figure below was re-derived with my own code (`openpyxl` plus the `csv` and `decimal` modules; the exporter was never imported). Scratch files are in `NFL/.work/r1/`. Nothing in the repository was changed except this report.

## Verdict

**Correct.** No wrong number, no data loss, no contract failure was found on the real data or on the three scoring and rounding variants I rebuilt. The findings are all Minor.

Not verified: opening the file in desktop Excel (no Excel in this environment). The XML parts, relationships, table definitions and string table were read by `openpyxl` without a warning and checked by eye, but "no repair prompt" in Excel is UNVERIFIED by me. The adversarial committee owns that attack.

## Findings

| ID | Grade | Where | Summary |
|---|---|---|---|
| R1-m1 | Minor | `Data.__init__`, error text | A missing `data_contract_version` prints `is None`, not "missing". |
| R1-m2 | Minor | `player_games`, SeasonTotals `wk` | A non-numeric `week` is silently treated as week 0 for the "last game" rule. |
| R1-m3 | Minor | `season_totals` | Name and position in SeasonTotals also come from the last game. The contract fixes only `team`. |
| R1-m4 | Minor | `build`, error path | Failures other than `ExportError` print the Python exception class (for example `FileNotFoundError: [Errno 2] ...`). |
| R1-m5 | Minor | `tests/test_export_xlsx.py` | Several contract clauses have no test (list below). |
| R1-m6 | Minor | `core_xml` | `generated_utc` is written into the file properties unvalidated. |
| R1-m7 | Minor (outside the exporter) | `nflpipe run` | Two `run` commands started at the same time against different data and config directories interfered with each other. |

### R1-m1: missing contract version reads as `None`
- What I did: removed the `data_contract_version` line from a copy of `status.csv` and ran `export`.
- Happened: exit 1, `status.csv data_contract_version is None; this exporter understands version '1'`. No file left behind. The refusal itself is correct.
- Should happen: say "is missing" (§13.1 says "missing or not the version", naming both values).
- Fix: in `Data.__init__`, print `'missing'` when `found is None`.

### R1-m2: non-numeric week becomes 0
- Where: `player_games`, `wk = float(row[1])` with `except ValueError: wk = 0.0`.
- Real data has only numeric weeks, so no output changes today. With a bad week the row would lose every "last game" comparison silently.
- Fix: raise `ExportError` naming file and line, as the other numeric checks do.

### R1-m3: name and position come from the last game
- The contract says only "`team` is the team of the player's last game". The builder takes `player_display_name` and `position` from the same row.
- On the real data it makes no difference: of 24,250 player-season-type keys, 624 have more than one team, and none has more than one name or position.
- Fix: none needed. Add one sentence to §13.2 so the rule is written down.

### R1-m4: raw exception text for unexpected errors
- `--out /proc/x/y.xlsx` gives exit 1 and `FileNotFoundError: [Errno 2] No such file or directory: '/proc/x'`. Exit code and cleanup are right.
- Fix: catch `OSError` in `build` and report "cannot write <path>: <reason>".

### R1-m5: untested contract clauses
I read all 41 tests. These behaviours have no test:
1. The cell number format for the points columns is only checked at the default (2 decimals). Nothing asserts `numFmtId` for `RoundDecimals` 0 or 3 (I verified them by hand, below).
2. Determinism against changed file timestamps of `04-data` (only "same input twice" is tested).
3. An inactive league sitting between active ones (the `Off` league in the fixture is last), so the order of `FF_` columns follows `leagues.csv` order among the Active ones.
4. A D/ST row (blank player metrics, text `player_id` that is a team code) going through PlayerGames and SeasonTotals.
5. A tie on `week` within one season and type for the "last game" rule.
6. A negative average at a half tie in the real shape (`-2 / 16 = -0.125` gives `-0.13`); the existing negative cases are 2 games.
7. The default `--data-dir` and `--out` (the dispatcher test passes both).
8. The hyperlinks on `About` and the exact About row list.
9. No test or script runs the real 180,000-row build for time or memory.

### R1-m6: `generated_utc` is not validated
- It is written into `dcterms:created` and `modified` as W3CDTF. A malformed value would produce invalid properties. Today it is `2026-11-20T23:32:09Z`. Fix: check the format with a regular expression and raise `ExportError`.

### R1-m7: concurrent pipeline runs
- While rebuilding variants I started two `nflpipe run` commands in parallel. One ended HOLD at `G-INDEX` ("staged manifest.csv disagrees with the files") and the other HOLD at `G-RECON` with 94.87% at `RoundDecimals` 3. Re-run one after the other, both PUBLISHED and everything reconciled.
- Cause (not investigated further): the two runs seem to share a staging area. It does not affect the exporter, and the scheduled workflows run one at a time. I record it so the owner does not start two runs at once.

## Verified independently

### Counts
- Build on the real `04-data` (run `20261120T233201Z-gh44837469898`, data through 2026 week 11 REG, pipeline 1.2.1): 37.9 MB, 12.6 s, exit 0.
- **PlayerGames:** 180,301 rows x 98 columns = **17,669,498 cells compared, 0 mismatches**. Header order equals the contract (9 identity columns, 5 `FF_` columns in `leagues.csv` order, 2 nflverse points columns, 82 metric columns). Each cell was checked for type (number, text, empty) and value against `player_week/*.csv` (ten seasons, 2017 to 2026) and the `FF_` columns of the matching `scored/*.csv`. No numeric-looking value was found in a numeric column that came out as text, and no text value in a metric column.
- **SeasonTotals:** my own recomputation gave 24,250 keys. **24,250 rows, 412,250 cells compared, 0 mismatches** (games, team of the last game, name, position, total and average for all 5 leagues, sort order). Rounding cases present in the real data: 174 keys with a negative ESPN_League total and 914 exact half ties in the average. Three negative ties checked by hand in the file: -2 / 16 = -0.125 gives -0.13, -0.62 / 4 = -0.155 gives -0.16, -0.08 / 16 = -0.005 gives -0.01. All are half away from zero.
- **Leagues** 5 rows (30 cells), **Scoring** 82 rows (830 cells), **Bonus** 24 rows (175 cells), **Checks** 13 rows (84 cells), **Dictionary** 82 rows (415 cells): 0 mismatches, including text-versus-number typing. Each of the three config sheets has the note row above the table.
- **About:** every one of its 26 data lines checked against `status.csv`, the config and the contract (version 3.001, data through `2026 week 11 (REG)`, generated, run id, pipeline and contract versions, seasons, leagues, gates 13 / 0 / 0, `data_source` and `data_license` verbatim, the two addresses, the stable release address, scoring instructions with the AUTOMATION.md link, and one line per sheet). 0 mismatches.
- No `<f>` element in any sheet, no defined names, no connections, no macros.
- Tests: `NFL/.work/venv/bin/python` (3.13.18): 471 passed in 20.4 s; `NFL/.work/venv311/bin/python` (3.11.18): 471 passed in 20.4 s. `tests/test_export_xlsx.py` alone: 41 passed on both.

### Contract section 13, clause by clause

| Clause | Result | Evidence |
|---|---|---|
| 13.1 command `python -m nflpipe export [--data-dir] [--out]`, defaults `../04-data` and `../.work/workbook/NFL-Analysis.xlsx` | PASS | Dispatcher routes `export` to `export_xlsx.main`; defaults read from the code and the usage text. I always passed `--out`, so the default path was not run. |
| Reads only `--data-dir`, never changes it | PASS | Opens files read-only only; `04-data` unchanged by the runs (git shows no change). |
| Refuse with exit 1 on missing or different `data_contract_version`, naming both | PASS (wording: R1-m1) | Value `2` and a missing line both gave exit 1, message names found and expected, no file left. |
| Exit 0 written; exit 1 error; no partial file | PASS | Tried: missing data directory, missing contract version, scored file one row short, a non-number (`abc`) on the last row of `scored_2026.csv` (after streaming had begun), unwritable output. Always exit 1 and no `.tmp` or output file. A pre-existing output file survived a failed run unchanged. |
| Standard library only | PASS | Imports: `argparse, csv, math, os, re, sys, zipfile, decimal, operator, pathlib` (and `__future__`). No third-party import. |
| Deterministic, time from `status.csv`, fixed zip date and order | PASS | Two builds are byte-identical (`9721fffa...2b8c7`). A build from a copy of `04-data` with every mtime set to 2001 (one file 1999) is byte-identical to it. All 31 zip entries have date 1980-01-01. |
| Well under 5 minutes | PASS | 12.6 s. |
| 13.2 sheet order About, PlayerGames, SeasonTotals, Leagues, Scoring, Bonus, Checks, Dictionary | PASS | `workbook.xml`. |
| Column order (PlayerGames, SeasonTotals) | PASS | Header lists compared with the contract. |
| Table names `tblPlayerGames, tblSeasonTotals, tblLeagues, tblScoring, tblBonus, tblGates, tblDictionary`; About has none | PASS | `xl/tables/table1..7.xml`. Refs: A1:CT180302, A1:Q24251, A2:E7, A2:J84, A2:G26, A1:F14, A1:E83. All end on the last data row. |
| 13.3 numbers, blanks, text; identity columns text; no formulas | PASS | Typing checked on all 17.7 million PlayerGames cells; every text cell is a shared string. |
| Every table has a header row, AutoFilter, frozen header; PlayerGames and SeasonTotals also freeze through `player_display_name` | PASS | Panes: PlayerGames xSplit 5 ySplit 1 (top-left F2), SeasonTotals xSplit 4 ySplit 1 (E2), note sheets ySplit 2 (A3), Checks and Dictionary ySplit 1. Each table XML has its own `autoFilter`. |
| Number formats: whole numbers without decimals, points with `RoundDecimals` places | PASS | Default 2: `numFmtId 2`. I rebuilt at `RoundDecimals` 0 (`numFmtId 1`) and 3 (custom `0.000`). `season`, `week` and `games` use format 1. |
| Limits checked before writing | PASS (read only) | Row and column limits and the 32,767 limit are tested in code before streaming. Not exercised at full size by me. |
| 13.4 version `3.001` in the file; Title `NFL-Analysis 3.001`; author `NFL-Analysis pipeline`; no personal data | PASS | `core.xml` and `app.xml` read. A search of the text parts for `/home/` and e-mail addresses found nothing; the only `wes-blue` occurrences are in the public URLs. Player names in the data are nflverse content. |

### Scoring change and rebuild (owner's customisation route)
- Copied `02-config`, changed Half_PPR `receptions` from 0.5 to 0.75, copied `04-data` and the cache, ran `run --seasons all --config-dir ... --data-dir ... --report-dir ...` into scratch: PUBLISH, 18 files written. The golden gate gave the expected WARN that Half_PPR values were skipped.
- Exported from that folder and re-ran my full comparison: 0 mismatches against the new CSVs.
- Effect against the first workbook: Half_PPR changed on 38,040 of 180,301 rows; every other column in all five leagues was unchanged; every Half_PPR change equals +0.25 x receptions (0 rows off by more than 0.005); `SeasonTotals` Half_PPR total changed on 5,757 of 24,250 rows and PPR totals on none; the `Scoring` sheet row shows `receptions` 0.75.
- Rounding variants, each run one after the other: `RoundDecimals` 0 and 3 both PUBLISH; both workbooks matched their CSVs with 0 mismatches over the same 17.7 million plus 412,250 cells, with the number formats above.

## Observations that are not defects
- The `PlayerGames` sheet XML is about 409 MB uncompressed (37.9 MB zipped). Excel opens such a sheet but may take a while and use much memory; I could not time it.
- The totals use the published (already rounded) `FF_` values, as §13.2 says, not the unrounded sums.
