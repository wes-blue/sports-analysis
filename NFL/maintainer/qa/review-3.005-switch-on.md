# Independent review: the 3.005 switch-on change (commit 2ae16fb)

Reviewer: Q1 QA Reviewer (independent of the builders). Date: 2026-11-23. Branch `agents/pensive-noether-dxfoz6`, compared with `origin/main` (`bded4d9`; the two records-only commits `fb2f663` and `d5f45d1` sit under the branch, so the diff also shows their record changes).

## Verdict: ready to merge

Critical 0, Major 0, Minor 4 (all optional).

## What was checked and how

### 1. The switch
- `git diff origin/main -- .github/` changes six lines in two files: in each, the comment above `PUBLISH_REFRESH_WORKBOOK` (two lines) and the value `"false"` to `"true"`. Nothing else in either workflow changed.
- Both values are the quoted string `"true"`. `test_the_switch_is_on_and_the_same_in_both_workflows` pins `["true", "true"]` and asserts a string, not a YAML boolean.
- Both publishing steps still reject any value other than `"true"` or `"false"`.

### 2. First run after the merge (workflow stand-ins, as `tests/test_workflows.py` does)
Scratch test: `NFL/.work/review-switch-on/test_scenario.py`. It reuses the repository's `WB` harness, stand-in `gh` (which, like the real `gh`, deletes before it uploads and records a violation if a live asset is deleted before every new file exists) and stand-in `curl`. The release held `NFL-Analysis.xlsx`, `NFL-PlayerGames.csv` and `NFL-SeasonTotals.csv`, with the key `20261122T020950Z-gh44974771246|1.2.1|3.002|1`. Run for the weekly and the monthly workflow: 2 passed.

- Decide, outcome SKIP: `build=true`, key unchanged (`...|3.002|1`), summary line `the release has no finished NFL-Analysis-Refresh.xlsx (an upload did not finish, or the asset is new)`. No write call was made.
- Build: four files written (`NFL-Analysis.xlsx`, `NFL-PlayerGames.csv`, `NFL-SeasonTotals.csv`, `NFL-Analysis-Refresh.xlsx`).
- Publish call order: `upload x4` (all four under `.next.` names, no `--clobber`), then `delete, patch` for each of the three live assets, then `patch` only for the refresh workbook, then `release edit` (notes). So 3 deletes, 4 renames, 1 notes edit.
- No live asset is touched before all four temporary files are uploaded and verified: the script's step 4 checks each new file (state `uploaded`, exact size) before step 5 starts the swaps, and the first delete in the log comes after the fourth upload. The stand-in recorded zero violations.
- The refresh workbook has nothing old to delete: `drop_assets` finds no asset of that name and succeeds; no delete is issued for it (3 deletes, not 4).
- Four public addresses are checked (loop over the four assets), then the notes are written, listing all four links (the check of the notes body found all four download addresses and the new key). A second decide then says `build=false`.
- Not run here: the real GitHub runner. The real run will show the same shape; a failed run leaves the old key, so the next run rebuilds.

### 3. The published file is the tested file
- Built `python -m nflpipe refresh-workbook` from `git archive origin/main` and from `git archive HEAD` (Python 3.13): both 14,375 bytes, SHA-256 `1e0a8a16e44838410b9a03241d49286d2e3e9830e99031d36f6c180339dfea06`. The branch build under Python 3.11 gives the same hash.
- `git diff --name-only origin/main` shows no change to `refresh_workbook.py`, `pq/*.m` or `export_xlsx.py`; `TABLES_VERSION` is still `"1"` and `WORKBOOK_VERSION` `"3.002"`. The branch changes no file under `nflpipe/`.
- Caveat already recorded in the memory entry: the runner's zlib could compress differently; the tests pin the uncompressed digest, so a different compressed hash would not mean different content.

### 4. Tests and lint
- Full suite, `NFL/.work/venv/bin/python` (3.13.18): 828 passed.
- Full suite, `NFL/.work/venv311/bin/python` (3.11.18): 828 passed.
- `actionlint` with shellcheck v0.11.0 over `.github/workflows/*.yml`: no findings (exit 0).
- `python3 NFL/maintainer/plan/validate_plan.py`: PASS, 0 errors (88 requirements, 109 RAID items, 36 controls, 25 roadmap versions).

### 5. Visitor pages
Read `README.md`, `NFL/README.md` and `NFL/05-excel/README.md` as a stranger.
- The refresh-workbook link is exactly `https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis-Refresh.xlsx` in all three places (checked by search).
- No decision numbers (D-, Q-, RAID), no jargon and nothing addressed to the owner on the three pages. The old "Coming" and "not yet measured" wording is gone.
- The steps are in a sensible order and do not contradict each other or the rest of the page: open and enable editing, **Data**, **Refresh All**, choose **Anonymous**, **Public** if asked. The front page and `NFL/README.md` give the one-line version.
- Times: the only figures are in "Good to know" in `NFL/05-excel/README.md` ("under two minutes", "about 30 seconds"), introduced as one test and "an estimate for your computer and connection". The size (about 14 KB) is stated.
- The refresh workbook's `Start` sheet (from `xl/sharedStrings.xml`) says: choose **Data**, **Refresh All**; the first time choose **Anonymous**, level `https://github.com/`; choose **Public** if a privacy question appears; the files read are the two release CSV links; nflverse attribution; a pointer to the finished `NFL-Analysis.xlsx`. It does not contradict the pages. It is shorter: it omits **Enable Editing/Enable Content**, the possible second prompt for an address ending in `githubusercontent.com`, "every season from 2017" and any time estimate (see M-1).

### 6. Records
- `NFL/maintainer/BLOCKERS.csv`: BOM present in both; 27 CRLF record terminators in both (the 2,269 bare LFs are inside quoted fields, the same count as before); 27 records in each. Parsed record by record against `origin/main` and against `d5f45d1`: only Q-026 differs.
- Q-026: `Status` is `Answered`. The earlier `Answer` text (given in chat, "works but only downloaded 2026 seasons", recorded by `d5f45d1`) is kept as the first part; the owner's second answer is appended after ` | `. Against `bded4d9` that earlier text was empty because it came with `d5f45d1`. `Claude_Response` was rewritten (Claude's own text, not the owner's).
- Facts against the owner's reported results, all consistent in D-059, the BLOCKERS answer, RAID-108/109 (both Closed, with matching response text), the memory entry, `CONTRACTS.md` and `AUTOMATION.md`: no repair message; Ctrl+End at 180302 (PlayerGames) and 24251 (SeasonTotals); seasons 2017 to 2026; at most 2 minutes, then about 30 seconds; ESPN value matched. I re-derived the row counts from a scratch export of the published tables (`NFL/.work/retest-3.005/exp`): 180,302 and 24,251 rows including the header, as the owner saw.
- D-059 says the first run publishes four assets, that 3.005 is released only when that run is green, and that the `Start` sheet is left as tested. The memory entry says the same, and tells the next session to verify the four links and the file hash. The plan still marks FR-54 "In progress" until that run, as D-059 says.

### 7. Privacy
Scanned all added lines of `git diff origin/main` (60 lines, one added-lines file in the scratch folder) and the commit message of `2ae16fb`. No email address (the author line is the generic `Claude <noreply@anthropic.com>`), no personal name, employer, local path, token, fantasy team or manager name, or private repository name. The only path-like match is the repository-relative scratch path `NFL/.work/pq/out3/...`, which was already in the memory text before this change. The visitor pages state no personal detail; "Microsoft 365, Windows" in the records is generic.

## Findings

### Critical
None.

### Major
None.

### Minor
- **M-1 (Minor, no action needed).** The `Start` sheet is shorter than the visitor guide. It does not mention Enable Editing/Content, the second `githubusercontent.com` prompt, the 2017 start or the time. It does not mislead, and the owner's test did not need them; D-059 records the choice to keep the tested bytes. If the sheet is ever changed, the file's `TABLES_VERSION` and pin must change with it.
- **M-2 (Minor).** The quick-way steps in `NFL/05-excel/README.md` give no time; the estimate sits lower down in "Good to know". A visitor who watches a long first refresh may not have read it. Suggest one short clause ("the first refresh can take a couple of minutes") in step 2 at the next edit.
- **M-3 (Minor, informational).** The local `origin/main` ref is `bded4d9`, not including the two records commits, so `git diff origin/main` also shows the D-058 records, the TEST3 answer and the memory line from those commits. Nothing in them is wrong. Merging after fetching `origin/main` will show only the switch-on change.
- **M-4 (Minor, informational).** `AUTOMATION.md` keeps the "How to flip it" steps and the paragraph "With the refresh workbook switched off, as shipped" for the earlier merge. Both are historical or reference text and are accurate for the earlier run; a reader of section 0 sees "(now)" against the `"true"` line.

## Commands run (results above)
- `git diff origin/main -- .github/`; `git diff --name-only origin/main`
- `NFL/.work/venv/bin/python -m pytest -p no:cacheprovider -s -q NFL/.work/review-switch-on/test_scenario.py` from `NFL/03-pipeline`: 2 passed
- `git archive origin/main` and `git archive HEAD` into `NFL/.work/review-switch-on/{main,branch}`, then `python -m nflpipe refresh-workbook --out ...`; `sha256sum`: identical `1e0a8a16...`
- `python -m pytest -p no:cacheprovider -q --ignore=../.work` in `NFL/03-pipeline` with both venvs: 828 passed each
- `actionlint -shellcheck=.../shellcheck .github/workflows/*.yml`: exit 0
- `python3 NFL/maintainer/plan/validate_plan.py`: PASS, 0 errors
- Python `csv` and byte checks of `BLOCKERS.csv` against `origin/main` and `d5f45d1`; `unzip` and a read of `xl/sharedStrings.xml`; searches over the added lines and the commit message.

Nothing was committed, pushed, published or released. Scratch files are in `NFL/.work/review-switch-on/` (git-ignored).
