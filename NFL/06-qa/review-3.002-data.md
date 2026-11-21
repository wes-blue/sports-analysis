# Review 3.002, R1: data correctness and contract conformance (`nflpipe export`, design 3.002)

Reviewer: R1 (Q1 QA Reviewer role), independent of the builder. Repository commit `d4c713b` (the working-tree change was committed by the orchestrator while I worked; I checked that its exporter and test diff is byte-identical to the working-tree diff I started from), branch `agents/pensive-noether-dxfoz6`.
Scope: `NFL/03-pipeline/nflpipe/export_xlsx.py` and `tests/test_export_xlsx.py` (the 3.002 change), `NFL/CONTRACTS.md` §13, decisions D-044/D-046/D-047, roadmap 3.002, FR-52, C-36, RAID-106/107, `BLOCKERS.csv` Q-025.
Method: my own code only (standard library plus openpyxl). The builder's scripts in `NFL/.work/x3/` were not used; the builder's 3.001 published file was used as the reference file, as briefed. My scratch files are in `NFL/.work/r3/`. Nothing in the repository was changed except this report.

## Verdict

**Correct. Releasable from the data and contract side.** The 3.002 file holds exactly the same cells as the live 3.001 file (same position, type, style and value in all 8 sheets), the omission rule holds on every one of the 14.4 million data cells with no violation in either direction, and all 17,669,498 `PlayerGames` cells equal the published CSVs. No Critical or Major finding. Four Minor findings, all stale or imprecise wording in records and comments.

Not verified by me: desktop Excel (none here; this stays the owner's Q-025). The ECMA-376 schema validation and the LibreOffice open named in roadmap criterion (e) were not re-run by me (LibreOffice is installed, but my brief was data and contract). The post-merge replacement of the release asset (criterion f) cannot be seen before the merge.

## Findings

| ID | Grade | Where | Summary |
|---|---|---|---|
| R1-m1 | Minor | `NFL/CONTRACTS.md` §13.2, `About` row | Still says "workbook version (`3.001`)". |
| R1-m2 | Minor | `CONTRACTS.md` §13.5; `PLAN.md` CON-15 and finding at line 57; `plan.json` lines 142, 1296 | "about 38 MB ... more than a gigabyte a season" is no longer true of the file being published. |
| R1-m3 | Minor | `.github/workflows/nfl-pipeline-weekly.yml:452`, `-monthly.yml:335`, `tests/test_workflows.py:988` | Comments and a test message say "the real file is about 38 MB". |
| R1-m4 | Minor | RAID-106, RAID-107, D-047-adjacent text | "Reverting is a one-line change" is two call sites, and a revert fails the new tests by design. |

### R1-m1: About row of the contract
- Evidence: `CONTRACTS.md` line 272: "workbook version (`3.001`)". The exporter writes `3.002` (About row 5, A1 and Title all verified).
- Fix: write "workbook version (the design version, `WORKBOOK_VERSION`; today `3.002`)".

### R1-m2: size claims that now describe 3.001
- `CONTRACTS.md` §13.5 now says "a file of about 8 MB ... rebuilt every week would grow the repository by more than a gigabyte a season". The "more than a gigabyte" was derived from 38 MB. At 8.4 MB the same arithmetic gives about a quarter of that; the conclusion (do not commit it) still holds but the figure is wrong.
- `NFL/PLAN.md` line 57 and CON-15 (line 369) and `plan.json` lines 142 and 1296 still say "about 38 MB ... roughly a gigabyte a season" with no 3.002 note.
- Fix: either restate with the 3.002 size and the arithmetic, or say "about 38 MB in 3.001; 8.4 MB in 3.002, still more than a few hundred MB a season".

### R1-m3: stale 38 MB in workflow comments
- `WORKBOOK_MIN_BYTES: "1000000"   # the real file is about 38 MB ...` in both workflows, and the assertion message "38 MB of zip data does not compress; store it" in `test_workflows.py`. The threshold (1 MB) is still safe at 8.4 MB, and storing the xlsx without recompression is still right. Comment only.
- Fix: "about 8 MB (3.002)".

### R1-m4: revert instructions
- RAID-106 and RAID-107 say that going back to `r` on every cell is "a one-line change in the exporter". The switch is `compact=True` at two call sites (`player_games`, line 854, and `write_table_sheet(... compact=True)` for SeasonTotals, line 1033).
- Reverting also fails the new tests (I ran this, below), and the file would still say 3.002 while being in the 3.001 form.
- Fix: say "two call sites; set `compact=False`, update the new tests, and raise the version (3.002 would then be ambiguous)".

## Verified independently

### 1. Same values (own reader, plus openpyxl)
Files: `NFL/.work/x3/NFL-Analysis-3.001-published.xlsx` (40,018,688 bytes) and my build `NFL/.work/r3/NFL-Analysis-3.002.xlsx` (8,432,121 bytes).

- **Reader 1 (own code, `zipfile` + `iterparse`, shared strings read, ECMA-376 placement: a `<c>` without `r` goes to the previous column plus one, a `<row>` without `r` to the previous row plus one; I also assert that every given `r` has the row of its `<row>`).** Compared row, column, type, style index and value:

| Sheet | Cells (3.002) | Differences |
|---|---|---|
| About | 70 | 2 (A1 `NFL-Analysis 3.001` to `3.002`; B5 "Workbook version" `3.001` to `3.002`) |
| PlayerGames | 14,170,258 (1,262,205 text, 12,908,053 number) | 0 |
| SeasonTotals | 412,267 (121,267 text, 291,000 number) | 0 |
| Leagues | 28 | 0 |
| Scoring | 775 | 0 |
| Bonus | 164 | 0 |
| Checks | 84 | 0 |
| Dictionary | 447 | 0 |

  Sheet names and order equal. Neither file had an extra cell after the other ended.
- **Reader 2 (openpyxl read-only; row, column, value, data type, number format, bold flag).** Same cell counts, same differences: only the two About cells. Title `NFL-Analysis 3.001` versus `3.002`.
- **Package level:** both zips have the same 31 entries in the same order. Only four parts differ in bytes: `sheet2.xml` (408,980,471 to 240,246,885 bytes), `sheet3.xml` (14,129,158 to 10,038,790), `sharedStrings.xml` (equal length; the only changed strings are `NFL-Analysis 3.001` and `3.001`) and `docProps/core.xml` (Title). Styles, workbook, tables, rels, About sheet XML and all small sheets are byte-identical.

### 2. The rule, exhaustively on the real file
Regex streaming over the raw XML text of every `<row>` and `<c>` (no XML parser), tracking the true column of each cell:

| Part | Rows (all have `r`) | Data cells with `r` | Data cells without `r` | Header / small-sheet cells with `r` | Violations |
|---|---|---|---|---|---|
| sheet2 PlayerGames | 180,302 (header + 180,301) | 185,591 | 13,984,569 | 98 (header) | 0 |
| sheet3 SeasonTotals | 24,251 | 24,250 | 388,000 | 17 (header) | 0 |
| sheets 1, 4, 5, 6, 7, 8 | 36, 7, 84, 26, 14, 99 | n/a | n/a | 70, 28, 775, 164, 84, 447 (all cells) | 0 |

- "r needed" was defined as: first written cell of the row, or column not equal to previous column plus one. Violations in either direction (r present but not needed; r missing where needed; a small-sheet or header cell without r): 0.
- Consistency: 185,591 + 13,984,569 + 98 = 14,170,258 = the PlayerGames cell count above.
- In SeasonTotals, `r` appears on exactly the 24,250 first cells (`A<row>`), so no SeasonTotals row has a blank gap on the real data; the gap case there is covered only by the unit test `test_season_totals_with_a_blank_keeps_r_after_it`. In PlayerGames, 180,301 of the 185,591 `r` cells are first-in-row cells and 5,290 follow a gap; the full comparison in section 1 shows every one of them lands correctly.

### 3. Against the sources (all rows, not a sample)
Own script: for each `player_week_<season>.csv` (2017 to 2026) read with `csv`, rows sorted by week descending (stable; seasons descending), `FF_*` columns taken from the `scored_<season>.csv` row with the same `(season, week, season_type, player_id)` key (keys unique; row counts equal), expected column order built from `leagues.csv` (5 Active leagues) and the contract §13.2, then compared with the cells read by my reader from the 3.002 file.
- Header equals the contract order (98 columns); 180,301 data rows equal the CSV rows.
- **17,669,498 cells compared (3,499,338 of them blank), 0 mismatches.** Blank CSV value: no cell written (0 violations). Identity and text columns: shared string with exact text. Numeric: number cell with the same decimal value (`Decimal` equality). Non-numeric text in a metric column: shared string. `fantasy_points` and `fantasy_points_ppr` equal in `player_week` and `scored` on every row. No cell beyond column 98.
- Run time: about 2 minutes for the whole check.
- Not re-derived here: SeasonTotals against the CSVs (the 3.001 review did this; here SeasonTotals is proven equal cell by cell to 3.001).

### 4. Tests
- Build twice (Python 3.13): `eb33017c...d9ed` both times, equal to the builder's own build in `NFL/.work/x3/`. Python 3.11 build: same SHA-256. Time 7.7 s.
- Mutations of `export_xlsx.py` (backed up first, restored by `cp`; `sha256sum -c` confirms both files are exactly as before, and the committed diff `HEAD~1..HEAD` for the two files is identical to the diff I captured at the start):

| Mutation | `test_export_xlsx.py` result |
|---|---|
| M1: `compact=False` at both real call sites | 3 failed, 143 passed (`test_gappy_workbook_xml_and_readback`, `test_gappy_season_totals_and_small_sheets_readback`, `test_season_totals_with_a_blank_keeps_r_after_it`) |
| M2: omit `r` also after a gap (`prev >= 0`) | 5 failed, 141 passed |
| M3: omit `r` on the first cell too | 7 failed |
| M4: Emitter ignores `compact` | 5 failed |
| M5: off-by-one rule (`k <= prev + 2`) | 6 failed |

  So the new tests catch both requested regressions and three more. Observation (not a defect): with M1 the direct Emitter unit tests still pass because they construct `compact=True` themselves; the call sites are guarded by the gappy workbook tests.
- Full suite, restored code: `NFL/.work/venv/bin/python` (3.13.18): **686 passed in 51.9 s**; `NFL/.work/venv311/bin/python` (3.11.18): **686 passed in 49.8 s**.

### 5. Contract and records

| Item | Result |
|---|---|
| §13.3 last bullet | Matches the code and the file: same rule, `r` kept on rows, headers and small sheets. Numbers measured: 40,018,688 to 8,432,121 bytes (I measured both), `PlayerGames` XML 409 MB to 240 MB (408,980,471 to 240,246,885). |
| §13.4 | Version 3.002 and Title `NFL-Analysis 3.002` present in the file; the sentence "3.001 wrote `r` on every cell; 3.002 omits it ... and nothing else changes" is true (section 1: nothing else differs). |
| D-047 | Accurate: 8,432,121 bytes, 240 MB, adversarial estimate 6.8 MB (the adversarial report says 6.8 MB from an 8 MB slice, A1-S1). Freshness key does include `WORKBOOK_VERSION` (workflow line 400 reads it from the exporter), so the first run after the merge rebuilds. |
| Roadmap 3.002 (a)-(d) | (a) met, (b) met, (c) met, (d) 8,432,121 bytes under 10 MB. (e), (f), (g), (h), (i): not for me; see "Not verified". |
| FR-52, C-36 | Text matches what was built. C-36 status "Designed", FR-52 "Planned": fine until the committees finish. |
| RAID-106, RAID-107, Q-025 | Describe the risk and the question accurately; Q-025 asks for the About text, repair message and time to open. Wording issue: R1-m4. |
| Other | R1-m1, R1-m2, R1-m3. `00-Governance/MEMORY.md` line 25 still says the smaller file "waits for the owner's go-ahead ... about 7 MB"; the orchestrator updates MEMORY at end of session. |

### 6. Public safety
- Every part of the 3.002 file scanned for home or Windows paths, e-mail addresses, token patterns (`ghp_`, `AKIA`, `sk-`, bearer, private key), and "password / secret / api key", and for `wes`: nothing found except the public repository URLs containing `wes-blue` (About hyperlinks and the sheet relationship) and four NFL players called Wes (nflverse content). `core.xml`: title `NFL-Analysis 3.002`, author and last modified by `NFL-Analysis pipeline`, created and modified `2026-11-20T23:32:09Z` (from `status.csv`). `app.xml`: application `NFL-Analysis pipeline`.
- Repository diff: the working-tree `git diff` was empty at the end (everything is in commit `d4c713b`), so I scanned `git diff HEAD~1 HEAD` (11 files, 527 insertions): no local path, e-mail, token or key. Matches were only the word "secrets" in existing risk text, `@pytest.fixture` and public `wes-blue` URLs.

## What I ran
1. `python -m nflpipe export --out ../.work/r3/a.xlsx` and `--out ../.work/r3/NFL-Analysis-3.002.xlsx` from `NFL/03-pipeline/` on `../.work/venv/bin/python` (3.13); a third build on `../.work/venv311/bin/python` (3.11); `sha256sum` of all.
2. `NFL/.work/r3/reader.py` and `cmp_std.py` (own streaming reader and cell-by-cell comparison of all 8 sheets), `cmp_opx.py` (openpyxl read-only comparison, 2 min 18 s), `rule.py` (raw-text rule check of all 8 sheets, plus the shared-string and zip-part diff), `src_check.py` (PlayerGames against `player_week` and `scored` CSVs, all rows).
3. Mutation runs M1 to M5 with `pytest tests/test_export_xlsx.py -q`, restoring from `NFL/.work/r3/export_xlsx.py.orig` after each; `sha256sum -c` against `NFL/.work/r3/files_before.sha` and a diff against `NFL/.work/r3/diff_before.txt`.
4. Full `pytest -q` on both interpreters.
5. Scans described in section 6.

## Not done
- Desktop Excel (owner, Q-025). Schema validation and LibreOffice open of the 3.002 file (roadmap criterion e). A non-read-only openpyxl load of the full real file (about 14 million cells; read-only mode was used on the real file, and the non-read-only loader is exercised by the unit tests on small gappy files). SeasonTotals recomputation from CSV (done for 3.001; here proven equal to 3.001 cell by cell). Post-merge asset replacement.
