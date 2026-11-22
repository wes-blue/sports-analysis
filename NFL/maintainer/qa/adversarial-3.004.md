# Adversarial review of roadmap 3.004 (ESPN blocked field goal, three ESPN game logs)

Reviewer: Q1 QA Reviewer, adversarial committee. Branch `agents/pensive-noether-dxfoz6`, head `8266215`, compared with `origin/main`. Reviewed 2026-11-22. Nothing was committed, pushed or published.

## Verdict

**Safe to merge.** There is no Critical finding. Nothing that was reproduced can publish wrong data or damage the live workbook.

- On today's upstream data the merge run is a PUBLISH, with 13 of 13 gates passing, in about 45 seconds.
- The pull request's `config-check` job passes with this config.
- The workbook rebuild works on the new data.
- The one real exposure is **Major M1**: a weekly run can turn red because a stat is corrected upstream. It is a safe failure (HOLD, old data and workbook kept, alert issue). It is cheap to reduce, and the fix is below. I recommend applying it, but it does not need to hold the merge.

Findings: 0 Critical, 1 Major, 4 Minor.

A note on method. While I worked, another session edited the shared working tree (uncommitted changes to `scoring_weights.csv`, `CONTRACTS.md`, `BLOCKERS.csv`, `DECISIONS.md`, `06-qa/README.md`). Everything below was run on a clean export of `HEAD` (`git archive HEAD`). The config hash of that export is `3535932a...`, which matches the one in my run's `status.csv`. Notes-only edits cannot change the ESPN_League contract hash, so the fixtures stay applicable. See "Contract hash" under Checks.

## What I traced, and the answers

### 1. The merge run

- **Does it re-score every season?** Yes. The push path calls `run --seasons current` without `--force` (`nfl-pipeline-weekly.yml`, "Resolve" and "Run pipeline"). `run.choose_seasons` returns every season in the window when `config_changed()` finds that `config_sha256` in `status.csv` differs. The hash is computed over the normalized config files, notes included. I confirmed: `config changed: every season rebuilt`, and 10 seasons (2017-2026) rebuilt.
- **How long?** 44 s with an empty cache (about 254 MB downloaded through the proxy) and 35 s with a warm cache. The job limit is 45 minutes and the workbook steps have their own 10 and 20 minute limits. The time is not a risk.
- **Upstream changed since the published run.** `Last-Modified` moved on 2026-11-21 16:47Z, but the bytes are identical (same sha256 for `stats_player`, `stats_team` and `pbp`). `player_week_2026.csv` is byte-identical to the published one, and G-RESTATE reports no changes in 9 complete seasons. The re-upload did not correct any stat.
- **Gates that could fail on GitHub but passed locally.**
  - Network: every fetch has retries (4 attempts). A download failure is an ERROR (exit 1), not a gate failure, and publishes nothing.
  - Blocking gates: CONFIG, GRAIN, RECON, GOLDEN, ESPN, DST, SHRINK, INDEX. Only G-ESPN touches the new data, so only M1 applies.
  - G-RESTATE is advisory. It compares raw `player_week`, not scored values, so the 179 re-scored rows cannot trip it. It cannot block.
  - Window and time: not gate inputs apart from the advisory G-WINDOW. A partial week 12 is handled as week 11 was on 2026-11-20. All new fixture rows are for weeks up to 11, and rows for weeks not yet published are `NOT_APPLICABLE`.
- **If a gate fails.** `run` returns exit 4 (HOLD) before anything is written. Reproduced: I changed one fixture value on a copy, got HOLD, and the data directory was byte-identical afterwards. The workflow then:
  - skips the data commit (it needs outcome PUBLISH);
  - skips the workbook steps (they need PUBLISH, SKIP or WORKBOOK), so the 3.002 asset stays;
  - turns the run red and opens or comments on the `nfl-pipeline-alert-weekly` issue.
  - **Consequence of a HOLD:** `resolve` keeps answering "run" while the published config hash differs, and later runs hold on the same fixture. New weeks do not publish until the fixture is fixed.

### 2. CI `config-check` on the pull request

Its command is `run --seasons current --dry-run --trigger pull_request-check`. I ran exactly that against a copy of the published data: exit 0, all 13 gates PASS, "would publish 16 changed data file(s)" (35 s). The job passes. The `pytest` job: 689 tests passed on a clean export of HEAD (Python 3.13), and the two new test files passed on Python 3.11.

### 3. The data commit

- 21 files differ from the published data (the run reports 21 written; 16 are the non-volatile ones): 450 insertions and 272 deletions in total.
- The 179 changed rows are all `K` rows in `FF_ESPN_League` (the only scored column that changed, in all ten files). The change equals minus `fg_blocked` on every one of them, and 4 rows have 2 or more blocks.
- Per-file diffs are small (11 to 28 lines per `scored_YYYY.csv`). The scored files total 11 MB. The data diff gzips to about 32 KB. Nothing about the commit step is a problem: it is a single `git add NFL/04-data` of 21 files.
- Consistency of the run files:
  - `status.csv`: new run id, `config_sha256` and `contract_ESPN_League` (`ccd67c66...`, equal to `fixture_contracts.csv`); `seasons_refreshed` lists all ten seasons.
  - `run_log.csv`: one appended row with the note `config changed: every season rebuilt`.
  - `sources.csv`: 4 rows changed (schedules and the three 2026 files). The old seasons keep their earlier `fetched_utc` because their bytes and `Last-Modified` are unchanged.
  - `manifest.csv` and `seasons.csv` agree with the files. `python -m nflpipe check --data-dir <new data>` passes all 10 checks.

### 4. The workbook rebuild

`python -m nflpipe export` on my full-run data: OK in 9 s, 8.4 MB, zip readable, 8 sheets. `PlayerGames` has 180,301 rows. The About sheet shows run id `20261122T010745Z`, which is my run's id; the title still says 3.002, since the design is unchanged. Core properties name only "NFL-Analysis pipeline". The freshness key is `run_id|pipeline_version|design`, so the key changes and the workflow builds and replaces the asset by the same path that 3.002 exercised (upload as `.next`, check, delete old, rename, public-URL check, then the notes). The next scheduled SKIP finds the key current. The workbook text has no personal data: the string `wes` only appears in the repository URL and in player names.

### 5. The new fixture rows and late stat corrections

The new rows are 10 Allgeier player rows (tolerance 0), 20 D/ST points rows (tolerance 1) and 20 `espn_dst_stats` rows (exact). `espn_dst_stats` compares only the event columns TD, INT, FR, SCK, SFTY, BLK and PA, not tackles or return yards. The tackle and return-yard corrections matter through the D/ST points rows.

See M1.

### 6. Config CSV formatting

I compared the bytes with `origin/main`. All four config files are LF only, have no BOM, end with a newline, are ASCII, and have the same quoting style (quotes only where there is a comma). The rewrite changed only note text. `.gitattributes` marks `*/02-config/*.csv` as `-text`, so Git does not convert them. I also simulated an Excel re-save (BOM, CRLF, rewritten quoting): the config hash is unchanged, because it is computed over the normalized copies and the loader reads `utf-8-sig`. The owner's next edit is no riskier than before. Two points:

- The `fg_blocked` note is now quoted because it contains commas. That is correct CSV.
- A note-only edit changes `config_sha256` and so triggers a full rebuild and a data commit (see Minor m4). It does not change the contract hash.

### 7. Privacy

I scanned the three evidence files, the whole diff and the three commits `git log origin/main..HEAD`.

- **Evidence files:** the game-log tables, the three-line header and a note saying the news items and the fantasy-transaction line were left out. They contain no account name, team name, manager name, league name or id, email, cookie, or path.
- **Commits:** the author is `Claude <noreply@anthropic.com>` and the trailers are the usual ones. There are no paths or tokens.
- **Diff:** no local paths, private-repository names, employer or personal names. The only hits are `wes-blue` (allowed) and one example path that is already on `main` (see m3).
- **One thing not introduced here:** see m3.

## Findings

### Major

**M1. Seven of the 32 D/ST points rows sit exactly on the tolerance, and one stat correction would stop all publishing.** (Major, not merge-blocking.)

- The ±1 rows are ARI wk 8 (ESPN 225, ours 224), IND wk 3 (122, 123) and wk 9 (174, 173), and NYJ wk 6 (208, 207), wk 7 (115, 116), wk 8 (161, 160) and wk 10 (195, 196). A late correction of one tackle or one return yard on any of them makes the difference 2, and G-ESPN, which is blocking, fails.
- The ±1 is the known noise between nflverse and ESPN tackle and return-yard counts (D-021). It already existed for 2 rows before this change and is now 7 (5 of them new).
- Once a run holds, `resolve` and `run` keep holding on the same fixture row. The old data and the workbook stay, but new weeks do not publish until someone edits the fixture through a pull request. `AUTOMATION.md` says only "pass the text on to whoever maintains it".
- **Reproduction.** Copy `NFL/06-qa/fixtures`, change `espn_actuals.csv` row `2026,3,REG,DST_IND,...,122,` to `121`, and run `python -m nflpipe run --seasons current --data-dir <copy of 04-data> --fixtures-dir <copy> --cache-dir <cache> --report-dir <dir>`. Result: `G-ESPN FAIL 1 of 55 ESPN values not reproduced: IND D/ST ESPN 121 ours 123`, `HOLD`, exit 4, data untouched.
- **How likely.** Low for weeks that are two or more weeks old. nflverse re-uploaded all three 2026 files on 2026-11-21 and the content was identical, and the published 2026 data did not change between 2026-11-20 and 2026-11-22. The most exposed row is IND week 11, the Thursday game, which is three days old at the merge (the NFL's own corrections usually arrive Tuesday or Wednesday). It currently matches exactly, so one unit of correction would still be inside the tolerance.
- **Is the tolerance right?** ±1 on a total near 200 still catches any real scoring error: a wrong weight changes the score by tens of points, and a wrong tier boundary by at least 2. ±2 loses nothing against those. Keep `espn_dst_stats` exact: it is the stricter check, and its inputs are discrete events that rarely change.
- **Fix.** In `NFL/06-qa/fixtures/espn_actuals.csv` set `tolerance` to `2` on the seven rows above (or on all D/ST rows). Update the two tests that assert `tolerance == "1"` (`test_colts_and_jets_game_logs_are_in_espn_actuals_and_stats`) and the G-ESPN detail text "(D/ST +/-1)" if it is hard-coded. Add one sentence to the HOLD row of `AUTOMATION.md` saying that a fixture row in `NFL/06-qa/fixtures/` can be re-measured in a pull request. If the owner prefers to merge as is, the risk is a red run and an alert issue, not bad data.

### Minor

**m1. `MEMORY.md` at `HEAD` is out of date.** It says Q-017 and Q-019 are still open and that 3.004 waits for the owner's go-ahead, but `BLOCKERS.csv` and `DECISIONS.md` (D-055) say they are answered and 3.004 is built. It has no mention of D-055. Fix: update the "Current status", "Next steps" and "Waiting on the owner" sections before merging (end-of-session checklist, section 7 of `.claude/CLAUDE.md`).

**m2. The new `-1` is never exercised by a published check, and its evidence is a statistics page.** `fg_blocked = -1` is covered only by the unit test. No fixture row is a kicker with a block, and the golden sample is unchanged, so the gates would not notice if the rule were wrong. The evidence (Q-016) is ESPN.com's statistics page showing 1 of 2 made, not a fantasy points column (the uncommitted edit of the note now says so). 179 historical rows hang on it. League_1 also scores `fg_missed` -1 but keeps `fg_blocked` 0; the note says the other leagues score 0, which is consistent but not confirmed. Fix: when the owner can paste the Seattle kicker's ESPN Fantasy game log, add the week 8 row to `espn_actuals.csv` with tolerance 0. The roadmap or `BLOCKERS.csv` could carry that ask.

**m3. Third-party and personal-looking text already on `main` (not introduced by this change).**
- `NFL/maintainer/BLOCKERS.csv` Answer cells hold the owner's pasted lineup (Q-007, Q-008: player names, scores and season totals) and verbatim ESPN.com page text including `Copyright: © 2026 ESPN Enterprises, LLC. All rights reserved.` (Q-016, Q-017, Q-019, the last about 13 KB).
- The Default cell of Q-001 holds an example path `C:\GitHub\sports-analysis`.
- None of it names a team, a manager or a league, so I do not call it a breach. It is public and it is third-party content. `.claude/CLAUDE.md` forbids altering an owner's answer, so Claude must not trim it. Fix: raise it with the owner in chat; if they agree, they edit the cells.

**m4. Any config edit, even a typo in a note, republishes everything.** `config_sha256` covers the notes, so a note edit triggers a full re-score and a data commit (about 21 files, about a minute of run time). It is harmless and the SKIP logic recovers on the next run. It is worth one line in `NFL/02-config/README.md` so the owner is not surprised by the commit.

**m5. Interpretation, not a defect.** A scheduled-run `HOLD` (M1) stays open as an alert issue until a PUBLISH of the same workflow closes it. Nothing to change.

## Checks that found nothing

- G-RESTATE cannot block; G-SHRINK, G-INDEX, G-DST and G-GRAIN passed on the full run and do not read the new fixtures.
- **Contract hash.** `league_contract_hash` hashes weights and bands only, not notes. The ESPN_League hash `ccd67c66...` in `fixture_contracts.csv` equals the one the run publishes, so the ESPN rows are applicable. A future change to ESPN_League weights turns the rows into `NOT_APPLICABLE` and a WARN (the run still publishes), by design.
- Line endings of the new fixture rows (LF, no BOM) match the files they were added to.
- The workbook contains no personal data, and `status.csv` and `run_log.csv` change consistently.
- Notes in the config no longer carry decision numbers or `BLOCKERS.csv` references (grep of `NFL/02-config`, the published dictionary and the visitor READMEs).

## Exactly what I ran

All paths under `/home/user/sports-analysis/NFL/.work/a304/` (git-ignored). The working tree had concurrent uncommitted edits by another session; runs 1 to 4 and `check` used the config as committed (hash `3535932a...`).

1. `git diff origin/main --stat`, `git log origin/main..HEAD`, `git diff` for the config, fixtures, tests and the maintainer files.
2. Read `.github/workflows/nfl-pipeline-weekly.yml` and `nfl-pipeline-ci.yml`, `nflpipe/run.py`, `resolve.py`, `gates.py`, `config.py`, `http.py`.
3. Byte comparison of the four config CSVs and the three fixtures with `origin/main` (BOM, CR, LF, last byte).
4. Run 1, a fresh full run as the push would do it: `python3 -m nflpipe run --seasons current --trigger a304-push --data-dir .../data --cache-dir .../cache --report-dir .../report`. It started with an empty cache and a copy of the published `04-data`. Result: PUBLISH in 44 s, 13 gates PASS (G-ESPN: 55 of 55 values, 217 of 217 stat columns).
5. Run 2, the CI command: `run --seasons current --dry-run --trigger pull_request-check` on an untouched copy of the published data. Exit 0, 35 s.
6. Run 3, the HOLD test: copied fixtures with `IND wk 3` changed from 122 to 121 and a copy of the published data. Result: HOLD, exit 4, data identical. Then `python -m nflpipe resolve --data-dir <that copy>`: `action=run`, reason "the config in 02-config differs from the one last published".
7. `python3 -m nflpipe check --data-dir .../data` (PASS, 10 checks) and `python3 -m nflpipe export --data-dir .../data --out .../wb/NFL-Analysis.xlsx` (8.4 MB, 9 s). I inspected the zip, `docProps` and the shared strings.
8. Scripts that compared old and new `scored_*.csv` (179 rows, K only, ESPN_League only), the status, sources, run_log and seasons files, and `player_week_2026.csv`.
9. A simulated Excel re-save of the config (BOM, CRLF) and a comparison of the config hash.
10. `pytest` (689 passed, Python 3.13) on a clean `git archive HEAD` export, and `tests/test_evidence.py tests/test_scoring.py` on Python 3.11 (35 passed). `python3 NFL/maintainer/plan/validate_plan.py`: PASS, 0 errors.
11. Privacy scans: the evidence files, the diff (patterns for paths, emails, tokens, team and manager names) and the three commit messages and authors.

Side effect: `python -m nflpipe check` and run 1 write their report to `NFL/.work/last-run` or my own report directory; `NFL/.work/last-run` was overwritten once by `check` (git-ignored scratch).
