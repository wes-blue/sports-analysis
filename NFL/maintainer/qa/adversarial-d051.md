# Adversarial committee report: D-051 (one repository, `NFL/maintainer/`)

Reviewer: Q1 QA Reviewer, acting as the adversarial committee. Branch `agents/pensive-noether-dxfoz6`, head `7ad635a`, compared with `origin/main` (`99336b0`, unchanged after a fresh fetch). Nothing was committed or pushed.

## Verdict

**Safe to merge.** There are no Critical and no Major findings. Nothing that executes reads a path that moved. The published data and the live workbook are reproduced exactly. Five Minor findings follow. Fix m-1 before merging (it is one line and breaks a stated rule). The rest can be done in a follow-up.

## Findings

### Critical
None.

### Major
None.

### Minor

**m-1. A folder name of the private repository is new public text.**
- Where: `NFL/maintainer/plan/validate_plan.py`, line 214 (the `FORBIDDEN` list). The list names six folders of the private repository. Five of them were already on `main`. The sixth, the 40-numbered workshop folder, is **new compared with `origin/main`** (`git grep` on `origin/main` finds none). It is also in commit `7ad635a`, which is on the public branch.
- It breaks the rule in `.claude/CLAUDE.md` section 2: never commit the name, folders or content of the private repositories. Sensitivity is low: it is a folder name, not the repository name or a path.
- Reproduce: `git diff origin/main -U0 -- NFL/maintainer/plan/validate_plan.py | grep Workshop`.
- Fix: in the `FORBIDDEN` list, replace the six folder-name patterns (all but `Personal/`) with one generic pattern: `r"\b[1-9]0-[A-Z][A-Za-z]+"`. I tested it. It finds 0 matches in `plan.json` and still catches every numbered folder name, without naming one. Then run `python3 NFL/maintainer/plan/validate_plan.py`. Use **Squash and merge** so `main` never holds the old line, and delete the branch afterwards. The old text stays public while the branch exists.

**m-2. A regression guard was deleted.**
- Where: `NFL/03-pipeline/tests/test_workflows.py`, in `test_scoped_to_the_nfl_folder`. The assertion that no workflow text contains the private-repository paths was removed. The decoy path `00-Governance/MEMORY.md` was also replaced with `docs/notes.md`.
- Impact: a workflow that regained a private-repository path would no longer fail CI. The assertion did name private folders, so removing it is understandable.
- Fix: put back a name-free check, for example `assert not re.search(r"\b[1-9]0-[A-Z][a-z]+/", text)` plus `assert "Personal/" not in text`. This is a test-only change, so the weekly workflow does not start (CI does).

**m-3. The `BLOCKERS.csv` line-ending guard was dropped.**
- Where: `.gitattributes` lost `BLOCKERS.csv -text` and nothing replaced it for `NFL/maintainer/BLOCKERS.csv`. The file ends each record with CRLF and has LF inside quoted fields (`git ls-files --eol` reports `i/mixed`).
- Impact: git keeps the file as it is on a normal checkout. Git for Windows with `autocrlf=true` can still normalise a mixed file, because nothing now says not to. Risk is low; the CLAUDE.md rule "edit as bytes" still applies.
- Fix: add `*/maintainer/BLOCKERS.csv -text` to `.gitattributes`. This file is not on any workflow trigger.

**m-4. Stale paths remain in files nobody runs, and in two files that cannot change.**
- `NFL/maintainer/archive-2.x/` scripts still build `05-excel/archive-2.x/...` and `01-plan/plan.json` paths. Examples: `build/build_workbook.py` (about lines 311-322) and `experimental/build_queries_installed.py` and `verify_queries_installed.py` (the `05-excel/archive-2.x` strings). They would fail if run. No test, workflow or tool imports or runs them; `pytest.ini` has `testpaths = tests`, and `NFL/maintainer` holds no `test_*.py` or `conftest.py`. The archive README says the scripts are not maintained. The archive docs also still say the Power Query files sit in `05-excel/`.
- `NFL/02-config/scoring_weights.csv` (row `dst_points_allowed_excl_def`) and `NFL/06-qa/evidence/espn-game-log-ARI-DST-2026.txt` mention `BLOCKERS.csv` at the old root location. Both are unchanged and protected. Editing the config CSV would start the pipeline. Leave both as they are, or fix them in a deliberate release.
- Fix: add one line to `NFL/maintainer/archive-2.x/README.md`: "Paths inside these scripts name the old layout; they are kept as a record and will not run unchanged."

**m-5. The spec text in `CONTRACTS.md` sections 10-12 was removed, and citations to it remain.**
- The old section 10 (the shape of `plan.json`), section 11 (the `BLOCKERS.csv` column list) and section 12 (releases) are now one stub, "9 to 12. Retired sections". Section 9 (Power Query) is retired as well, but it describes a retired route.
- `plan.json` still cites `CONTRACTS.md §9`, `§10` and `§11` as sources (for example lines 83, 1069 and 1089). `validate_plan.py` and `render_plan_md.py` cite `§10` in their docstrings.
- Impact: documentation only. The formats are still enforced by `validate_plan.py`.
- Fix: either restore the `plan.json` and `BLOCKERS.csv` column text into `NFL/maintainer/README.md` (or the plan folder README), or change the two docstring citations to "see the header of this script".

## Attack 1: break the pipeline

**Executable reads of moved paths: none.**
- I searched `nflpipe/`, `tests/`, `.github/workflows/`, `.gitattributes` and `.gitignore` for every old and new path name. The only path reads are `NFL/06-qa/fixtures` and `NFL/06-qa/evidence`, which did not move, and `NFL/05-excel/README.md`, which still exists.
- Mentions of `CONTRACTS.md` are comments or docstrings. Every `.md` link in the repository resolves (my script: 0 broken).
- The diff of executable code is docstring and comment changes in `derive.py` and `scoring.py`, one `.gitattributes` line, and one test assertion. No behaviour changed.

**Results.**
- Tests from `NFL/03-pipeline`: 686 passed on Python 3.13.18 (`../.work/venv`), and 686 passed on Python 3.11.18 (`../.work/venv311`).
- `python -m nflpipe check`: `PASS: 10 checks on 04-data` (golden 125/125, ESPN 25/25, D/ST, index, rows, long TD, overlap).
- `python -m nflpipe export --out ../.work/a51/x.xlsx`: SHA-256 `eb33017ce791d4ba11216bd348175b5453720d7b3cbd29799a7b029f2cadd9ed`. **It equals the live value.** The file properties name only the pipeline as creator.
- `actionlint` on the four workflows: no output, exit 0.
- `git diff origin/main --stat -- NFL/04-data .github NFL/02-config/*.csv NFL/06-qa/fixtures NFL/06-qa/evidence`: **empty.**
- `python3 NFL/maintainer/plan/validate_plan.py`: `PASS: 0 errors`, from the repository root, from `/tmp` and from its own folder. `render_plan_md.py`, run on a scratch copy, reproduces `PLAN.md` byte for byte. Both still read `BLOCKERS.csv` and `governance/DECISIONS.md` correctly from their new locations.
- The retired archive scripts are not run by any test (see m-4).

**Which workflows does merging start?**
- `nfl-pipeline-weekly` (push on `main`): yes. `derive.py` and `scoring.py` match `NFL/03-pipeline/nflpipe/**`. The change to `NFL/02-config/README.md` does not match, because of the `!NFL/02-config/**/*.md` exclusion. The README is not one of the four hashed config files either (`Config.sha256` hashes only the CSVs), so it cannot change `config_sha256`.
- `nfl-pipeline-ci` (push on `main`): yes. Paths `NFL/03-pipeline/**` and `NFL/02-config/**` match. It runs pytest on 3.11 and 3.13 with read-only permissions.
- Monthly and watchdog: schedule only, not started. Nothing under `NFL/maintainer/`, `.claude/`, the root `README.md` or `DATA-LICENSE.md` starts anything.

**Trace of the weekly run started by the merge.**
1. `resolve` sees a push, so it is bypassed. The decision is `run` with no `--force`. `NFL/02-config` holds only the allowed file names, so there is no HOLD.
2. `python -m nflpipe run` downloads the nflverse data. `pipeline_version` is still 1.2.1 (`nflpipe/__init__.py`). The config hash and the code do not appear in any published file, so unchanged upstream data means nothing to publish. The outcome is SKIP (exit 3) and `04-data` is untouched (no data commit).
3. Workbook check: the key is `run_id|pipeline_version|WORKBOOK_VERSION`. The live release body carries `20261120T233201Z-gh44837469898|1.2.1|3.002`. Local `status.csv` has the same run id and version, and `WORKBOOK_VERSION` is `"3.002"`, so the keys match. The asset is `uploaded`, 8,432,121 bytes. Result: **`build=false`; the workbook is not rebuilt** and the live link is not touched.
4. Caveat, not a defect: this run re-reads nflverse. If nflverse changed since the last publish (the season is in progress), the run will PUBLISH, commit new data and rebuild the workbook. That is the normal weekly behaviour and does not come from this change. I could not run the download here.
- Comment-only changes in `nflpipe/` therefore cost one run and, with unchanged upstream data, change nothing published.

**Links the workflows emit.**
- The alert body uses `GUIDE_URL#alert-issues` (monthly, weekly, watchdog). `NFL/03-pipeline/AUTOMATION.md` still has `## Alert issues`, and `test_workflows.py` asserts the string `AUTOMATION.md#alert-issues`.
- The release notes say `See DATA-LICENSE.md`; the file exists at the root.
- The only AUTOMATION heading that changed is section 2, now "Maintainer's first-time setup". No workflow, test or document links to its old anchor (`grep` found none).

## Attack 2: privacy

**Scope.** Every commit reachable from any ref (26 commits, including `origin/main` history), commit messages, author and committer fields, the net diff against `origin/main` (about 500 added lines), the full HEAD tree, and two unreachable local commits.

- **Email addresses:** none in added text. Author and committer addresses are the GitHub noreply form for the owner and the bot, and the noreply address for the assistant. No personal address appears in any commit field.
- **Real name of the owner:** none found. The only owner identifier in the new text is the GitHub username, which is allowed.
- **Machine paths:** no Windows paths, no home paths and no `/Users/` paths in added text. The only matches are the regex strings in the `FORBIDDEN` list of `validate_plan.py`, which are patterns, not paths.
- **Tokens and secrets:** none. The only matches are CLAUDE.md and AUTOMATION wording about not storing secrets.
- **Workbook properties:** all four workbooks in the tree show a tool or pipeline name as creator, and they are identical blobs to `main` (R100 renames).
- **Private repository name:** **not found in any commit, message, author field or file reachable from the branch head, or from `main`.** I searched all reachable history for the name and for `workspace`; the only hits are `github.workspace` in workflows and the English word in a test docstring. This branch never carried a commit that named the private repository.
- **Private repository folders, new text compared with `origin/main`:**
  - `validate_plan.py` `FORBIDDEN` list: the 40-numbered folder name is new (m-1). The other five names there were already on `main`.
  - `DECISIONS.md` D-050 and D-051, `BLOCKERS.csv` Q-018 and `.claude/CLAUDE.md`: they say "private repository" or "private workshop" in general terms only, with no repository name and no folder. D-051 says the earlier review reports "name the private repository" and that they stay with the owner. Grade: no issue.
  - Old historical rows in `DECISIONS.md` (D-001, D-015, D-023 and others) carry the 1.x folder names. They were on `main` already and are not new.
- **Pushed commits.** Commit `73350d4` (message: internal files moved to the private workshop) and its `.claude/CLAUDE.md` say "the owner's private workshop repository" and name the owner's GitHub username. That tells a reader a private repository exists. It names neither the repository nor a folder. Grade: Minor, informational, no action beyond m-1's squash merge.
- **Unreachable local commits** `3960b6c` and `a5af43a` (older releases, not on any ref or pushed): no private name. They can be ignored.

## Exactly what I ran

All from `/home/user/sports-analysis` unless a directory is shown.

1. Read `.claude/CLAUDE.md` and the Q1 role card in `NFL/maintainer/governance/committee/ROLE-CARDS.md`.
2. `git diff origin/main --stat`, `--name-status -M`, and the empty-diff command from the brief; `git fetch -q origin`.
3. `git diff origin/main` on `.gitattributes`, `nflpipe/` and `tests/`; read the four workflow `on:` blocks and the weekly workflow's resolve, run, commit and workbook steps in full.
4. `grep -rnE` over `nflpipe/`, `tests/`, `.github/`, `.gitattributes` and `.gitignore` for every old and new path name; `git grep` over all of `HEAD` for old path names.
5. From `NFL/03-pipeline`: `../.work/venv/bin/python -m pytest -q -x`, then `../.work/venv311/bin/python -m pytest -q -x`.
6. From `NFL/03-pipeline`: `../.work/venv/bin/python -m nflpipe check`, and `... -m nflpipe export --out ../.work/a51/x.xlsx` followed by `sha256sum`.
7. `NFL/.work/c1/actionlint-dl/actionlint .github/workflows/*.yml`.
8. `python3 NFL/maintainer/plan/validate_plan.py` (from the repository root, `/tmp` and `NFL/maintainer/plan`); `render_plan_md.py` on a scratch copy in `NFL/.work/a51/plan/`, then `diff` with `PLAN.md`.
9. A link checker for all tracked `.md` files, `NFL/.work/a51/links.py`: 0 broken.
10. `gh api repos/wes-blue/sports-analysis/releases/tags/nfl-workbook`, read-only, to read the release key and asset.
11. Privacy: `git log --all --format=...` for all author, committer and message fields; `git log -S` and a per-commit `git grep` across all 26 commits; the net added lines saved to `NFL/.work/a51/added.txt` and searched for emails, machine paths, tokens and the folder and repository names; `git fsck --lost-found` and inspection of the two unreachable commits; reading the core properties of every tracked `.xlsx`.
12. A trial of the generic regex for m-1 against `plan.json`.

I created only files under `NFL/.work/a51/` (git-ignored) and this report. A `compileall` run created `__pycache__` folders under `NFL/maintainer/archive-2.x/`; I deleted them, and `git status` is clean apart from this report.
