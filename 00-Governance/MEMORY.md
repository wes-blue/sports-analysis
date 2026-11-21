# Memory: what a new session must know

_Last updated: 2026-11-21, when 3.001 was approved for release (pull request opened)._

Read this after `CLAUDE.md`. The decision log (`00-Governance/DECISIONS.md`), the NFL contract (`NFL/CONTRACTS.md`), the plan (`NFL/PLAN.md`) and `BLOCKERS.csv` hold the detail; this file says where things stand and what is not written anywhere else.

## Current status

- **In progress: version 3.001, the workbook built on GitHub (decisions D-041 to D-043).** The owner tried the experimental 2.001 workbook on 2026-11-20: it opened, but Refresh All was still running after five minutes, which was too long, and the owner asked for Python on GitHub to build the workbook (`BLOCKERS.csv` Q-020). So from 3.001 `python -m nflpipe export` writes `NFL-Analysis.xlsx` from `NFL/04-data` (values only, nothing to refresh; `NFL/CONTRACTS.md` section 13), and the weekly and monthly workflows upload it after a PUBLISH as the release asset of tag `nfl-workbook`, at `https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx`. It is not committed to git (D-042). Scoring is changed by editing `NFL/02-config/` on GitHub.
  - **State on 2026-11-21: approved for release, pull request open.** Built by three Sonnet teams (exporter, workflows, documents); examined by a review committee (data: correct, 0 major; journey: ready after fixes) and an adversarial committee (file: no repair trigger on today's data, 4 critical findings on unusual inputs; workflows: no link for 3.5 days after the merge, and a failed upload would delete the live file); all critical and major findings fixed by two fix teams and confirmed by an independent re-test. 679 tests on Python 3.11 and 3.13; 17,669,498 cells verified three times independently with 0 mismatches. QA: `NFL/06-qa/qa-disposition-3.001.md`. Decision D-044 defers the size reductions.
  - **The Power Query route is retired (D-043):** `NFL/05-excel/archive-2.x/` holds the Power Query sources, generators and both 2.001 workbook copies (moved with `git mv`, scripts' folder paths adjusted, not run again) with a README saying so. `NFL/08-releases/NFL-Analysis-2.001.xlsx` is unchanged; the register marks 2.001 Superseded by 3.001. `BLOCKERS.csv` Q-023 asks whether to keep the route at all (default: retired).
  - **Release details for 3.001:** approved 2026-11-21; the workbook is published by the first weekly run after the merge (push trigger on `nflpipe/**`), at the stable link. After the merge: check that run on the Actions tab, that the link answers 200, and record the published asset's data run and size here and in `NFL/08-releases/RELEASES.md`. Then the owner opens it in Excel (`BLOCKERS.csv` Q-024).
- **Released 2026-11-20: NFL-Analysis 2.001**, the first release in this repository (D-035). `NFL/08-releases/NFL-Analysis-2.001.xlsx`, a byte-identical copy in `NFL/05-excel/archive-2.x/`. SHA-256 `ac72364839f46e35b68a2594ffcfcf50960081e12cdb08590da897eb7899da87`. Gates G1–G5 passed; QA report and dispositions in `NFL/06-qa/`.
  - It is **paste-ready**: the owner adds the 15 queries once in Excel, or uses the experimental workbook.
  - **Experimental workbook:** `NFL/05-excel/archive-2.x/NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx` (version `2.001-experimental`, SHA-256 `5a254114540a7d5648b30e3bc8d959422eadf7bc169cbb74bd688b5cd0128d1b`): the owner's own Excel-built workbook with the 15 queries installed and personal data removed. Not a release. The owner also has a private copy whose Data Model was left untouched, as a second chance if this one fails to load.
- **2026-11-20: the NFL project moved** from the owner's private repository to this public repository (D-033), in the multi-sport layout. No git history was copied. The 1.x archive, raw inputs and 1.006 QA records stay private (D-034).
- **Pipeline 1.2.1**, data contract version 1. 679 tests pass on Python 3.11 and 3.13 (381 ran on GitHub's runners before 3.001). Published data on `main`: 175,011 player rows plus 5,290 D/ST rows, 2017–2026 through week 11 (Thursday game only, at the merge on 2026-11-20); all 13 gates pass.
- **ESPN points allowed (D-038)** now follow the owner's ESPN game log: all ten Arizona weeks of ESPN's points-allowed column reproduced, 9 of 10 weekly scores exact.
- **Merged and live (2026-11-20 23:31Z).** The owner merged pull request #1 (a regular merge commit, `5fbad73`). The merge started `nfl-pipeline-weekly` (push trigger on `NFL/02-config/**`): PUBLISH in 17 seconds, all 13 gates PASS, data commit `ff90d3b` pushed to `main` by `github-actions[bot]` on the first attempt. It picked up week 11's Thursday game (HOU at IND; 66 player rows plus 2 D/ST rows), so `status.csv` reads `latest_week` 11 while week 11 is still being played. `nfl-pipeline-ci` passed on the merge. Proven on GitHub by this run: workflow token write access to `main`, the alert-issue step (`gh issue list --author app/github-actions` accepted, issues enabled), no loop (the bot's commit started no workflow). The data address serves the files (HTTP 200 for `status.csv`, `seasons.csv`, `player_week_2026.csv`, `scored_2026.csv`). Not yet seen: a scheduled run (first: Tue 2026-11-24 15:17 UTC), the watchdog (Fri 2026-11-27), the monthly run (2026-12-01), a red run and its alert issue.
- **Power Query is retired.** In the owner's one trial of the pipeline-fed design (the experimental 2.001 workbook) it opened but its refresh was still running after five minutes (Q-020).

## Next steps

1. **Finish 3.001** (acceptance criteria in `NFL/PLAN.md`, roadmap 3.001): integrate the exporter and the workflow steps; run the exporter on the published data and read the file back; run quality gates G1-G5 and an independent QA pass (include a personal-data scan of the workbook, control C-34); push the branch and open a pull request; after the owner merges, run the weekly workflow by hand (`workflow_dispatch`) and confirm the stable link downloads a file whose `About` sheet matches `NFL/04-data/status.csv` (control C-33).
2. **Ask the owner to open the downloaded workbook in desktop Excel** and report any repair message word for word (control C-32, NFR-15). Until then say "not yet opened in Excel" everywhere.
3. **Release 3.001:** fill in the placeholder row in `NFL/08-releases/RELEASES.md` and the release details above, and update this file.
4. **3.002, automation proven:** a manual run of each workflow, the first scheduled weekly run (Tue 2026-11-24), the watchdog, the monthly run, a config edit made on GitHub that publishes and rebuilds the workbook, and an alert from a failed build or upload.
5. **3.003, remaining ESPN rules:** when Q-016, Q-017 or Q-019 is answered.
6. **Documents corrected for 3.001 by the orchestrator (2026-11-21):** the contract (§0 diagram, §9 marked retired, §12, §13.1 data-contract check), `CLAUDE.md` §5, the charter, the role cards, `_Sport-Template/` and `NFL/02-config/README.md`.

The plan's roadmap (`NFL/PLAN.md`) has the acceptance criteria for each.

## Waiting on the owner (`BLOCKERS.csv`)

Q-001 to Q-006 and Q-009 to Q-014 are answered and acted on (D-033 to D-039). Q-007 and Q-008 were not settled by the text pasted and have follow-ups. Open:

| ID | About | Default in force |
|---|---|---|
| Q-016 | Paste the Seattle kicker J. Myers' 2026 ESPN game log (blocked field goals; follow-up to Q-007) | A blocked field goal is not a miss |
| Q-017 | Paste the 2026 ESPN game log of a long-touchdown or return-fumble player (follow-up to Q-008) | A 50+ yard TD earns both bonuses; a lost return fumble costs 2 points |
| Q-018 | Confirm what stays private | The 1.x archive and raw inputs stay private (D-034) |
| Q-019 | ESPN game logs for the Jets, Colts, Titans or Cowboys D/ST (special-teams TDs, blocked-kick returns, safeties, own-fumble TDs) | Assumptions in D-038 |
| Q-021 | Confirm CC BY 4.0 for the derived data | CC BY 4.0, crediting nflverse |
| Q-022 | Require approval before outside pull requests run workflows | GitHub's default |
| Q-023 | Keep the Power Query route available at all? | Retired and archived (D-043) |

Answered since: Q-015 (merged 2026-11-20) and Q-020 (the Power Query refresh was too slow; acted on in D-041 to D-043).

## Working with the owner

- The owner appears in this repository only as the GitHub username `wes-blue`. Never write any other personal detail (`CLAUDE.md` §2).
- Windows, Excel for Microsoft 365. The generated workbook does not use the Data Model.
- Plays in one ESPN league that rosters a team D/ST and a kicker, with no individual defensive players (D-017). Its rules are the `ESPN_League` column in `NFL/02-config/`.
- Prefers everything on GitHub; the laptop is not always on (Q-014). Nothing routine may depend on the owner's computer. Scoring changes are made by editing `NFL/02-config/` on GitHub.
- Do not pause on blockers: take the stated default, keep working, and put each question or action in `BLOCKERS.csv` with a default used meanwhile. Write each question so it can be answered in one line, and say exactly where to click.
- The owner merges pull requests. Claude does not merge, and pushes to `main` only when told to in chat.

## Durable decisions (detail in `DECISIONS.md`)

- **Split of work (D-041, superseding D-024):** the pipeline downloads, derives long-TD counts and team D/ST rows, scores every league, runs the gates, publishes CSV files and builds the values-only workbook (`NFL/CONTRACTS.md` section 13); there is no second scoring engine and no Power Query. The workbook is a release asset, not in git (D-042).
- **Standard library only** at pipeline run time (D-025). `pytest` is for tests.
- **Long-TD from play-by-play for every season** (D-029); finished seasons are re-read when nflverse changes them.
- **Gates (D-031, D-032):** a failed blocking gate holds the publish and leaves `04-data` untouched. The golden, ESPN and reconciliation gates skip a league whose rules changed (WARN, still publishes; owner confirmed, Q-013). A correction to a test player's stats upstream stops the run and alerts (owner confirmed, Q-012).
- **Public repository (D-033, D-034), GitHub-only runtime (D-036).** The web data location of D-037 applied to the retired Power Query workbook; the CSV files are still public at their address. The optional second data repository of the 1.x plan is gone.
- **Versioning (D-035, D-041):** the major number names the design generation; 1.x private and closed, 2.x (Power Query) here and retired, 3.x the workbook built on GitHub. The design version in the file changes only when the design changes; the data changes every publish. `00-Governance/VERSIONING.md`.
- **ESPN points allowed (D-038):** subtract touchdowns scored by the opposing defense, keep special-teams touchdowns. Evidence: `NFL/06-qa/evidence/espn-game-log-ARI-DST-2026.txt`.
- **1.005 withdrawn** and never reused (D-028, confirmed Q-005).

## Verified facts about the data

- Player stats: `https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_<season>.csv`, one file per season; the link redirects to `release-assets.githubusercontent.com`. All four upstream sources are in `NFL/CONTRACTS.md` §2.
- nflverse-data is licensed CC BY 4.0: its `LICENSE.md` was compared with the Creative Commons legal code on 2026-11-20 and is identical apart from spacing. Attribution: `DATA-LICENSE.md`.
- The schema has 150 columns, identical in name and order across 2016–2026; 13 are text; an empty field means a missing value. Every week has one placeholder row with an empty `player_id`, which is dropped.
- nflverse's `fantasy_points` and `fantasy_points_ppr` formulas are reproduced exactly on 174,237 of 174,237 source rows (2017–2026, checked 2026-11-14); they are the Standard and PPR control leagues.
- `fumbles_lost_total` exceeds the sum of the sack, rushing and receiving fumble columns on 393 rows (return fumbles): weight the total or the components, never both (gate G-OVERLAP warns).
- `fg_missed` excludes blocked kicks. Whether ESPN counts a block as a miss is open (Q-016).
- ESPN week 8 2026 (D-021): 12 of 12 players exact; D/ST within 1 point (residuals are feed differences). D/ST tackles = solo + assists + tackles-with-assist; yards allowed = net; fumble recoveries = opponent fumbles only; points allowed for the ESPN league per D-038.
- nflverse back-corrects finished seasons, so finished seasons need a restatement check (G-RESTATE).
- GitHub's scheduled runs often start late (a median of about 80 minutes was measured by another project) and are sometimes dropped; hence three weekly attempts and a watchdog. GitHub disables scheduled workflows in a public repository after 60 days without activity; the monthly run keeps the repository active (`NFL/CONTRACTS.md` §8).

## Environment facts

- The build container has Linux, Python 3.13 with openpyxl, pandas, lxml and PyYAML, LibreOffice (used to recalculate workbooks) and Node 22 with npm. `pytest` is installed into a virtual environment under `NFL/.work/` when needed.
- **There is no Excel, so the generated workbook cannot be opened in Excel here, and GitHub Actions cannot be run from here.** The workbook is read back with openpyxl and opened in LibreOffice; the workflows are linted and unit-tested; each needs a first real run.
- The M parser setup in `NFL/.work/` belonged to the retired Power Query route (its scripts are in `NFL/05-excel/archive-2.x/build/pq/`). `.work/` is not in git.
- Downloads go through a proxy; Python reads nflverse files through it with the CA bundle named by `SSL_CERT_FILE`. `raw.githubusercontent.com` and `git ls-remote` on public repositories work.
- Subagents' Write tool refuses some report-style files; they return the text and the orchestrator saves it.

## Lessons

- Give parallel engineers disjoint files and a written contract first. It held for seven teams on 1.006 with no merge conflict.
- Engineers leave generators and validators in `.work/`, which git ignores. Promote anything a later change needs into the repository (done on 2026-11-20 for the plan validator, the workbook verifier and the M parser runner; originally at `NFL/.work/a1/validate_plan.py`).
- An independent QA pass that re-derives the results found a critical defect that every builder's own tests missed (1.006, finding C-01). Always run one, and re-test the fixes independently.
- Publishing cannot be undone. Scan everything for personal details, local paths and private content before each commit, including workbook file properties, and keep paths into the private repository out of public files.
- The build container runs as the administrator; a GitHub runner does not. The first real run on GitHub failed on a hard-coded certificate path that only the container can read (fixed in pipeline 1.2.1). Treat the pull request's `config-check` job as the real end-to-end test, and never build a machine-specific path into the pipeline (a test now enforces this).
- Documents copied from an earlier setup keep describing it. After a move, check every document against the new contract before release.
