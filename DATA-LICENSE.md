# Data licence and attribution

## Attribution

> The NFL data in this repository contains data from **nflverse** (<https://github.com/nflverse/nflverse-data>), licensed under the **Creative Commons Attribution 4.0 International licence (CC BY 4.0)**, <https://creativecommons.org/licenses/by/4.0/>. This repository has modified it: see "What this repository changes" below.

Please keep this attribution, or an equivalent one, in anything you share that contains this data.

## The source and its licence

The NFL pipeline downloads four kinds of file from the nflverse-data releases (the exact paths are in [`NFL/CONTRACTS.md`](NFL/CONTRACTS.md) §2):

| File | Used for |
|---|---|
| `stats_player_week_<season>.csv` | Weekly player statistics |
| `stats_team_week_<season>.csv` | Team defense and special teams (D/ST) statistics |
| `games.csv` (schedules) | Final scores, season types, the week calendar |
| `play_by_play_<season>.csv.gz` | Touchdown lengths |

The licence of the nflverse-data repository is its `LICENSE.md`, titled "Attribution 4.0 International". It was checked on 2026-11-20 against the CC BY 4.0 legal code published by Creative Commons (<https://creativecommons.org/licenses/by/4.0/legalcode.txt>): apart from spacing, the two texts are identical. The nflverse-data `LICENSE.md` adds no copyright line or attribution request of its own, so the attribution above names the project and links to its repository.

What CC BY 4.0 asks of anyone who shares the data, including in modified form (Section 3(a)(1) of the licence): keep any creator identification and notices supplied with it, link to the material where reasonably practicable, **indicate that it was modified**, and say that it is licensed under CC BY 4.0 with a link to the licence. Read the licence itself for the exact terms.

## What this repository changes

The files in [`NFL/04-data/`](NFL/04-data/README.md) are built from the nflverse files above. Compared with the source:

- **Selection.** Only the seasons in the configured window and the configured season types are kept. Placeholder rows with an empty `player_id` are dropped. Only the statistic columns that the scoring rules use (plus any extra columns the configuration asks for) are published.
- **Player values are copied, not edited.** A published player statistic carries the value nflverse published for that player and game.
- **Derived metrics.** Long-touchdown counts per player-game are derived from play-by-play. One team D/ST row per team-game is built from team statistics and schedules, including the D/ST statistics, points allowed (the opponent's final score), points allowed excluding touchdowns scored by the opponent's defense, and yards allowed. The rules are in [`NFL/CONTRACTS.md`](NFL/CONTRACTS.md) §3.
- **League scores.** Fantasy points for each league defined in [`NFL/02-config/`](NFL/02-config/README.md) are calculated from those values (`FF_<League>` columns in `scored/`). They are this repository's calculations, not nflverse figures. nflverse's own `fantasy_points` and `fantasy_points_ppr` are kept for comparison.
- **Added files.** Check results (`checks/`), an index of seasons, a list of the upstream files used with their fingerprints (`sources.csv`), a manifest, run status and log files, a data dictionary, and copies of the scoring configuration. These describe the pipeline's own work.

Some test fixtures in [`NFL/06-qa/fixtures/`](NFL/06-qa/README.md) also hold values derived from nflverse data (expected scores, row counts, long-touchdown totals). The same attribution applies to them.

## Licence of the published data

The published NFL data, including this repository's additions to it (the derived metrics and league scores), is shared under the same **CC BY 4.0** licence. If you reuse it, credit nflverse and this repository, link to the licence, and say what you changed.

Neither nflverse nor this repository gives any warranty for the data: the licence offers the material "as-is and as-available" (Section 5).

This project is not affiliated with, sponsored by or endorsed by nflverse, the NFL or ESPN. The licence itself says it gives no permission to suggest any such connection (Section 2(a)(6)).

## How this relates to the code licence

The repository's [`LICENSE`](LICENSE) is the MIT licence. It covers the software and its documentation written here: the pipeline code and tests, the workbook generators, the GitHub Actions workflows and the documents.

The MIT licence does **not** cover nflverse's data, or the data derived from it. That data stays under CC BY 4.0 as described above, wherever it appears: in `NFL/04-data/`, in test fixtures, or placed in a workbook.

## Content that is not from nflverse

`NFL/06-qa/fixtures/espn_actuals.csv` and the files in `NFL/06-qa/evidence/` hold a small number of fantasy-point totals reported by ESPN for one ESPN league. They are used only to test that the scoring rules match ESPN's. They are not nflverse data, and the CC BY 4.0 statement above does not apply to them.
