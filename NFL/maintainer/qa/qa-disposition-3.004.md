# QA Disposition: roadmap 3.004 (the remaining ESPN rules)

| | |
|---|---|
| Change | `fg_blocked` −1 for `ESPN_League` (D-052). Config notes rewritten without internal reference IDs. Three ESPN Fantasy game logs (Allgeier, Colts D/ST, Jets D/ST) added as evidence and to the ESPN reconciliation (D-055). ESPN_League contract hash refreshed. |
| Review committee | [`review-3.004.md`](review-3.004.md): pass; 1 major, 4 minor |
| Adversarial committee | [`adversarial-3.004.md`](adversarial-3.004.md): safe to merge; 1 major, 4 minor |
| Independent re-test | [`retest-3.004.md`](retest-3.004.md): ready to merge; 3 new minor |
| Dispositions by | Orchestrator, 2026-11-22 |

## Verified independently (review and re-test, each with its own full run)

- **Scope of the change:** only `FF_ESPN_League` changes, in 179 kicker player-games across 2017–2026, by `−fg_blocked` each, for a total of −183. Four games have two blocks (−2). In 2026, 11 games change. No other league or column changes, and `player_week` and `long_td` are byte-identical.
- **Gates:** all 13 pass on full runs (51 s and 44 s). G-GOLDEN checks 125 values for `ESPN_League`, so it does not report "not applicable". G-ESPN reproduces 55 of 55 (48 exact, 7 within tolerance), and 217 of 217 D/ST stat columns are equal.
- **Tests and checks:** 689 tests pass on Python 3.11 and 3.13. The CI `config-check` passes locally and on GitHub. `actionlint` is clean.
- **Configuration:** the only non-text cell that changed is `fg_blocked`/`ESPN_League`. Formatting is unchanged (LF, no BOM, same quoting), and a simulated Excel re-save leaves the configuration hash unchanged.
- **Privacy:** no personal data, fantasy-team or manager names, or private names in the evidence, the diff or the commits.

## Findings and dispositions

| ID | Grade | Finding | Disposition |
|---|---|---|---|
| Review M1 | Major | The `fg_blocked` note stated as fact what rests on one ESPN statistics page, not a fantasy score | **Fixed.** The note now says "Not yet confirmed by an ESPN fantasy score". A J. Myers fantasy game log was requested from the owner; when it arrives, it joins the ESPN check, so the −1 is tested on every run. |
| Adversarial M1 | Major | Seven D/ST rows sat exactly on the ±1 tolerance, so one late nflverse correction would hold every run | **Fixed.** Those seven rows have tolerance 2. `CONTRACTS.md` §6 states the rule, and `AUTOMATION.md` gives the remedy. |
| Review m1, re-test N1 | Minor | The safety case was understated; the contract still called confirmed cases assumptions | **Fixed** in D-055, `CONTRACTS.md` §3 and the config description ("safeties on scrimmage plays") |
| Review m2, re-test N3 | Minor | 20 stat rows were quoted; the real count is 21 | **Fixed** in the records. Past reports keep their wording. |
| Review m3 | Minor | The evidence list named only the Arizona log | **Fixed** |
| Review m4 | Minor | "Owner's league" appeared on a visitor page | **Fixed** |
| Re-test N2 | Minor | The G-ESPN message said "D/ST +/-1" | **Fixed:** a message string in `gates.py`, with no change to the logic |
| Adversarial m1 | Minor | Memory was stale | **Fixed** |
| Adversarial m2 | Minor | No gate exercises `fg_blocked = −1` | **Accepted** until the Myers fantasy log arrives; a unit test covers the rule |
| Adversarial m3 | Minor | `BLOCKERS.csv` on `main` holds full ESPN page text | **Owner's choice:** the answers are the owner's; trimming was offered |
| Adversarial m4 | Minor | Any config edit, even a note, triggers a full republish | **Accepted:** by design, and it takes under a minute |

## Version policy

`pipeline_version` stays 1.2.1. `VERSIONING.md` raises MINOR for a change to the code's scoring arithmetic; this is a configuration weight, which `config_sha256` tracks. The review agreed. The `gates.py` change is a message string only.

## What merging starts

`nfl-pipeline-weekly` re-scores all seasons, publishes `NFL/04-data` (about 21 files), rebuilds the workbook and replaces it at the stable link. `nfl-pipeline-ci` also runs.
