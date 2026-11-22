# Interface Contracts: NFL-Analysis Pipeline

These are the file formats and command behaviours that the pipeline, the GitHub Actions workflows and the workbook hand to each other.

This file lives in the repository `wes-blue/sports-analysis` (public). Each sport has its own top-level folder; this is the contract for `NFL/`. **Paths are relative to `NFL/`** unless they start with `/`, which means the repository root (for example `/.github/workflows/`).

Changing a contract needs the maintainer's approval, because other parts of the project depend on it. The data contract version is **1**; it is written to `04-data/status.csv` as `data_contract_version`. Adding a metric (a new row in `scoring_weights.csv`, and so a new column in `player_week`) does not change the contract version, because §5.1 defines the metric columns as whatever the config lists; readers must find columns by name.

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
                                    you download it and open it: nothing to refresh
```

GitHub Actions (`/.github/workflows/nfl-pipeline-*.yml`) runs the same command on a schedule, and whenever `02-config` changes on `main`, commits `04-data`, and then builds and publishes the workbook (§13.5). A PC needs only Excel: no Python, git, copy of the repository or Power Query. Anyone can also read the CSV files in `04-data` from the web address above.

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

**Long TDs** (per player-game, from play-by-play; same rules as the earlier, Excel-based version of this project):
- Only plays with `touchdown = 1` and `pass_touchdown = 1` or `rush_touchdown = 1`. Length is `yards_gained`.
- Pass TD: `passer_player_id` gets `pass_td_40` / `pass_td_50`; `td_player_id` (the scorer, so laterals are credited correctly) gets `rec_td_40` / `rec_td_50`.
- Rush TD: `td_player_id` gets `rush_td_40` / `rush_td_50`.
- Counts are cumulative: a 55-yard TD adds 1 to both the `_40` and the `_50` column.

**Team D/ST rows** (one per team-game; same rules as the earlier, Excel-based version of this project, reconciled to ESPN):
- `player_id = DST_<TEAM>`, `position = DST`, `position_group = DST`, `player_display_name = "<TEAM> D/ST"`.
- `dst_sacks`, `dst_interceptions`, `dst_fumble_recoveries` (opponent fumbles only), `dst_fumbles_forced`, `dst_safeties`, `dst_blocked_kicks` (punt + PAT + FG blocks), `dst_tackles` (solo + assists + tackles-with-assist), `dst_kr_yards`, `dst_pr_yards`, `dst_int_tds`, `dst_fumble_tds`, `dst_st_tds`, `dst_2pt_returns`.
- `dst_points_allowed` = the opponent's full final score from `games.csv`. Blank until the game has a final score. **Missing is never zero.**
- `dst_points_allowed_excl_def` = the opponent's final score minus the points the opponent's **defense** scored against this team's offense; never below 0. Counted from play-by-play:
  - 6 for a touchdown on a scrimmage play (pass, run, kneel, spike) where the scoring team was on defense (an interception or fumble returned for a touchdown);
  - 2 for a safety that the defense scored on a scrimmage or penalty play;
  - 2 for a two-point try (a scrimmage play) returned by the defense.

  Kick and punt plays never count, so special-teams touchdowns (including a blocked kick returned for a touchdown) stay in points allowed, and so does the extra point after a defensive touchdown. Blank until the game has a final score and play-by-play has its plays. The team-stats file cannot give this alone: its `fumble_recovery_tds` mixes defensive returns with an offense recovering its own fumble in the end zone.

  This is ESPN's "points allowed" as far as the project's evidence shows (`06-qa/evidence/`: the ESPN game logs of the Arizona D/ST for 2026 weeks 1–10, the Indianapolis D/ST for weeks 1–11 and the New York Jets D/ST for weeks 1–10): in week 4 the opponent scored 36 including one defensive touchdown and ESPN counts 30, and the metric reproduces ESPN's points-allowed column in all 31 games of the three logs. They also confirm three of the choices above: special-teams touchdowns stay in points allowed (Jets week 8), so does a blocked-kick return touchdown (Colts week 6), and a safety the defense scored on a scrimmage play is subtracted (Colts week 11). A blocked extra point returned for 2 and a safety on a kick play are not yet shown by any log; they follow the same play-type rule. The ESPN league's points-allowed bands use this metric.
- `dst_points_allowed_excl_def_st` (an older approximation from the team-stats file that also subtracts special-teams touchdowns and an offense's own end-zone fumble recoveries) is kept at weight 0 for reference; it is not ESPN's rule.
- `dst_yards_allowed` = opponent passing yards + rushing yards + sack yards lost (net yards).

## 4. Scoring semantics

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
| G-RECON | Each control league equals its nflverse reference within `ReconcileTolerance` on at least 99.9% of rows. Like G-GOLDEN, it applies only while the control league's rules match `fixture_contracts.csv`; a control league the user has changed is reported as WARN. When `RoundDecimals` is below 2 the tolerance widens to half a unit of the last kept decimal. | blocking |
| G-GOLDEN | Every golden-sample value is reproduced exactly, for each league whose rules still match the rules the expected values were made with (`06-qa/fixtures/fixture_contracts.csv`: league, rules hash, `RoundDecimals`). A league whose rules the user has changed is reported as WARN "not applicable" and never holds the publish. | blocking |
| G-ESPN | ESPN actuals: players exact; D/ST within the row's `tolerance`: 1 point, or 2 on the rows whose score already differs from ESPN's by 1 (the nflverse feed differs from ESPN's by a tackle or a return yard in places, and a later correction of one stat must not stop every run). ESPN's D/ST stat columns, points allowed included, must match exactly. The same rule as G-GOLDEN applies when the league's rules have changed. | blocking |
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

Modules inside `nflpipe/`, by function:
- **Pipeline core:** `__init__.py`, `__main__.py` (dispatcher), `config.py`, `http.py`, `ingest.py`, `derive.py`, `scoring.py`, `publish.py`, `run.py`.
- **Gates and checks:** `gates.py`, `check.py`; the tests are under `tests/`.
- **Automation:** `resolve.py`, `watchdog.py`, `freshness.py`; their tests are `tests/test_resolve.py`, `tests/test_watchdog.py` and `tests/test_workflows.py`; the workflow files are under `/.github/workflows/`.

Each command module exposes `main(argv: list[str]) -> int`. `__main__.py` imports the module for a command only when that command is called.

## 8. GitHub Actions: `/.github/workflows/`

The workflow files are **installed** at the repository root (by the maintainer's choice). They are active once they are on the default branch `main`. `03-pipeline/AUTOMATION.md` explains them for the maintainer.

Every workflow sets the working directory to `NFL/03-pipeline`. The pipeline needs no package installs.

| Workflow | Trigger | Does |
|---|---|---|
| `nfl-pipeline-weekly.yml` | Tue, Wed and Thu in season (months 1, 2, 9–12), off the hour; a push to `main` that changes `NFL/02-config/**` (not its README), `NFL/03-pipeline/nflpipe/**` or this workflow file; manual dispatch | A check for stray files in `02-config` (for example `scoring_weights (1).csv`); `resolve` on scheduled runs; `run --seasons current` (no `--force` on any push: a changed config or pipeline version makes `current` rebuild every season and PUBLISH; an unchanged re-save ends SKIP); commit `NFL/04-data` on PUBLISH; then the workbook steps (§13.5); open or update its rolling issue on HOLD or error. Started on a branch other than `main`, it is always a dry run, and `workbook_only` there ends red saying nothing was rebuilt. |
| `nfl-pipeline-monthly.yml` | The 1st of each month (`run --seasons all`, which repairs back-corrections) and the 16th (heartbeat only); manual dispatch | After a PUBLISH on the 1st, builds and publishes the workbook (§13.5). Both fires end with the heartbeat |
| `nfl-pipeline-watchdog.yml` | Fri in season | `watchdog`; turns red when no publish landed. It has its own concurrency group, so a queued watchdog never displaces a waiting publish. |
| `nfl-pipeline-ci.yml` | Push or pull request touching `NFL/03-pipeline/**`, `NFL/02-config/**`, `NFL/06-qa/fixtures/**` or the workflow files | `pytest`; on pull requests also `config-check`, a dry run of the pipeline with the proposed config |

**Alerts:** each scheduled workflow has its own rolling issue. An issue is closed only by a run of the same workflow that proves the problem is gone (a PUBLISH for the weekly and monthly runs, a healthy result for the watchdog). A SKIP never closes an alert.

**Config changes need no PC.** The maintainer edits a file in `NFL/02-config/` on GitHub (or pushes it). The push starts the weekly workflow, which rebuilds and publishes. A commit made by a workflow does not start another workflow, and the workflow commits only `NFL/04-data`, so there is no loop.

**Heartbeat.** GitHub disables scheduled workflows in a public repository after 60 days without repository activity; its documentation does not define "activity". The off-season is longer than that, so each monthly fire looks at the newest commit on `main` and, when it is 21 days old or more, pushes one empty commit (no file changes). Fires are 15 or 16 days apart, so the longest gap is under 37 days. It does nothing in season or when anyone has committed recently. Whether an empty commit made with the workflow token counts as activity is unverified until an off-season has passed.

**Security.** The repository is public. Workflows run only on `schedule`, `push`, `pull_request` and `workflow_dispatch` (never `pull_request_target`), give each job only the permissions it needs, do not leave the token on disk after checkout, pin third-party actions by commit SHA, pass inputs through `env:`, and use no secrets. The alert steps count only issues opened by the workflow's own bot, because anyone can open an issue in a public repository.

## 9. Power Query (retired, 2.x)

Retired with the 2.x workbook. Its description, the firewall rule and the query files are kept for the record in `NFL/maintainer/archive-2.x/` (see `powerquery/README.md` there) and are not maintained. The current workbook is §13.

## 10. Plan content: `NFL/maintainer/plan/plan.json`

`plan.json` is one JSON object with these top-level keys, in this order: `objective`, `what_you_are_trying_to_do`, `key_findings`, `architecture`, `scope_in`, `scope_out`, `roadmap`, `requirements`, `raid`, `controls`, `glossary`. `architecture[].where` names where a step runs, for example `nflverse (GitHub Releases)`, `Python pipeline`, `GitHub Actions`, `Published CSV`, `Excel sheet` or `PivotTable`; `validate_plan.py` holds the full list of allowed values. `PLAN.md` (same folder) is rendered from it by `render_plan_md.py`, and `validate_plan.py` checks the shape, the allowed values, the ID formats and the cross-references.

## 11. Blockers for the owner: `NFL/maintainer/BLOCKERS.csv`

Columns: `Question_ID,Question,Answer,Type,Default_Used_Meanwhile,Options,What_It_Blocks,Raised,Status,Claude_Response`. The owner fills in `Answer`. `Type` is `Answer needed` or `Action needed`. `Status` is `Open`, `Answered` (acted on; see `Claude_Response`) or `Still open` (the answer did not settle it; a follow-up question exists). Only the maintainer's coordinating session edits the other columns, and it never changes or removes an answer the owner wrote. Team members report blockers in their hand-back.

## 12. Releases: `NFL/maintainer/releases/`

`RELEASES.md` is the release register. From 3.001 the workbook is a GitHub Release asset rebuilt on every publish (§13.5), and the register records each design version with the run that first published it. The 2.001 workbook (`NFL-Analysis-2.001.xlsx`) stays there unchanged for the record; its working copies are in `NFL/maintainer/archive-2.x/`. Versions 1.001 to 1.006 were released from an earlier, separate repository and are listed for the record only.

## 13. The generated workbook (design generation 3.x)

**Why.** The first refresh of the 2.001 workbook was still running after five minutes: Power Query re-scoring 180,000 rows in Excel is too slow. From 3.001 the pipeline builds the finished workbook itself, on GitHub, every time it publishes. The workbook holds **values only**: no Power Query, no formulas, no connections, no macros, nothing to refresh. Scoring is changed by editing `02-config/` on GitHub (§8); the next run rebuilds the workbook.

### 13.1 Command

`python -m nflpipe export [--data-dir DIR] [--out FILE] [--tables-dir DIR]`, run from `03-pipeline/`. Defaults: `--data-dir ../04-data`, `--out ../.work/workbook/NFL-Analysis.xlsx`; `--tables-dir` has no default (off).

- Reads **only** the published files in `--data-dir` (§5). It never downloads anything and never changes `04-data`.
- Refuses (exit 1) when `status.csv` `data_contract_version` is missing or is not the version the exporter understands (today `1`), naming both values.
- Exit codes: `0` written; `1` error (message names the cause; no partial file is left at `--out`).
- **Standard library only** (by design): the file is written with `zipfile` and XML text. Test code may use `openpyxl` to read it back.
- **Deterministic:** the same `04-data` gives byte-identical output with the same Python build (verified across Python 3.11 and 3.13 here; a different zlib library could in principle compress differently, which changes the bytes but never a value). Time stamps inside the file come from `status.csv` `generated_utc`, never from the clock; zip entries use a fixed date and a fixed order.
- Runs in well under 5 minutes on a GitHub runner for the full window.
- **`--tables-dir DIR`** (from tables version `1`, §13.6): the same run also writes `DIR/NFL-PlayerGames.csv` and `DIR/NFL-SeasonTotals.csv`, the values of the `PlayerGames` and `SeasonTotals` sheets. Both files and the workbook come from one pass over one row generator, so they cannot differ. Without the option no CSV is written and the workbook's bytes are the same. Each file is written under a temporary name and renamed into place after the workbook is complete; on error (exit `1`) no partial file is left in `DIR` and an earlier file there is kept.
- **`python -m nflpipe refresh-workbook [--out FILE]`** writes the small Power Query workbook of §13.6 (default `--out ../.work/workbook/NFL-Analysis-Refresh.xlsx`). It reads no data. Exit codes: `0` written; `1` error (message names the cause; no partial file at `--out`; the file is written under a temporary name and renamed). Deterministic: the same code and the same `.m` text give the same bytes. The workflows rebuild it on every publish (§13.5), so republishing it changes nothing unless the generator, the `.m` text or `TABLES_VERSION` changed (§13.6).

### 13.2 Sheets, in this order

| Sheet | Contents | Excel table |
|---|---|---|
| `About` | Title; workbook version (`3.002`); a line naming each league column (`FF_<League>`) and saying which leagues are scored; when the latest season is `in_progress` (`seasons.csv`), a line saying the latest week may still be incomplete; data through (`latest_season`, `latest_week`, `latest_season_type` from `status.csv`); generated (UTC); pipeline and data contract versions; gates passed / warned / failed; the data source and licence lines from `status.csv` (`data_source`, `data_license`) with the nflverse and licence addresses; where the latest file is (§13.5); how to change scoring (edit `NFL/02-config/` on GitHub, link to `NFL/03-pipeline/AUTOMATION.md`); one line per sheet saying what it holds. Two columns: item, value. | none |
| `PlayerGames` | One row per row of every `player_week/player_week_<season>.csv`, **newest first**: season descending, week descending (so a season's playoff weeks come before its regular season), then the published order within a week. Columns: `season, week, season_type, player_display_name, position, team, opponent_team`, then `FF_<League>` for each Active league (`config/leagues.csv` order, so the order is set in the config; values from the `scored/scored_<season>.csv` row with the same key, found by **column name**, never by position), then `player_id, position_group, fantasy_points, fantasy_points_ppr`, then every metric column of `player_week` in its file order. | `tblPlayerGames` |
| `SeasonTotals` | One row per `season, season_type, player_id`. Columns: `season, season_type, player_display_name, position, team, games`, then for each Active league `FF_<League>_total` and `FF_<League>_avg`, then `player_id`. `player_display_name`, `position` and `team` come from the player's last game in that season and season type (highest week; ties keep the later published row); `games` counts rows; `_total` is the sum rounded half away from zero to `RoundDecimals` (§4); `_avg` is `_total / games` rounded the same way. Sorted newest season first, `REG` before `POST`, then by the first Active league's total, highest first, then `player_id`. | `tblSeasonTotals` |
| `Leagues`, `Scoring`, `Bonus` | `config/leagues.csv`, `config/scoring_weights.csv`, `config/bonus_rules.csv` exactly as published: the rules these scores were made with. A note row above each table says: to change them, edit the file in `NFL/02-config/` on GitHub. | `tblLeagues`, `tblScoring`, `tblBonus` |
| `Checks` | `checks/gates.csv` | `tblGates` |
| `Dictionary` | One row per column of `PlayerGames`, in its order: the identity and `FF_<League>` columns described by the exporter (a league's description comes from `config/leagues.csv`), then the rows of `dictionary.csv` | `tblDictionary` |

### 13.3 Cell rules

- A CSV value that parses as a number is a **number cell** (whole numbers stay whole). A blank CSV value is an **empty cell** (no cell written). Everything else is a **text cell**.
- Identity columns (`player_id`, `season_type`, names, positions, teams) are always text, even if a value looks numeric. `season` and `week` are numbers.
- **Text is never a formula.** Text is written as a typed string cell, so a value that starts with `=`, `+`, `-` or `@` stays text. Upstream names are untrusted data.
- Characters XML 1.0 does not allow are removed; text longer than 32,767 characters (Excel's cell limit) is an error, not silently cut.
- Every table has a header row, AutoFilter, and a frozen header row. `PlayerGames` and `SeasonTotals` also freeze through `player_display_name`. Column widths are set for readability; number formats show whole numbers without decimals and fantasy points with `RoundDecimals` places.
- Every input value is validated before it reaches the file: numbers must be finite (`nan`, `inf` and values Excel cannot store are errors naming the file, row and column); `status.csv` `generated_utc` must be an ISO 8601 UTC time stamp; text that becomes a table column name or a header must be unique after Excel's own normalisation (case-insensitive, whitespace collapsed) and at most 255 characters; text longer than 32,767 UTF-16 code units is an error. Blank lines in a CSV are ignored everywhere. Scored values are matched to `player_week` rows by key and column name, and a `scored` file whose keys or leagues do not match is an error.
- The workbook carries no theme part and no style refers to a theme colour, so nothing depends on one.
- Limits are checked before writing: a sheet with more than 1,048,575 data rows or 16,384 columns is an error. (The rolling ten-season window is about 180,000 rows.)
- **Cell references (from design version 3.002).** In the data rows of `PlayerGames` and `SeasonTotals`, a cell that directly follows the previous written cell of the same row is written without its `r` attribute. The first written cell of every row, and the first written cell after a blank (omitted) cell, keep `r`. Every `<row>` keeps its `r`. Header rows and the small sheets keep `r` on every cell. The `r` attribute is optional in the ECMA-376 schema (`CT_Cell`). The readers tested (openpyxl, LibreOffice, pandas and python-calamine) place a cell without it in the column after the previous cell, so every value stays in the same cell; desktop Excel was confirmed by opening the 3.002 file with no repair message. On the real ten-season data this cut the file from 40,018,688 to 8,432,121 bytes (about 8 MB) and the `PlayerGames` XML from 409 MB to 240 MB, with no value changed (measured 2026-11-21).

### 13.4 Versions

- **Workbook design version** `3.002`: a constant in the exporter, shown on `About` and in the file properties (Title `NFL-Analysis 3.002`). 3.001 wrote `r` on every cell; 3.002 omits it as §13.3 says, and nothing else changes. It changes only when the workbook's design changes (sheets, columns, rules), not when the data changes.
- **Data version** is the `run_id` and "data through" of the `status.csv` it was built from, shown on `About`.
- File properties carry no personal data: author `NFL-Analysis pipeline`.

### 13.5 Publication: four release assets

- The workbook is **not committed to git**: a file of about 8 MB (design 3.002; 3.001 was about 38 MB; measured 2026-11-21 for 2017–2026; it grows with the window) rebuilt every week would grow the repository by hundreds of megabytes a season (more than a gigabyte at the 3.001 size).
- The 2.x Power Query workbooks are retired and no longer published in this repository.

The workbook, the two table files and the refresh workbook are not committed to git. They are four assets of one release, tag `nfl-workbook` (a pre-release, never "Latest", so it does not pose as a software release), at addresses that never change:

| Asset | Built by | Stable address (`https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/<name>`) |
|---|---|---|
| `NFL-Analysis.xlsx` | `python -m nflpipe export --data-dir DIR --out FILE --tables-dir DIR2` | `.../NFL-Analysis.xlsx` |
| `NFL-PlayerGames.csv` | the same call (`--tables-dir`) | `.../NFL-PlayerGames.csv` |
| `NFL-SeasonTotals.csv` | the same call (`--tables-dir`) | `.../NFL-SeasonTotals.csv` |
| `NFL-Analysis-Refresh.xlsx` | `python -m nflpipe refresh-workbook --out FILE` | `.../NFL-Analysis-Refresh.xlsx` |

**Freshness key.** The release notes end with `<!-- nfl-workbook-key: <run_id>|<pipeline_version>|<WORKBOOK_VERSION>|<TABLES_VERSION> -->`. `run_id` and `pipeline_version` are read from `NFL/04-data/status.csv`; `WORKBOOK_VERSION` and `TABLES_VERSION` are read as text from the lines `WORKBOOK_VERSION = "..."` and `TABLES_VERSION = "..."` in `nflpipe/export_xlsx.py` (never imported). Each field matches `[0-9A-Za-z._-]+`. A run compares the whole key with the line in the notes (followed by a space, so `1.2.1` is not a prefix match of `1.2.10`). A different key, or any of the four assets missing, in `starter` state or of size 0, means "build and publish all four". `TABLES_VERSION` changes only when the column design of the two table files (or the refresh workbook's queries) changes. The key had three fields up to 3.002; a release carrying a three-field key is always stale, so the first run after the tables were added republishes everything, whether or not the workbook asset exists.

**Build checks (before anything is uploaded).** Both workbooks are zip files whose every member reads back (`testzip`) and that hold `xl/workbook.xml`; the finished workbook is at least 1,000,000 bytes, the refresh workbook at least 5,000. Each CSV starts with the header `season,` (so no byte-order mark), and has at least 1,000,000 bytes and 1,000 lines (PlayerGames) or 100,000 bytes and 100 lines (SeasonTotals). Any failed check removes every built file, turns the run red and uploads nothing.

**Safe swap.** 1) Upload each file under a temporary name (`NFL-Analysis.next.xlsx`, `NFL-PlayerGames.next.csv`, `NFL-SeasonTotals.next.csv`, `NFL-Analysis-Refresh.next.xlsx`): a leftover temporary asset of a dead run is removed first, an upload is tried three times, and `--clobber` is never used on a live asset. 2) Verify **every** temporary asset (`state` `uploaded`, size equal to the local file) before any live asset is touched; on any failure every temporary asset is removed and the live assets are untouched. 3) For each asset, back to back: delete the live asset (none to delete for an asset that is new), rename the temporary one to the stable name (five tries); if the rename is refused, upload the file again under the stable name with `--clobber` (nothing is left to overwrite). A failed pair is recorded and the other pairs still run. 4) Ask for each of the four public addresses with a ranged request (`curl -sL -r 0-0`, five tries with growing waits); 200 or 206 passes. 5) Only if steps 3 and 4 had no failure, edit the release notes: a line per asset with its address, the data lines and the key. A failure in any step turns the run red and opens or comments on the alert issue; the notes keep the old key, so the next run builds and publishes again.

**Runs.** The same three workflow steps (decide, build, publish) run after a PUBLISH, after a SKIP (reads only when all four assets are current), and for the `workbook_only` dispatch, which also rebuilds the two table files and the refresh workbook. They never run on a dry run, off `main`, or for the monthly heartbeat. The 7-day run artifact `workbook-<run_id>-<attempt>` holds all four files.

### 13.6 The published tables and the refresh workbook

**Why.** Some people want to refresh in Excel instead of downloading a new workbook. Re-scoring in Excel is too slow (§13), so Excel refreshes only the finished tables the pipeline already scored: two plain CSV files, and a small workbook whose Power Query queries load them.

**The two tables** (written by `export --tables-dir`, §13.1):

| File | Same values as | Columns |
|---|---|---|
| `NFL-PlayerGames.csv` | the `PlayerGames` sheet (§13.2) | the sheet's columns, in its order: `season, week, season_type, player_display_name, position, team, opponent_team`, one `FF_<League>` per Active league, `player_id, position_group, fantasy_points, fantasy_points_ppr`, then every metric column |
| `NFL-SeasonTotals.csv` | the `SeasonTotals` sheet (§13.2) | `season, season_type, player_display_name, position, team, games`, then `FF_<League>_total` and `FF_<League>_avg` per Active league, `player_id` |

- The header row is the sheet's header row, and rows are in the sheet's order (§13.2). The columns follow the config (leagues) and the data (metrics), so a reader must pick columns by name.
- A field holds exactly the text the sheet cell shows: numbers as in `04-data` or the rounded sums (`.` decimal mark, no thousands separator, no scientific notation added), a blank cell as an empty field, text unchanged. The same characters XML 1.0 forbids are removed as in the workbook (§13.3). Every error that stops the workbook (non-finite numbers, text over 32,767 UTF-16 code units, unmatched scored rows) stops the CSV export too.
- **Encoding:** UTF-8 **without** a byte order mark. Records end with LF only: the writer never emits CRLF, and a CR is never a record terminator. RFC 4180 quoting: a field is quoted only when it holds a comma, a double quote, a CR or an LF (a field with a line break is always quoted, so a reader sees one field; a double quote inside is doubled). A CR can therefore appear only inside such a quoted field, and only if the source text holds one (none does today). No gzip.
- Text is data: a field is never prefixed or escaped for spreadsheets. To read the files in Excel use Data > From Text/CSV (file origin UTF-8) or the refresh workbook, not a double click.
- **`TABLES_VERSION`** (`"1"`) is a constant in `nflpipe/export_xlsx.py`, on its own line after `WORKBOOK_VERSION`. It changes only when the column design of the two files changes, not when the data or the leagues change.
- Publication (the same release as the workbook, §13.5): asset names `NFL-PlayerGames.csv` and `NFL-SeasonTotals.csv`, addresses `https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/<name>`. Like the workbook they are release assets, not files in git.

**The refresh workbook** (`python -m nflpipe refresh-workbook`): file `NFL-Analysis-Refresh.xlsx`.
- Sheets `Start` (what to click: Data > Refresh All; connect as Anonymous; answer Public to a privacy question; the data source and licence line), `PlayerGames` (table `PlayerGames`) and `SeasonTotals` (table `SeasonTotals`): as Excel does for a query loaded to a table, the table is named after its query. Each table is query-backed (Power Query connection `Query - <name>`, query table `ExternalData_<n>`, with `<n>` = 1 for `PlayerGames` and 2 for `SeasonTotals`) and holds only a header row and an empty row: **the file carries no data and does no scoring**. The seed header names only columns that every build has; Excel lays the table out to the query's real columns on refresh.
- Structure, as Excel writes it for query tables: the table name, the query name, the `FillTarget` and the metadata item path `Section1/<name>` are the same word; `xl/workbook.xml` carries one hidden, sheet-scoped defined name per table (`ExternalData_1` on `PlayerGames!$A$1:$K$2`, `ExternalData_2` on `SeasonTotals!$A$1:$G$2`, `localSheetId` = the zero-based sheet index) that equals the `name` of its `queryTable` part and the table's `ref`; connection ids, table ids and query table names are unique.
- The queries are the text of `nflpipe/pq/PlayerGames.m` and `nflpipe/pq/SeasonTotals.m`. Each reads exactly one address, the release asset above, with `Web.Contents` (the only option is `[Timeout = #duration(0, 0, 10, 0)]`, because the 38 MB PlayerGames file can take longer than the 100-second default; no headers, credentials or query string) and `Csv.Document` (`Delimiter = ","`, `Encoding = 65001`, `QuoteStyle.Csv`); promotes the headers; turns blank into null; and types the columns **by name rules**: `season` and `week` (`games` in SeasonTotals) are whole numbers, the identity text columns are text, every other column is a number (`en-US` culture).
- The Power Query package (DataMashup, MS-QDEFF) is written by the generator; its package skeleton (`Package.xml`, content types, permission list: firewall on, public workbook group) is embedded as constants, and the permission-bindings block is empty (Excel asks its privacy question once). Nothing is read from the archived 2.x files.
- Deterministic bytes (fixed time stamp and zip order, ids derived from names); author and last modified by `NFL-Analysis pipeline`; no path, user name or machine name in any part.
- It is about 14 KB (14,375 bytes at tables version `1`; the workflows reject a file under 5,000 bytes). It is the same file for every data version, and the build is deterministic: the workflows rebuild it on every publish, so republishing it replaces the asset with identical bytes. Its content changes only when the generator (`nflpipe/refresh_workbook.py`), the text of `nflpipe/pq/*.m` or `TABLES_VERSION` changes.
- **Any change to the refresh workbook or to the `.m` text must bump `TABLES_VERSION`** (and the new version's digest is pinned in `tests/test_tables.py`, `REFRESH_PINS`). A test builds the file and compares the SHA-256 of every part's name and uncompressed bytes with the pin for the current `TABLES_VERSION`; it fails with a message telling the developer to bump the version. (Compression is left out of the digest because it can differ between zlib builds.)
- **Not verified here:** that desktop Excel opens it without a repair message and refreshes it. Only Excel can confirm that; the tests check the package structure, and LibreOffice (which ignores the queries) opens the sheets.
