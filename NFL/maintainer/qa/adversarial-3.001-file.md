# Adversarial review A1: `export_xlsx.py` and the 3.001 workbook file

Reviewer: A1 of the adversarial committee (role Q1, QA Reviewer). Target: `NFL/03-pipeline/nflpipe/export_xlsx.py` at commit `dd05adb`, run on the published `NFL/04-data` (2017-2026, run `20261120T233201Z-gh44837469898`).
Nothing in the repository was changed except this report and the scratch folder `NFL/.work/a1x/` (git-ignored). No Excel was available. Every statement about Excel's behaviour is marked with a confidence; everything else was run and observed.

## Method

- Built the real workbook (`python -m nflpipe export`, 3.13): 39.76 MB zip, 409 MB uncompressed `sheet2.xml`, 12 s.
- Fetched the ECMA-376 transitional schemas (the `sml.xsd` family, from the Apache POI schema jar on Maven Central) and validated every XML part of the real file with `xmllint --schema`, including the 409 MB `sheet2.xml` in streaming mode. Result: all parts validate. (One false positive: `sml.xsd` does not declare `xml:space` on `<t>`; Excel itself writes it. Ignored.)
- Wrote an own structural validator (`NFL/.work/a1x/h.py`): cell and row order, style indexes against `cellXfs`, shared-string indexes, `count` and `uniqueCount`, table header text equal to `tableColumn` names, table name uniqueness, relationships, content types.
- Built about 90 scratch `04-data` folders (`NFL/.work/a1x/d/`, scripts `t1.py` to `t14.py`) and ran the exporter on each. Outputs were checked with the validator, with openpyxl, and for selected files with a LibreOffice round trip (xlsx to xlsx, values compared cell by cell).
- Determinism, memory and size were measured on the real data and on a synthetic 1999-2028 window.

## Summary

| Grade | Count |
|---|---|
| Critical | 4 (all need unusual input; likelihood stated on each) |
| Major | 2 |
| Minor | 12 |

On the real published data and ordinary input the package is clean: schema valid, structurally consistent, deterministic. I found no reason to expect a repair prompt on today's data. The findings below are about inputs that deviate from the contract, and one design risk (A1-S1, the size work).

---

## Critical

### A1-01 Scored columns are located once, from the first season only: later seasons with a different column order read the wrong column (silent wrong values)

- **Where:** `player_games()`, `sc_idx = [shdr.index(c) for c in league_cols]` is computed when `header0 is None`, then reused for every season. `player_week` headers of later seasons are compared with the first (`hdr != header0`), `scored` headers are not.
- **Reproduction:** `NFL/.work/a1x/t4.py`. Copy `04-data`, insert one extra column `FF_New` before `FF_Standard` in `scored/scored_2026.csv` (header and values), run `python -m nflpipe export --data-dir <copy> --out x.xlsx`.
- **What happened:** exit 0. For 2026 rows, `FF_Standard` in `PlayerGames` shows the value of the inserted column (9) instead of the real `FF_Standard` value. `SeasonTotals` sums the same wrong values. Swapping two league columns in one season file does the same.
- **Dropped last column in a later season:** exit 1 with `IndexError: list index out of range` (no useful message).
- **Likelihood:** low (the pipeline writes all `scored` files from one config, and a config change rebuilds every season). It becomes plausible after a partial refresh that adds or reorders a league, or a hand edit. The result is wrong with no warning.
- **Confidence:** high (reproduced).
- **Fix:** recompute `sc_idx` for every season, or require `shdr == shdr0` for every season and raise `ExportError` naming the file. Same check for the `scored` identity columns.

### A1-02 Table column names are not protected against Excel's `_xHHHH_` escape; header cells are, so the two can differ

- **Where:** `esc()` rewrites `_x0041_` to `_x005F_x0041_` for shared strings (header cells), but `table_xml()` writes `esc_attr(c.name)` with no such protection.
- **Reproduction:** `t7.py`. Rename a `scoring_weights.csv` header to `Not_x0041_es`, run the export. Also any league named `Q_x0041_Z` (column `FF_Q_x0041_Z`).
- **What happened:** exit 0. The header cell decodes to `Not_x0041_es`; the `tableColumn name` is the raw text `Not_x0041_es`, which Excel decodes to `NotAes`. The table name no longer equals its header cell.
- **Evidence:** Excel's own files store a line break inside a table column name as `_x000a_` (so Excel does decode this syntax in table parts). LibreOffice decodes shared strings as described; table parts could not be tested there.
- **Impact if right:** the repair prompt, and Excel drops the table (autofilter, style) on that sheet.
- **Likelihood:** very low (needs a header or league name containing `_x` plus four hex digits plus `_`).
- **Confidence:** 60 percent that Excel repairs.
- **Fix:** apply the same `_x` protection to `tableColumn name` (it must decode to exactly the header cell text), or refuse such names in `check_columns`.

### A1-03 Duplicate-name check runs before whitespace normalisation: two columns can become identical table column names

- **Where:** `check_columns()` builds `key` from `clean_text(c.name).lower()` and only afterwards rewrites tabs and line breaks to a space.
- **Reproduction:** `t7.py` case "league names that collide after whitespace normalisation": two Active leagues `A B` and `A<LF>B`, with scored columns `FF_A B` and `FF_A<LF>B`.
- **What happened:** exit 0. `table1.xml` and `table2.xml` each contain two `tableColumn`s with the same name (`FF_A B`, `FF_A B_total`, ...).
- **Impact:** Excel requires unique table column names (case-insensitive). I am certain of this rule. Expect the repair prompt and a dropped table.
- **Likelihood:** very low.
- **Confidence:** 95 percent that Excel repairs on duplicates (the duplicate was observed in the XML).
- **Fix:** normalise first, then check uniqueness. Also compare with `casefold()` and after stripping, since Excel compares with its own case rules.

### A1-04 `status.csv` `generated_utc` is copied into `docProps/core.xml` without validation or cleaning

- **Where:** `core_xml(created)` writes `esc(created)` into `dcterms:created` and `dcterms:modified` (declared `xsi:type="dcterms:W3CDTF"`). `clean_text` is not applied; the value is not checked for the W3CDTF format.
- **Reproduction:** `t5.py`: set `generated_utc` to `yesterday`, to `2026&<`, or to a value with `\x01`.
- **What happened:** exit 0 each time. With `yesterday` or `2026&<`: openpyxl refuses the workbook ("could not read properties"). With `\x01`: `core.xml` is not well-formed XML (xmllint: `PCDATA invalid Char value 1`).
- **Impact in Excel:** a malformed part is certainly a repair or rejection. An invalid but well-formed date: I believe Excel ignores or repairs it; not verified.
- **Likelihood:** low (the pipeline writes `%Y-%m-%dT%H:%M:%SZ`). Cheap to close, and it is the one value that goes into a part that Excel reads before anything else.
- **Confidence:** 90 percent for the control-character case, 50 percent for the invalid-date case.
- **Fix:** validate `generated_utc` against `^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$` in `Data.__init__` and exit 1 naming the value.

---

## Major

### A1-05 Non-finite or very large score values: `NaN` is written as text in numeric columns; `inf` and large values crash with an unreadable message

- **Reproduction:** `t3.py`. Put `nan`, `inf`, `1e400`, `1e60` or `1e100` into `FF_Standard` of one `scored` row (and a matching row so the player has two games).
- **What happened:**
  - `nan`: exit 0. `SeasonTotals` `FF_Standard_total` and `_avg` become the text `NaN` (Decimal accepts `NaN`, and `quantize` of a quiet NaN does not raise). `PlayerGames` holds the text `nan`. No warning anywhere.
  - `inf`, `-inf`, `Infinity`, `1e400`, `1e60`, `1e61`, `1e70`, `1e100`: exit 1 with `nflpipe export: error: InvalidOperation: [<class 'decimal.InvalidOperation'>]`, no file, no line number. (`quantize` fails once the sum has more than 60 digits; with `inf` immediately.)
- **Impact:** the failure itself is fine (nothing is published), but the message does not name the file, line or value, so the owner cannot act on it. The `NaN` case ships a text value in a numeric column.
- **Likelihood:** low (the gates should catch it upstream), but a scoring bug upstream is exactly when it appears.
- **Confidence:** high (reproduced).
- **Fix:** in `player_games()`, use `d = Decimal(v)`; `if not d.is_finite()` raise `ExportError` with file, line, column and value. Also reject anything `is_number()` rejects, so `PlayerGames` and `SeasonTotals` agree (see A1-09).

### A1-06 `PlayerGames` is strict about blank lines, `read_table` is not

- **Reproduction:** `t5.py` "trailing blank line": append one `\n` to `player_week_2026.csv` and `scored_2026.csv`.
- **What happened:** exit 1 `player_week_2026.csv line 12: 0 values but 93 columns`. The small config tables silently drop blank rows (`read_table`); `count_rows` counts a blank line as a row.
- **Impact:** a hand-saved or concatenated season file with a blank trailing line stops the whole build. Message is understandable. Not a wrong value.
- **Confidence:** high (reproduced). Severity depends on whether you want tolerance; the contract (§5) says files end with `\n` and are written by the pipeline, so this is Major only for hand-edited data.
- **Fix:** skip rows equal to `[]` in `player_games` and in `count_rows`, or document that blank lines are an error.

---

## Minor

### A1-07 `_x` escape misses overlapping underscores (wrong text)
`esc()` uses a non-overlapping regex. Text `_x005F_x0041_` (two escapes sharing one underscore) is written as `_x005F_x005F_x0041_`; a spec-following decoder reads it as `_x005FA`. Reproduced with the LibreOffice round trip (`t1.py`, `t9.py`: row with that name comes back as `_x005FA`). Text with a single `_x0041_` or `_x005F_` survives. Confidence in the exporter bug: high; that real Excel decodes the same way: 75 percent. Fix: `re.sub(r"_(?=x[0-9A-Fa-f]{4}_)", "_x005F_", s)`.

### A1-08 Column width above Excel's 255 limit for long league names
`Col(..., width=max(len(nm) + 4, 12))` has no cap. A league of 300 characters gives `<col width="314">`/`312`/`307` (`t11.py`). Excel's maximum column width is 255; XlsxWriter clamps. Likely a repair of "column information". Likelihood very low. Fix: `min(255, ...)`.

### A1-09 Number detection differs between `PlayerGames` and `SeasonTotals`
`PlayerGames` uses `is_number` (strict decimal syntax), `SeasonTotals` uses `Decimal(v)`, which also accepts `+3`, `.5`, ` 7`, `12.5 `, `1_0`, `٣` and `NaN`. Reproduced in `t3.py`: such a value is a text cell in `PlayerGames` and is summed in `SeasonTotals`. Fix: use one parser.

### A1-10 `SeasonTotals.season` comes from the file name, `PlayerGames.season` from the row
`t14.py`: rows of `player_week_2025.csv` that say `2031` appear as 2031 in `PlayerGames` and are counted under 2025 in `SeasonTotals`. No error. Fix: assert `row[0] == str(season)`.

### A1-11 Text length is counted in code points; Excel counts UTF-16 units
`MAX_CELL_CHARS` is compared with `len(text)`. A name of 20,000 emoji (40,000 UTF-16 units) is accepted (`t11.py`). I believe Excel truncates or repairs a string over 32,767 units (confidence 60 percent). Fix: `len(text.encode("utf-16-le")) // 2`.

### A1-12 Table header text length is not limited
A header (or `FF_<League>_total`) over 255 characters is written as is (`t6.py` "long 300", `t7.py`). I recall Excel limiting table header text to 255 characters (confidence 50 percent that a longer one is repaired). Fix: reject headers over 255 characters.

### A1-13 Numbers outside what Excel can store are written verbatim
`1e-400`, `5e-324`, `1e-320` pass `is_number` (Python's `float` underflows to 0 or a denormal) and are written as `<v>1e-400</v>`. Whether Excel loads these cleanly is unverified (confidence 30 percent of a repair). Numbers with more than 15 significant digits (`12345678901234567890`) are written exactly but Excel keeps 15 (LibreOffice round trip shows `1.23456789012346e+19`). No such value exists in nflverse stats. Fix: reject or text-ify numbers whose `float` round trip differs or whose magnitude is below 1e-300 and not zero.

### A1-14 Zip64 is not forced for the big sheet
`pkg.stream()` calls `zf.open(info, "w")` without `force_zip64=True`. `zipfile` raises `RuntimeError` when a stream grows past 2 GiB. `sheet2.xml` is 409 MB for 180,301 rows (2.27 KB per row), so the limit is reached at about 880,000 rows. A 1999-2028 window (540,903 rows) writes 1.24 GB and passes (`t10.py`), so this is not reachable with nflverse data. Fix: `force_zip64=True` (adds a few bytes of header).

### A1-15 Off-by-one at the row limit for sheets with a note row
`MAX_DATA_ROWS` (1,048,575) is checked against `rn - first` for every sheet. For `Leagues`/`Scoring`/`Bonus`, data starts at row 3 so 1,048,575 data rows end at row 1,048,577. Unreachable. `PlayerGames` and `SeasonTotals` hit exactly row 1,048,576 and pass (`t8.py rows`: 1,048,575 rows OK, 1,048,576 rejected with a clear message).

### A1-16 Error messages and cleanup details
- A column error names the part path (`xl/worksheets/sheet5.xml: duplicate column name 'notes'`), not the sheet or the CSV file.
- A zero-byte `player_week_2026.csv` reports "has 0 rows but scored_2026.csv has 10: different row counts" rather than "empty file".
- A failure while a worksheet stream is open leaves the file handle open (`ZipFile.close()` raises and is swallowed). On Linux the temp file is still removed (tested, `t12.py`); on Windows `tmp.unlink()` would fail with `PermissionError` and mask the original error. Only matters if the owner runs the export locally on Windows.
- The temp name `NFL-Analysis.xlsx.tmp` is fixed; two concurrent runs to the same `--out` collide.

### A1-17 Zip bytes depend on the zlib build
Output is byte-identical for `PYTHONHASHSEED` 1 and 999, `TZ` Pacific/Kiritimati and America/New_York, `LC_ALL=C` and `LANG=tr_TR.UTF-8`, and Python 3.13 versus 3.11 (same SHA-256, `det.txt`). Both used zlib 1.3. A runner whose Python links a different zlib (for example zlib-ng) can produce different compressed bytes for identical XML. The contract promises byte identity; the uncompressed parts are identical. Say "same content" or compare CRCs.

### A1-18 `SeasonTotals` shows `0` for a player whose scores are all blank
Blank score cells are skipped, total stays `0`, average is `0 / games`. A reader cannot tell "all blank" from "all zero". Contract-conformant, noted only.

---

## Size and opening time (attack surface 4)

Measured on the real file (`size.py`, `size2.py`):

| Fact | Value |
|---|---|
| Zip | 39.76 MB; `sheet2.xml` 409.0 MB uncompressed, 38.14 MB compressed (96 percent of the file); `sheet3.xml` 14.1 MB / 1.5 MB; shared strings 0.32 MB / 0.07 MB |
| Cells in `sheet2` | 14.17 million written (3.50 million blanks are already omitted); 81 percent are the number `0`, 9 percent strings, 10 percent other numbers |
| Style attribute | on only 11 percent of cells (season, week, points columns); negligible |
| Strings | already shared; 11,328 unique. Inline strings would be larger, not smaller |

What makes it large: the cell reference `r="CF180302"` written on every cell. It is highly variable text and dominates the compressed size. Rows of 80 identical `<c r="X..."><v>0</v></c>` cells would otherwise compress almost to nothing.

| Change | Estimated size (zip) | Uncompressed | Cost and risk |
|---|---|---|---|
| **A1-S1: omit `r` on a cell that directly follows the previous cell (keep it on the first cell of a row and after a gap)** | about 6.8 MB (-82 percent), measured on an 8 MB slice: 785 KB to 140 KB | 409 MB to about 242 MB, so also much faster to parse | Values unchanged. The `r` attribute is optional in the schema, and the file still validates, but I could not test Excel. I am about 85 percent sure Excel and its table logic accept this (it is how several streaming writers work). Test once in real Excel before adopting. |
| Omit zero cells | about 13 MB (35 percent of today) | much smaller | Changes meaning: blank means null (§5), so `AVERAGE`, `COUNT` and filters on those columns change for the owner. Do not do it without an owner decision. |
| Both | about 4.7 MB | | as above |
| Drop the one all-zero column (`fg_missed_0_19`) | about 0.2 MB | | changes the column list (§13.2) |
| 37 columns with less than 1 percent non-zero values | no change possible without dropping zeros | | |
| zlib level 9 | none (slightly larger on the test slice) | | |
| Inline strings or fewer styles | none or worse | | |

Opening time: Excel must parse 14 million cells either way; fewer bytes per cell (A1-S1) reduces that. LibreOffice opened and re-saved the full file in 31 s (`lofull.txt`). I cannot state Excel's time.

Memory and run time: the exporter used 146 MB peak and 37 s for a synthetic 1999-2028 window of 540,903 rows (1.24 GB `sheet2.xml`, 120 MB zip). 1,048,575 rows by 16 columns: 59 s, 106 MB. Memory is not a risk.

---

## Things I tried that held up

Package and schema
- All XML parts of the real file validate against the ECMA-376 `sml.xsd`, including the 409 MB sheet in streaming mode; `core.xml` and `app.xml` are well-formed; content types, relationships and part names all resolve.
- Table `ref`, `autoFilter ref`, column count, `id` (1 to 7, unique) and names (unique, valid, not cell-like) are consistent; every table header cell equals its `tableColumn name` and is a shared-string cell (`t13.py`).
- `sst` `count` equals the number of string cells (1,384,483) and `uniqueCount` equals the `<si>` count; `xml:space="preserve"` appears where a string has leading or trailing space or a line break (tested).
- All style indexes are below `cellXfs count` (9); fonts, fills, borders, `cellStyleXfs` and `cellStyles` have the required default entries; `numFmt` for RoundDecimals 0, 1, 2, 3 and 6 validates (`t5.py`).
- `sheetView`, `pane` (`xSplit`, `ySplit`, `topLeftCell`, `activePane`) and the three `selection` elements follow Excel's own pattern; `cols` entries are contiguous, one per column, not overlapping; rows and cells are in strict increasing order; element order inside `worksheet` is correct (`hyperlinks` before `pageMargins` before `tableParts`).
- Zip: `[Content_Types].xml` first, deflate, no data descriptors, fixed 1980-01-01 date, `testzip` clean. A missing theme part is not an error for Excel as far as I know (about 90 percent sure; table style falls back to the default theme).

Hostile data (all exit 0 with a valid file unless stated)
- Names starting `=`, `+`, `-`, `@`, tab, or `=HYPERLINK(...)`: stored as shared strings, read back as text (`t1.py`). Config Notes with commas, quotes, CR/LF, tabs and `=cmd|...`: stored as text, identical on read-back (`t7.py`).
- Names with `& < > " '`, emoji and astral characters, right-to-left Hebrew, ZWSP, BOM, `0042`, `1e5`, `2025-01-01`, `TRUE`, `#REF!`: round trip exactly (openpyxl and LibreOffice). XML-illegal characters (`\x00`, `\x01`, `\x0b`, U+FFFE) are removed as the contract says; a name made only of illegal characters becomes an empty string (valid `<si><t></t></si>`).
- 32,767-character text accepted, 32,768 rejected with a clear message. `_x0041_` and `_x005F_` single escapes round trip.
- Numbers: `nan`, `inf`, `-inf`, `1e400`, `1e309` in a metric column become text cells, not formulas or invalid numbers; `-0`, `0.1`, `0.30000000000000004`, `1E5`, `1e308` become numbers; leading zeros, `00-0034857`, `+5`, `.5`, `0x10`, `2025-01-01`, `1/2` stay text.
- Header-only season files, header-only for all seasons (valid table with one empty data row), a missing `scored` row (clear error), a key mismatch between `scored` and `player_week` (clear error, no partial file and the old output untouched), a league with no `scored` column (clear error), an extra inactive league (ignored), league names with spaces, brackets, `#`, apostrophe, quote, `&<>`, comma, emoji, a numeric name, `week` as a league name, an empty-ish name.
- 16,384 columns: accepted, last cell `XFD`, table `A1:XFD4`; 16,385: rejected. 1,048,575 data rows: accepted, tables end at row 1,048,576; 1,048,576: rejected in 1.3 s, before anything is written.
- `status.csv`: wrong or padded `data_contract_version`, missing `latest_week`, 40,000-character `data_source` are all rejected with a clear message; a non-numeric `gates_pass` is written as text.
- Real data: no name starts with `=+-@`, no string contains `_x`, one non-ASCII name (`Audric Estimé`), two strings containing `&lt;`; all correct.

Environment
- Output is byte-identical across hash seeds, time zones, locales and Python 3.11 versus 3.13 (A1-17 for the zlib caveat). `glob` order does not matter (`sorted`). Memory 146 MB for 540,903 rows.

LibreOffice and openpyxl
- openpyxl read-only load and LibreOffice conversion succeed on every valid output. LibreOffice round trip of the real 2017-2026 file: opens in 31 s; the 2-season sample, hostile-name file, number file and extra-league file show only the differences listed under A1-07 and A1-13 (plus CRLF in a cell becoming LF, which is LibreOffice's normalisation).

## Not tested

- Real Excel for Windows (no Excel here): every "Excel would" statement above is from rules and experience, with the confidence given.
- Excel's behaviour with cells that lack `r` (A1-S1), with table headers over 255 characters (A1-12), with strings over 32,767 UTF-16 units (A1-11), and with a missing `theme1.xml`.
- A full value-by-value comparison of the real 17.7 million cells against the CSVs (the builder and the reviewer cover ordinary data).
- Excel's opening time and memory.

## Scratch files

`NFL/.work/a1x/`: `h.py` (harness and validator), `t0.py` to `t14.py` (cases), `size.py`/`size2.py` (size experiments), `xsd/` (ECMA schemas), `d/` (scratch data folders and outputs), `det.txt`, `lofull.txt`. Nothing was written to `NFL/04-data`.
