# QA Disposition: NFL-Analysis 2.001

| | |
|---|---|
| QA report | [`qa-report-2.001.md`](qa-report-2.001.md) (independent, 2026-11-20): safe to publish; 0 Critical, 1 Major, 12 Minor |
| Dispositions by | Orchestrator |
| Released file | `NFL-Analysis-2.001.xlsx`, SHA-256 `ac72364839f46e35b68a2594ffcfcf50960081e12cdb08590da897eb7899da87` |

Every finding is **Fixed**, **Fixed in part** (with what remains) or **Accepted** (not changed, with the reason).

## Major

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| QA-M1 | One test asserted a raw floating-point sum that differs between Python 3.11 and 3.12 or later, so the test job would have been red on the pull request and on the merge | **Fixed.** The version-dependent assertion is removed; the two assertions on the rounded score, which must not depend on the Python version, stay. | 377 tests pass on Python 3.11.18 and on 3.13. |

## Minor

| ID | Finding | Disposition |
|---|---|---|
| QA-m1 | The contract named the wrong fixture file for ESPN's D/ST stat columns | **Fixed** in `NFL/CONTRACTS.md` §5.5; the fixture is listed in `06-qa/README.md`. |
| QA-m2 | A blocked extra point returned for 2 by the defense was not named as an assumption | **Fixed.** Named in the contract §3, in decision D-038 and in `BLOCKERS.csv` Q-019. It is a kick play and is not subtracted; no published score depends on it today. |
| QA-m3 | The metric's description stated unproven cases as facts | **Fixed** in `02-config/scoring_weights.csv`; the pipeline was re-run so `04-data/dictionary.csv` and the workbook carry the new wording. |
| QA-m4 | Two documents said the 1.006 QA records were copied here | **Fixed** in the release register and in memory: those records stay in the private repository. |
| QA-m5 | Three places pointed at Q-011 for reporting the experimental trial | **Fixed.** They point at Q-020; memory's table of open questions is current. |
| QA-m6 | Q-020 called the paste-ready workbook "proven" | **Fixed.** It now says the paste-ready workbook is the fallback and has not run in Excel either. |
| QA-m7 | Wrong Start_Here section numbers in the paste-ready workbook | **Fixed** (three references). |
| QA-m8 | Misleading leftovers in the experimental workbook | **Fixed in part.** The version log has its 1.006 row. The metric check that shows "NOT IN DATASET" for the new derived metric is listed under Known differences in the experimental README, because fixing it would mean editing two more parts of the owner's file. |
| QA-m9 | The experimental build re-compressed the Data Model part | **Fixed.** Every part is stored as the base stores it, and the verifier checks it. While fixing this, the engineer found that the earlier name removals inside the Data Model had left two internal checksums wrong; the build now recomputes them, and all 790 inner files verify. |
| QA-m10 | A critical remark about a named third-party project, and paraphrases of the owner's private search transcript | **Fixed in part.** The remark is reworded in the decision log, and 58 cells of 1.x plan text in the experimental workbook are neutralized. The plan itself still cites the transcript by line number as the source of some findings, and quotes the owner's instruction that started this work: **Accepted**, because traceability to the owner's instructions is a stated requirement and none of it identifies the owner. |
| QA-m11 | The attribution in the workbooks had no link to the licence | **Fixed** in both build scripts (licence and repository addresses). |
| QA-m12 | Commit and pull-request attribution carries a link to the Claude session, which stays in public history | **Accepted.** It is the tool's standard attribution, and the link opens only for the owner. The owner was told before the first push and can ask for it to be left out. |

## Changes after the QA report

The fixes above changed files after the review. The orchestrator re-ran, on the final state: the test suite on Python 3.11 and 3.13 (377 passed each); `run --seasons all` (PUBLISH once, then SKIP) and `check` (pass); the plan validator; Microsoft's M parser on all 15 queries; the workbook verifier (284 passed), a LibreOffice recalculation (262 formulas, 0 errors) and M-text equality on the released workbook; both verifiers of the experimental workbook (SHA-256 `5a254114540a7d5648b30e3bc8d959422eadf7bc169cbb74bd688b5cd0128d1b`); and a byte-level search of both workbooks for strings derived from the owner's private base workbook (none found; the only matches are the public GitHub username). This was not a second independent review.

## Not verifiable here (carried into 2.002 and 2.003)

1. Neither workbook has run in Excel: the web refresh and its prompts, the edited Data Model in the experimental file, refresh time.
2. The workflows have never run on GitHub: token rights, the alert-issue commands, schedule timing, and whether the heartbeat commit counts as activity.
3. Whether the session's GitHub access may push workflow files at all is only known at the first push.
