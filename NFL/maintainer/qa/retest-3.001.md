# Retest 3.001 (Q1, independent re-tester)

Repository commit `9926d1a`, branch `agents/pensive-noether-dxfoz6`, compared with `0e7fb80`. Date: 2026-11-21.
I did none of the building or fixing. Nothing in the repository was changed except this report and the git-ignored scratch folder `NFL/.work/qr/`. No Excel was available; every statement about Excel is a statement about the file, not about Excel's behaviour. The real GitHub was never called: the workflow steps were run from the YAML against my own stand-in `gh` and `curl` (`NFL/.work/qr/gh`, `curl`, `run.py`, `merge.py`, `swap.py`, `l.py`). The stand-in models GitHub's documented behaviour independently of the fix team's test stub: `release upload --clobber` deletes first, a duplicate asset name is refused, a failed upload can leave a zero-byte `starter` asset, and the public address serves only a published release with a finished, non-empty asset under the stable name. The step executor is the fix team's `NFL/.work/fw/scen.py`, which I read and which evaluates the same step text GitHub would run.

## Verdict

**Ready for the pull request.** Every Critical and Major finding is fixed in my own reproductions. The merge sequence ends with the stable address serving the workbook, and the asset swap never leaves the address worse off than "old file" or "new file" except in one double-failure case that repairs itself on the next run. The one thing nobody can have tested is Excel itself and the real GitHub release API (rename of an asset, the CDN answer); both are on the owner's first-run checklist (`AUTOMATION.md` section 2, `BLOCKERS.csv` Q-024).

Counts. Finding IDs examined: 18 A1 (A1-01..18, plus the size proposal A1-S1), 13 A2, 17 R2, 7 R1 = 56.

| Result | Count |
|---|---|
| Fixed | 41 |
| Partly fixed | 5 |
| Not fixed (Minor, unreachable or cosmetic) | 3 |
| Accepted / deliberately not fixed, reason holds | 7 |
| New findings | 0 Critical, 0 Major, 5 Minor |

## Findings

### A1 (the workbook file)

| ID | Grade | Result | Evidence |
|---|---|---|---|
| A1-01 | Critical | Fixed | Inserted `FF_New` before `FF_Standard` in a season file, and swapped two league columns: export succeeds, `PlayerGames` and `SeasonTotals` sheet XML byte-identical to the unmodified build (columns found by name). Dropping a column: exit 1, message names `scored_2025.csv` and the column. |
| A1-02 | Critical | Fixed | Header `Not_x0041_es`: shared string and `tableColumn name` both hold `Not_x005F_x0041_es`, so they decode to the same text. |
| A1-03 | Critical | Fixed | Leagues `A B` and `A<LF>B`: exit 1, "PlayerGames: duplicate column name 'FF_A B'", no file left. |
| A1-04 | Critical | Fixed | `generated_utc` of `yesterday`, `2026&<`, or with a control character: exit 1 naming the value and the expected form, no file. |
| A1-05 | Major | Fixed | `nan`, `inf`, `1e400`, `1e100`: exit 1 with file, line, column and value each time. |
| A1-06 | Major | Fixed | Trailing blank line in `player_week` and `scored`: builds, sheet XML identical to the clean build. |
| A1-07 | Minor | Fixed | `_x005F_x0041_` is written as `_x005F_x005F_x005F_x0041_`, which a spec-following decoder reads back as the original. (openpyxl decodes it differently, a reader quirk.) |
| A1-08 | Minor | Fixed | Width capped at 255; a 300-character league name is now refused earlier by the 255-character header rule. |
| A1-09 | Minor | Fixed | `+3` in a score column: exit 1 "is not a number"; one parser for both sheets. |
| A1-10 | Minor | Fixed | Row saying 2031 inside the 2025 file: exit 1 "season is '2031' but the file is for 2025". |
| A1-11 | Minor | Fixed | 20,000 emoji (40,000 UTF-16 units) refused, counted as Excel counts. |
| A1-12 | Minor | Fixed | 300-character header refused (255 limit). |
| A1-13 | Minor | Fixed | `1e-400` and a 20-digit value refused with file, line, column. |
| A1-14 | Minor | Not fixed | `force_zip64` is not set (no `zip64` in the source). Unreachable with nflverse data (about 880,000 rows needed). |
| A1-15 | Minor | Fixed | The row limit now counts from the sheet's first data row (source line 815). Unreachable anyway. |
| A1-16 | Minor | Fixed | Zero-byte file: "player_week_2026.csv is empty"; `OSError` message is plain ("cannot create the folder /proc/x"); temp name carries the process id; `pkg.abort()` closes the stream on failure. The error for a duplicate column now names the sheet. |
| A1-17 | Minor | Not fixed | Contract 13.1 still promises byte-identical output; a different zlib build could change compressed bytes. Same result on Python 3.13 and 3.11 here (below). The GitHub runner's Python is 3.12, not tested here. |
| A1-18 | Minor | Accepted | Noted as contract-conformant by A1. |
| A1-S1 | proposal | Accepted | Omitting cell references (about 6.8 MB) is deferred until Excel has opened 3.001 cleanly. Decision D-044 records it. The reason holds: a smaller file is not worth a repair prompt on the first open. |

### A2 (the workflows), executed against the stand-in

| ID | Grade | Result | Evidence |
|---|---|---|---|
| A2-01 | Critical | Fixed | **Merge sequence** (`merge.py`, real exporter, real `04-data`, no release): push to `main` -> `Resolve` decides `run` (the weekly push filter now includes `NFL/03-pipeline/nflpipe/**` and the workflow file, which the merge changes) -> `run` finds the config hash equal to `status.csv` (I computed it: `65eabafe...`) and the pipeline version unchanged, so SKIP -> `Decide`: "there is no nfl-workbook release yet", build=true -> exporter 12.5 s, 40,018,688 bytes, zip check and size floor pass -> release created as pre-release -> asset uploaded, renamed, public address answers 206 -> notes carry key `20261120T233201Z-gh44837469898|1.2.1|3.001`. **Stable address serves the workbook (40,018,688 bytes), run green, no alert.** The next scheduled run (SKIP, current key) only reads (build=false). Variant where upstream data changed (run PUBLISH): same ending. That GitHub starts a run for the merge push is my reading of the path-filter rules, not observed. |
| A2-02 | Major | Fixed | **Asset swap, failure injected at each step**, old asset live, PUBLISH run. What the stable address serves afterwards: |

| Injected failure | Run | Stable address afterwards | Next run |
|---|---|---|---|
| None | green | new file | skips |
| Upload fails 3 times (a half-uploaded `starter` asset left) | red | **old file** (the reporter's scenario S1 now keeps it); half asset removed | rebuilds, green |
| Upload fails twice, then works | green | new file | skips |
| Old-asset delete fails | red | **old file**; new file left as `.next` | rebuilds, green |
| Verify read fails after upload | red | **old file**; `.next` left | rebuilds, green |
| Rename refused every time, fallback upload works | green | new file | skips |
| Rename fails once | green | new file | skips |
| Rename refused AND fallback upload fails | red | **404** (new file sits as `NFL-Analysis.next.xlsx`) | finds no finished stable asset, rebuilds, green |
| Public address answers 404 after the swap | red | new file | rebuilds (notes still old key) |
| Notes edit fails | red | new file, link works | rebuilds once, green |
| Listing releases fails (502) | red, nothing touched | old file | next run proceeds |
| Draft release holds the tag | red with a message | unchanged (a draft has no public address) | needs owner |

The only state that ends in 404 is the double failure (rename refused and re-upload failed), which the guide says in words. `PATCH` rename of an asset on a pre-release is UNVERIFIED on the real API. The fallback exists for that.

| ID | Grade | Result | Evidence |
|---|---|---|---|
| A2-03 | Major | Fixed | Both workbook and gate-report artifacts are named with `run_id` and `run_attempt`, both `continue-on-error`. |
| A2-04 | Minor | Partly fixed | The alert now says what failed ("the workbook could not be published"). Closing is still only by PUBLISH; the guide tells the owner to close the issue by hand. |
| A2-05 | Minor | Fixed | Releases are found from a structured listing; a 502 stops the run before any `gh release create` (tested). |
| A2-06 | Minor | Fixed | Draft stops with a message; step 7 requests the public address and fails on anything but 200/206. |
| A2-07 | Minor | Partly fixed | The key now includes `WORKBOOK_VERSION`, so a design change republishes on a SKIP. An exporter bug fix with no version bump still does not (the suggested hash was not adopted). The contract says "design version", so this is a stated rule. |
| A2-08 | Minor | Fixed | Notes edit retried three times. |
| A2-09 | Minor | Fixed | `Decide` fetches `main` and checks out the newest `04-data` (scenario with a newer commit built `gh777`). |
| A2-10 | Minor | Fixed | `workbook_only` off `main` ends red (ERROR) and says nothing was rebuilt (run). |
| A2-11 | Minor | Fixed (owner check) | `AUTOMATION.md` section 2 step 3 asks the owner to confirm immutable releases and tag rules are off; step 7 of the publish step turns a refusal into a red run. |
| A2-12 | Minor | Fixed | `seasons` input validated by regex (a value with a newline gives ERROR); `run_id`, version and design checked for characters; backticks neutralised in the build tail. |
| A2-13 | Minor | Partly fixed | Mutation log: 63 of 64 mutations caught. The test file still has one shared `ALLOWED_EVENTS` set including `pull_request`, so a `pull_request` trigger added to the weekly workflow would not be caught (the `main` guards still prevent harm). |

### R2 (the owner's journey)

| ID | Grade | Result | Evidence |
|---|---|---|---|
| R2-01 | Major | Fixed | `AUTOMATION.md` section 2 step 1 is now "watch the workbook get built" and matches my merge run (messages `build=true; there is no nfl-workbook release yet`, `built, ... bytes`, `published at ...`). |
| R2-02 | Major | Fixed | Root README, `05-excel/README.md` and `AUTOMATION.md` section 0 give the action for "not found" (Run workflow, tick `workbook_only`). |
| R2-03 | Major | Fixed | "about 38 MB" in README, `05-excel/README.md`, `AUTOMATION.md`, `PLAN.md`, `plan.json`. D-042 keeps "20 MB" with D-044 correcting it. |
| R2-04 | Major | Fixed (as far as a document can) | Warnings in both READMEs, `AUTOMATION.md` and on the `About` sheet; open time stays UNVERIFIED until Excel. |
| R2-05 | Major | Fixed | `BLOCKERS.csv` Q-024 asks for repair messages, open time and `FF_ESPN_League` check; owner-written answers unchanged. |
| R2-06 | Major | Fixed | `NFL/02-config/README.md` no longer mentions Refresh All; the stale "has not yet run" line is replaced. |
| R2-07 | Minor | Accepted | "About ten minutes" is now labelled an estimate in `AUTOMATION.md`; still unmeasured. |
| R2-08 | Minor | Fixed | Clause removed from `NFL/04-data/README.md`. |
| R2-09 | Minor | Fixed | `CONTRACTS.md` line 239 points into `archive-2.x/`. |
| R2-10 | Minor | Partly fixed | Q-020 response says "stable download link after every run", still ahead of the facts until the first upload. Owner answers intact. |
| R2-11 | Minor | Not fixed | `00-Governance/MEMORY.md` still says 381 tests, week 10, and "exporter and workflow steps" in progress; `RELEASES.md` repeats week-10 counts and "Never run on GitHub". (See N-3.) |
| R2-12 | Minor | Fixed | "Enable Editing" in the root README, `05-excel/README.md` and `AUTOMATION.md`; the string "Enable Content" no longer appears in README files. |
| R2-13 | Minor | Partly fixed | `About` now names each `FF_` column and says the latest week may be incomplete and that the file is large. Missing: the note that D/ST scores run about 100 to 300 a game. |
| R2-14 | Minor | Fixed | `Dictionary` now has rows for the identity columns, each `FF_<League>` and the nflverse points. |
| R2-15 | Minor | Fixed | League columns sit right after `opponent_team` and the player name is frozen through column D; newest first; `SeasonTotals` is `REG` before `POST`, then by the first league's total. All checked in the file. |
| R2-16 | Minor | Accepted | The `League_1` note ("keep the League name identical in tblScoring") lives in `02-config/leagues.csv`; editing it starts a pipeline run, so it waits for the next scoring edit. Reason holds. |
| R2-17 | Minor | Accepted | Now stated with a caveat that the release may not appear in the front-page sidebar; the Releases page does. |

### R1 (data review)

| ID | Result | Evidence |
|---|---|---|
| R1-m1 | Fixed | "status.csv data_contract_version is missing; this exporter understands version '1'". |
| R1-m2 | Fixed | Week `abc`: exit 1 naming file and line. |
| R1-m3 | Accepted | Name and position from the last game are now written into the contract (13.2). |
| R1-m4 | Fixed | Plain message for an unwritable output path. |
| R1-m5 | Fixed | Test file grew (679 tests in total) and has a "revision 2" block for these clauses. |
| R1-m6 | Fixed | Same as A1-04. |
| R1-m7 | Accepted | Two simultaneous `nflpipe run` commands against separate folders: outside the exporter and the workflows (which never overlap); not touched. I did not re-investigate. |

## New findings

| ID | Grade | Where | Finding |
|---|---|---|---|
| N-1 | Minor | `test_workflows.py` | One shared `ALLOWED_EVENTS` allows `pull_request` for every workflow file (A2-13 #23, still open). Suggest per-file sets. |
| N-2 | Minor | `NFL/02-config/README.md` | Says any change in the folder starts the weekly workflow; the weekly filter excludes `*.md`, so an edit to that README starts nothing. (The `AUTOMATION.md` text is exact.) |
| N-3 | Minor | `00-Governance/MEMORY.md`, `NFL/08-releases/RELEASES.md` | Stale: MEMORY says 381 tests, data through week 10, and that the exporter and workflow steps are still in progress; the suite has 679 tests and the data runs through week 11. CLAUDE.md section 7 requires MEMORY to be current at the end of the session. |
| N-4 | Minor | `NFL/01-plan/plan.json` (RAID detail) and `NFL/PLAN.md` line 469 | One leftover "a slow open of a 20 MB file". |
| N-5 | Minor | archive scripts (`archive-2.x/build/README.md`, `build_workbook.py`) | Contain a sandbox path `/root/.claude/skills/...`. Not a personal path; mentioned for completeness. |

No Critical or Major new finding. Open risks that only the owner's first run can settle: Excel's opening time and any repair message (file is 40.0 MB; the big sheet is 409 MB of XML with a cell reference on every cell), the `PATCH` rename and the CDN answer on GitHub, and whether the repository has immutable releases or a tag rule on.

## Regression numbers

- Test suite from `NFL/03-pipeline`: **679 passed** on `NFL/.work/venv/bin/python` (3.13) in 52 s and **679 passed** on `NFL/.work/venv311/bin/python` (3.11) in 52 s (R1 saw 471 on the earlier commit).
- `actionlint` 1.7.12 on all four workflows: no output, exit 0.
- Build from the real `NFL/04-data` (run `20261120T233201Z-gh44837469898`, through 2026 week 11): 40,018,688 bytes, 12.5 s, exit 0.
- **Determinism:** built twice, once on 3.13 and once on 3.11: both SHA-256 `66d6e26abc6d64c040ac8a413a2e1c89bb3d3bba955f4ded197d77d936fba2f2`, identical bytes.
- **`PlayerGames`, my own reader (openpyxl, never importing the exporter):** 180,301 rows x 98 columns = 17,669,498 cells compared against `player_week` plus `scored` matched by key, with type checks (identity columns text, metric numbers numeric, blanks empty): **0 mismatches**; header equals the contract order; rows are newest first.
- **`SeasonTotals`:** recomputed independently (Decimal, half away from zero, last game by highest week with later row winning ties, sort order): 24,250 rows, 412,250 cells, **0 mismatches**.
- **Package:** 31 parts, first part `[Content_Types].xml`, `testzip` clean, all XML parts well-formed, every part has a content type, no override points at a missing part, no broken relationship, no defined names. Shared strings: `count` 1,384,561 equals the string cells counted in the sheets; `uniqueCount` 11,357 equals the `si` count. Seven tables (`tblPlayerGames` A1:CT180302, `tblSeasonTotals` A1:Q24251, `tblLeagues`, `tblScoring`, `tblBonus`, `tblGates`, `tblDictionary`): `ref` ends on the last data row, header cells equal the `tableColumn` names, names unique case-insensitively, each has an `autoFilter` over its `ref`. Formulas (`<f>`): 0.
- **Scope of the fixes:** `git diff 0e7fb80 HEAD --stat -- NFL/04-data NFL/02-config` shows only `NFL/04-data/README.md` (one clause removed) and `NFL/02-config/README.md` (documentation text). No CSV in either folder changed, and the config hash still equals the one in `status.csv`. Neither README change starts the pipeline (the `*.md` exclusion).

## Public safety, final pass

Scanned: every text file in `git diff --name-only 0e7fb80 HEAD` (82 paths, full content, not only added lines), the commit author metadata, and every part of the built workbook (file properties, shared strings, all sheets, tables). Checks: e-mail addresses, Windows and Unix home or user paths, machine names, token and key patterns, session addresses, references to other repositories of the owner.

- **Workbook:** clean. File properties carry only the title `NFL-Analysis 3.001` and the author `NFL-Analysis pipeline`. The only owner-related text is the GitHub username in the public addresses and the phrase "the owner's ESPN league" in the league description.
- **Commit metadata:** authors are the GitHub username, `github-actions[bot]` and the assistant, all with `noreply` addresses.
- **Files in the pull request:** no e-mail address (the only matches are `@pytest` decorators and a placeholder test address on the `.invalid` domain), no token or key, no session address, no reference to another repository of the owner. Matches for "OneDrive", `C:\` and `/root/` are, by location and kind: `BLOCKERS.csv` rows Q-010 (a question and a generic example folder, unchanged by this branch), `plan.json` and `NFL/PLAN.md` (the same question's title), `validate_plan.py` and `archive-2.x/build/pii_scan.py` (the patterns the scanner itself looks for), archived Power Query text and READMEs (words about OneDrive folders), the archive build scripts (a sandbox path under `/root/`). None is a personal value. I do not know the owner's full name, so I checked what I can: that no identifier from the commit metadata other than the username appears.
- **The two archived 2.001 workbooks** are 100 percent renames of files already public (same blob hashes as at `0e7fb80`; `NFL-Analysis-2.001.xlsx` SHA-256 prefix `ac723648...`, experimental `5a254114...`); a scan found only drive-letter-like fragments inside the binary query model, not paths or addresses. Not newly published.

**Result: no personal data, no secrets, no private-repository reference found.**

## The documents the owner will follow

- **Root `README.md`**, **`NFL/05-excel/README.md`**: the link first; both say the file is about 38 MB, Protected View and Enable Editing, and what to do when the link says "not found" (wait two minutes, then Run workflow with `workbook_only`). That text matches what my run did: the link is empty only between the delete and the rename, and after a failed double step until the next run or a manual `workbook_only`. One inaccuracy: the root README ends with "the workbook upload step is not yet running", which is true today and needs removing at release.
- **`NFL/03-pipeline/AUTOMATION.md`**: section 2 now describes the merge as it behaves (CI plus weekly start, result usually SKIP, the three summary lines, green tick means the link works); section 0 describes the swap and its one failure mode accurately; "If the link says not found" leads with the right button. The alert table matches the workflow (closed only by PUBLISH, close it yourself after a workbook failure).
- **`NFL/02-config/README.md`**: Refresh All is gone; the rebuild is described. See N-2 for the README exclusion.

## Not tested

Excel itself (repair prompt, opening time, memory, Protected View). The real GitHub: whether the merge push starts the weekly run (path filter read, not observed), asset `PATCH` rename, the CDN answer, release-asset limits and repository settings. Python 3.12 (the runner's version): 3.11 and 3.13 only. LibreOffice was not run on the final build; the openpyxl reader and my own package checks stand in.
