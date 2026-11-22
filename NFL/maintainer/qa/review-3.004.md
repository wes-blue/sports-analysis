# Review of roadmap 3.004 (Q1 QA Reviewer, independent)

Branch `agents/pensive-noether-dxfoz6`, head `8266215`, compared with `origin/main`. Scratch work is in `NFL/.work/r304/` (git-ignored). Nothing was committed, and `NFL/04-data/` was not touched.

## Verdict

**PASS, with one Major and four Minor findings. No Critical finding.** The scoring change does exactly what D-052 says and nothing more. All 13 gates pass on a full independent run. Both Python versions pass the full suite. The Major finding is a wording and evidence-strength issue in the `fg_blocked` note, which publishes to `04-data/config/`. It does not block the merge if the owner accepts the wording.

## What I re-derived

| Check | Result |
|---|---|
| Config cells changed (parsed with `csv`, before and after) | In `scoring_weights.csv`, only `fg_blocked`/`ESPN_League` 0 to -1 differs in any non-text cell. In `bonus_rules.csv`, no non-text cell differs. Every other difference is in the `Notes` column (13 rows) or, once, the `Description` column (`dst_points_allowed_excl_def`). |
| Formatting | Both files have no BOM, LF endings and a final newline, as before. The diff shows only the changed rows and no "no newline" markers. The quoting changes only on rows whose text lost its comma. |
| Internal reference IDs left in the two config CSVs | None (grep for `D-0nn`, `Q-0nn`, `BLOCKERS`). |
| Delta scorer (own code on `04-data/player_week/*.csv`) | 179 player-games, total -183. Four games are at -2 and 175 at -1. Every affected row is a kicker. No non-K row has `fg_blocked` greater than 0. |
| Per season (games / total) | 2017 23/-23; 2018 11/-11; 2019 18/-19; 2020 12/-13; 2021 15/-16; 2022 28/-28; 2023 19/-19; 2024 19/-19; 2025 23/-24; 2026 11/-11. This agrees with the builder's counts. |
| 2026 games | W2 Santos CHI; W2 Loop BAL; W3 Aubrey DAL; W3 Smack GB; W4 Pineiro SF; W4 Aubrey DAL; W5 Mevis LA; W7 Reichard MIN; W7 Smack GB; W8 Myers SEA; W11 Shrader IND. All are -1. |
| Full pipeline run | `run --seasons all --force`, with data and cache copies in `NFL/.work/r304/run/`, gave PUBLISH with exit 0. In all 10 `scored_*.csv` files, the only column that differs from the published files is `FF_ESPN_League`. It changes in exactly 179 rows, and each change equals my expected delta (0 mismatches, total -183). All `player_week_*.csv` and `long_td_*.csv` files are byte-identical to the published ones. Other differences are metadata only: `status.csv` (run id, time, `config_sha256`), `sources.csv`, `seasons.csv` timestamps, `manifest.csv`, `dictionary.csv` (notes), `checks/*` and the `config/*` copies. |
| Gates (13) | All PASS. G-GOLDEN: "all 125 golden values reproduced exactly", so it checks `ESPN_League` and does not WARN. G-ESPN: "55 of 55 ... 48 exact, 7 within tolerance (D/ST +/-1); D/ST stat columns all 217 equal". |
| `fixture_contracts.csv` hash | `ccd67c66...` equals the `contract_ESPN_League` that my run wrote to `status.csv`. |
| Tests | `venv` (Python 3.13.18): 689 passed. `venv311` (Python 3.11.18): 689 passed. |
| Mutation test | I set `fg_blocked`/`ESPN_League` to 0 and ran `tests/test_scoring.py`. `test_blocked_field_goal_costs_one_point_in_espn_league_only` fails (`assert 0.0 == -1`). I restored the file from a backup, and its SHA-256 matches the original (`a8ab357c...`). `git status` is clean. |
| Evidence against fixtures (own parser) | All 10 Allgeier weeks match `espn_actuals.csv` exactly, with tolerance 0. All 21 IND and NYJ D/ST weeks match `espn_dst_stats.csv` (TD, INT, FR, SCK, SFTY, BLK, PA). All 19 new D/ST point rows match FPTS with tolerance 1. NYJ week 8 (161) was already on `main` and is correctly not duplicated. |
| D/ST differences | Seven rows differ in `espn_reconciliation.csv`: NYJ W6 -1, W7 +1, W8 -1, W10 +1; IND W3 +1, W9 -1; ARI W8 -1. None exceeds 1. Two of these (NYJ W8 and ARI W8) pre-date this change. The ±1 matches the D-021 convention for the tackle and return-yard inputs. |
| Config notes that make claims | The week-8 Myers claim holds: nflverse has `fg_att` 2, `fg_made` 1, `fg_missed` 0 and `fg_blocked` 1. "A block is never also counted in `fg_missed`" holds: in all 179 blocked-kick rows, `fg_att` equals made + missed + blocked. The Allgeier 63-yard rush TD claim holds: the published row has `rush_td_40` 1 and `rush_td_50` 1, and a score of 46.1 (G-ESPN tolerance 0) needs both. "Safeties do not count", "special-teams TDs and blocked-kick returns still count" and "the extra point after a defensive TD still counts" are each supported by a game (IND W11, NYJ W8 and IND W6, IND W8). |
| Public safety | The diff and the three evidence files contain no email, path, token, name of the owner, fantasy team or manager name, or private repository name. The only names are NFL players and teams. |

## Version policy (item 5)

I agree with the orchestrator. `VERSIONING.md` line 74 says: "A change to scoring arithmetic or to a derived-metric rule raises MINOR". It speaks of arithmetic and derived-metric rules, which live in code. This change touches no code. `config_sha256` is built for config changes: it moved from `65eabafe...` to `3535932a...`, and `resolve.py` and `run.py` rebuild every season on a changed config. The history agrees: pipeline 1.2.0 and 1.2.1 were code releases, and the D-021 weight changes were config. `pipeline_version` stays 1.2.1.

## Findings

### Major

**M1. The `fg_blocked` note states as fact something that one ESPN stats page supports.**
- Evidence: `scoring_weights.csv` says "ESPN_League: -1, because ESPN counts a blocked field goal as a missed one."
  - D-052 says the proof is one ESPN.com stats page (week 8, J. Myers, "1 of 2 made"). It was not a fantasy game log with points. D-052 adds that "the week-8 Seattle kicker score would confirm it".
  - No row in `espn_actuals.csv` is a kicker, and `golden_sample.csv` has no `fg_blocked` column. So no gate exercises the -1. G-GOLDEN and G-ESPN would pass on any value. Their only guard is the `fixture_contracts` hash, which makes them report "not applicable" if the rules change.
  - The only protection of the new value is the unit test. The change rescored 179 published games across 10 seasons.
  - This note is copied into the public `04-data/config/scoring_weights.csv`.
- Fix:
  - (a) Reword to say what is known: "ESPN's stats page counts a blocked field goal among the attempts not made (2026 week 8, J. Myers, SEA v CHI: 1 of 2 made; nflverse has one blocked and none missed). Not yet checked against a kicker's ESPN fantasy score."
  - (b) When the owner can supply a kicker game log with a blocked field goal (Myers week 8 is the obvious one, and Aubrey W4 or Shrader W11 would also do), add it as a K row in `espn_actuals.csv` so G-ESPN covers the weight. Record it as an open item in MEMORY.md and the plan.

### Minor

**m1. D-055 and the config note disagree about safeties.** D-055 says the safety case "stays on its default for lack of an example". The `dst_points_allowed_excl_def` description says "safeties do not count" is confirmed. The logs do contain a case: IND week 11 (HOU scored 26 including a safety on a scrimmage pass; ESPN PA is 24, which equals the pipeline's value). The description is right, but it should say "a safety on a scrimmage play". D-055 should be corrected, since it understates the evidence. Safeties on non-scrimmage plays remain unproven.

**m2. Stat-row count.** The brief and the builder say 20 rows were added to `espn_dst_stats.csv`. The diff adds 21 (IND 11, NYJ 10), and D-055 says "all 21 games". The files are consistent. Only the quoted count is off, so correct any text that says 20.

**m3. `NFL/CONTRACTS.md` lines 79 to 81** still describe the evidence as "the ESPN game log of the Arizona D/ST for 2026 weeks 1–10". That is now only a third of the evidence. Update it to name the Colts and Jets logs and the Allgeier log (the D-055 findings). I did not edit it.

**m4. Visitor-page wording.** `NFL/06-qa/README.md` now says "ESPN game logs from the owner's league". That signals that a private league exists, and "the owner" is the maintainer's vocabulary. A visitor-facing wording such as "ESPN Fantasy game logs for a league whose scoring this project reproduces" matches `CLAUDE.md` §2 better. The evidence headers say "the owner's ESPN league scoring" and "pasted by the owner in chat". Both are low risk and consistent with the pre-existing Arizona header, so this is cosmetic.

## Limits of this review

- I could not compare the evidence files with the owner's original paste, which is not in the repository. I checked their internal consistency instead: whole 10- or 11-column rows, and week numbers running from 1 to the last week. I also checked the headers' statements about what was left out. The values agree with `espn_actuals.csv`, `espn_dst_stats.csv` and the pipeline's own scores.
- My `--force` run re-downloaded nflverse files. The upstream `games.csv` had changed by 3 bytes, with no effect on any derived value (all `player_week` and `long_td` files are identical).
- I did not run the workbook export, because the change does not touch it.

## What I ran

- `git diff origin/main` on the three paths. My own CSV parse of both config files, before and after (`NFL/.work/r304/cfg.py`).
- My delta scorer (`NFL/.work/r304/delta.py`) and my comparison script (`NFL/.work/r304/cmp.py`).
- A full pipeline run into `NFL/.work/r304/run/` using `../.work/venv311/bin/python`.
- `pytest` (689 tests each) on `venv` and `venv311`, from `NFL/03-pipeline/`.
- The mutation test on the config, restored to the exact original.
- Direct checks of the raw `stats_player` files (attempts equal made + missed + blocked in all 179 rows), the pbp files (IND W8 extra point, IND W11 safety) and the evidence files.
