# Independent re-test of roadmap 3.004 (Q1 QA Reviewer)

Branch `agents/pensive-noether-dxfoz6`, head `6931340`, compared with `origin/main` (`e7564b1`, an ancestor of the head). I did not build or review this change. I re-derived the results below and did not rely on the earlier reports. Scratch work is in `NFL/.work/rt304/` (git-ignored). Nothing was committed, and `NFL/04-data/` was not touched.

## Verdict

**Ready to merge.** No Critical or Major finding remains. There are three new Minor findings, all wording. None affects data, gates, the workbook or the workflows.

## Findings from the two earlier reports

| ID | Finding | State | Evidence |
|---|---|---|---|
| Review M1 | `fg_blocked` note overstated its evidence | **Fixed** | The note now says "ESPN's statistics count a blocked field goal as a missed attempt", cites J. Myers 2026 week 8 (nflverse shows one block and no miss; ESPN shows 1 of 2 made), and says "Not yet confirmed by an ESPN fantasy score". D-052 says the same. No claim goes beyond that evidence. "The other leagues score 0" is true: `League_1` has `fg_blocked` 0. |
| Review m1 | Safety wording | **Fixed in D-055**, partly in config | D-055 now says a safety on a scrimmage play is subtracted (IND week 11). The config description says "safeties do not count" with no qualifier. See N1. |
| Review m2 | Row count (20 or 21) | **Fixed**, one stale mention | `espn_dst_stats.csv` went from 10 to 31 rows (+21: IND 11, NYJ 10). D-055 says 21. `adversarial-3.004.md` still says "20 `espn_dst_stats` rows". See N3. |
| Review m3 | `CONTRACTS.md` evidence list | **Fixed** (list), stale sentence after it | The list now names the Arizona, Indianapolis and Jets logs. See N1. |
| Review m4 | Visitor wording in `06-qa/README.md` | **Fixed** | It now reads "ESPN Fantasy game logs in one league's scoring". No "owner" and no decision numbers. |
| Adversarial M1 | D/ST rows 1 point off need tolerance 2 | **Fixed** | See below. |
| Adversarial m1 | `MEMORY.md` out of date | **Fixed** | It names D-055, the built, reviewed and attacked 3.004, and the open Myers ask. `validate_plan.py` passes with 0 errors. |
| Adversarial m2 | `fg_blocked = -1` not exercised by a gate | **Accepted** | A Myers fantasy game log is requested. The unit test covers the rule meanwhile. The review's mutation test showed it fails when the weight is 0. |
| Adversarial m3 | Third-party and personal-looking text in `BLOCKERS.csv` on `main` | **Accepted** | It belongs to the owner and is not part of this change. The branch changes only `Raised` date format (reverted from Excel's format), `Status` and `Claude_Response`. Every `Answer` cell is identical to `main`. The only other change is a trailing space removed from the Q-021 question. |
| Adversarial m4 | A note-only config edit republishes everything | **Open, optional** | The suggested line in `02-config/README.md` was not added. It has no effect on this merge, and the repeat merge run is harmless. |
| Adversarial m5 | Interpretation only | None needed | |

### Adversarial M1 in detail

My own comparison of `NFL/06-qa/fixtures/espn_actuals.csv` with `FF_ESPN_League` in the scored data of my run found 54 present rows and 1 row marked `row_expected = No`.

- 22 player rows: difference 0, tolerance 0.
- 25 D/ST rows: difference 0, tolerance 1.
- **7 D/ST rows: difference exactly 1, tolerance 2.** They are 2026 ARI week 8 (ESPN 225, ours 224), IND week 3 (122, 123), IND week 9 (174, 173), NYJ week 6 (208, 207), NYJ week 7 (115, 116), NYJ week 8 (161, 160) and NYJ week 10 (195, 196).

These are exactly the rows named in the adversarial report. No other row has a non-zero difference.

Documentation:
- `NFL/CONTRACTS.md` §6, row G-ESPN, states the rule: "within the row's `tolerance`: 1 point, or 2 on the rows whose score already differs from ESPN's by 1".
- `NFL/03-pipeline/AUTOMATION.md` gives the remedy: check the new value against the log in `NFL/06-qa/evidence/` and raise that row's `tolerance` by one in a pull request.
- The tests accept 1 or 2, and I checked that the D/ST rows added in this change correspond to the evidence files.

## Config integrity

I parsed both changed files with `csv`, before and after.

- The only changed non-text cell is `fg_blocked` / `ESPN_League`, 0 to -1, in `scoring_weights.csv`.
- `bonus_rules.csv` has no non-text change. Its 18 changes are all `Notes`.
- `scoring_weights.csv` has 12 other changes, all in `Notes` or `Description`.
- `leagues.csv` and `pipeline_config.csv` are byte-identical to `main`.
- All four files have no BOM, no CR and a final LF, as on `main`.
- Quoting changes only on rows whose text lost a comma.
- No `D-nnn`, `Q-nnn` or `BLOCKERS` appears in any config cell.
- Claims checked: the `rush_td_40` and `rush_td_50` notes ("a 63-yard rushing TD scored both") agree with the 46.1 Allgeier row, which matches at tolerance 0. The `fg_blocked` claim is covered above.

## Full run

Command: `python -m nflpipe run --seasons all --force --trigger rt304`, with `--data-dir`, `--cache-dir` and `--report-dir` under `NFL/.work/rt304/` and `../.work/venv311/bin/python`. A copy of the published `04-data` was the data directory. Result: **PUBLISH, exit 0, 51 s, 21 files written.**

- **13 of 13 gates PASS.**
  - G-GOLDEN: "all 125 golden values reproduced exactly".
  - G-ESPN: "55 of 55 ESPN values reproduced: 48 exact, 7 within tolerance"; D/ST stat columns all 217 equal.
  - Neither is a WARN, so both check `ESPN_League`.
- **Scored diff.**
  - 10 files, 179 rows changed, total **-183**.
  - Only `FF_ESPN_League` changes, with 0 changes in any other column.
  - Every changed row is a kicker.
  - Every change equals `-fg_blocked` of the same row in `player_week` (0 mismatches).
  - Per season (rows / total): 2017 23/-23; 2018 11/-11; 2019 18/-19; 2020 12/-13; 2021 15/-16; 2022 28/-28; 2023 19/-19; 2024 19/-19; 2025 23/-24; 2026 11/-11.
- **`player_week`** (10 files) and `long_td` (10 files) are **byte-identical** to the published ones. The other 21 files that differ are the 10 `scored` files, the config copies, the check files, `dictionary.csv`, `manifest.csv`, `run_log.csv`, `seasons.csv`, `sources.csv` and `status.csv`. They are the expected files, not a surprise.
- **Workbook.**
  - `python -m nflpipe export --data-dir <my data>` wrote an 8.0 MB file. The zip is valid and has the 8 sheets. `PlayerGames` has 180,301 rows.
  - The About sheet shows run id `20261122T012120Z`, which equals `run_id` in my `status.csv`.
  - The title still says 3.002, as expected for an unchanged design.
  - The core properties name only "NFL-Analysis pipeline".

## Tests and CI

- Full tests: `../.work/venv/bin/python` (Python 3.13.18) **689 passed**; `../.work/venv311/bin/python` (3.11.18) **689 passed**.
- `config-check` command from `nfl-pipeline-ci.yml` (`run --seasons current --dry-run --trigger pull_request-check`), against a copy of the published data: exit 0, 13 of 13 PASS, "would publish 16 changed data file(s)". The copy was unchanged afterwards (`diff -rq`).
- `actionlint` (`NFL/.work/c1/actionlint-dl/actionlint`) on all workflows: exit 0, no findings.
- `git diff origin/main --stat -- NFL/04-data .github`: empty.
- `validate_plan.py`: PASS, 0 errors.

## Merge effect

I do not expect the merge run to be red.

- The config hash changed, so `resolve` returns "run" and every season is rebuilt. This is what my `--force` run did. It took about 51 s, against a 45-minute limit.
- The data commit is the 21 files above. `nfl-pipeline-ci` runs the tests, which pass.
- The only blocking gate that reads the new data is G-ESPN, and it passes on today's upstream data.
- The remaining exposure is a late nflverse correction to an ESPN-checked D/ST game. For the 7 rows at tolerance 2 a one-unit correction is now absorbed. For the 25 rows that match exactly, a correction of 1 is still inside tolerance 1, and a correction of 2 would not be. The `espn_dst_stats` columns stay exact by design. A failure would be a safe HOLD: old data and workbook kept, an alert issue opened, and the remedy is in `AUTOMATION.md`.
- Upstream data matched my run and the published `player_week` byte for byte, so nothing has moved.

## Privacy

I scanned every added line of the diff and the five commits since `origin/main`. Patterns: email, local paths (`/home`, `/Users`, drive letters), tokens, passwords, cookies, "manager", team and league names.

- No hit. The `@` matches are NFL team abbreviations.
- The three evidence files carry generic headers ("the owner's ESPN league scoring", "pasted by the owner in chat"), which is the wording of the Arizona header already on `main`. They name no account, team, manager or league.
- The commit author is `Claude <noreply@anthropic.com>`, with the standard trailers.
- Checked separately: the added lines of `BLOCKERS.csv` contain no email, path or manager name. Third-party ESPN text already on `main` is covered by the accepted adversarial m3.

## New findings (all Minor)

**N1. `CONTRACTS.md` §3 still says the safety, special-teams-TD and blocked-kick cases are assumptions.**
- Line 81 ends with: "The evidence does not show ESPN's treatment of special-teams touchdowns, blocked-kick returns ... or safeties; the choices above are assumptions until the maintainer confirms them against ESPN."
- This contradicts D-055 and the published `dst_points_allowed_excl_def` description ("Confirmed against ESPN game logs"). D-055 confirms special-teams TDs (Jets week 8), the blocked-punt case (Colts week 6) and a safety on a scrimmage play (Colts week 11). It does not confirm a safety on a non-scrimmage play.
- The config description says "safeties do not count" with no qualifier, which is slightly wider than the evidence.
- Fix: update the sentence in §3 and add "on a scrimmage play" to the description. This is a wording fix that can follow the merge. A config text edit republishes all seasons once more, so bundle it with the next change.

**N2. The G-ESPN detail text is hard-coded as "D/ST +/-1".**
- The run says "7 within tolerance (D/ST +/-1)" (`nflpipe/gates.py` line 844), but the seven rows are now at tolerance 2.
- The message is published in `04-data/checks/` and the run summary. It is cosmetic. Fixing it changes code in `nflpipe/` and so republishes. Not worth a separate run.

**N3. `adversarial-3.004.md` quotes "20 `espn_dst_stats` rows".** The real number is 21 (IND 11, NYJ 10). Historical report text only.

## What I ran

All in `/home/user/sports-analysis`, with files under `NFL/.work/rt304/`.

1. `git fetch`, `git diff origin/main --stat`, `git log origin/main..HEAD`, and a read of both reports, D-052, D-055 and the diffs of config, `CONTRACTS.md`, `AUTOMATION.md`, `06-qa/` and `MEMORY.md`.
2. `cfg.py`: parse the config before and after, check the BOM, CR and final LF, and search for internal IDs.
3. The full run (command above) into a copy of `04-data`, then `cmp.py` (scored diff against `player_week`), `cmp -s` on every `player_week` and `long_td` file, and `diff -rq`.
4. `tol.py`: `espn_actuals.csv` against `FF_ESPN_League` from my run's scored files.
5. `python -m nflpipe export` and an inspection of the zip: sheets, About run id, core properties.
6. `pytest -q` from `NFL/03-pipeline/` on both interpreters.
7. The CI `config-check` command on a second copy of the published data, `actionlint`, `git diff origin/main --stat -- NFL/04-data .github`, and `validate_plan.py`.
8. A `BLOCKERS.csv` comparison by column, `main` against the head, plus privacy scans of the added lines and the commit messages.
