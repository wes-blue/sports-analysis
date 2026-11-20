# NFL/06-qa: QA records, evidence and test fixtures

Everything here is public. Personal details are never written into these files.

## QA records

| File | What it is |
|---|---|
| `qa-report-2.001.md` | The independent review of version 2.001, the first release in this repository |
| `qa-disposition-2.001.md` | What was done about each finding |

Version 1.006, the last release in the owner's private repository, had its own independent review and re-test (1 critical, 8 major and 15 minor findings, all fixed or dispositioned; a re-test confirmed the fixes). Those records are kept in the private repository, because they are written in terms of its folders. One re-test finding, N-1 (the workbook's reconciliation and golden checks disagreed with the pipeline after certain deliberate rule changes), was carried into 2.001 and is fixed there.

## Evidence

| File | What it is |
|---|---|
| `evidence/espn-game-log-ARI-DST-2026.txt` | The owner's ESPN game log for the Arizona D/ST, 2026 weeks 1–10, kept verbatim. It shows how ESPN counts points allowed (decision D-038 in [`/00-Governance/DECISIONS.md`](../../00-Governance/DECISIONS.md); [`../CONTRACTS.md`](../CONTRACTS.md) §3, metric `dst_points_allowed_excl_def`). |

## Fixtures

The pipeline's gates read these files ([`../CONTRACTS.md`](../CONTRACTS.md) §5.5 and §6). They change only with the orchestrator's approval.

| File | Purpose | Used by |
|---|---|---|
| `fixtures/golden_sample.csv` | Player-games with hand-checked expected points per league | G-GOLDEN |
| `fixtures/fixture_contracts.csv` | The rules each league had when its expected values were made (league, rules hash, `RoundDecimals`), so a league whose rules changed is skipped with a warning | G-GOLDEN, G-ESPN, G-RECON |
| `fixtures/espn_actuals.csv` | Points ESPN reported for the owner's league, used to prove the ESPN scoring rules | G-ESPN |
| `fixtures/espn_dst_stats.csv` | ESPN's own stat columns for a team defense (TD, INT, FR, SCK, SFTY, BLK, PA), from the game log in `evidence/`, used to prove the inputs to D/ST scoring | G-ESPN |
| `fixtures/row_count_baseline.csv` | Expected rows per completed season (verified 2026-11-14) | G-ROWS |
| `fixtures/long_td_baseline.csv` | Long-touchdown season totals, 2017–2025, from play-by-play | G-LONGTD |
| `fixtures/long_td_static_2017_2025.csv` | The long-touchdown table used by the 1.x workbooks, kept as a reference: the pipeline's counts were compared with it when it was built | No gate |

Values in these fixtures that come from nflverse data are covered by the attribution in [`/DATA-LICENSE.md`](../../DATA-LICENSE.md). The ESPN values are not nflverse data.
