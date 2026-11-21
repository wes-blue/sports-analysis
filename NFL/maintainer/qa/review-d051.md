# Review of D-051 (one repository, maintainer folder): Q1 QA Reviewer

Reviewed: branch `agents/pensive-noether-dxfoz6`, head `7ad635a`, against `origin/main`. Nothing was committed or pushed. Scratch files are in `NFL/.work/r51/` (git-ignored).

## Verdict

**Approve after three Major fixes.** There are no Critical findings. Nothing that runs has changed in substance, the visitor pages work, no `Answer` cell was altered, and links, plan validation and plan rendering are all clean. The Major findings are one lost contract, one lost line-ending guard and one stale memory statement. Each is a small edit.

## Major findings

### M1. `NFL/CONTRACTS.md` §§9 to 12 were deleted, but maintainer files still cite §10 and §11

- **Where the text went:** `NFL/CONTRACTS.md:211` now says "9 to 12. Retired sections", and the sections' content is gone. The old §10 gave the shape of `plan.json`. The old §11 gave the `BLOCKERS.csv` columns, the `Type` values, the `Status` values (`Open`, `Answered`, `Still open`) and the rule that the owner's `Answer` is never changed. The old §12 described the release register. §9 held the Power Query contract.
- **Where it is still cited:**
  - `NFL/maintainer/plan/README.md:3` links to "§10".
  - `NFL/maintainer/plan/validate_plan.py:4` and `NFL/maintainer/plan/render_plan_md.py:4` cite §10.
  - `NFL/maintainer/sport-template/README.md:21` and `NFL/maintainer/sport-template/maintainer/plan/README.md:5` cite §10.
  - `NFL/maintainer/plan/plan.json` cites §9, §10 and §11 as sources at lines 83, 659, 789, 809, 909, 1069, 1089, 1605, 1901 and 1904.
- **Substance lost:** the `plan.json` shape and the `BLOCKERS.csv` column and `Status` rules now exist nowhere in the working tree. `validate_plan.py` uses `OPEN_STATUSES = {"Open", "Still open"}`, and `.claude/CLAUDE.md` mentions only the CRLF rule.
- **Suggested fix:**
  1. Add to `NFL/maintainer/plan/README.md` a section "Shape of `plan.json`", with the old §10 text verbatim.
  2. Add to `NFL/maintainer/README.md`, under the `BLOCKERS.csv` row, a "BLOCKERS.csv format" paragraph with the old §11 text verbatim.
  3. Add a sentence on the release register to `NFL/maintainer/releases/RELEASES.md`.
  4. Change the "§10" and "§11" citations listed above to point at those new places. In `plan.json` edit the source strings, then re-run `render_plan_md.py` and `validate_plan.py`.
  5. Optionally keep the old §9 text in `NFL/maintainer/archive-2.x/powerquery/README.md`. It is partly there already: the firewall rule is at line 69.

### M2. `.gitattributes` lost the `BLOCKERS.csv -text` line, and no pattern covers the new path

- **Evidence:** `.gitattributes` on `origin/main` line 8 read `BLOCKERS.csv -text`. It is gone, and `git check-attr -a NFL/maintainer/BLOCKERS.csv` shows no attribute. The file has CRLF record ends with LF inside quoted fields (`git ls-files --eol` reports `i/mixed`).
- **Risk:** `.claude/CLAUDE.md` §2 requires the CRLF to be kept. On a Windows checkout with `core.autocrlf=true`, git can rewrite the embedded LFs, and then every later commit shows spurious changes to the owner's answers.
- **Suggested fix:** add to `.gitattributes` the line `NFL/maintainer/BLOCKERS.csv -text`. The `.gitattributes` header comment ("The leading */ ...") may stay as it is.

### M3. `NFL/maintainer/governance/MEMORY.md` still carries D-050 ideas, which D-051 reverses

- **Line 51:** "Q-018 (public/private split; D-050)". Change it to "Q-018 (one repository with a maintainer folder; D-051; D-050 was superseded)".
- **Line 58:** "Wants the public repository to serve visitors, with the internal files visible only to the owner (Q-018, D-050)". This contradicts D-051, where the files are visible in `NFL/maintainer/`. Replace it with "Wants the public repository to serve visitors, with the internal files kept in the clearly labelled `NFL/maintainer/` folder (Q-018, D-051)."
- **Line 34 (step 7):** "nothing that runs was changed" is not quite right. See m1 below. Reword it to "no code changed except two docstrings and comments, so merging starts one routine weekly run".
- **Lines 10 to 16 (stale, but already stale on `origin/main`):** the 3.002 bullet still ends "Waiting for the owner to merge the pull request ...". 3.002 is released (D-049). Delete that clause and the "After the merge: ..." sentence.

## Minor findings

- **m1. The merge will start the pipeline.** `NFL/03-pipeline/nflpipe/derive.py` and `scoring.py` changed. I confirmed with an AST comparison that only docstrings and comments differ, so behaviour is identical. But `weekly.yml` triggers on `NFL/03-pipeline/nflpipe/**`, so merging to `main` starts one weekly run and workbook rebuild, which is probably a SKIP. D-051 says "nothing that runs is affected". Say so in the pull request description.
- **m2. Wrong path in `ROLE-CARDS.md:44`.** `<sport>/NFL/maintainer/qa/qa-report-<version>.md` should be `<sport>/maintainer/qa/qa-report-<version>.md`.
- **m3. `releases/RELEASES.md:79` makes a claim that is no longer true.** It says "`NFL/06-qa/README.md` summarizes them" (the 1.006 QA records), but the rewritten `NFL/06-qa/README.md` no longer has that summary. Fix it in one of two ways:
  - Restore the old note into `NFL/maintainer/qa/README.md`: version 1.006 had 1 critical, 8 major and 15 minor findings, all fixed or dispositioned, and N-1 was carried into 2.001. Then point line 79 at that file.
  - Or reword line 79 to "are kept in that earlier repository".
- **m4. Detail dropped from `NFL/06-qa/README.md`** (old lines 5 to 34):
  - the per-fixture "purpose / used by" table;
  - the fixture row-count date (verified 2026-11-14);
  - the note that `long_td_static_2017_2025.csv` is a reference table used by no gate;
  - the rule that fixtures change only with the orchestrator's approval.

  Nothing is garbled, but a maintainer now has to read `NFL/CONTRACTS.md` §5.5 and §6 for it. Suggest moving the old table into `NFL/maintainer/qa/README.md`, as "Fixtures: what each is for".
- **m5. Template step 10** (`sport-template/README.md`) says to add a row to the root README's "Sports table", which no longer exists. The root README has "What's in this repository". Reword the step: "add the sport to the root README's folder table and to its workbook section".
- **m6. `test_workflows.py:170`:** the assertion that no workflow text contains `Personal/` or `20-Projects` was removed. This is intended, because it names a private path. It does weaken the guard slightly. `validate_plan.py` FORBIDDEN still covers `plan.json`. No action is needed unless you want an equivalent pattern guard for `.github/workflows/`.
- **m7. Root `README.md` table (lines 36 to 47)** lacks a `.claude/` row. A visitor who sees the dot-folder in the file list has no explanation. Add: "`.claude/` | Instructions for Claude sessions | Yes".
- **m8. `NFL/02-config/README.md` is addressed to someone who can commit to `main`.** An ordinary visitor cannot. Add one sentence after line 11: "Only people with write access can save changes on `main`; anyone else can open a pull request with the change."
- **m9. Unqualified `BLOCKERS.csv` in a few maintainer files** (`MEMORY.md:5`, `CHARTER.md:19`, `CHARTER.md:28`, `CHARTER.md:57`, `MEMORY.md:38`). The reader is already inside `NFL/maintainer/`, so these resolve. The path would be clearer written in full, once per file.

## 1. Visitor journey (all five pages walked)

- **Root README.** Within the first lines it says what the project is, gives the workbook download link and the version, and says what the workbook holds.
- **Reaching `NFL/maintainer/` as a visitor.** The root README and `NFL/README.md` both have a row saying "How the project is run (plans, decisions, reviews). You can ignore it." The root README's table also has an "Ignore it?" column. A visitor can tell in 30 seconds what this is, how to get the workbook and which folders to skip.
- **Jargon scan.** I searched the visitor pages (the root README, `NFL/README.md`, `05-excel`, `04-data`, `02-config`, `03-pipeline`, `CONTRACTS.md`, `06-qa` and `DATA-LICENSE.md`) for decision numbers (D-0xx), question IDs (Q-0xx), "orchestrator", "Claude", "BLOCKERS", "committee", "owner", "private" and "workshop". There were no hits.
- **Maintainer wording.** "Maintainer" appears only in `AUTOMATION.md` and `CONTRACTS.md`, which `.claude/CLAUDE.md` allows.
- **Dependence on maintainer files.** The visitor pages do not link to or depend on anything in `NFL/maintainer/`. They mention it only in plain text.
- **Excel claims.** The claim that 3.002 "opens in desktop Excel, no repair message" is backed by Q-025, which is answered in `BLOCKERS.csv`.
- **Remaining small points:** m7 and m8.

## 2. Nothing lost

199 files on `origin/main` were mapped through the table in `NFL/maintainer/README.md`.

- **Byte-identical:** 157, including:
  - all 59 files under `archive-2.x/` except two READMEs;
  - the QA reports, dispositions and reviews (all 15);
  - the four config CSVs;
  - the four workflows;
  - `LICENSE`;
  - the `NFL/06-qa/` fixtures and evidence;
  - both 2.001 workbooks;
  - `NFL/04-data/` and the pipeline code except the files below;
  - `NFL/05-excel/archive-2.x/powerquery/*`.
- **Present at a new path:** every file except four. Those four are `_Sport-Template/01-plan/README.md`, `07-research/README.md`, `08-releases/README.md` and `PLAN.md`. They map to `sport-template/maintainer/{plan,research,releases}/README.md` and `sport-template/maintainer/plan/PLAN.md`, so they have counterparts. The restructure is as intended.
- **Differing files, all read.** Intended changes only (path updates, one-repository wording, D-050 superseded, D-051, Q-018, memory), except:
  - `NFL/CONTRACTS.md`: §§9 to 12 removed (M1), the module-ownership list recast by function, "it was 100% in 1.x" dropped from G-RECON. Only M1 is substantive.
  - `NFL/06-qa/README.md`: m4.
  - `NFL/05-excel/README.md`: the archive row replaced by a version-history table. No loss.
  - `NFL/03-pipeline/AUTOMATION.md` and `README.md`: owner wording made neutral. The first-time setup is intact.
  - `derive.py` and `scoring.py`: comments only (m1).
  - `test_workflows.py`: m6.
  - `DATA-LICENSE.md`: the Power Query mention removed, which is consistent.
  - `.gitattributes`: M2.
  - `plan.json`: private-repository wording and path updates only. `PLAN.md` was re-rendered.
  - `validate_plan.py` and `render_plan_md.py`: path logic correctly changed, and the FORBIDDEN list extended.
- **`BLOCKERS.csv`:**
  - A CSV parse shows 26 records (header plus 25 rows). The raw bytes keep 26 CRLF and 750 LF, the same counts as `origin/main`, and the BOM is kept.
  - Only the Q-018 row differs, in three cells: `Answer`, `Status` (Open to Answered) and `Claude_Response`.
  - Every other cell of every row is identical, including every answer the owner wrote.
  - Q-018 `Answer` holds the first instruction (keep the repository public, designed for visitors) and the later one (one repository, with a maintainer folder inside NFL). On `origin/main` the cell was empty; the text was added on this branch.

## 3. Links

`NFL/.work/r51/links.py` checked 114 relative and absolute links, with anchors, in the 50 tracked `.md` files, skipping code spans and blocks. All resolve. The four absolute `github.com/wes-blue/sports-analysis/blob/main/NFL/03-pipeline/AUTOMATION.md` links (three workflow files and `export_xlsx.py`) name a file that exists. Beyond M1's dangling section numbers, no link, anchor or old path is broken in a living document.

## 4. Maintainer usability

- **`python3 NFL/maintainer/plan/validate_plan.py` passes** ("PASS: 0 errors"; 25 of 25 Q-IDs found, 49 decisions cited).
- **The plan renders identically.** `render_plan_md.py` run in a temporary copy at `NFL/.work/r51/cp/` reproduced `NFL/maintainer/plan/PLAN.md` byte for byte (`cmp` clean). `git status` is clean.
- **Reading as a fresh session.** `.claude/CLAUDE.md` §4 and §5 and `NFL/maintainer/README.md` point correctly to `MEMORY.md`, `BLOCKERS.csv`, `DECISIONS.md`, `releases/RELEASES.md` and `plan/`. Findings:
  - The memory file's stale D-050 text and step 7 are M3.
  - The `plan/README.md` and template §10 pointers are M1.
  - `.claude/CLAUDE.md` and `NFL/maintainer/README.md` have no contradiction about two repositories. The only repository-name reference is the generic privacy rule at `.claude/CLAUDE.md:22`.
  - No file in a living document still sits at an old path. The remaining old paths are in dated records (decisions, QA reports, release notes), which the "Older paths" table covers.
- **Workflow triggers.** Only the `nflpipe/**` merge effect is relevant (m1). The claim "Changes inside `NFL/maintainer/` start nothing" is correct: the CI path filters cover only `03-pipeline`, `02-config`, `06-qa/fixtures` and the workflows.

## What I ran

- `git ls-tree` of `origin/main`, then a mapping and byte-comparison script (`NFL/.work/r51/map.py`).
- `git show` and `diff` of every differing file.
- A CSV-level comparison of `BLOCKERS.csv` (`origin/main` and `HEAD~1`).
- An AST comparison of `derive.py` and `scoring.py`.
- The link and anchor checker `links.py`.
- A grep of the visitor pages for jargon, and of the living documents for old paths and private-repository wording.
- `validate_plan.py` and `render_plan_md.py`, the latter in a temporary copy.

I did not run the pytest suite, because pytest is not installed in this environment. The code differences are comment-only, as shown by the AST comparison.
