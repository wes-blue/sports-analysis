# 03-pipeline: the `nflpipe` Python pipeline

`nflpipe` turns public NFL statistics into scored fantasy-football tables. It downloads the weekly player and team statistics, schedules and play-by-play that [nflverse](https://github.com/nflverse/nflverse-data) publishes, derives long-touchdown counts and one team defense / special teams (D/ST) row per team-game, scores every league defined in [`../02-config/`](../02-config/), checks the result with 13 gates, and publishes plain CSV files to [`../04-data/`](../04-data/). The Excel workbook in `../05-excel/` reads those files from the web. Every file format is defined in [`../CONTRACTS.md`](../CONTRACTS.md).

**Where it runs.** On GitHub. Scheduled GitHub Actions workflows run the pipeline during the season, after every change to `NFL/02-config/` on `main`, and once a month, and commit what it publishes. Nobody needs Python on their own computer to use the data or to change the scoring rules. How the workflows work, and what to do when one turns red, is in [`AUTOMATION.md`](AUTOMATION.md). This page is for developers: what the code does, how to run it and how to test it.

**Data licence.** The published data is derived from nflverse data, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The attribution and the list of changes are in [`/DATA-LICENSE.md`](../../DATA-LICENSE.md). Every publish also records the source and licence in `04-data/status.csv` (keys `data_source` and `data_license`).

## Layout

```
NFL/
  02-config/            scoring rules and settings (input; CONTRACTS.md section 1)
  03-pipeline/          this folder
    nflpipe/            the package (standard library only)
    tests/              pytest suite, offline (a fabricated miniature nflverse in tests/miniverse.py)
    tools/              write_fixture_contracts.py
    AUTOMATION.md       how the GitHub Actions workflows run it
    pytest.ini, requirements-dev.txt
  04-data/              what the pipeline publishes (output; never edited by hand)
  06-qa/fixtures/       expected values the gates compare with
  06-qa/evidence/       the owner's ESPN pages the fixtures were taken from
  .work/                git-ignored scratch: download cache, staging folder, last-run report
```

| Module | Job |
|---|---|
| `__main__.py` | Command dispatcher (`run`, `check`, `resolve`, `watchdog`, `version`) |
| `config.py` | Reads and checks `02-config`; resolves the season window |
| `http.py` | Downloads with retries, proxy and certificate support, and the cache |
| `ingest.py` | Reads the nflverse CSV files (only the columns needed) |
| `derive.py` | One pass over play-by-play (long touchdowns, defensive scores); team D/ST rows |
| `scoring.py` | League scoring (`../CONTRACTS.md` section 4), the arithmetic of the verified 1.x engine |
| `publish.py` | Writes CSV files deterministically; copies changed files into `04-data`, all or nothing |
| `run.py` | The `run` command, step by step |
| `gates.py` | The 13 gates of `../CONTRACTS.md` section 6 and the check files they write |
| `check.py` | The read-only `check` command |
| `resolve.py`, `freshness.py` | The `resolve` command: is there new work for a scheduled run? |
| `watchdog.py` | The `watchdog` command: has a publish landed recently enough? |

The version is `pipeline_version` in `nflpipe/__init__.py` (now **1.2.1**). Following `/00-Governance/VERSIONING.md`, a change to scoring arithmetic or to a derived-metric rule raises the middle number and a breaking change the first. Every publish records it in `status.csv` and `run_log.csv`; a new version makes the next run rebuild every season.

## How a run works

1. Read `02-config`. If a setting or a column is wrong, the run stops with `HOLD` before downloading anything.
2. Find the newest season nflverse has published ("Latest") and work out the window (`Latest-9` to `Latest`, 10 seasons). An `EndSeason` after the newest published season is clamped to it.
3. Choose the seasons to rebuild. `current` means the latest season, plus older seasons whose upstream files have a newer `Last-Modified` than `04-data/sources.csv` records, plus seasons not yet published. A changed config (compared after normalizing, so re-saving a file from Excel is not a change) or a new pipeline version rebuilds every season.
4. Build a complete candidate `04-data` in `../.work/stage/`: rebuilt seasons from nflverse, the other seasons copied unchanged.
5. Run the gates on the candidate.
6. Replace only the files whose content changed, all or nothing, with the index files written last.

Identical inputs give byte-identical files. The files that hold time stamps (`status.csv`, `run_log.csv`, `manifest.csv`, `checks/gates.csv`, `sources.csv`) are rewritten only when real data changed, so a run with nothing new makes no commit.

### Derived metrics

`../CONTRACTS.md` section 3 has the rules; in short:

- **Long touchdowns** (`pass_td_40` ... `rec_td_50`) per player-game, from play-by-play.
- **Team D/ST rows** (`player_id = DST_<TEAM>`), from `stats_team_week` and `games.csv`.
- **Points allowed** in three versions:
  - `dst_points_allowed`: the opponent's full final score.
  - `dst_points_allowed_excl_def` (new in 1.2.0, decision D-038): **ESPN's points allowed**, which the ESPN league's bands use. It is the opponent's final score minus the points the opponent's *defense* scored against this team's offense. Those points are interception and fumble returns for a touchdown (a touchdown on a scrimmage play by the team without the ball), safeties on scrimmage plays, and two-point tries returned by the defense, all found in play-by-play. Special-teams touchdowns, an offense recovering its own fumble in the end zone and the extra point after a defensive touchdown still count. The value is never below 0. It stays blank until the game has a final score and while play-by-play has no plays for the game. Play-by-play is needed because `stats_team_week` puts defensive fumble-return touchdowns and an offense's own end-zone recoveries in the same column. It reproduces the `PA` column of ESPN's game log for all ten 2026 weeks of the Arizona D/ST (`../06-qa/evidence/`).
  - `dst_points_allowed_excl_def_st`: the older reference figure (weight 0; not ESPN's rule).

All three are blank, never 0, until the game is final ("missing is never zero").

## Running it as a developer

Python 3.11 or later; nothing to install for the pipeline itself (decision D-025). Run every command from this folder, `NFL/03-pipeline`, so that `python -m nflpipe` finds the package. Default folders are found from the package's location, so the commands work in any clone. A full run takes about half a minute once the downloads (about 290 MB) are cached in `../.work/cache/`; a later run downloads a file again only when nflverse has published a newer one.

| Command | Does |
|---|---|
| `python -m nflpipe run --seasons all` | Rebuild every season in the window and publish |
| `python -m nflpipe run --seasons current` | Weekly refresh: latest season plus corrected older ones |
| `python -m nflpipe run --seasons 2025` or `--seasons 2023-2025` | Rebuild one season or a range |
| `python -m nflpipe run --seasons all --dry-run` | Everything except changing `04-data` |
| `python -m nflpipe check` | Read-only check of what is published (manifest hashes and the structural gates) |
| `python -m nflpipe resolve` | Print whether a scheduled run has work (`action=run` or `skip`) |
| `python -m nflpipe watchdog --max-age-hours N` | Fail when the last publish is older than N hours in season |
| `python -m nflpipe version` | Print `pipeline_version` |

On Windows use `py` in place of `python`.

| Option | Default | What it does |
|---|---|---|
| `--seasons` | `current` | `current`, `all`, a year, or a range such as `2017-2026`, inside the window |
| `--dry-run` | off | Do everything except change `--data-dir` |
| `--force` | off | Ignore the download cache and publish even when no data changed |
| `--trigger` | `manual` | Free text saved in `run_log.csv` (the workflows write `weekly`, `monthly` ...) |
| `--config-dir` | `../02-config` | The config files |
| `--data-dir` | `../04-data` | Where the published files go |
| `--fixtures-dir` | `../06-qa/fixtures` | Expected values for the gates |
| `--cache-dir` | `../.work/cache` | Download cache (git-ignored) |
| `--report-dir` | `../.work/last-run` | Gate results and a summary of the last run, written even on `HOLD` |

A run on your own computer publishes into your clone's `04-data`. On `main` the published data is the workflows' job, so commit only what they would commit, or leave publishing to them.

### Exit codes

| Code | `run` | `check` | `resolve` | `watchdog` |
|---|---|---|---|---|
| 0 | `PUBLISH`: changed files replaced | pass | `run` | healthy |
| 3 | `SKIP`: nothing changed, `04-data` untouched | | `skip` | |
| 4 | `HOLD`: a blocking gate failed, `04-data` untouched | a blocking check failed | | |
| 5 | | | | stale: no recent publish |
| 1 | error (no network, unreadable file ...), `04-data` untouched | | error | error |

Publishing is all or nothing: the run first proves it can write every file it will replace, writes the index files last, and puts back the old files from `../.work/publish-backup/` if anything fails part-way.

## Tests

```bash
python -m pip install -r requirements-dev.txt     # pytest and its exact dependencies; tests only
python -m pytest
```

The suite runs offline in a few seconds. `tests/miniverse.py` fabricates a two-season nflverse release (players, team stats, schedule, play-by-play) and installs it in place of the downloader, so `run`, `check` and every gate are exercised end to end without the network. `tests/test_evidence.py` checks that the ESPN fixtures carry the owner's game log unchanged. `tests/test_workflows.py` checks the workflow files in `/.github/workflows/`; it needs PyYAML.

## Gates

Every run checks the candidate data before anything is published. A failed **blocking** gate is a `HOLD`: nothing is published and the scheduled workflow raises an alert. An **advisory** gate publishes with a `WARN`. Results go to `04-data/checks/gates.csv` (on a publish) and always to `../.work/last-run/`.

| Gate | Checks | Severity |
|---|---|---|
| G-CONFIG | Every league has a weights column, every metric exists, bands are well-formed, no unknown setting | blocking |
| G-GRAIN | One row per season, week, season type and player | blocking |
| G-RECON | The control leagues equal nflverse's own fantasy points on at least 99.9% of rows | blocking |
| G-GOLDEN | 25 hand-checked player-games reproduce their expected score in every league | blocking |
| G-ESPN | The owner's ESPN scores: players exact, D/ST within 1 point (25 values); and ESPN's D/ST game-log columns TD, INT, FR, SCK, SFTY, BLK and PA equal our derived columns exactly (70 values, `checks/espn_dst_stats.csv`) | blocking |
| G-DST | Every team-game has a D/ST row; points allowed is filled exactly for finished games; ESPN points allowed is filled for finished games and lies between 0 and the final score; play-by-play and team stats agree on defensive touchdowns and safeties | blocking |
| G-SHRINK | No season loses more than 1% of its rows | blocking |
| G-INDEX | Index files, scored files and the manifest agree with the data | blocking |
| G-ROWS | Completed seasons match the row-count baseline | advisory |
| G-LONGTD | Completed-season long-touchdown totals match the baseline | advisory |
| G-RESTATE | Values nflverse changed in finished seasons are logged | advisory |
| G-WINDOW | The season window asks only for published seasons | advisory |
| G-OVERLAP | No league scores a total and its parts (or two versions of points allowed); every position code exists | advisory |

**Expected values follow the rules they were made with.** G-GOLDEN and the points part of G-ESPN compare a league only while its rules hash and `RoundDecimals` match `../06-qa/fixtures/fixture_contracts.csv`. After someone changes a league in `02-config`, its expected values report `WARN` "not applicable" instead of holding the publish, and every other league is still checked. G-RECON does the same for a changed control league. The ESPN stat columns do not depend on any league's rules and are always checked.

**Re-establishing expected values.** When a league's rules change on purpose, first verify each stored expected value the change can affect (recompute it, or compare it with new evidence), then record the new rules:

```bash
python tools/write_fixture_contracts.py
```

Running it without that verification would make the gates compare values made with other rules.
