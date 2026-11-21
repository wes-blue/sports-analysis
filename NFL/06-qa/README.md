# NFL/06-qa: test fixtures and evidence

This folder holds the files that the automatic tests and the pipeline's own checks read. Nothing here is meant to be read or edited by hand. The review reports are in `NFL/maintainer/qa/`.

| Folder | What it holds | Read by |
|---|---|---|
| `fixtures/` | Hand-checked expected values: a golden sample of player-games, the rules each league had when its values were made, ESPN's reported points, row-count and long-touchdown baselines | The pipeline's checks ([`../CONTRACTS.md`](../CONTRACTS.md) §5.5 and §6) and the tests |
| `evidence/` | The ESPN game log for the Arizona D/ST, 2026 weeks 1 to 10, kept verbatim. It shows how ESPN counts points allowed ([`../CONTRACTS.md`](../CONTRACTS.md) §3, metric `dst_points_allowed_excl_def`). | The tests and the ESPN check |

Values that come from nflverse data are covered by the attribution in [`/DATA-LICENSE.md`](../../DATA-LICENSE.md). The ESPN values are not nflverse data.
