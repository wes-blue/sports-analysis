# QA Disposition: roadmap 3.005 (Power Query option A)

| | |
|---|---|
| Change | Each publish also writes the workbook's `PlayerGames` and `SeasonTotals` sheets as `NFL-PlayerGames.csv` and `NFL-SeasonTotals.csv`, published as release assets next to the workbook at stable links. A "Get Data, From Web" guide in `NFL/05-excel/README.md`. A generated refresh workbook `NFL-Analysis-Refresh.xlsx` (two Power Query queries, no data), built and tested but **not published**: `PUBLISH_REFRESH_WORKBOOK` is `"false"` until the owner's Excel test passes (D-057, Q-026). The safe swap now covers three or four assets, with a four-field freshness key. |
| Review committee | [`review-3.005.md`](review-3.005.md): pass with conditions; 2 major, 7 minor |
| Adversarial committee | [`adversarial-3.005.md`](adversarial-3.005.md): safe to merge; 2 major, 7 minor |
| Fix teams | Generator (X1): commit 9a84622. Workflows and documents (C1): commit 7acdbb7, integrated by the orchestrator (contract §13.5 merged, guide query text aligned with a test) |
| Independent re-test | [`retest-3.005.md`](retest-3.005.md): ready to merge with the switch off; no critical or major finding, 4 new minor |
| Dispositions by | Orchestrator, 2026-11-22 |

## Verified independently (review, re-test and orchestrator, each with its own runs)

- **The tables equal the workbook (C-37):**
  - `PlayerGames`: 180,302 rows, 17,669,596 cells; `SeasonTotals`: 24,251 rows, 412,267 cells.
  - 0 differences, found by the review and again by the re-test, each with its own reader.
  - UTF-8 without a byte-order mark, LF record ends.
- **The workbook does not change:** SHA-256 `be3ed041…` on the current data, the same as the released 3.004 file. The CSV writer shares the workbook's row generator, and the exporter's byte-identity test pins it.
- **Determinism:** the CSV files and the refresh workbook are byte-identical across two builds and across Python 3.11 and 3.13. The refresh workbook is 14,375 bytes, SHA-256 `1e0a8a16…`.
- **Tests and checks:**
  - 828 tests pass on Python 3.11 and 3.13, locally and in the re-test.
  - `nfl-pipeline-ci` is green on GitHub for 7acdbb7 and 4498198.
  - `actionlint` with shellcheck is clean, and `validate_plan.py` passes.
- **Mutation checks:** the switch and lost-reply logic catch 12 of 13 mutations. The survivor is equivalent in practice: the start-of-publish cleanup already removes the refresh temporary file.
- **Privacy:** the diff, the commit messages, the refresh workbook, its decoded DataMashup and the owner's test copy hold no personal data, fantasy-team or manager names, or private names.

## Findings and dispositions

| ID | Grade | Finding | Disposition |
|---|---|---|---|
| Review F1, adversarial M-1 | Major | The refresh workbook lacked the hidden `ExternalData_N` names, and its table names differed from the query names and `FillTarget`: probable Excel repair triggers | **Fixed and confirmed.** There is one hidden, sheet-scoped name per query table, its number equals the query table's `name`, and its range equals the table `ref`. Table name = query name = `FillTarget` = metadata path. All ids are unique. Only Excel can confirm the file (Q-026). |
| Review F2 | Major | Nothing held the refresh workbook back until Excel had accepted it | **Fixed** by the switch `PUBLISH_REFRESH_WORKBOOK` (D-057). While it is `"false"`, three assets are published and the visitor pages do not link to the refresh workbook (a test checks this). When it is set to `"true"`, the next run publishes all four with no version bump. |
| Adversarial M-2 | Major | A lost reply to a delete stranded the new file and left the headline link dark until the next run | **Fixed and confirmed.** After a failed delete or rename, the release's assets are listed again. A failed listing counts as "not removed", so a failed delete is never counted as done, and no live asset is touched before every temporary file is verified. |
| Review F3 | Minor | Size given as about 20 KB | **Fixed:** about 14 KB everywhere |
| Review F4 | Minor | The contract said the refresh workbook is rebuilt only when `TABLES_VERSION` changes | **Fixed.** It is rebuilt on every publish, with identical bytes. Any change to its generator or query text must bump `TABLES_VERSION`, and a pin test enforces that (it fails on a `.m` edit and on a generator edit). |
| Review F5 | Minor | Refresh time and platform claims not labelled | **Fixed:** labelled as estimates or not tested |
| Review F6, re-test N2 | Minor | Redirect host named wrongly; the refresh workbook's `Start` sheet does not mention the possible second prompt for an address ending in `githubusercontent.com` | **Guide fixed. Start sheet left as tested (D-059).** The guide covers the second prompt. The owner's Excel test of the real file (Q-026) needed no extra guidance, so the file is published byte-identical to the one Excel accepted, rather than changed after the test. |
| Review F7 | Minor | Stale records | **Fixed:** plan, memory and the C-37 status |
| Review F8 | Minor | A bare CR inside a quoted field contradicted "LF line ends" | **Fixed** in the wording (§13.6), with a test |
| Review F9 | Minor | The query text cannot be run here | **Closed by Q-026 (D-059):** the owner's desktop Excel ran both queries and loaded every season |
| Review observation | Note | The archived 2.x workbook carries a user-bound permission block | **Accepted:** outside this change. The new generator writes an empty block and reads nothing from the archive. |
| Adversarial m-1 | Minor | A stray temporary asset survived a SKIP | **Fixed:** a leftover `*.next.*` asset makes the decide step rebuild, and publish removes all four temporary names first |
| Adversarial m-2 | Minor | The link check could outlast the publish step | **Fixed:** `--max-time 20` and bounded waits; the worst case is 600 s of the 30-minute step |
| Adversarial m-3 | Minor | CSV text can look like a formula to Excel | **Accepted, with a warning:** text is data and is never altered. The guide says to load the files through Data or Get Data, never by double-clicking. No such cell exists today. |
| Adversarial m-4 | Minor | Power Query's 100-second default timeout | **Fixed:** 10 minutes, in both `.m` files and both guide code blocks (kept equal by a test) |
| Adversarial m-5 | Minor | A fix to the refresh workbook would not republish by itself | **Fixed:** the pin test forces a `TABLES_VERSION` bump, and the bump changes the key |
| Adversarial m-6 | Minor | The first run swaps a byte-identical workbook | **Accepted:** the link answers "not found" for about a second, once |
| Adversarial m-7 | Minor | Documentation overstated link uptime | **Fixed** |
| Re-test N1 | Minor | The build step does not check the switch value itself | **Accepted:** unreachable, because the decide step stops on any value other than `"true"` or `"false"` before build runs |
| Re-test N3 | Minor | The refresh workbook still differs from an Excel-saved file: never-loaded state, empty bindings, an empty row | **Closed by Q-026 (D-059):** Excel opened the file with no repair message; the switch is now on |
| Re-test N4 | Minor | `NFL/README.md` and `NFL/04-data/README.md` did not mention the two CSV files | **Fixed** by the orchestrator: both pages now point to them and to the guide |

## Version policy

- `pipeline_version` stays 1.2.1: no scoring or derivation code changed.
- `WORKBOOK_VERSION` stays 3.002: the workbook's bytes are unchanged.
- `TABLES_VERSION` "1" is new. It names the column design of the two tables and the refresh workbook, and it enters the freshness key as a fourth field.
- 3.005 is a roadmap increment. It is recorded as released only after the merge run has published the CSV files and their links answer.

## What merging starts

- **Workflows:** `nfl-pipeline-weekly` runs, because the weekly workflow and `nflpipe/` changed. `nfl-pipeline-ci` also runs.
- **Pipeline:** it ends SKIP if nflverse has no new data.
- **The workbook step:**
  - it finds the two CSV files missing and a three-field key;
  - it builds three files and uploads them under temporary names;
  - it verifies all three, then swaps them;
  - it checks the three links and writes the notes with the four-field key.
- **Downtime:**
  - The workbook link answers "not found" for about a second.
  - The two CSV links, already shown on the visitor pages, answer "not found" from the merge until this run renames them, typically a few minutes.
- **Not published:** the refresh workbook.
