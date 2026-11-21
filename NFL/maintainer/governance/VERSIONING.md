# Versioning Policy

This policy applies to every sport in `wes-blue/sports-analysis`. Paths are relative to the repository root. `<Sport>` is a sport's top-level folder (today only `NFL`).

## Workbook names

- Each sport's workbook has its own name: `<Workbook>-<MAJOR>.<MINOR>`, where the minor part always has 3 digits. The NFL workbook is **`NFL-Analysis`**, for example `NFL-Analysis-2.001`.
- Each increment of scope adds 0.001: 2.001, 2.002, … 2.999.
- A new major number starts at `.001` (2.001, not 2.000).
- A number is never reused, including the number of a version that was withdrawn or never started.

## What the major number means (decision D-035)

**The major number names the design generation**, so a reader can tell from the first digit which system produced a file and where its source lives.

| NFL major | Generation | Where it lives |
|---|---|---|
| 1.x | Everything computed inside Excel (1.001–1.004), plus the transitional 1.006 (fed by the pipeline, reading a local data folder). 1.005 was withdrawn and never released. | Released and kept in the owner's earlier repository (not public). The 1.x line is closed: no further 1.x version is made. |
| 2.x | The workbook fed by the pipeline in the public repository, reading the published data from its web address with Power Query. The only release is **NFL-Analysis-2.001**. **Retired** by D-041 and D-043: not maintained, no further 2.x workbook is made. | `NFL/maintainer/releases/` (the released file) and `NFL/maintainer/archive-2.x/` (the Power Query sources, generators and copies) |
| 3.x | The workbook **built by the pipeline on GitHub**: a finished, values-only file with no Power Query, formulas, connections or macros, rebuilt after every data publish (D-041, `NFL/CONTRACTS.md` section 13). The first version is **3.001**. | A GitHub Release asset at a stable address, not in git (D-042); `NFL/05-excel/README.md` says where; `NFL/maintainer/releases/RELEASES.md` records each version |

A new major number marks a new design generation: a change after which an existing copy of the workbook no longer works as before, such as a new place to read its data from. It needs the owner's approval, or a decision the owner has delegated, as for 2.x (D-035). Every major in use is listed here and in the sport's release register.

## Generation 3.x: the workbook built on GitHub (decisions D-041, D-042, D-043)

- **What it is.** `python -m nflpipe export` writes `NFL-Analysis.xlsx` from the published files in `NFL/04-data/`, and the workflows upload it after a publish (`NFL/CONTRACTS.md` sections 13.1 and 13.5). Scoring is changed by editing `NFL/02-config/` on GitHub, which reruns the pipeline; the workbook is never edited or refreshed by hand.
- **Two things are versioned separately.**
  - The **workbook design version** (`3.001`, then `3.002`, and so on) names how the workbook is built: its sheets, columns and rules. It changes only when that design changes. It is a constant in the exporter and is shown on the `About` sheet and in the file properties (Title `NFL-Analysis 3.001`). It is not in the file name.
  - The **data** inside the workbook changes on every publish. It is identified by the `run_id` and the "data through" season and week of the `status.csv` it was built from, shown on `About`, and by the pipeline and data contract versions below. A rebuild with new data is not a new workbook version.
- **Where the file lives.** It is not committed to git. It is a release asset (tag `nfl-workbook`, asset `NFL-Analysis.xlsx`) replaced on every publish, at the stable address in `NFL/05-excel/README.md` (D-042).
- **What the register records.** `NFL/maintainer/releases/RELEASES.md` has one row per released roadmap version, written when it is released: version, date, status, scope, gates passed, the design version shown in the file, the data version (run id, data through) of the file as first published for it, that file's SHA-256 (later rebuilds replace the file and have other hashes), and the release address. Rule 5 below (Draft, Released, Superseded) applies to these rows.
- **Not every increment changes the design.** A roadmap increment that only proves the automation or settles scoring rules (for example 3.003 and 3.004 in the plan) delivers pipeline and data changes: the design version in the file stays as it was, and the register row says so. The design version is raised only by an increment that changes the workbook's sheets, columns or rules.
- **Immutability.** Rule 2 applies to the files in `NFL/maintainer/releases/`. The file at the stable address is rebuilt on purpose and is not immutable; the register row is the permanent record of what a design version was.
- **A new major number** is needed again only if the workbook stops being built this way (for example, a different place to get it from), by the same approval as for 2.x.

## A second sport

- Its folder is the sport's usual short name at the top of the repository (for example `NBA/`), copied from `NFL/maintainer/sport-template/`.
- Its workbook has its own name, `<SPORT>-Analysis` (for example `NBA-Analysis`), and its own version line, starting at **1.001**. Its major numbers name that workbook's own design generations and are listed in the table above when they are first used.
- It has its own release register, `<Sport>/maintainer/releases/RELEASES.md`, and its own pipeline and data-contract versions (below).
- The NFL version numbers say nothing about another sport's, and the other way round.

## Where files live

| File | Location |
|---|---|
| The workbook the owner opens (3.x) | GitHub Release asset `NFL-Analysis.xlsx`, tag `nfl-workbook` (not in git, D-042) |
| Immutable release copy of 2.001 | `NFL/maintainer/releases/NFL-Analysis-2.001.xlsx` |
| Working copy and experimental copy of 2.001 (retired) | `NFL/maintainer/archive-2.x/` |
| Release register | `NFL/maintainer/releases/RELEASES.md` |
| 1.001–1.006 | The owner's earlier repository (not public). `NFL/maintainer/releases/RELEASES.md` lists them for the record. |

For another sport, replace `NFL` and `NFL-Analysis` with its folder and workbook name.

## Rules

1. One version is one increment of scope. (For 2.x it was one file. For 3.x the workbook is rebuilt with new data on every publish, and the design version shown in the file is raised only by an increment that changes the design.) The increments are listed in the sport's plan (`<Sport>/maintainer/plan/plan.json`, roadmap), which the workbook's Plan sheet shows.
2. Released files are immutable. A fix ships as the next version. Never overwrite a released file; the build script refuses to unless `--force` is passed.
3. The version string must match in these places. For 2.x there were five:
   - the filename;
   - the Cover sheet (named cell `WorkbookVersion`);
   - file properties (Title and Version);
   - the `Version_Log` sheet;
   - `<Sport>/maintainer/releases/RELEASES.md`.
   For 3.x there are four: the constant in the exporter, the `About` sheet, the file properties (Title) and `<Sport>/maintainer/releases/RELEASES.md`.
4. Every version gets a row in `RELEASES.md` with: version, date, status, scope, gates passed and SHA-256.
5. Status moves Draft → Released → Superseded. A version becomes Superseded when the next one is released, and that status is recorded in `RELEASES.md`. The released file itself is never edited.
6. Before a workbook is committed, its file properties and contents are checked for the owner's name (`.claude/CLAUDE.md` §2). The repository is public, so check before a workbook is committed.

## Pipeline and data versions

These are separate from the workbook's version number, and each sport's pipeline has its own.

- `pipeline_version` (in `NFL/03-pipeline/nflpipe/__init__.py`) follows `MAJOR.MINOR.PATCH`. It starts at `1.0.0`. A change to scoring arithmetic or to a derived-metric rule raises MINOR; a breaking change raises MAJOR.
- `data_contract_version` is a whole number, starting at `1`. It rises only when a published file's columns or meaning change (`NFL/CONTRACTS.md` §5). The workbook checks it.
- Both are written to `NFL/04-data/status.csv` on every publish.
- Published data is not versioned by file name. Git history and `run_log.csv` are the audit trail.

## Build chain

- **3.x.** The workbook is built by `python -m nflpipe export` (run from `NFL/03-pipeline/`). It reads only the published files in `NFL/04-data/`, uses only the Python standard library, and gives the same bytes for the same data (`NFL/CONTRACTS.md` section 13.1). **The published data and the code are the single source of truth. The workbook is a build output.**
- **2.x (retired).** The workbook was generated by `python3 NFL/maintainer/archive-2.x/build/build_workbook.py --version <v>` from the plan, the config tables, the Power Query source in `NFL/maintainer/archive-2.x/powerquery/` and the fixtures. It was paste-ready: the queries were added in Excel (D-007), and the experimental copy with the queries installed was made by `NFL/maintainer/archive-2.x/experimental/`. These scripts are archived and not maintained (D-043).

## Release procedure

### 3.x

1. **Build a release candidate** with the exporter into `NFL/.work/workbook/` (its default output). Never build straight into the repository.
2. **Run quality gates G1-G5** (see `CHARTER.md`) on that exact file and on the published data it was built from. Q1 gives the independent QA verdict, and every finding gets a disposition in `NFL/maintainer/qa/qa-disposition-<version>.md`. Opening the file in Excel is part of G3: anything not yet opened in Excel is labelled so.
3. **The workflows publish the file** as the release asset (`NFL/CONTRACTS.md` section 13.5). Confirm that the asset downloaded from the stable address has the SHA-256 that was verified, and that its `About` sheet matches `NFL/04-data/status.csv`.
4. **Record the release** in `NFL/maintainer/releases/RELEASES.md` (see "What the register records" above). Mark the previous design version Superseded there (the 2.x line is Superseded by 3.001).
5. **Update `NFL/maintainer/governance/MEMORY.md`**, commit, push and make sure a pull request is open. The workflows run from `main`, so the workbook is usable once the owner has merged it (`.claude/CLAUDE.md` section 6).

### 2.x (retired)

1. **Build a release candidate** into `NFL/.work/rc/`. Never build straight into `NFL/05-excel/` or `NFL/maintainer/releases/`.
2. **Run quality gates G1-G5** on that exact file and on the published data, with Q1's verdict and dispositions as above.
3. **Promote byte for byte.** Copy the verified candidate into `NFL/maintainer/releases/` and confirm the SHA-256 matches the one that was verified.
4. **Record the release** in `NFL/maintainer/releases/RELEASES.md` and mark the previous version Superseded.
5. **Update `NFL/maintainer/governance/MEMORY.md`**, commit, push and make sure a pull request is open.
