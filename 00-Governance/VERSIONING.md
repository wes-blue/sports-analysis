# Versioning Policy

This policy applies to every sport in `wes-blue/sports-analysis`. Paths start at the repository root. `<Sport>` is a sport's top-level folder (today only `NFL`).

## Workbook names

- Each sport's workbook has its own name: `<Workbook>-<MAJOR>.<MINOR>`, where the minor part always has 3 digits. The NFL workbook is **`NFL-Analysis`**, for example `NFL-Analysis-2.001`.
- Each increment of scope adds 0.001: 2.001, 2.002, … 2.999.
- A new major number starts at `.001` (2.001, not 2.000).
- A number is never reused, including the number of a version that was withdrawn or never started.

## What the major number means (decision D-035)

**The major number names the design generation**, so a reader can tell from the first digit which system produced a file and where its source lives.

| NFL major | Generation | Where it lives |
|---|---|---|
| 1.x | Everything computed inside Excel (1.001–1.004), plus the transitional 1.006 (fed by the pipeline, reading a local data folder). 1.005 was withdrawn and never released. | Released and kept in the owner's private repository. The 1.x line is closed: no further 1.x version is made. |
| 2.x | The workbook fed by the pipeline in this repository, reading the published data from its web address. The first release here is **NFL-Analysis-2.001**. | This repository: `NFL/05-excel/` and `NFL/08-releases/` |

A new major number marks a new design generation: a change after which an existing copy of the workbook no longer works as before, such as a new place to read its data from. It needs the owner's approval, or a decision the owner has delegated, as for 2.x (D-035). Every major in use is listed here and in the sport's release register.

## A second sport

- Its folder is the sport's usual short name at the top of the repository (for example `NBA/`), copied from `_Sport-Template/`.
- Its workbook has its own name, `<SPORT>-Analysis` (for example `NBA-Analysis`), and its own version line, starting at **1.001**. Its major numbers name that workbook's own design generations and are listed in the table above when they are first used.
- It has its own release register, `<Sport>/08-releases/RELEASES.md`, and its own pipeline and data-contract versions (below).
- The NFL version numbers say nothing about another sport's, and the other way round.

## Where files live (2.x)

| File | Location |
|---|---|
| Working copy the owner opens | `NFL/05-excel/NFL-Analysis-<version>.xlsx` |
| Immutable release copy | `NFL/08-releases/NFL-Analysis-<version>.xlsx`, byte-identical to the working copy at release (`NFL/CONTRACTS.md` §12) |
| Experimental workbook (not a release) | `NFL/05-excel/NFL-Analysis-<version>-queries-installed-EXPERIMENTAL.xlsx`, with the internal version label `<version>-experimental` (D-032) |
| Release register | `NFL/08-releases/RELEASES.md` |
| 1.001–1.006 | The owner's private repository. `NFL/08-releases/RELEASES.md` lists them for the record. |

For another sport, replace `NFL` and `NFL-Analysis` with its folder and workbook name.

## Rules

1. One version is one file and one increment of scope. The increments are listed in the sport's plan (`<Sport>/01-plan/plan.json`, roadmap), which the workbook's Plan sheet shows.
2. Released files are immutable. A fix ships as the next version. Never overwrite a released file; the build script refuses to unless `--force` is passed.
3. The version string must match in five places:
   - the filename;
   - the Cover sheet (named cell `WorkbookVersion`);
   - file properties (Title and Version);
   - the `Version_Log` sheet;
   - `<Sport>/08-releases/RELEASES.md`.
4. Every version gets a row in `RELEASES.md` with: version, date, status, scope, gates passed and SHA-256.
5. Status moves Draft → Released → Superseded. A version becomes Superseded when the next one is released, and that status is recorded in `RELEASES.md`. The released file itself is never edited.
6. Before a workbook is committed, its file properties and contents are checked for the owner's name (`CLAUDE.md` §2). This repository is public.

## Pipeline and data versions

These are separate from the workbook's version number, and each sport's pipeline has its own.

- `pipeline_version` (in `NFL/03-pipeline/nflpipe/__init__.py`) follows `MAJOR.MINOR.PATCH`. It starts at `1.0.0`. A change to scoring arithmetic or to a derived-metric rule raises MINOR; a breaking change raises MAJOR.
- `data_contract_version` is a whole number, starting at `1`. It rises only when a published file's columns or meaning change (`NFL/CONTRACTS.md` §5). The workbook checks it.
- Both are written to `NFL/04-data/status.csv` on every publish.
- Published data is not versioned by file name. Git history and `run_log.csv` are the audit trail.

## Build chain

- The workbook is generated from source:
  `python3 NFL/05-excel/build/build_workbook.py --version <v>`
- The build reads:
  - the plan from `NFL/01-plan/plan.json`;
  - config tables from `NFL/02-config/*.csv`;
  - Power Query source from `NFL/05-excel/powerquery/*.pq`, in the order set by `manifest.json`;
  - fixtures from `NFL/06-qa/fixtures/`.
- **Source files are the single source of truth. The workbook is a build output.**
- A generated workbook is paste-ready: Power Query cannot be embedded without Excel, so the queries are added in Excel (D-007). Once a version has been saved from Excel it is Excel-authored, and later changes are made by guided steps or by XML edits that preserve its Power Query and Data Model parts (D-014, D-020). The experimental workbook with the queries already installed is made by `NFL/05-excel/experimental/` and is labelled experimental until the owner has opened it in Excel.

## Release procedure

1. **Build a release candidate** into `NFL/.work/rc/`. Never build straight into `NFL/05-excel/` or `NFL/08-releases/`.
2. **Run quality gates G1–G5** (see `CHARTER.md`) on that exact file and on the published data. Q1 gives the independent QA verdict, and every finding gets a disposition in `NFL/06-qa/qa-disposition-<version>.md`.
3. **Promote byte for byte.** Copy the verified candidate into `NFL/05-excel/` and `NFL/08-releases/`, and confirm both SHA-256 values match the one that was verified.
4. **Record the release** in `NFL/08-releases/RELEASES.md`. Mark the previous version Superseded there.
5. **Update `00-Governance/MEMORY.md`**, commit, push and make sure a pull request is open. The workbook reads data from `main`, so a release is usable once the owner has merged it (`CLAUDE.md` §6).
