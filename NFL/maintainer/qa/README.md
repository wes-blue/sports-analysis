# QA reports

The review reports, re-tests and dispositions for each version, kept as written. They are historical: paths inside them use the layout of their time, so read them with the old-to-new table in [`../README.md`](../README.md#older-paths). The test fixtures and ESPN evidence they cite are still in `NFL/06-qa/`.

## Version 1.006 (earlier repository)

Version 1.006, the last release in the earlier repository, had its own independent review and re-test: 1 critical, 8 major and 15 minor findings, all fixed or dispositioned, and a re-test confirmed the fixes. Those records stay in that repository, because they are written in terms of its folders. One re-test finding, N-1 (the workbook's reconciliation and golden checks disagreed with the pipeline after certain deliberate rule changes), was carried into 2.001 and is fixed there.

## Fixtures: what each is for

The pipeline's gates read the files in `NFL/06-qa/fixtures/` ([`NFL/CONTRACTS.md`](../../CONTRACTS.md) §5.5 and §6). They change only with the maintainer's approval. Row counts in `row_count_baseline.csv` were verified on 2026-11-14.

| File | Purpose | Used by |
|---|---|---|
| `fixtures/golden_sample.csv` | Player-games with hand-checked expected points per league | G-GOLDEN |
| `fixtures/fixture_contracts.csv` | The rules each league had when its expected values were made (league, rules hash, `RoundDecimals`), so a league whose rules changed is skipped with a warning | G-GOLDEN, G-ESPN, G-RECON |
| `fixtures/espn_actuals.csv` | Points ESPN reported for the owner's league, used to prove the ESPN scoring rules | G-ESPN |
| `fixtures/espn_dst_stats.csv` | ESPN's own stat columns for a team defense (TD, INT, FR, SCK, SFTY, BLK, PA), from the game log in `evidence/`, used to prove the inputs to D/ST scoring | G-ESPN |
| `fixtures/row_count_baseline.csv` | Expected rows per completed season | G-ROWS |
| `fixtures/long_td_baseline.csv` | Long-touchdown season totals, 2017-2025, from play-by-play | G-LONGTD |
| `fixtures/long_td_static_2017_2025.csv` | The long-touchdown table used by the 1.x workbooks, kept as a reference: the pipeline's counts were compared with it when it was built. A reference table; no gate uses it. | No gate |
