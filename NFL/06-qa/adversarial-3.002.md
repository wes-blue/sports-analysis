# Adversarial review A1: workbook design 3.002 (cells without `r`)

Reviewer: A1 of the adversarial committee (role Q1, QA Reviewer). Target: the working tree at `be84477` (design 3.002, D-047): `export_xlsx.py` `Emitter(compact=True)` for `PlayerGames` and `SeasonTotals`, contract `NFL/CONTRACTS.md` §13.3 to §13.5, and the workflows `nfl-pipeline-weekly.yml` / `nfl-pipeline-monthly.yml`.
Nothing in the repository was changed except this report and the scratch folder `NFL/.work/a3/` (git-ignored). None of the builder's scripts (`NFL/.work/x3/`) were used; the 3.001 published file in `x3/` was used only as an input. No Excel was available.

Labels: **VERIFIED** = I ran it or read the source myself. **VERIFIED-2** = a statement found by web search whose primary page I could not open (`learn.microsoft.com` and `mailman.vse.cz` are outside this session's allowed network, so I saw only search-result summaries). **UNVERIFIED** = reasoning only.

## Summary

| Grade | Count |
|---|---|
| Critical | 0 |
| Major | 2 |
| Minor | 4 |

Everything that can be checked without Excel is clean: the file is schema valid, every cell lands in the same position as in 3.001 according to four independent readers, and the publish path rebuilds and replaces the asset in the simulation. The remaining risk is the one nobody can remove here: whether desktop Excel accepts `<c>` without `r` (A3-01), and the order in which the owner's test and the publish happen (A3-02).

---

## Major

### A3-01 No primary evidence that desktop Excel accepts a `<c>` without `r` in table data rows (UNVERIFIED)

- **What is certain:** ECMA-376 `CT_Cell` declares `r` optional (the schema validates, see the checks below). Excel itself always writes it.
- **Evidence for Excel accepting it (all VERIFIED-2, none primary):**
  - An Apache OpenOffice bug report (issue 127672) says a file with omitted cell references showed all four cells in MS Excel and only one in OpenOffice; another (issue 126344) says Excel assumes the next cell is in the same row, one column right of the previous cell.
  - A Microsoft Open Specifications answer on Microsoft Q&A ("Why CellReference is null?") says the Office XSDs, and so the Open XML SDK, treat a cell without a reference as valid.
  - MS-OI29500 §2.1.590 (note on §18.3.1.4 `c`) shows that Microsoft documents `r` as optional; in the ISO/IEC 29500 defect report DR 16-0007 Microsoft's Excel team proposed text that an omitted `r` places the cell in the first column when it is the first `c` of the row (and the follow-up discussion, "if not specified, the column is one greater than the previous cell").
- **Evidence against (VERIFIED-2, one report):** in the same SC34 WG4 thread family ("Problems with optional spans and r attributes in worksheet rows and cells", 2018-08) a participant wrote that, having tested Excel 2016 for Mac, "the r attribute does seem to be essential". The search summary cut off before the detail; it may be about rows (`<row r>`), not cells, and it is Mac. I could not read it.
- **Other readers have been less tolerant** (LibreOffice bug 49028/65059 and ClosedXML, openxlsx2 and Open XML PowerTools issues, all long ago for LibreOffice). That does not bear on Excel, but it matters for any other program the owner may later point at the file (see the readers I tried below: LibreOffice, openpyxl, pandas and python-calamine all read it correctly).
- **Interactions I checked that could make Excel stricter than usual (all VERIFIED unless said):**
  - `spans`: absent on every row, as in 3.001 (which Excel accepted). Not new. UNVERIFIED whether the combination "no `spans` and no `r`" matters; the ambiguity discussed in the thread is about this combination.
  - `<dimension>`: absent, as in 3.001. Not new.
  - Shared formulas: none; no `<f>` anywhere.
  - Table `ref` and AutoFilter `ref`: `A1:CT180302` and `A1:Q24251`, equal to the cells written; every data row keeps `r` on its first cell and the row's `r`; the last row 180,302 and last column CT (98) are present and `r`-bearing where they follow a gap.
  - First cell after a blank, a run of blanks, the last column, rows of a single cell: tested through the real exporter and by a 20,000-case fuzz of `Emitter.row` (below); the rule held every time. Single-cell rows cannot occur through the exporter (season, week and season type are always written), but the fuzz produced 8,661 of them.
  - Cell order: strictly increasing in every row of both big sheets (checked on all 14,582,525 cells).
- **Likelihood:** I put the chance that Excel shows a repair prompt at roughly 10 percent and the chance that it silently misplaces cells at below 2 percent (a reader that infers the column from the previous cell has no reason to shift). These are judgement, not measurement. The failure is visible and reversible.
- **Reproduction:** none possible here. The file to test is `NFL/.work/a3/NFL-Analysis-3.002.xlsx` (8,432,121 bytes; byte-identical to the builder's `x3/NFL-Analysis-3.002.xlsx`).
- **Fix / mitigation:** the owner's test (Q-025) is the only real control, so make it catch silent misplacement as well as the prompt (it would not show a prompt):
  1. Open the file; note any message.
  2. On `PlayerGames` press Ctrl+End: it must land on column **CT**, row **180302**.
  3. Pick one player-week the owner knows (the ESPN check from Q-024) and compare `FF_ESPN_League` and one far-right metric column (for example column CT) with the CSV.
  4. Check that on `SeasonTotals` Ctrl+End lands on column **Q**, row **24251**.

### A3-02 The owner's test and the publish are in the wrong order: the merge replaces the known-good asset first

- **Where:** D-047 and Q-025 say the owner opens the 3.002 file "once before it counts as released". But `nfl-pipeline-weekly.yml` runs on the push of `NFL/03-pipeline/nflpipe/**` to `main`, finds the freshness key changed, builds, and replaces `NFL-Analysis.xlsx` at the stable address. After that the 3.001 file that Excel accepted is no longer served; the only copies are the owner's own download and `NFL/.work/x3/` here (git-ignored).
- **Reproduction:** simulation `NFL/.work/a3/sim.py`: release holds a 40,018,688-byte asset with key `<run_id>|1.2.1|3.001`; a push event with the run result SKIP; result: build=true ("not built from the published data and the current workbook design"), asset replaced by the 8,432,121-byte file, notes key `...|1.2.1|3.002`. A following scheduled SKIP reads only (build=false).
- **Impact:** if Excel does show a repair prompt, the public link serves a file that prompts until a revert is merged. Only the owner uses it, so the harm is small, but it contradicts the intent of Q-025.
- **Fix, any of:**
  1. Test before merging: the orchestrator attaches the built 8.4 MB file to the pull request (GitHub accepts `.xlsx` attachments up to 25 MB; UNVERIFIED from here) or gives it to the owner another way; the owner opens it and answers Q-025; then merge. The exporter is deterministic, so the file the pipeline builds after the merge has the same XML (A1-17 of the 3.001 report: zlib bytes may differ, the values and XML do not). Data that changes between now and the merge changes values, not structure.
  2. If the order stays as it is, write the rollback in `BLOCKERS.csv` Q-025: "if Excel complains, tell Claude; the fix is a revert of the `WORKBOOK_VERSION` and `Emitter` change; the revert changes the key back to `...|3.001`, so the next push rebuilds the 3.001 form automatically". I checked the logic of the key (below), not a revert end to end.
  3. Keep the previous asset under another name until the new one is confirmed (a workflow change; not worth it for one user).

---

## Minor

### A3-03 The first real asset replacement on GitHub has only been run against a stand-in (UNVERIFIED on the real API)

- The seven-step replacement (upload `.next`, check `state==uploaded and size`, delete the old asset, `PATCH` the new one to the stable name, ranged `curl`, edit the notes) ran against `NFL/.work/qr/gh` (my run: `sim.py`, real exporter, the real workflow steps executed by the `fw/scen.py` harness): all steps rc=0, the stable address served the new size, the notes key was `...|3.002`. The stand-in is the committee's own model of GitHub, not GitHub.
- Real-API points I could not test: the `PATCH /repos/{o}/{r}/releases/assets/{id}` rename (documented as accepting `name`; UNVERIFIED here), that GitHub keeps `NFL-Analysis.next.xlsx` as typed (dots and hyphens are kept in my understanding), and the CDN returning 200/206 for the stable name right after the rename.
- A rename or delete that GitHub refuses would be blocked if the repository had "immutable releases" turned on. The 3.001 upload added an asset to an already published release and worked, which would have failed under that setting, so I think it is off (inference, UNVERIFIED).
- **Failure modes are safe by design:** every failure turns the run red, opens the alert issue and keeps the built file as a run artifact for 7 days; the worst case is the stable address answering 404 until the next run (the "rename refused and re-upload failed" branch, which the committee exercised on the stand-in in 3.001).
- **Fix:** none needed. After the merge the orchestrator should look at the first run's step summary (the line "workbook: published at ...") and open the stable address once.

### A3-04 Open time will not change much, so do not promise a faster open

- LibreOffice headless open and re-save to xlsx, wall clock, same machine, alternating order: 3.001 47.2 s and 49.6 s; 3.002 45.5 s and 46.8 s (about 5 percent faster). python-calamine read of both big sheets: 8.1 s against 7.0 s. The cell count (14.58 million) dominates, not the XML bytes. Excel's own time is UNVERIFIED; expect "about a minute" as for 3.001. `README.md` line 11 says "a little while" and `AUTOMATION.md` says "up to a minute", which is accurate. No change needed; do not describe 3.002 as faster to open.

### A3-05 Stale comments

- `nfl-pipeline-weekly.yml` line 452 and `nfl-pipeline-monthly.yml` line 335: "the real file is about 38 MB; anything this small is a broken export" (now about 8 MB; the 1,000,000-byte floor is still right). `NFL/README.md` line 9 still reads "Version 3.001 ... was released". Changing a workflow file also starts the weekly run, which is harmless but should be deliberate, so fix the comments with the next real workflow change.

### A3-06 The contract wording "a reader places a cell without it in the column after the previous cell" is not in ECMA-376's prose

- §13.3 states this as the schema's rule. ECMA-376 only says `r` is optional; the placement rule comes from Excel/LibreOffice behaviour and the defect-report discussion (A3-01). Reword to "Excel and the other readers tried here place it ..." and name the test. Cosmetic.

---

## What held up

- **Same cells, all readers (VERIFIED).**
  - Own streaming comparison (`cmp_full.py`) of the published 3.001 file and the 3.002 file: `sheet2` 14,170,258 cells and `sheet3` 412,267 cells, identical row, column, type, style and value on every cell; 13,984,569 and 388,000 cells are written without `r`; 0 rule violations (every cell is without `r` exactly when it directly follows the previous written cell and is not the first cell of its row). All other parts are byte-identical except `docProps/core.xml` and two strings in `sharedStrings.xml` (the version text `3.001` to `3.002`).
  - ECMA schema (`sml.xsd`, from the 3.001 report's folder): all 8 sheets, 7 tables, workbook, styles and shared strings validate. (One false positive, as in the 3.001 report: the schema lacks `xml:space` on `<t>`, so a shared-strings file that holds a string with leading or trailing space or a line break "fails"; Excel itself writes that attribute.)
  - LibreOffice open and re-save of the full file: 14,584,093 values compared against the original, 0 differences; the re-saves of 3.001 and 3.002 differ only in the two version strings.
  - openpyxl (read-only, 180,301 rows by 98 columns), pandas `read_excel` and python-calamine (a Rust reader) read it correctly; calamine's values for both big sheets equal those of 3.001.
- **Edge-case inputs through the real exporter (VERIFIED).** 13 fixtures built from `NFL/04-data` (`NFL/.work/a3/fx/`, generator `mkfx.py`, cases in `fxrun.py`, checker `fxcheck.py`): blank first identity columns, blank last metric columns, alternating blanks (also in the scored file), rows with only the key columns, one metric only, all metrics blank, a long run of blanks between two written cells, no blanks, formula-like text (`=1+1`, `+SUM(A1)`, `-2+3`, `@A1`, `=HYPERLINK(...)`, `=cmd|...`), Unicode (accents, CJK, emoji, Hebrew, zero-width space, nbsp, `_x0041_`, line breaks), 32,000 and 32,767 character text, numeric forms (`-0`, `1e5`, `1E-3`, `007`, `1.`). For each: the compact file and a reference built by the same exporter with compaction switched off (`refbuild.py`) have the same cells (rule checked), pass the schema, read equal through openpyxl, pandas and LibreOffice (CSV of `PlayerGames`, and xlsx re-save compared value by value). 0 differences in all 13. Two further fixtures (blank `season`, blank `week`) are rejected by the exporter with a clear message, as before.
- **Fuzz (VERIFIED).** `fuzz.py` drove `Emitter.row` directly with 20,000 random rows of 100 columns (random, runs and gaps, one cell anywhere, first or last column only, dense, empty): positions equal the reference form every time, and the number of cells carrying `r` equals the number of runs of written cells.
- **Publishing logic (VERIFIED by reading and by the simulation).**
  - `WORKBOOK_VERSION` is read by `sed -n 's/^WORKBOOK_VERSION = "\([0-9A-Za-z._-]*\)".*/\1/p' nflpipe/export_xlsx.py | head -n 1`; run on the current file it prints `3.002`. The key is `${run_id}|${pipeline_version}|${design}` = `20261120T233201Z-gh44837469898|1.2.1|3.002` and is compared with `grep -qF "nfl-workbook-key: ${key} "` against the release notes; the notes heredoc writes that line with the trailing space.
  - A push touching `NFL/03-pipeline/nflpipe/**` takes the `push` branch of "Resolve" (`decision=run`, no `--force`); the run says SKIP when config, pipeline version and upstream data are unchanged; the workbook step then builds because the key differs (simulation: `wb build=true`, real export 7.3 s, replacement as described). A run that already holds the 3.002 key builds nothing. The monthly workflow has no push trigger and is otherwise the same step text (it differs only in reading `steps.outcome.outputs.dry_run`).
  - `NFL/03-pipeline/tests/test_workflows.py`: 267 passed (46.5 s). `tests/test_export_xlsx.py`: 146 passed (4.7 s), including the builder's own 3.002 tests.
- **Determinism:** building the real file again from `NFL/04-data` gave a file byte-identical to the builder's (8,432,121 bytes, 7.4 s).

## Not tested

- Real desktop Excel, any version (A3-01). Excel Online, Mac and Protected View.
- The real GitHub API replacement (A3-03).
- Excel's open time and memory.
- A revert end to end (only the key logic was read).
- The primary texts of MS-OI29500 and the SC34 WG4 thread (network).

## Overall view: is the repair-prompt risk acceptable for the owner's one test open?

Yes, with the order in A3-02 fixed or the rollback written down. The only unknown is Excel's reaction to the `r`-less cells; there is no primary source either way, the secondary evidence leans toward acceptance, one report from a Mac Excel 2016 test leans against, and everything else about the file (schema, structure, positions, four other readers, 13 hostile fixtures, a fuzz, the unchanged parts that Excel already accepted in 3.001) is clean. The cost of being wrong is one prompt on the owner's machine and a revert; the change is lossless, so nothing is lost. The owner's test should include the Ctrl+End and value checks of A3-01, because a silent misplacement would not show a prompt.

## Exactly what I ran

Working folder `NFL/.work/a3/`.

1. `python -m nflpipe export --out ../.work/a3/NFL-Analysis-3.002.xlsx` from `NFL/03-pipeline/` with `NFL/.work/venv/bin/python` (7.4 s; `cmp` against `x3/NFL-Analysis-3.002.xlsx`: identical).
2. `cmp_full.py` (own `iterparse` comparison and rule check) on `sheet2.xml` and `sheet3.xml` of the 3.001 published file and the new file; Python comparison of every other part.
3. `xmllint --noout --stream --schema` (schema from `NFL/.work/a1x/xsd/`) on all sheets, tables, workbook, styles, shared strings.
4. `lo.sh` (`soffice --headless --convert-to xlsx`, fresh profile per run) on both files, twice each, alternating; `cmp_vals.py` (own value-level comparison with positions resolved per the rule) original against re-save, and re-save 3.001 against re-save 3.002.
5. openpyxl read-only over `PlayerGames` (180,301 rows), pandas `read_excel` on `SeasonTotals`, `python-calamine` (installed in a scratch venv outside the repository) on both big sheets of both files.
6. `mkfx.py`, `fxrun.py` (15 cases), `refbuild.py`, `fxcheck.py` (13 passing fixtures), `fuzz.py` (20,000 rows).
7. Reading `.github/workflows/nfl-pipeline-weekly.yml` and `-monthly.yml`, `sed` against the real `export_xlsx.py`, `sim.py` (three scenarios through the `NFL/.work/qr/` stand-in and the `NFL/.work/fw/scen.py` harness), `pytest tests/test_workflows.py` and `tests/test_export_xlsx.py`.
8. Web searches (four) on omitted `r`, MS-OI29500 and the SC34 WG4 defect report; page fetches failed on network access.
