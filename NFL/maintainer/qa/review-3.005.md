# Review of roadmap 3.005: the Power Query refresh option

Reviewer: Q1 QA Reviewer (independent of the builders). Branch `agents/pensive-noether-dxfoz6`, head `ea046a8`. Scratch work: `NFL/.work/r305/` (git ignores it). No repository file was changed apart from this report.

## Verdict

**Pass with conditions.**

- The data side is correct. The two CSV files equal the sheets cell for cell, the workbook is byte-identical to the build from `origin/main`, every build is deterministic, and the tests catch the regressions I injected.
- No Critical finding.
- The refresh workbook (`NFL-Analysis-Refresh.xlsx`) is **unverified in Excel**. I found two Major points about it (F1, F2) and several Minor ones.
- Release the CSV files, the exporter change and the guide as they are. Do not ship the refresh workbook as "tested" until F1 is fixed (or consciously accepted) and the owner has opened a copy in desktop Excel (roadmap 3.005 (e), RAID-108).

## Findings

### Major

**F1. The refresh workbook has structural differences from the workbook Excel accepted, and one of them is a known repair trigger.** Only desktop Excel can settle this.
Evidence: I compared `rf1.xlsx` with the 2.x file `NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx`, whose query tables Excel loaded.
1. **No hidden defined names for the query tables.** The 2.x file has `ExternalData_1` to `_4` as hidden, sheet-scoped names (`localSheetId`) pointing at each query table's range, for example `Checks!$A$5:$E$6`. Our `xl/workbook.xml` has no `<definedNames>` at all, yet both `queryTable1.xml` and `queryTable2.xml` carry `name="ExternalData_1"`. Excel always writes the name that binds a query table to its range, and a missing binding is the most likely cause of a "Removed Part: queryTable" repair message.
2. **Both query tables are named `ExternalData_1`.** The 2.x file numbers them 1 to 4 (unique names).
3. **Table name differs from the query name and `FillTarget`.** In the 2.x file the table name equals the query name equals `FillTarget` (`Check_Golden`). Ours is `tblPlayerGames` against `FillTarget=PlayerGames` (and the same for `tblSeasonTotals`). Excel may not recognise the table as the query's output and may add a second table on refresh.
4. **Never-loaded state.** The metadata says `FillEnabled=l1`, `FillCount=l0`, `FilledCompleteResultToWorksheet=l0`, with no `FillLastUpdated` or `FillStatus`. No Excel-written item in the archive has that combination.
5. **Permission bindings.** The block is empty (0 bytes). The 2.x file has a 294-byte machine- and user-bound block. This is by design (D-056); the likely effect is only that Excel asks its privacy question.

Fix: (a) add `<definedNames><definedName name="ExternalData_1" localSheetId="1" hidden="1">PlayerGames!$A$1:$K$2</definedName>` and `ExternalData_2` for `SeasonTotals!$A$1:$G$2` (`localSheetId="2"`), and give the two query tables the names `ExternalData_1` and `ExternalData_2`; (b) make the table name equal the query name (`PlayerGames`, `SeasonTotals`), or keep `tbl...` and set `FillTarget` to the table name. Keep the `tbl` names only if the owner's Excel test shows no second table appearing. (c) Have the owner test a copy (F2). If Excel repairs it after (a) and (b), publish only the CSV files and the guide (RAID-108's fallback).

**F2. Nothing holds the refresh workbook back until the owner has tested it.**
Evidence: FR-54 and RAID-108 say it is published only if it opens cleanly and refreshes. Both workflows (`nfl-pipeline-weekly.yml` lines 480 to 500 and 600 onwards; the monthly file likewise) build and upload all four assets after the merge, with no gate. MEMORY.md 1b says a test copy "went to the owner" but no result is recorded in `BLOCKERS.csv` or `DECISIONS.md`.
Fix: record the owner's Excel result (prompts, time) before merge, or add a question to `BLOCKERS.csv` and state in the pull request that the file is published untested. The guide already tells visitors to use "Get Data, From Web" if Excel reports a problem, so the visitor impact is bounded.

### Minor

**F3. Size is wrong in four places.** The refresh workbook is 14,282 bytes, not "about 20 KB". It appears in `NFL/05-excel/README.md` (table), `NFL/03-pipeline/AUTOMATION.md` line 28, the comments next to `REFRESH_MIN_BYTES` in both workflows, and `MEMORY.md` 1b. Fix: "about 15 KB". The 5,000-byte minimum is fine.

**F4. CONTRACTS §13.6 and FR-54 say the refresh workbook is "rebuilt and republished only when `TABLES_VERSION` changes".** §13.5 and the workflows republish all four assets whenever the key changes, and the key contains `run_id`, so every publish replaces it (identical bytes). Fix: say "rebuilt on every publish with identical bytes; its content changes only when `TABLES_VERSION` changes", or exclude it from the swap when its size and checksum are unchanged.

**F5. Claims in the guide not labelled as estimates or as untested.** In `NFL/05-excel/README.md`:
- "A refresh takes about a minute or two". It was never measured. The owner's 2.x experience was over five minutes for scoring, and the new numbers are a guess. Label it "an estimate; not yet measured".
- "Excel for the web cannot refresh these queries". Stated as fact and not tested. Microsoft supports some query refresh on the web. Say "may not be able to".
- "On a Mac, a current Microsoft 365 build" and the menu path "Get Data, From Other Sources, From Web". Mac menus differ (Get Data (Power Query), then a list). Say the steps were written for Windows desktop Excel and are untested on Mac.
- "Enable Editing and then Enable Content". Plausible, not verified.
- The 3.002 workbook claim ("opened in desktop Excel with no repair message") is supported by Q-025 and D-048.

**F6. Redirect host in step 3.** The guide names `objects.githubusercontent.com`. GitHub's own content-security policy now lists `release-assets.githubusercontent.com` as well. Say "a second address ending in `githubusercontent.com`". The refresh workbook's `Start` sheet and the "quick way" paragraph do not mention this second prompt at all.

**F7. Stale records.**
- `plan.json` and `PLAN.md` C-37 still say "Not yet built / Designed" although `test_tables.py` exists.
- MEMORY.md 1b still says "build it after 3.004 merges".
- FR-53 to FR-56 are `Planned`.
- Update these at disposition.

**F8. Bare CR in a text field.** `clean_text` keeps `\r`, so a name containing a carriage return gives a quoted field with a raw CR in the CSV. The sheet keeps the same character (`&#13;`), so values are equal, but §13.6 says "LF line ends". No real value is affected (0 CR bytes in both files). Add one sentence to §13.6, or a test.

**F9. The M text cannot be run here.** Section1.m is syntactically plausible (reviewed by eye and checked for balanced structure), and I found no `File.Contents`, `Excel.CurrentWorkbook`, credentials or headers. The `//` comment directly after `shared X =` is legal M, but only Excel can confirm it.

**Observation (outside this change).** The archived 2.x experimental workbook carries a 294-byte DPAPI-bound permission block. It holds no readable strings (checked), so no personal data, but it is user-bound material in a public repository.

## What I ran, and the results

**1. Same values**
- Built from `NFL/04-data` with `python -m nflpipe export --out ../.work/r305/w.xlsx --tables-dir ../.work/r305/t` (Python 3.13 and 3.11).
- Compared every cell of the `PlayerGames` and `SeasonTotals` sheets with the CSVs, using openpyxl (read-only) and the `csv` module. Numbers by value, text exactly, blank equals blank.
  - `PlayerGames`: 180,302 rows including the header, 17,669,596 cells (3,499,338 blank), 0 differences.
  - `SeasonTotals`: 24,251 rows, 412,267 cells, 0 differences.
- Built `origin/main`'s `nflpipe/` (extracted with `git archive` into scratch) on the same data: the workbook SHA-256 is `be3ed041cae19f6bf8bff37dd8903205b1783b14038ce4b4f4dc5c80e802ff0b`, identical to the branch build. It also equals the SHA recorded for the released 3.004 workbook.
- Two runs, and Python 3.11 against 3.13, give identical hashes for the workbook and both CSVs. `NFL-PlayerGames.csv` is `ddb95ecd...`, `NFL-SeasonTotals.csv` is `75c45dea...`.

**2. CSV format**
- No BOM, 0 CR bytes, 0 NUL bytes, ends with LF.
- Every row has the header's width (98 and 17 columns).
- No `nan`, `inf`, `null` or `none` fields.
- 90 and 8 lines with quotes; none is quoted unnecessarily.
- Re-serialising the parsed rows with the `csv` module gives identical bytes.
- Non-ASCII characters present (`é`) and `"Kenneth Murray, Jr."` round-trip.
- Column order follows §13.2 and §13.6: seven identity columns, then `FF_<League>` for the five Active leagues, then `player_id, position_group, fantasy_points, fantasy_points_ppr`, then the 82 metric columns equal to `player_week`'s file order. `SeasonTotals` matches §13.2.
- Every column the M types as number holds only numbers (0 exceptions); `season`, `week` and `games` are whole numbers everywhere.

**3. Refresh workbook**
- Three builds (Python 3.13 twice, 3.11 once) are byte-identical: `39bf9bcd...`, 14,282 bytes.
- All 23 parts parse as well-formed XML, the zip tests clean, every relationship target exists, and every part is covered by a content type.
- Table and query-table columns equal the header cells, with no duplicates.
- Decoded the DataMashup:
  - version 0;
  - package length 1,412;
  - package zip with three parts;
  - permission list 317 bytes;
  - metadata 3,490 bytes;
  - bindings 0 bytes;
  - no trailing bytes.
- `FillColumnTypes` has the same number of entries as `FillColumnNames` (11 and 7), with the same type codes (3 whole, 5 number, 6 text) as the Excel-written 2.x file.
- `Formulas/Section1.m` contains the text of both `.m` files unchanged, with CRLF line ends.
- The only non-schema URLs in any part, including the decoded package and binary blocks, are the two stable release addresses (plus the three addresses on the `Start` sheet).
- Personal-data scan of every part, zip metadata, the decoded package and the metadata block: no email, path, user name, machine name, token or similar. The author is `NFL-Analysis pipeline`.
- Structural comparison with the 2.x workbook: see F1.

**4. Visitor guide**
- Both M snippets equal `nflpipe/pq/*.m` apart from the leading comment lines.
- Every relative link in `NFL/05-excel/README.md` and `README.md` resolves.
- No decision numbers or internal jargon in the visitor pages; the only `maintainer` mentions are the old pointer to the archive and the front page's own table.
- CC BY 4.0 attribution with the "modified" statement and a link to `DATA-LICENSE.md` is present, and also on the refresh workbook's `Start` sheet.
- Steps 1 to 7 read correctly for Windows desktop Excel. I could not run Excel (F5, F6).

**5. Contract and records**
- §13.1, §13.5 and §13.6 match the code on asset names, `TABLES_VERSION = "1"` (on its own line), the four-field key, the build checks and the swap order, except F3 and F4.
- Roadmap 3.005, FR-53 to FR-56, C-37 and RAID-108 agree with the contract in substance. Exceptions: F2, F4, F7.
- `python3 NFL/maintainer/plan/validate_plan.py` passes with 0 errors.

**6. Tests**
- The full suite passes: 782 passed on `../.work/venv/bin/python` (3.13, 152 s) and 782 passed on `../.work/venv311/bin/python` (3.11, 150 s).
- Mutations, each run against `tests/test_tables.py` (all caught):

| Mutation | Test that failed |
|---|---|
| Drop the last column in CSV rows | `test_csvs_equal_the_sheets_on_the_mini_publish` |
| `QUOTE_ALL` | `test_format_no_bom_lf_quoting_and_roundtrip` |
| CRLF line ends | `test_format_no_bom_lf_quoting_and_roundtrip` |
| Write a BOM | `test_csvs_equal_the_sheets_on_the_mini_publish` |
| `QUOTE_NONE` with backslash escape | `test_format_no_bom_lf_quoting_and_roundtrip` |
| Typo in the `PlayerGames.m` URL | `test_power_query_text_reads_only_the_release_asset[PlayerGames]` |
| Wrong tag in the `SeasonTotals.m` URL | same test, `[SeasonTotals]` |
| `https` changed to `http` | same test, `[SeasonTotals]` |
| `Encoding = 1252` in `PlayerGames.m` | same test, `[PlayerGames]` |
| `week` removed from the whole-number list | `test_type_lists_name_real_columns_and_the_rest_is_numeric` |

- After every mutation each file was restored from a copy, and `sha256sum -c` confirmed the four files (`export_xlsx.py`, `refresh_workbook.py`, both `.m` files) are identical to the originals; `git status` is clean.
- Strength: the format and equality tests use an independent reader (openpyxl) and a fixture with commas, quotes, newlines and non-ASCII characters.
- Gap: no test checks the hidden defined names or the table-to-query binding, because the generator writes none (F1).
