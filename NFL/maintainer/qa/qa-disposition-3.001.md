# QA Disposition: NFL-Analysis 3.001 (the workbook built on GitHub)

| | |
|---|---|
| Review committee | [`review-3.001-data.md`](review-3.001-data.md) (R1: data and contract, verdict correct), [`review-3.001-journey.md`](review-3.001-journey.md) (R2: the owner's journey, ready after fixes) |
| Adversarial committee | [`adversarial-3.001-file.md`](adversarial-3.001-file.md) (A1: the Excel file), [`adversarial-3.001-workflow.md`](adversarial-3.001-workflow.md) (A2: publishing on GitHub) |
| Independent re-test | [`retest-3.001.md`](retest-3.001.md): ready for the pull request |
| Dispositions by | Orchestrator, 2026-11-21 |

Every finding is **Fixed**, **Partly fixed** (what remains is stated), or **Accepted** (not changed, with the reason). The re-test reproduced each Critical and Major finding against the fixed code.

## Critical and Major

| ID | Finding | Disposition |
|---|---|---|
| A2-01 / R2-01 | Merging 3.001 started no workflow that builds the workbook; the download link would be dead until the next scheduled run (about 3.5 days) | **Fixed.** The weekly workflow also starts on a push to `main` that changes `NFL/03-pipeline/nflpipe/**` or the workflow file; its SKIP path builds the workbook when the release is missing (`NFL/CONTRACTS.md` §8, §13.5). Re-test: a simulated merge with no release ends with the stable address serving the workbook and a green run. |
| A2-02 | `gh release upload --clobber` deletes the live asset before uploading; a failed upload left no workbook | **Fixed.** Upload as `NFL-Analysis.next.xlsx`, check it, delete the old asset, rename the new one (a gap of about a second); fallback re-upload if the rename is refused. Re-test: with a failure injected at each step, the address serves the old or the new file in every case but one (rename and fallback both fail), which the next run repairs. |
| A2-03 | The run artifact would turn "Re-run failed jobs" red | **Fixed.** Artifact names carry the run attempt; artifact steps cannot fail the run. |
| A1-01 | Scored values located by the first season's column order; a later file with another order would show the wrong league's values | **Fixed.** Matched by key and column name; a mismatch is an error. |
| A1-02, A1-03 | Table column names could differ from their header cells, or collide, under Excel's normalisation (a likely repair prompt) | **Fixed.** One function writes both; names validated under Excel's rules before writing. |
| A1-04 | `generated_utc` written into the file properties unvalidated | **Fixed.** Validated as ISO 8601 UTC. |
| A1-05 | `NaN` written as text; `inf` or huge numbers crashed with a raw error | **Fixed.** Non-finite or unrepresentable numbers are an error naming file, row and column. |
| A1-06 | A trailing blank line crashed the export | **Fixed.** Blank lines are ignored everywhere. |
| R2-02 | The "not found" warning gave the owner no action | **Fixed.** The READMEs and `AUTOMATION.md` say what to do (wait, then run `workbook_only`). |
| R2-03 | Documents said about 20 MB; the file is about 38 MB | **Fixed** everywhere; D-044 records the measured size. |
| R2-04 | A large file, 409 MB of sheet XML; opening time unknown and not mentioned | **Partly fixed.** The documents and the `About` sheet say it is a large file; the newest games are first. The size reductions are **deferred** by D-044 until the owner confirms the file opens cleanly in Excel (`BLOCKERS.csv` Q-024): omitting cell references would cut it to about 7 MB without changing a value, but carries some risk of an Excel repair prompt that the owner's first open should not take. |
| R2-05 | Nobody asked the owner to report the first open | **Fixed.** `BLOCKERS.csv` Q-024. |
| R2-06 | The config README still said "next Refresh All" | **Fixed.** |

## Minor

All minor findings are listed with their state in [`retest-3.001.md`](retest-3.001.md). The ones not fully fixed:

| ID | Disposition |
|---|---|
| A1-14 | **Accepted.** Zip64 is not forced; it is unreachable with this data (the largest part is about 409 MB, well under the 4 GB limit) and changing the zip layout would add risk to the first Excel open. |
| A1-17 | **Fixed in the contract.** Byte-identical output is promised for the same Python build; a different zlib could change the bytes but never a value. |
| A2-04 | **Partly fixed.** The alert heading now says what failed. An alert is still closed only by a PUBLISH; the guide says to close it by hand after a workbook-only repair. |
| A2-07 | **Fixed as designed.** The freshness key carries the workbook design version, which changes whenever the workbook's design changes; an exporter change that does not change the design does not need a republish. |
| A2-13 / N-1 | **Already fixed.** The re-test missed that `test_each_workflow_has_exactly_its_events` asserts each file's exact event set; adding `pull_request` to the weekly workflow fails it (checked by the orchestrator). |
| R2-13 | **Accepted.** The D/ST point scale (about 100 to 300 a game in the owner's league) is not explained on the `About` sheet; the `Scoring` and `Bonus` sheets show the rules that produce it. |
| R2-11 / N-3, N-2, N-4 | **Fixed** (memory, release register, config README, plan wording). |

## Changes after the re-test

Text only: the config README wording (N-2), the plan's size wording (N-4), the contract's determinism note (A1-17), memory and the release register. No code, workflow, config or data changed after the re-test.

## Verified

- 679 tests pass on Python 3.11 and 3.13; `actionlint` clean; 64 of 64 workflow mutations caught; pinned actions match their tags.
- From the real published data, three independent readers (R1, the exporter fix team, the re-test) compared all 17,669,498 `PlayerGames` cells and all 24,250 `SeasonTotals` rows: 0 mismatches.
- The file validates against the ECMA-376 schema (A1), opens in LibreOffice, and is byte-identical across Python 3.11 and 3.13.
- No personal data, secrets or private-repository references in the pull request or in the workbook.

## Not verifiable here

1. Excel: whether it opens without a repair prompt, and how long it takes (Q-024). (Since answered by the owner: no repair message, about a minute; D-046.)
2. GitHub: the asset rename through the API, the CDN's answer, and the first real publish after the merge. (Since checked on GitHub, apart from replacing an existing asset: see the next section.)

## Verified on GitHub after the merge (2026-11-21)

Checked by the orchestrator after the owner merged the pull request (commit `8d91b3f`); recorded as decision D-045.

| Check | Result |
|---|---|
| The merge starts the weekly workflow (finding A2-01) | Run [44853664413](https://github.com/wes-blue/sports-analysis/actions/runs/44853664413), event push, started at 02:02:52 UTC; green in 36 seconds |
| SKIP path builds a missing workbook | Pipeline SKIP (data current, no data commit); the workbook was built in 12 seconds |
| Release created and asset published (A2-02) | Pre-release `nfl-workbook` created; file uploaded under the temporary name and renamed through the API with no warning; the run's own check of the public address passed |
| Same bytes as tested | Asset 40,018,688 bytes, SHA-256 `66d6e26abc6d64c040ac8a413a2e1c89bb3d3bba955f4ded197d77d936fba2f2`, identical to the local builds on Python 3.11 and 3.13; the runner used 3.12.16 (A1-17) |
| Stable address | Answered 206 to a ranged request; the downloaded file has the same SHA-256 |
| `About` sheet against `NFL/04-data/status.csv` (C-33) | Equal: version 3.001, run `20261120T233201Z-gh44837469898`, generated 2026-11-20T23:32:09Z, data through 2026 week 11 REG, gates 13/0/0 |
| File properties | Author and last modified by "NFL-Analysis pipeline"; no personal data |
| Run artifact (A2-03) | `workbook-44853664413-1`, kept 7 days |

Since then the owner opened the file in desktop Excel: no repair message, about a minute to open, and the ESPN points for a known player and week matched (Q-024, D-046).

Still not seen: replacing an existing asset (the next publish deletes the old file and renames the new one), and a red workbook step with its alert. They move to roadmap 3.002 (D-045).
