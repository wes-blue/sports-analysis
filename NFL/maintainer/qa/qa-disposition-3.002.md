# QA Disposition: NFL-Analysis 3.002 (the smaller workbook)

| | |
|---|---|
| Change | In the data rows of `PlayerGames` and `SeasonTotals`, a cell that directly follows the previous written cell is written without its `r` attribute (`NFL/CONTRACTS.md` §13.3, decision D-047). Workbook design version 3.002. No value, sheet, column, style or table changes. |
| Build | X1 (exporter): about 15 lines in `export_xlsx.py`, 8 new tests; 686 tests pass on Python 3.11 and 3.13 |
| Review committee | [`review-3.002-data.md`](review-3.002-data.md) (R1: data and contract): correct and releasable; 0 critical, 0 major, 4 minor |
| Adversarial committee | [`adversarial-3.002.md`](adversarial-3.002.md) (A1: the Excel file and its publication): 0 critical, 2 major, 4 minor; the repair-prompt risk is acceptable for one test open if the owner tests before the merge |
| Dispositions by | Orchestrator, 2026-11-21 |

## The file

Built from the published data of run `20261120T233201Z-gh44837469898` (the same data as the live 3.001 file):

| | 3.001 (live) | 3.002 |
|---|---|---|
| File size | 40,018,688 bytes | **8,432,121 bytes** (4.75 times smaller) |
| `PlayerGames` XML (uncompressed) | 408,980,471 bytes | 240,246,885 bytes |
| `SeasonTotals` XML (uncompressed) | 14,129,158 bytes | 10,038,790 bytes |
| Build time on this machine | about 12 s | about 7.7 s |
| SHA-256 | `66d6e26a…f2` | `eb33017ce791d4ba11216bd348175b5453720d7b3cbd29799a7b029f2cadd9ed` (two builds, Python 3.11 and 3.13) |

## Verified

- **Same values.** R1 compared every cell of every sheet of 3.002 with the live 3.001 file using its own streaming reader and openpyxl. A1 did the same with its own reader. Both found 0 differences in row, column, type, style or value, apart from the version text (`About` A1, "Workbook version", file Title). That is 14.58 million cells in `PlayerGames` and `SeasonTotals`.
- **Against the sources.** R1 checked all 180,301 `PlayerGames` rows against `player_week/*.csv` and `scored/*.csv`: 17,669,498 cells, 0 mismatches. X1 matched a LibreOffice CSV export of the whole sheet against the sources: 15.87 million cells, 0 mismatches.
- **The rule, exhaustively.** In `PlayerGames`, 185,591 data cells keep `r` (180,301 first cells of a row and 5,290 after a gap) and 13,984,569 omit it. In `SeasonTotals`, 24,250 keep it and 388,000 omit it. Every row, header cell and small-sheet cell keeps `r`. There are 0 violations in either direction.
- **Other readers.** openpyxl, pandas, python-calamine and LibreOffice (open, CSV export, re-save as xlsx) all place every value in the same cell as in 3.001. 13 edge-case fixtures and 20,000 random rows were placed correctly.
- **Schema.** Every part validates against the ECMA-376 schema, apart from the known `xml:space` false positive recorded for 3.001.
- **Tests catch a regression.** Five mutations of the rule each fail 3 to 7 export tests.
- **Publication.** A1 traced the weekly and monthly workflows. They read `WORKBOOK_VERSION` from the exporter, so the freshness key becomes `…|1.2.1|3.002` and the first run after the merge (pipeline result SKIP) rebuilds the workbook and replaces the existing asset. A simulation with the local stand-in replaced the 40,018,688-byte asset with the 8,432,121-byte file; the next SKIP built nothing.
- **No personal data** in any part of the file or in the change.

## Findings and dispositions

| ID | Grade | Finding | Disposition |
|---|---|---|---|
| A3-01 | Major | No primary source shows that desktop Excel accepts a cell without `r`; the adversary judged a repair prompt about 10 percent likely and a silent misplacement under 2 percent | **Accepted with a check before the merge.** The owner opens a test copy in Excel before anything is merged (A3-02). `/BLOCKERS.csv` Q-025 adds a Ctrl+End check, which must land on CT180302 in `PlayerGames` and on Q24251 in `SeasonTotals`, plus the ESPN spot check, so that a silent shift would show. If Excel objects, the pull request is not merged and the exporter goes back to the 3.001 form. |
| A3-02 | Major | Merging would replace the working 3.001 file at the stable address before the owner had tried 3.002 | **Fixed.** A test copy built here from the same code and data (SHA-256 `eb33017c…`, the reviewed file) was sent to the owner in chat on 2026-11-21. The build is deterministic, so the file published after the merge has the same XML. Q-025, roadmap 3.002 (f) and (g), D-047, RAID-106 and RAID-107 now say "before the merge". The 3.002 pull request is not to be merged until Q-025 is answered. |
| A3-03 | Minor | The real replacement on GitHub (upload, delete, rename through the API) has only run against a stand-in | **Accepted.** It runs for the first time at the merge. A failure turns the run red, opens the alert issue and leaves a "not found" link until a `workbook_only` run, as `AUTOMATION.md` says. The orchestrator watches that run. |
| A3-04 | Minor | Opening time barely changes (LibreOffice about 47 s against 49 s), so a faster open must not be promised | **Fixed.** D-047 and `NFL/05-excel/README.md` now say the download is about five times smaller and the opening time is about the same. |
| A3-05 | Minor | "About 38 MB" in workflow comments; the NFL README did not mention 3.002 | **Fixed.** Comments only (no workflow logic changed). The README says 3.002 is in test. |
| A3-06 | Minor | §13.3 described reader behaviour as if it were in ECMA-376's prose | **Fixed.** It now says the attribute is optional in the schema and names the readers tested; Excel is confirmed only by Q-025. |
| R1-m1 | Minor | §13.2 still said workbook version `3.001` | **Fixed.** |
| R1-m2 | Minor | The "more than a gigabyte a season" argument still used 38 MB | **Fixed** in the contract and the plan: hundreds of megabytes a season at 8 MB, still too much for git. |
| R1-m3 | Minor | "About 38 MB" in workflow comments and a test message | **Fixed.** The guide test now checks that `AUTOMATION.md` states "about 8 MB". |
| R1-m4 | Minor | The plan called a revert "a one-line change" | **Fixed:** a small change (the compact flag at its two call sites, the tests and the version). |

## Changes after the reviews

None to the exporter. Changed after the reviews:
- text in the contract, decision, plan, READMEs and `BLOCKERS.csv` Q-025;
- comment text in the two workflow files (their logic is byte-identical);
- two test assertions in `test_workflows.py` updated to the new documented size.

The full suite was run again afterwards. No separate re-test agent was used, because no code that either committee examined has changed.

## Not verifiable here

1. Desktop Excel: a repair message, a silent shift, and the time to open (Q-025, before the merge).
2. The first real replacement of the asset on GitHub (at the merge).
