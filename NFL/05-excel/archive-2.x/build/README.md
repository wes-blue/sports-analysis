# Workbook build

`build_workbook.py` generates the paste-ready workbook `NFL-Analysis-<version>.xlsx` from source files. The source files are the single source of truth; the workbook is a build output. Adapted from the 1.x generator (archived in the owner's private repository).

`P` = the `NFL` folder of this repository. The `pq/` folder beside this file generates `05-excel/archive-2.x/powerquery/*.pq` (`pq/build_pq.py`; `pq/lint.js` checks undefined names and firewall breaches; `pq/emulate.py` reproduces the queries' logic in Python on a local copy of the published data); this script only reads the generated `.pq` files. `pii_scan.py` is the personal-data scan run on every workbook before it is published.

## Rebuild

From the repository root (any directory works; paths resolve from the script):

```
python3 NFL/05-excel/archive-2.x/build/build_workbook.py --version 2.001 --release-date 2026-11-20 --force
```

This writes the release candidate to `P/.work/rc/NFL-Analysis-2.001.xlsx`, recalculates a copy with LibreOffice, checks the inventory, runs the personal-data scan (the output is deleted if it finds anything) and the instruction check (the output is deleted if a sheet this script writes would tell the owner to clone, pull, sync, switch branch or run Python; copied plan and BLOCKERS text only gives a WARN line), and prints the SHA-256. Never build straight into `05-excel/` or `08-releases/`: the orchestrator promotes the verified candidate byte for byte (`00-Governance/VERSIONING.md`). `--force` only overwrites an earlier candidate in `.work/rc/`.

Needs Python 3 with `openpyxl` (built with 3.1.5) and, for the recalculation, LibreOffice and the xlsx skill's `recalc.py`.

| Option | Meaning |
|---|---|
| `--version` | Required, `^\d+\.\d{3}$`. Must match the output file name. |
| `--out` | Output path. Default `P/.work/rc/NFL-Analysis-<version>.xlsx`. |
| `--force` | Overwrite an existing output. Without it the script refuses. Never use it on a released file. |
| `--release-date` | ISO date (default today). Used on the Cover, in Version_Log, in the file properties and as the fixed zip timestamp. |
| `--status` | Default `Released` (the candidate is what gets promoted). |
| `--summary` | Version_Log summary. Default: the `plan.json` roadmap entry for `--version`. |
| `--gates` | Version_Log "Gates Passed" text. Default `G1–G5`. |
| `--built-by` | Version_Log "Built By" text. |
| `--no-recalc` | Skip LibreOffice. |
| `--recalc-script` | Path to `recalc.py`; else `$XLSX_RECALC`, `/mnt/skills/public/xlsx/scripts/recalc.py`, then a search under `/root/.claude/skills/`. |
| `--recalc-dir` | Where the recalculated copy goes. Default `P/.work/build-recalc/`. |
| `--input-root` | The repository root, which holds `BLOCKERS.csv` and `NFL/` (default: this repository). |
| `--forbid-file` | Extra words the personal-data scan must not find, one per line (for example the owner's name, which must never be written into this public repository; keep that file in a git-ignored folder such as `P/.work/`). |

## Inputs

| Input | Becomes |
|---|---|
| `P/01-plan/plan.json` | Cover scope, Plan (objective, goals, scope, `tblKeyFindings`), `tblArchitecture`, `tblRoadmap`, `tblRequirements`, `tblRAID`, `tblControls`, `tblGlossary`. Missing keys give empty sheets with a WARN line; a missing roadmap entry for the version uses the built-in summary. |
| `P/02-config/pipeline_config.csv` + the `DataLocation` row (the published data's web address, D-037) | `tblConfig` (Config!A4), Value column as Text |
| `P/02-config/leagues.csv` | `tblLeagues` (Scoring!A4) + `Column_Check` |
| `P/02-config/scoring_weights.csv` | `tblScoring` (Scoring!H4, file column order) + `Metric_Check` |
| `P/02-config/bonus_rules.csv` | `tblBonus` (Bonus!A4) |
| `P/06-qa/fixtures/golden_sample.csv` | `tblGolden` (Validation!A4) |
| `P/06-qa/fixtures/fixture_contracts.csv` | `tblGoldenRules` (Validation, row 4, right of `tblGolden`): the rules the expected values were made with, read by `Pipeline_Status` |
| `P/04-data/dictionary.csv` | `tblDictionary` (Data_Dictionary!A4), a snapshot |
| `P/05-excel/archive-2.x/powerquery/manifest.json` + `*.pq` | `tblMCode` (M_Code!A4, one line per row) and `tblQueries` (M_Code!E4), plus one defined name per query, `PQ_<nn>_<Query>`, covering its code cells |
| `BLOCKERS.csv` (repository root) | `tblOpenQuestions` (Open_Questions!A4): the rows whose Status is Open or Still open, a snapshot |
| `version_history.csv` (this folder) | `tblVersionLog`, then a row for the version being built |

Layout and names follow `P/05-excel/archive-2.x/powerquery/WORKBOOK-REQUIREMENTS.md`. A missing input, a header that does not match its contract, a weight that is not a number, or a `manifest.json` anchor that disagrees with the requirements stops the build.

The SHA-256 changes whenever any input changes, including `04-data/dictionary.csv` and `BLOCKERS.csv`.

## Rules the generator keeps

- **No table below another table on any sheet**, a gap column between neighbours, and `tblScoring` (which gains a column per league) rightmost on its sheet. That is why the plan tables each have their own sheet and the controls moved off Validation.
- **M text is stored one line per cell** (blank lines are empty cells). Copying a range gives the lines joined by line breaks; copying one multi-line cell would make Excel wrap the text in quotes and double every `"`. The `.pq` files must be LF-only with no tabs and end with one newline; the build checks this.
- Text that may start with `=` is written as text, never as a formula. Formulas use Excel 2010 functions and explicit `tbl[[#This Row],[Col]]` references.
- `WorkbookFolder` is the exact formula from the requirements. The candidate carries **no cached values**: `fullCalcOnLoad` is set, so Excel computes every formula when the file opens, and `CELL("filename")` then returns the real folder.

## Determinism

Two builds from the same inputs are byte-identical (checked with different `PYTHONHASHSEED` values). openpyxl stamps the save time into `docProps/core.xml` and the zip entries; the script rewrites the zip afterwards with the release date as every timestamp, the same entry order, and fixed attributes. It also adds `<ignoredErrors numberStoredAsText>` to the Config sheet (openpyxl cannot), so the text-formatted Value cells show no warning triangles.

What remains outside the script's control: the bytes of the compressed streams depend on the `zlib` build, and the XML depends on the openpyxl version. A different machine or openpyxl version can therefore give a different SHA-256 for the same content; compare content (for example with `.work/e1/verify.py`) rather than hashes across machines.

## Recalculation

LibreOffice recalculates a **copy** in `--recalc-dir`, so the candidate is never rewritten (the 1.x build recalculated the output file itself). The build fails unless `recalc.py` reports `success` with `total_errors: 0`. In LibreOffice `WorkbookFolder` evaluates to the `file:///...` folder of LibreOffice's temporary copy; that value is only in the recalculated copy, never in the candidate.

## Adding a sheet

1. Add `(name, purpose)` to `SHEETS` (order = tab order; the Cover index picks it up).
2. Build it in `build()` with `add_table`, `list_dv`, `widths`; keep one table per sheet unless the left table has fixed columns.
3. Add its tables to `EXPECTED_TABLES`.
