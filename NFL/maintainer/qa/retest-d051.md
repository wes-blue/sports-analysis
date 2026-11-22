# Re-test of D-051 (one repository, maintainer folder): Q1 QA Reviewer, independent

Branch `agents/pensive-noether-dxfoz6`, head `aac70b7`, compared with `origin/main` (`99336b0`, unchanged after `git fetch`). I did not build or review this work. Every result below was re-derived. Nothing was committed or pushed. Scratch files are in `NFL/.work/rt51/`.

## Verdict

**Ready to merge, as a squash merge, with two notes.** There are no Critical and no Major findings, and every Major and Minor finding from the two earlier reports is fixed or accepted as described. Nothing that runs has changed. Two small new Minor findings need no action before merging. One privacy point needs a choice from the owner (N-3).

- **Use Squash and merge.** Two commits that are still on the public branch (`7ad635a`, `3663202`) contain a numbered folder name of the private workshop (see N-3). The tree at head is clean. Squashing keeps it off `main`. The commits stay reachable by hash on GitHub for as long as the branch or pull request exists.
- **Say in the pull request description** that the merge starts CI and one weekly run (see section 3).

## Findings from the two reports

| ID | Grade | State | Evidence |
|---|---|---|---|
| M1 (review) and m-5 (adversarial): `CONTRACTS.md` §10 to §12 lost | Major / Minor | **Fixed** | `NFL/CONTRACTS.md:211` §9 (Power Query, retired, points to `archive-2.x`), `:215` §10 (plan keys), `:219` §11 (BLOCKERS columns and statuses), `:223` §12 (releases). §10 lists the 11 keys in `plan.json` order, and I confirmed they equal the real keys. §11 lists 10 columns, equal to the real header of `NFL/maintainer/BLOCKERS.csv`. Its `Type` and `Status` values match the data (`Answer needed`/`Action needed`; `Open`/`Answered`/`Still open`). Citations of §10 and §11 in `plan/README.md:3`, `validate_plan.py:4`, `render_plan_md.py:4`, the template files and `plan.json` now resolve. One gap: N-1. |
| M2 (review) and m-3 (adversarial): `.gitattributes` lost `BLOCKERS.csv -text` | Major / Minor | **Fixed** | `.gitattributes:9` `*/maintainer/BLOCKERS.csv -text`. `git check-attr -a NFL/maintainer/BLOCKERS.csv` prints `text: unset`. `git ls-files --eol` prints `i/mixed w/mixed attr/-text`. |
| M3: `MEMORY.md` still carried D-050 | Major | **Fixed** | `MEMORY.md:9` (one repository; D-050 "built and then dropped"), `:51` ("Q-018 (one repository with a maintainer folder; D-051; D-050 was superseded)"), `:58` (internal files kept in the labelled `NFL/maintainer/` folder, D-051), `:34` (step 7 says comment-only change, one weekly run, expect SKIP, no rebuild). The 3.002 bullet no longer says "waiting for the owner to merge". |
| m1: the merge starts the pipeline | Minor | **Addressed** | `MEMORY.md:34` says so. Section 3 below confirms it. The pull request description must say it too. |
| m2: wrong path in `ROLE-CARDS.md:44` | Minor | **Fixed** | `ROLE-CARDS.md:44` reads `<sport>/maintainer/qa/qa-report-<version>.md`. |
| m3: `RELEASES.md:79` claim about `06-qa/README.md` | Minor | **Fixed, with a wording slip** | The line now points to `../qa/README.md`. `qa/README.md:5-7` holds the 1.006 summary: 1 critical, 8 major and 15 minor findings, and N-1 carried into 2.001. The sentence is garbled: see N-2. |
| m4: fixture detail dropped | Minor | **Fixed** | `NFL/maintainer/qa/README.md:9` "Fixtures: what each is for". It has the approval rule (`:11`) and the `long_td_static_2017_2025.csv` reference note (`:21`). |
| m5: template step 10 wording | Minor | **Fixed** | `sport-template/README.md:45` says to add the sport to the root README's "What's in this repository" folder table and the workbook section. |
| m6 and m-2: workflow-text guard removed | Minor | **Fixed in substance** | `test_workflows.py:158` is new. It asserts that no workflow text contains `/home/`, `/Users/` or a drive path. There is no name-based check, which is intended, because such a check would have to name private folders. Tests pass. |
| m7: no `.claude/` row in the root README | Minor | **Fixed** | `README.md:46`. |
| m8: `NFL/02-config/README.md` write-access sentence | Minor | **Fixed** | `NFL/02-config/README.md:12` "Only people with write access can save changes on `main`; anyone else can open a pull request with the change." |
| m9: unqualified `BLOCKERS.csv` in maintainer files | Minor | **Not changed, cosmetic** | `MEMORY.md:91` and others still say `BLOCKERS.csv`. They sit inside `NFL/maintainer/`, so they resolve. No action. |
| m-1: private folder name in `validate_plan.py` `FORBIDDEN` | Minor | **Fixed at head** | `validate_plan.py:214` now has the generic `r"\b[1-9]0-[A-Z][A-Za-z]+"`. `git grep` of the literal name finds nothing at head. It remains in two earlier commits: N-3. |
| m-4: stale paths in archive scripts; two protected files | Minor | **Accepted, exactly as described** | `archive-2.x/README.md:28`: "The scripts in `build/` and `experimental/` still use the old folder paths ... kept as a record and are not run." The scripts still carry the old paths, for example `experimental/build_queries_installed.py:9`, `:64`, `:81`, `:144` and `:876`. `NFL/02-config/scoring_weights.csv` line 80 still says "BLOCKERS.csv Q-019". `NFL/06-qa/evidence/espn-game-log-ARI-DST-2026.txt:2` still says "pasted by the owner into BLOCKERS.csv". The diff of both against `origin/main` is empty. |
| Accepted: historical `DECISIONS.md` rows untouched | n/a | **Confirmed** | The diff of `DECISIONS.md` (as a rename from `00-Governance/`) has only three changes: a note about old paths, a reworded header sentence, and the new rows D-050 and D-051. No row from D-001 to D-049 differs. |

## New findings

| ID | Grade | Finding | Fix |
|---|---|---|---|
| N-1 | Minor | `NFL/CONTRACTS.md:215` (§10) says `architecture[].where` "may be `Python pipeline`, `GitHub Actions` or `Published CSV`". `plan.json` uses six values, and `validate_plan.py:61-62` allows eight. The extra ones are `Excel sheet`, `PivotTable`, `nflverse (GitHub Releases)`, `Power Query` and `Data Model`. The old §10 said "may also be", which covered them. As written, a reader of the contract would think the real `plan.json` is invalid. | In §10 write "may also be", or list all eight values. The edit is documentation only. |
| N-2 | Minor | `NFL/maintainer/releases/RELEASES.md:79` reads "are kept in that earlier repository; are summarized in [`../qa/README.md`]". The sentence is garbled, and half of it contradicts the other half. | Reword to "A summary of the 1.006 QA records is in [`../qa/README.md`](../qa/README.md)." |
| N-3 | Minor, privacy | Commits `7ad635a` and `3663202` are on the pushed branch. `git log -S` finds the literal 40-numbered workshop folder name in `validate_plan.py` in both. It appears in no other commit and not at head or on `origin/main`. It is a folder name only: no repository name, path or content. The earlier commit `73350d4` and its message say "private workshop" in general terms. | Squash and merge, then delete the branch. If the owner wants the name gone from history, the branch needs a history rewrite; that is the owner's decision. Nothing else is needed. |

## 2. Nothing breaks

- **Tests.** From `NFL/03-pipeline/`: 686 passed on Python 3.13.18 (`../.work/venv`) and 686 passed on Python 3.11.18 (`../.work/venv311`).
- **`python -m nflpipe check`:** `PASS: 10 checks on 04-data`.
- **Export.** The output file's SHA-256 is `eb33017ce791d4ba11216bd348175b5453720d7b3cbd29799a7b029f2cadd9ed`. This is the required value.
- **`actionlint`** on the four workflows (`NFL/.work/c1/actionlint-dl/actionlint`): no output, exit 0.
- **Protected paths.** `git diff origin/main --stat -- NFL/04-data .github NFL/02-config/*.csv NFL/06-qa/fixtures NFL/06-qa/evidence` is empty.
- **Changes under `NFL/03-pipeline/nflpipe/`:** `derive.py` and `scoring.py` only. I compared the ASTs with module, class and function docstrings removed, and they are **equal** for both files. Comments do not appear in an AST. The full ASTs differ only by the docstrings. `__init__.py` is unchanged, so `pipeline_version` is still 1.2.1. `export_xlsx.py` is unchanged, so `WORKBOOK_VERSION` is still "3.002". The only other code change is the test assertion in `test_workflows.py` and the `.gitattributes` line.

## 3. What the merge starts

From the `on:` blocks, read directly:

- **`nfl-pipeline-weekly`** starts on push to `main`. Its path filter is `NFL/02-config/**` (but not `*.md`), `NFL/03-pipeline/nflpipe/**` and the weekly workflow file. `derive.py` and `scoring.py` match.
- **`nfl-pipeline-ci`** starts on push to `main`. Its paths are `NFL/03-pipeline/**`, `NFL/02-config/**`, `NFL/06-qa/fixtures/**` and the workflow files. The code, test and `02-config/README.md` changes match.
- **Monthly and watchdog** are schedule and manual only: not started.
- Changes under `NFL/maintainer/`, `.claude/`, `README.md` and `DATA-LICENSE.md` match no filter.

**Expected weekly run, if nflverse has nothing new since the last publish.**

1. Resolve: push event, decision `run`.
2. Pipeline result: **SKIP** (exit 3). No new data, and the config hash and code do not appear in any published file.
3. Commit step: **skipped**, because it runs only after PUBLISH. `NFL/04-data` is untouched.
4. Workbook check ("Decide whether to build the workbook", which runs after SKIP): the key is `run_id|pipeline_version|WORKBOOK_VERSION`. Local `NFL/04-data/status.csv` gives `20261120T233201Z-gh44837469898|1.2.1`, and `WORKBOOK_VERSION` is `3.002`. The live release body, read with `gh api repos/wes-blue/sports-analysis/releases/tags/nfl-workbook`, contains `<!-- nfl-workbook-key: 20261120T233201Z-gh44837469898|1.2.1|3.002 -->`. They are equal, so the result is **`build=false`** with "the workbook on the release already holds the published data".
5. Build and publish the workbook: **skipped**. The workbook is not rebuilt and the download link is not touched.
6. Alert issue step: green outcome. "Fail the run" step: skipped.

Caveat: the run re-reads nflverse. If new data has appeared, the result is PUBLISH, the data is committed and the workbook rebuilds. That is normal weekly behaviour, not a result of this change. I could not run the download.

## 4. Nothing lost

- **Old paths.** `git diff origin/main --name-status -M30%` shows 65 pure renames (R100), 18 renames with edits, 13 modified, 10 added and 5 deleted. The five deletions each have a counterpart:
  - `CLAUDE.md` is now `.claude/CLAUDE.md`.
  - `NFL/01-plan/README.md` is now `NFL/maintainer/plan/README.md`.
  - `NFL/07-research/README.md` is now `NFL/maintainer/research/README.md`.
  - `_Sport-Template/06-qa/README.md` is now `NFL/maintainer/sport-template/06-qa/README.md`.
  - `_Sport-Template/PLAN.md` is now `NFL/maintainer/sport-template/maintainer/plan/PLAN.md`.
  
  The old-to-new table is in `NFL/maintainer/README.md`.
- **`NFL/maintainer/BLOCKERS.csv`.**
  - Parsed with `csv`: header plus 25 rows.
  - Raw bytes: 26 CRLF, 724 LF that are not part of a CRLF (750 LF in all), and the BOM is kept. These are the same counts as on `origin/main`.
  - A cell-by-cell comparison with `origin/main:BLOCKERS.csv` finds only three differing cells, all in Q-018: `Answer` (empty before, now filled), `Status` and `Claude_Response`. No other `Answer` cell differs. Q-018's `Answer` was empty on `main`, so no owner-written answer was altered.
  - `git diff -M --stat` shows one rename with one line changed.
  - Attributes: see M2 above.
- **`CONTRACTS.md` §10 to §12:** present and consistent with the real files (see M1 and N-1).

## 5. Maintainer tools

- `python3 NFL/maintainer/plan/validate_plan.py` prints `PASS: 0 errors` from the repository root and from `/tmp`.
- `render_plan_md.py`, run in a temporary copy at `NFL/.work/rt51/cp/NFL/maintainer/` with `PLAN.md` deleted first, reproduces `NFL/maintainer/plan/PLAN.md` byte for byte (`cmp` clean).

## 6. Privacy

I searched the tree at head and every commit reachable from the head (30 commits, including `origin/main` history).

- **Email addresses.** Author and committer fields: the owner's GitHub `noreply` address, the Actions bot `noreply` address, and `noreply@anthropic.com` and `noreply@github.com`. No other address appears in any commit message, author field or added diff line. Tree matches: only `t@example.invalid` in `test_workflows.py` (a test fixture). **Judgement: clean.**
- **Machine paths.** No person's home folder, `/Users/` or Windows user path. The hits are code and regexes that look for such paths (`test_workflows.py:158`, `test_http_environment.py:23`, `archive-2.x/build/pii_scan.py`, `validate_plan.py:215`). Another hit is `C:\GitHub\sports-analysis` in `BLOCKERS.csv` Q-010. It is an illustrative default on `main` already, with no person's name. Mentions of OneDrive are about the same question. **Judgement: no personal paths.**
- **Tokens.** None. The only match is a QA report that describes scanning for token patterns.
- **The word `workspace`.** Only `github.workspace` in workflows and the English word in two test comments. It is not used as a repository name in any commit. **Judgement: clean.**
- **Other repository names.** `wes-blue/sports-analysis` and one former public data repository name inside Q-001 in `BLOCKERS.csv`. That text is on `main` already and is unchanged. It is not the private repository.
- **Numbered folders (`\b[1-9]0-[A-Z][A-Za-z]+`).**
  - At head: 9 matches. They are `10-Assets`, `20-Projects`, `30-Deliverables` and `90-Archive` in `DECISIONS.md` rows D-001, D-015 and D-023. These were on `origin/main`, which has 18 matches, and are not new. **Judgement: historical, accepted.**
  - New compared with `origin/main`: none at head. In history, the 40-numbered name is in commits `7ad635a` and `3663202` (N-3).
- **"private workshop" wording.** `73350d4`, D-050 and D-051, Q-018 and `.claude/CLAUDE.md:22` say "private repository" or "workshop" in general terms. No repository name and no folder. **Judgement: acceptable.**
- **Workbooks.** The four `.xlsx` files are R100 renames or unchanged from `main`. The 3.002 file was exported again here with the same hash, and its properties name the pipeline only.

## 7. Visitor and maintainer views

- **Links.** `NFL/.work/rt51/links.py` checked 107 relative links, plus the absolute `github.com/wes-blue/sports-analysis/blob/main` links, and their `#anchors`, in 52 tracked `.md` files, skipping code. **0 broken.** Backticked `NFL/...` paths in living documents that do not exist are only the old-to-new table in `NFL/maintainer/README.md` and two git-ignored `NFL/.work/` paths in `VERSIONING.md`.
- **Front page (`README.md`).**
  - Line 3 says what it is.
  - Line 7 gives the download link, with size and version.
  - Lines 11 to 17 list the sheets: About, PlayerGames, SeasonTotals, Leagues, Scoring, Bonus, Checks, Dictionary. `NFL/CONTRACTS.md` §13.2 lists the same eight.
  - The table "What's in this repository" has an "Ignore it?" column. The `NFL/maintainer/` row is on line 44 ("You can ignore it", Yes), and `.claude/` is on line 46.
- **Visitor pages.** There are no decision numbers, question IDs, "orchestrator", "committee", "BLOCKERS" or "workshop" in `README.md`, `NFL/README.md`, `05-excel`, `04-data`, `02-config`, `03-pipeline/README.md`, `06-qa` or `DATA-LICENSE.md`. They name `NFL/maintainer/` only in plain text. No link points into it.
- **A fresh session.** `.claude/CLAUDE.md` §4 sends it to `NFL/maintainer/governance/MEMORY.md`, `NFL/maintainer/BLOCKERS.csv`, `governance/VERSIONING.md` and `releases/RELEASES.md`. §5 lists `plan/`. All of those exist, and `NFL/maintainer/README.md` links to the same files. `.claude/CLAUDE.md` has no two-repository wording.

## Exactly what I ran

All from `/home/user/sports-analysis`, unless a directory is shown.

1. Read `.claude/CLAUDE.md`, the Q1 role card, and both reports in full.
2. `git fetch -q origin`, `git rev-parse HEAD origin/main`, `git status`.
3. Line checks with `grep -n` of every finding's location. `git check-attr -a`, `git ls-files --eol`, `git diff origin/main` of `.gitattributes` and `test_workflows.py`, and `git diff -M` of `DECISIONS.md` and `BLOCKERS.csv`.
4. A Python script (stdlib `csv`) to compare the `plan.json` keys and `BLOCKERS.csv` header, `Type` and `Status` values with `CONTRACTS.md` §10 and §11. A second script to compare `BLOCKERS.csv` with `origin/main:BLOCKERS.csv` by bytes (CRLF, LF, BOM) and cell by cell.
5. A Python script that strips docstrings and compares `ast.dump` of `origin/main` with head for `derive.py` and `scoring.py`.
6. From `NFL/03-pipeline`: `../.work/venv/bin/python -m pytest -q` and `../.work/venv311/bin/python -m pytest -q`; `../.work/venv/bin/python -m nflpipe check`; `... -m nflpipe export --out ../.work/rt51/x.xlsx` and `sha256sum`.
7. `NFL/.work/c1/actionlint-dl/actionlint .github/workflows/*.yml`.
8. `git diff origin/main --stat` for the protected paths, and `--name-status -M30%` for the mapping of old paths.
9. The `on:` blocks and the resolve, run, outcome, commit and workbook steps of the four workflows, and `grep` of `status.csv`, `__init__.py` and `export_xlsx.py`. A read-only `gh api repos/wes-blue/sports-analysis/releases/tags/nfl-workbook`.
10. `python3 NFL/maintainer/plan/validate_plan.py` from the repository root and from `/tmp`. `render_plan_md.py` in `NFL/.work/rt51/cp/`, then `cmp`.
11. Privacy: `git log` of author and committer fields, and of messages; `git grep` over `HEAD` and over every commit in `origin/main..HEAD` for emails, home and Windows paths, token patterns, the word `workspace`, `wes-blue/<name>`, `[1-9]0-[A-Z]...` and `Workshop`; `git log -S` for the literal folder name on `HEAD` and `origin/main`; the diff of added lines of each new commit.
12. `NFL/.work/rt51/links.py`: relative and absolute links and anchors in all tracked `.md` files. A `grep` of visitor pages for internal terms. A check that backticked `NFL/...` paths exist.

I changed only files under `NFL/.work/rt51/` (git-ignored) and this report.
