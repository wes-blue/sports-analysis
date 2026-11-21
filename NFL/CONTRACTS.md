# Interface Contracts: NFL-Analysis Pipeline

These are the file formats and command behaviours that the pipeline, the GitHub Actions workflows and the workbook hand to each other.

This file lives in the repository `wes-blue/sports-analysis` (public). Each sport has its own top-level folder; this is the contract for `NFL/`. **Paths are relative to `NFL/`** unless they start with `/`, which means the repository root (for example `/.github/workflows/`, `/BLOCKERS.csv`, `/00-Governance/`).

Changing a contract needs the orchestrator's approval, because it breaks other members' work. The data contract version is **1**; it is written to `04-data/status.csv` as `data_contract_version`. Adding a metric (a new row in `scoring_weights.csv`, and so a new column in `player_week`) does not change the contract version, because §5.1 defines the metric columns as whatever the config lists; readers must find columns by name.

**Published data address.** Once on the default branch `main`, every file under `04-data/` is readable by anyone at
`https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/<path>`.
This is the address the workbook reads by default.

## 0. Architecture in one picture

```
nflverse releases (public)        02-config/*.csv (you edit)
  stats_player_week_<season>.csv    leagues, weights, bonus bands, settings
  stats_team_week_<season>.csv              |
  schedules/games.csv                       v
  play_by_play_<season>.csv.gz ---> 03-pipeline  (Python, standard library only)
                                    ingest -> derive long-TD and Team D/ST -> score -> gates
                                            |
                                            v  PUBLISH only if every blocking gate passes
                                    04-data/*.csv   (plain CSV files, committed)
                                            |
                                            v
                                    python -m nflpipe export  (§13)
                                            |
                                            v
                                    NFL-Analysis.xlsx  (values only; GitHub Release asset)
                                    the owner downloads it and opens it: nothing to refresh
```

GitHub Actions (`/.github/workflows/nfl-pipeline-*.yml`) runs the same command on a schedule, and whenever `02-config` changes on `main`, commits `04-data`, and then builds and publishes the workbook (§13.5). The owner's PC needs only Excel: no Python, git, copy of the repository or Power Query. Anyone can also read the CSV files in `04-data` from the web address above.

## 1. Config files: `02-config/` (inputs; the single source of scoring rules)

All are UTF-8 CSV with a header row.

| File | Columns | Rules |
|---|---|---|
| `pipeline_config.csv` | `Setting,Value,Allowed_Values,Description` | Settings: `StartSeason`, `EndSeason` (a year, `Latest` or `Latest-N`), `SeasonTypes` (`REG`, `POST`, `REG+POST`), `RoundDecimals` (0–6), `PublishExtraColumns` (blank, a comma list of nflverse columns, or `ALL`), `ReconcileTolerance`. |
| `leagues.csv` | `League,Description,Active,Reconcile_To,Notes` | `League` is an identifier (letters, digits, underscore; starts with a letter) and exactly matches a column header in `scoring_weights.csv`. `Active` is `Yes` or `No`. `Reconcile_To` is `fantasy_points`, `fantasy_points_ppr` or blank. |
| `scoring_weights.csv` | `Metric,Category,Description,<one column per League, same order as leagues.csv>,Notes,Applies_To` | `Metric` is an nflverse `stats_player_week` column or a derived metric (§3). Weights are numeric; blank counts as 0. `Applies_To` is the position gate (§4). |
| `bonus_rules.csv` | `League,Metric,Lower,Upper,Points,Applies_To,Notes` | A row awards `Points` when `Lower ≤ value ≤ Upper`. A blank bound means no limit on that side. Bands are independent: overlapping bands stack, disjoint bands do not. |

**"Latest"** means the newest season for which nflverse has published `stats_player_week_<season>.csv`. An `EndSeason` after the newest published season is clamped to it (gate G-WINDOW names the unpublished seasons). A `StartSeason` after the newest published season is an error, because no season would be left. `Latest-9` to `Latest` is a rolling 10 seasons (2017–2026 today).

## 2. Upstream sources

Base: `https://github.com/nflverse/nflverse-data/releases/download/`

| Kind | Path | Used for |
|---|---|---|
| `stats_player` | `stats_player/stats_player_week_<season>.csv` | Player rows (150 columns). Rows with an empty `player_id` are placeholders and are dropped. |
| `stats_team` | `stats_team/stats_team_week_<season>.csv` | Team D/ST rows. |
| `schedules` | `schedules/games.csv` | Final scores (points allowed), season types, week calendar. |
| `pbp` | `pbp/play_by_play_<season>.csv.gz` | Long-TD counts. |

All upstream content is untrusted data: parse it, never execute it.

## 3. Derived metrics

**Long TDs** (per player-game, from play-by-play; same rules as the 1.x `LongTD.pq` and `build_long_td_static.py`):
- Only plays with `touchdown = 1` and `pass_touchdown = 1` or `rush_touchdown = 1`. Length is `yards_gained`.
- Pass TD: `passer_player_id` gets `pass_td_40` / `pass_td_50`; `td_player_id` (the scorer, so laterals are credited correctly) gets `rec_td_40` / `rec_td_50`.
- Rush TD: `td_player_id` gets `rush_td_40` / `rush_td_50`.
- Counts are cumulative: a 55-yard TD adds 1 to both the `_40` and the `_50` column.

**Team D/ST rows** (one per team-game; same rules as the 1.x `Team_DST.pq` and `engine105.py`, reconciled to ESPN in D-021):
- `player_id = DST_<TEAM>`, `position = DST`, `position_group = DST`, `player_display_name = "<TEAM> D/ST"`.
- `dst_sacks`, `dst_interceptions`, `dst_fumble_recoveries` (opponent fumbles only), `dst_fumbles_forced`, `dst_safeties`, `dst_blocked_kicks` (punt + PAT + FG blocks), `dst_tackles` (solo + assists + tackles-with-assist), `dst_kr_yards`, `dst_pr_yards`, `dst_int_tds`, `dst_fumble_tds`, `dst_st_tds`, `dst_2pt_returns`.
- `dst_points_allowed` = the opponent's full final score from `games.csv`. Blank until the game has a final score. **Missing is never zero.**
- `dst_points_allowed_excl_def` = the opponent's final score minus the points the opponent's **defense** scored against this team's offense; never below 0. Counted from play-by-play:
  - 6 for a touchdown on a scrimmage play (pass, run, kneel, spike) where the scoring team was on defense (an interception or fumble returned for a touchdown);
  - 2 for a safety that the defense scored on a scrimmage or penalty play;
  - 2 for a two-point try (a scrimmage play) returned by the defense.

  Kick and punt plays never count, so special-teams touchdowns (including a blocked kick returned for a touchdown) stay in points allowed, and so does the extra point after a defensive touchdown. Blank until the game has a final score and play-by-play has its plays. The team-stats file cannot give this alone: its `fumble_recovery_tds` mixes defensive returns with an offense recovering its own fumble in the end zone.

  This is ESPN's "points allowed" as far as the owner's evidence shows (`06-qa/evidence/`, the ESPN game log of the Arizona D/ST for 2026 weeks 1–10): in week 4 the opponent scored 36 including one defensive touchdown and ESPN counts 30, and the metric reproduces ESPN's points-allowed column in all ten weeks. The evidence does not show ESPN's treatment of special-teams touchdowns, blocked-kick returns (including a blocked extra point returned for 2, which is a kick play and so is not subtracted), or safeties; the choices above are assumptions until `/BLOCKERS.csv` Q-019 is answered. The ESPN league's points-allowed bands use this metric (decision D-038).
- `dst_points_allowed_excl_def_st` (an older approximation from the team-stats file that also subtracts special-teams touchdowns and an offense's own end-zone fumble recoveries) is kept at weight 0 for reference; it is not ESPN's rule.
- `dst_yards_allowed` = opponent passing yards + rushing yards + sack yards lost (net yards).

## 4. Scoring semantics (Python; the 2.x Power Query mirrored it)

For one row and one league:

1. **Linear:** sum of `weight × value` over every metric whose position gate allows the row. A null value counts as 0.
2. **Bands:** add `Points` for each bonus row of that league where the value is not null, `Lower ≤ value ≤ Upper` (inclusive; a blank bound is open), and the gate allows the row.
3. **Position gate (`Applies_To`):** blank allows every row. Otherwise it is a comma list, matched case-insensitively against the row's `position` **or** `position_group`.
4. **Rounding:** the sum is first rounded to 9 decimals, which removes binary floating-point noise, and then rounded half away from zero to `RoundDecimals`. (Added in pipeline 1.1.0 after QA finding m-02: without the first step, a sum that is exactly 13.5 could be stored as 13.499999999999998 and round down when `RoundDecimals` is 0. No published value changes at 2 decimals.)
5. The result column is named `FF_<League>`.

## 5. Published data: `04-data/` (outputs)

Common rules for every file:
- UTF-8 without a byte-order mark, comma-separated, a header row, `\n` line endings, RFC 4180 quoting.
- **Blank means null** (not applicable or not yet known). A real zero is written as `0`.
- Whole numbers have no decimal point. Other numbers use the shortest text that round-trips.
- Rows are sorted by `season`, `week` (numeric), `season_type`, `player_id`, so re-runs produce identical bytes when nothing changed.
- A file is rewritten only when its content changes.

### 5.1 `player_week/player_week_<season>.csv`: the scoring-ready table

One row per player-game plus one row per team D/ST game.

Columns, in order:
1. `season,week,season_type,player_id,player_display_name,position,position_group,team,opponent_team`
2. One column per metric, in `dictionary.csv` order: every `Metric` in `scoring_weights.csv` (file order), then any `bonus_rules.csv` metric not already listed, then `PublishExtraColumns`.
3. `fantasy_points,fantasy_points_ppr` (nflverse's own figures; blank on D/ST rows).

Player rows carry real values for nflverse and long-TD metrics and blanks for `dst_*` metrics. D/ST rows carry values for `dst_*` metrics and blanks elsewhere.

### 5.2 `scored/scored_<season>.csv`: the pipeline's own scores

Columns: `season,week,season_type,player_id,player_display_name,position,team,fantasy_points,fantasy_points_ppr`, then `FF_<League>` for each Active league in `leagues.csv` order. Same rows and order as the matching `player_week` file.

### 5.3 `long_td/long_td_<season>.csv`

Columns: `season,week,season_type,player_id,pass_td_40,pass_td_50,rush_td_40,rush_td_50,rec_td_40,rec_td_50`. Only player-games with at least one long TD.

### 5.4 Index and run files

| File | Columns |
|---|---|
| `seasons.csv` | `season,season_type,player_rows,dst_rows,max_week,season_status,refreshed_utc`. One row per season and season type. `season_status` is `complete` or `in_progress`. |
| `sources.csv` | `season,kind,url,last_modified,size_bytes,sha256,fetched_utc`. One row per upstream file used. `last_modified` is the upstream HTTP `Last-Modified` in ISO 8601 UTC. `season` is blank for `schedules`. |
| `manifest.csv` | `file,kind,season,rows,columns,size_bytes,sha256,written_utc`. One row per published file except `manifest.csv` itself. `file` is the path relative to `04-data/` with `/` separators. |
| `status.csv` | `key,value`. Keys: `run_id`, `generated_utc`, `pipeline_version`, `data_contract_version`, `outcome`, `window_start`, `window_end`, `season_types`, `latest_season`, `latest_week`, `latest_season_type`, `upstream_last_modified_max`, `config_sha256`, `gates_pass`, `gates_warn`, `gates_fail`, `seasons_refreshed`, `data_source` and `data_license` (the nflverse attribution), and `contract_<League>` (a hash of that league's weights and bands) for each Active league. |
| `run_log.csv` | `run_id,started_utc,finished_utc,trigger,seasons_requested,seasons_refreshed,outcome,latest_season,latest_week,latest_season_type,gates_fail,gates_warn,pipeline_version,notes`. Append-only, newest last. Only PUBLISH runs are recorded here. |
| `dictionary.csv` | `metric,category,description,source,applies_to`. `source` is `nflverse`, `derived:long_td` or `derived:team_dst`. One row per metric column of `player_week`, in column order. |
| `config/leagues.csv`, `config/scoring_weights.csv`, `config/bonus_rules.csv`, `config/pipeline_config.csv` | Normalized copies of the config used for the run, so the workbook can compare its own rules with the pipeline's. Normalized means the common rules of §5 apply: no byte-order mark, `\n` line endings, and empty trailing columns and rows (which Excel adds when it saves a CSV) removed. `config_sha256` is computed over these normalized copies, so re-saving a config file from Excel without changing a value does not trigger a rebuild. |

`04-data/README.md` is a hand-written note. It is not written by the pipeline and is not listed in `manifest.csv`.

### 5.5 Check files: `checks/`

| File | Columns |
|---|---|
| `gates.csv` | `gate_id,gate,severity,result,detail,checked_utc`. `severity` is `blocking` or `advisory`. `result` is `PASS`, `WARN` or `FAIL`. |
| `reconciliation.csv` | `league,reconcile_to,season,rows_compared,rows_matched,max_abs_diff,match_pct`. One row per control league and season, plus a row with `season = ALL`. |
| `row_counts.csv` | `season,season_type,baseline_rows,actual_rows,difference,status`. Baseline from `06-qa/fixtures/row_count_baseline.csv` (`expected_stats_raw_rows`). |
| `golden.csv` | `season,week,season_type,player_id,player_display_name,league,expected,actual,difference,status`. Expected values from `06-qa/fixtures/golden_sample.csv`. |
| `espn_reconciliation.csv` | `season,week,season_type,player_id,player_display_name,league,espn_points,our_points,difference,tolerance,status,note`. ESPN values from `06-qa/fixtures/espn_actuals.csv`. |
| `espn_dst_stats.csv` | `season,week,season_type,player_id,player_display_name,stat,espn_value,our_value,our_columns,status,note`. ESPN's own stat columns for a team defense (TD, INT, FR, SCK, SFTY, BLK, PA) against the published inputs, from `06-qa/fixtures/espn_dst_stats.csv`. It tests the inputs to the score, where `espn_reconciliation.csv` tests the score. |
| `restatements.csv` | `detected_utc,season,week,season_type,player_id,column,old_value,new_value`. Values in a previously published season that changed upstream. Capped at 5,000 rows per run, with the true count in `gates.csv`. |

## 6. Gates

A run publishes only when no **blocking** gate fails. Advisory gates publish with a `WARN`.

| ID | Gate | Severity |
|---|---|---|
| G-CONFIG | Every league has a weights column; every metric exists in the data or is derived; bands are well-formed; no unknown setting. | blocking |
| G-GRAIN | `season, week, season_type, player_id` is unique in every `player_week` file. | blocking |
| G-RECON | Each control league equals its nflverse reference within `ReconcileTolerance` on at least 99.9% of rows (it was 100% in 1.x). Like G-GOLDEN, it applies only while the control league's rules match `fixture_contracts.csv`; a control league the user has changed is reported as WARN. When `RoundDecimals` is below 2 the tolerance widens to half a unit of the last kept decimal. | blocking |
| G-GOLDEN | Every golden-sample value is reproduced exactly, for each league whose rules still match the rules the expected values were made with (`06-qa/fixtures/fixture_contracts.csv`: league, rules hash, `RoundDecimals`). A league whose rules the user has changed is reported as WARN "not applicable" and never holds the publish. | blocking |
| G-ESPN | ESPN actuals: players exact; D/ST within ±1 point (the nflverse feed differs from ESPN's by a tackle in places). ESPN's D/ST stat columns, points allowed included, must match exactly. The same rule as G-GOLDEN applies when the league's rules have changed. | blocking |
| G-DST | Every team-game in `stats_team` has a D/ST row; finished games have `dst_points_allowed`; unfinished games leave it blank; the defensive scores counted from play-by-play agree with the team-stats file. | blocking |
| G-SHRINK | No season loses more than 1% of its rows compared with the last publish. | blocking |
| G-ROWS | Completed seasons match the row-count baseline. | advisory |
| G-LONGTD | Completed-season long-TD totals match `06-qa/fixtures/long_td_baseline.csv`. | advisory |
| G-RESTATE | Counts values that changed in previously published completed seasons (nflverse back-corrects old games). Differences caused by the user's own config change (for example `SeasonTypes`) are not restatements and are not logged as such. | advisory |
| G-WINDOW | The season window asks only for published seasons. An `EndSeason` after the newest published season is clamped to it and the unpublished seasons are named; the run does not fail. | advisory |
| G-OVERLAP | No league weights both a total and its components (for example `fumbles_lost_total` with the sack, rushing and receiving fumble columns, or `fg_missed` with the `fg_missed_<range>` columns), and every `Applies_To` code is a position or position group that exists in the data. | advisory |
| G-INDEX | `seasons.csv` row counts equal the rows in each `player_week` file; `scored` files have the same keys in the same order; `season_type` is only `REG` or `POST`; `manifest.csv` hashes match the files. | blocking |

## 7. Command line: `03-pipeline/`

Run from `03-pipeline/` as `python -m nflpipe <command>`. Python 3.11 or later. **Run time uses the standard library only**; `pytest` is needed only for tests.

Common options: `--config-dir` (default `../02-config`), `--data-dir` (default `../04-data`), `--fixtures-dir` (default `../06-qa/fixtures`), `--cache-dir` (default `../.work/cache`), `--report-dir` (default `../.work/last-run`).

| Command | Does | Exit codes |
|---|---|---|
| `run --seasons current\|all\|YYYY\|YYYY-YYYY [--dry-run] [--force] [--trigger TEXT]` | Ingests, derives, scores, runs the gates and publishes. `current` refreshes the latest season, plus any other season in the window whose upstream `Last-Modified` changed since `sources.csv` was written. `--dry-run` does everything except change `--data-dir`. Gate results always go to `--report-dir`. | `0` PUBLISH, `3` SKIP (nothing changed), `4` HOLD (a blocking gate failed; `--data-dir` untouched), `1` error |
| `check` | Read-only: verifies `manifest.csv` hashes and the structural gates against what is published. | `0` pass, `4` fail |
| `resolve` | Decides whether there is work to do: reads the schedule for the latest finished week, the upstream `Last-Modified`, and `status.csv`. It also says `run` when the config in `--config-dir` or the pipeline version differs from what `status.csv` records, so a pushed scoring change is published at the next scheduled attempt. Prints `key=value` lines and appends them to `$GITHUB_OUTPUT` when that variable is set. Keys: `action` (`run` or `skip`), `season`, `week`, `season_type`, `upstream_last_modified`, `published_through`, `reason`. | `0` run, `3` skip, `1` error |
| `watchdog --max-age-hours N` | Fails when the last PUBLISH is older than N hours during the season. | `0` healthy, `5` stale, `1` error |
| `version` | Prints `pipeline_version`. | `0` |

Module ownership inside `nflpipe/` (so two engineers never edit the same file):
- **B1 Pipeline Engineer:** `__init__.py`, `__main__.py` (dispatcher), `config.py`, `http.py`, `ingest.py`, `derive.py`, `scoring.py`, `publish.py`, `run.py`.
- **B2 Gates and Test Engineer:** `gates.py`, `check.py`, everything under `tests/` except the files C1 owns. From Phase 2, B2 may also fix defects in B1's modules, reporting each change.
- **C1 Actions Engineer:** `resolve.py`, `watchdog.py`, `freshness.py`, `tests/test_resolve.py`, `tests/test_watchdog.py`, `tests/test_workflows.py`, everything under `workflows/`.

Each command module exposes `main(argv: list[str]) -> int`. `__main__.py` imports the module for a command only when that command is called.

## 8. GitHub Actions: `/.github/workflows/`

The workflow files are **installed** at the repository root (owner's instruction, `BLOCKERS.csv` Q-002). They are active once they are on the default branch `main`. `03-pipeline/AUTOMATION.md` explains them for the owner.

Every workflow sets the working directory to `NFL/03-pipeline`. The pipeline needs no package installs.

| Workflow | Trigger | Does |
|---|---|---|
| `nfl-pipeline-weekly.yml` | Tue, Wed and Thu in season (months 1, 2, 9–12), off the hour; a push to `main` that changes `NFL/02-config/**` (not its README); manual dispatch | A check for stray files in `02-config` (for example `scoring_weights (1).csv`); `resolve` on scheduled runs; `run --seasons current` (with `--force` after a config push, so every config commit ends in PUBLISH or a red run; a changed config already makes `current` rebuild every season); commit `NFL/04-data` on PUBLISH; open or update its rolling issue on HOLD or error. Started on a branch other than `main`, it is always a dry run. |
| `nfl-pipeline-monthly.yml` | The 1st of each month (`run --seasons all`, which repairs back-corrections) and the 16th (heartbeat only); manual dispatch | Both fires end with the heartbeat |
| `nfl-pipeline-watchdog.yml` | Fri in season | `watchdog`; turns red when no publish landed. It has its own concurrency group, so a queued watchdog never displaces a waiting publish. |
| `nfl-pipeline-ci.yml` | Push or pull request touching `NFL/03-pipeline/**`, `NFL/02-config/**`, `NFL/06-qa/fixtures/**` or the workflow files | `pytest`; on pull requests also `config-check`, a dry run of the pipeline with the proposed config |

**Alerts:** each scheduled workflow has its own rolling issue. An issue is closed only by a run of the same workflow that proves the problem is gone (a PUBLISH for the weekly and monthly runs, a healthy result for the watchdog). A SKIP never closes an alert.

**Config changes need no PC.** The owner edits a file in `NFL/02-config/` on GitHub (or pushes it). The push starts the weekly workflow, which rebuilds and publishes. A commit made by a workflow does not start another workflow, and the workflow commits only `NFL/04-data`, so there is no loop.

**Heartbeat.** GitHub disables scheduled workflows in a public repository after 60 days without repository activity; its documentation does not define "activity". The off-season is longer than that, so each monthly fire looks at the newest commit on `main` and, when it is 21 days old or more, pushes one empty commit (no file changes). Fires are 15 or 16 days apart, so the longest gap is under 37 days. It does nothing in season or when anyone has committed recently. Whether an empty commit made with the workflow token counts as activity is unverified until an off-season has passed.

**Security.** The repository is public. Workflows run only on `schedule`, `push`, `pull_request` and `workflow_dispatch` (never `pull_request_target`), give each job only the permissions it needs, do not leave the token on disk after checkout, pin third-party actions by commit SHA, pass inputs through `env:`, and use no secrets. The alert steps count only issues opened by the workflow's own bot, because anyone can open an issue in a public repository.

## 9. Power Query (retired, 2.x): `05-excel/archive-2.x/powerquery/`

**Retired by D-043.** This section describes the 2.x workbook, kept for the record. Its files moved to `05-excel/archive-2.x/` and are not maintained. The current workbook is §13.

`manifest.json` lists the queries in dependency order (same shape as 1.x):

```json
{"queries": [{"name": "...", "file": "....pq", "purpose": "...", "load_as": "...",
              "depends_on": ["..."], "reads_tables": ["..."], "target_version": "2.001", "status": "..."}]}
```

Each `.pq` file holds one query's complete M text.

**Firewall rule (D-009, proven in real Excel in 1.003):** a query that reads a workbook table, a file or the web must not reference another query. Queries that combine other queries read no source themselves.

**Where the data is read from:** `tblConfig` setting `DataLocation`. In the workbook as shipped it holds the published data address, so a refresh reads from the web and nothing has to be downloaded or synced first.
- A value starting with `http` reads from that web address with `Web.Contents` (a fixed base address plus `RelativePath`). **The shipped default is `https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/`.** Reading nflverse from the web this way ran in real Excel in 1.003 and 1.004.
- Blank means automatic local search: `<parent of the workbook's folder>\04-data\`, which is right when the workbook sits in `05-excel` or `08-releases` of a local copy of the repository. The workbook folder comes from the named cell `WorkbookFolder`.
- A local folder path reads files from that folder.

Workbook tables the queries read: `tblConfig` (`Setting`, `Value`), `tblLeagues`, `tblScoring`, `tblBonus` (same columns as the config CSVs), `tblGolden`. `WORKBOOK-REQUIREMENTS.md` in that folder is the exact list for the workbook builder: tables, named cells, settings with defaults, and the Checks-sheet anchor of every loaded query.

**As built (D1, 2026-11-19):**
- 15 queries. Source readers: `Stats_Raw`, `Pipeline_Scored`, `Published_Seasons`, `Pipeline_Status`, `Check_Rules_Drift` (published CSVs), `Scoring_Weights`, `Bonus_Rules`, `Golden_Keys` (workbook tables). Combiners: `Stats_Scored`, `Check_Parity`, `Check_Metrics`, `Check_Reconciliation`, `Check_RowCounts`, `Check_Golden`, `Check_Integrity`.
- `manifest.json` entries may also carry `reads_names` (named cells) and `reads_files` (published files).
- `tblConfig` also holds `ReconcileTolerance` (default 0.005, the pipeline's value).
- `Check_Parity` treats two scores as equal when they differ by no more than 0.000001. With the current rules no score sits on a rounding boundary, so the workbook and the pipeline agree exactly.
- A season the window asks for that the pipeline has not published shows as `NOT PUBLISHED`; it is not an error.
- The `.pq` files are generated: edit `05-excel/build/pq/templates/` or `snippets/`, then run `python3 05-excel/build/pq/build_pq.py`. `lint.js` in that folder checks for undefined names and firewall breaches.

## 10. Plan content: `01-plan/plan.json`

Same shape as the 1.x contract (keys `objective`, `what_you_are_trying_to_do`, `key_findings`, `architecture`, `scope_in`, `scope_out`, `roadmap`, `requirements`, `raid`, `controls`, `glossary`). `architecture[].where` may also be `Python pipeline`, `GitHub Actions` or `Published CSV`. `PLAN.md` is rendered from it.

## 11. Blockers for the owner: `/BLOCKERS.csv`

Columns: `Question_ID,Question,Answer,Type,Default_Used_Meanwhile,Options,What_It_Blocks,Raised,Status,Claude_Response`. The owner fills in `Answer`. `Type` is `Answer needed` or `Action needed`. `Status` is `Open`, `Answered` (acted on; see `Claude_Response`) or `Still open` (the answer did not settle it; a follow-up question exists). Only the orchestrator edits the other columns, and never changes or removes an answer the owner wrote. Members report blockers in their hand-back.

## 12. Releases: `08-releases/`

`RELEASES.md` is the release register. From 3.001 the workbook is a GitHub Release asset rebuilt on every publish (§13.5), and the register records each design version with the run that first published it. The 2.001 workbook (`NFL-Analysis-2.001.xlsx`) stays here unchanged for the record; its working copies moved to `05-excel/archive-2.x/`. Versions 1.001 to 1.006 were released in the owner's private repository and are listed for the record only.

## 13. The generated workbook (design generation 3.x)

**Why (decision D-041).** The owner's first refresh of the 2.001 workbook was still running after five minutes: Power Query re-scoring 180,000 rows in Excel is too slow. From 3.001 the pipeline builds the finished workbook itself, on GitHub, every time it publishes. The workbook holds **values only**: no Power Query, no formulas, no connections, no macros, nothing to refresh. Scoring is changed by editing `02-config/` on GitHub (§8); the next run rebuilds the workbook.

### 13.1 Command

`python -m nflpipe export [--data-dir DIR] [--out FILE]`, run from `03-pipeline/`. Defaults: `--data-dir ../04-data`, `--out ../.work/workbook/NFL-Analysis.xlsx`.

- Reads **only** the published files in `--data-dir` (§5). It never downloads anything and never changes `04-data`.
- Refuses (exit 1) when `status.csv` `data_contract_version` is missing or is not the version the exporter understands (today `1`), naming both values.
- Exit codes: `0` written; `1` error (message names the cause; no partial file is left at `--out`).
- **Standard library only** (D-025): the file is written with `zipfile` and XML text. Test code may use `openpyxl` to read it back.
- **Deterministic:** the same `04-data` gives byte-identical output. Time stamps inside the file come from `status.csv` `generated_utc`, never from the clock; zip entries use a fixed date and a fixed order.
- Runs in well under 5 minutes on a GitHub runner for the full window.

### 13.2 Sheets, in this order

| Sheet | Contents | Excel table |
|---|---|---|
| `About` | Title; workbook version (`3.001`); data through (`latest_season`, `latest_week`, `latest_season_type` from `status.csv`); generated (UTC); pipeline and data contract versions; gates passed / warned / failed; the data source and licence lines from `status.csv` (`data_source`, `data_license`) with the nflverse and licence addresses; where the latest file is (§13.5); how to change scoring (edit `NFL/02-config/` on GitHub, link to `NFL/03-pipeline/AUTOMATION.md`); one line per sheet saying what it holds. Two columns: item, value. | none |
| `PlayerGames` | One row per row of every `player_week/player_week_<season>.csv`, in published order. Columns: `season, week, season_type, player_id, player_display_name, position, position_group, team, opponent_team`, then `FF_<League>` for each Active league (`config/leagues.csv` order, values from the matching `scored/scored_<season>.csv` row), then `fantasy_points, fantasy_points_ppr`, then every metric column of `player_week` in its file order. | `tblPlayerGames` |
| `SeasonTotals` | One row per `season, season_type, player_id`. Columns: `season, season_type, player_id, player_display_name, position, team, games`, then for each Active league `FF_<League>_total` and `FF_<League>_avg`. `team` is the team of the player's last game in that season and season type; `games` counts rows; `_total` is the sum rounded half away from zero to `RoundDecimals` (§4); `_avg` is `_total / games` rounded the same way. Sorted by `season, season_type, player_id`. | `tblSeasonTotals` |
| `Leagues`, `Scoring`, `Bonus` | `config/leagues.csv`, `config/scoring_weights.csv`, `config/bonus_rules.csv` exactly as published: the rules these scores were made with. A note row above each table says: to change them, edit the file in `NFL/02-config/` on GitHub. | `tblLeagues`, `tblScoring`, `tblBonus` |
| `Checks` | `checks/gates.csv` | `tblGates` |
| `Dictionary` | `dictionary.csv` | `tblDictionary` |

### 13.3 Cell rules

- A CSV value that parses as a number is a **number cell** (whole numbers stay whole). A blank CSV value is an **empty cell** (no cell written). Everything else is a **text cell**.
- Identity columns (`player_id`, `season_type`, names, positions, teams) are always text, even if a value looks numeric. `season` and `week` are numbers.
- **Text is never a formula.** Text is written as a typed string cell, so a value that starts with `=`, `+`, `-` or `@` stays text. Upstream names are untrusted data.
- Characters XML 1.0 does not allow are removed; text longer than 32,767 characters (Excel's cell limit) is an error, not silently cut.
- Every table has a header row, AutoFilter, and a frozen header row. `PlayerGames` and `SeasonTotals` also freeze through `player_display_name`. Column widths are set for readability; number formats show whole numbers without decimals and fantasy points with `RoundDecimals` places.
- Limits are checked before writing: a sheet with more than 1,048,575 data rows or 16,384 columns is an error. (The rolling ten-season window is about 180,000 rows.)

### 13.4 Versions

- **Workbook design version** `3.001` (D-041, `00-Governance/VERSIONING.md`): a constant in the exporter, shown on `About` and in the file properties (Title `NFL-Analysis 3.001`). It changes only when the workbook's design changes (sheets, columns, rules), not when the data changes.
- **Data version** is the `run_id` and "data through" of the `status.csv` it was built from, shown on `About`.
- File properties carry no personal data: author `NFL-Analysis pipeline`.

### 13.5 Publication (decision D-042)

- The workbook is **not committed to git**: a ~20 MB file rebuilt every week would grow the repository by about a gigabyte a season.
- It is a **GitHub Release asset**: release tag `nfl-workbook`, asset name `NFL-Analysis.xlsx`, replaced on every publish. Stable download address:
  `https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx`
- The weekly and monthly workflows build and upload it after a PUBLISH, and also when the asset is missing. Manual dispatch can rebuild it on demand. A failed build or upload turns the run red and raises the workflow's alert issue; the data commit already made stays.
- The release notes say which data the file holds (data through, run id, gates).
- The 2.x Power Query workbooks stay immutable in `08-releases/` for the record; they are no longer the recommended route (D-043).

