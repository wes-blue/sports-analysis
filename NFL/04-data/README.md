# NFL/04-data: the published NFL data

Scored NFL fantasy-football data, written by the pipeline in [`../03-pipeline/`](../03-pipeline/README.md) and committed by its GitHub Actions workflows. Every column of every file is defined in [`../CONTRACTS.md`](../CONTRACTS.md) §5.

**Never edit these files by hand,** and do not open and save them in Excel, which changes the bytes when it saves. Each file's fingerprint (SHA-256) is recorded in `manifest.csv`, and the pipeline's checks fail when a published file no longer matches it. To change the scoring, edit [`../02-config/`](../02-config/README.md) instead.

## Read it from anywhere

Every file here is public. On the `main` branch it is served at

```
https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/<path>
```

where `<path>` is the file's path inside this folder, for example `scored/scored_2025.csv` or `checks/gates.csv`. This is the address the NFL workbook reads by default. Any tool that reads a CSV file from a web address can use it.

## What each file is

| File | What it holds | Contract |
|---|---|---|
| `player_week/player_week_<season>.csv` | The scoring-ready table: one row per player-game plus one row per team defense and special teams (D/ST) game, with every statistic the scoring rules use | §5.1 |
| `scored/scored_<season>.csv` | The pipeline's fantasy points, one `FF_<League>` column per active league, same rows as `player_week` | §5.2 |
| `long_td/long_td_<season>.csv` | Touchdowns of 40+ and 50+ yards per player-game, from play-by-play | §5.3 |
| `seasons.csv` | Rows per season and season type, and whether the season is complete or in progress | §5.4 |
| `status.csv` | The last publish: when (`generated_utc`), what it covers (`latest_season`, `latest_week`), versions and gate counts | §5.4 |
| `run_log.csv` | One row per publish, newest last | §5.4 |
| `sources.csv` | Every nflverse file used, with its address, last-modified time, size and SHA-256 | §5.4 |
| `manifest.csv` | Every published file with its rows, columns and SHA-256 | §5.4 |
| `dictionary.csv` | What each statistic column means and where it comes from | §5.4 |
| `config/*.csv` | Copies of the scoring configuration used for the run | §5.4 |
| `checks/*.csv` | The results of the pipeline's checks: gates, reconciliation with nflverse's own points, row counts, golden sample, ESPN comparison, back-corrections | §5.5 |

Blank means "not applicable or not yet known"; a real zero is written as `0`. Rows are sorted by season, week, season type and player.

## When it changes

The workflows publish here only when every blocking check passes, so a failed run leaves the last good data in place. `status.csv` says when the data was last published. [`../03-pipeline/AUTOMATION.md`](../03-pipeline/AUTOMATION.md) explains the schedule and what to do when an update is missing.

## Licence and attribution

This data is derived from [nflverse](https://github.com/nflverse/nflverse-data) data, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The league scores, the long-touchdown counts and the D/ST rows are this repository's own calculations. [`../../DATA-LICENSE.md`](../../DATA-LICENSE.md) gives the full attribution and lists what was changed.

This README is written by hand. The pipeline does not write it, and `manifest.csv` does not list it.
