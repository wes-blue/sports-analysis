# NFL/06-qa: test fixtures and evidence

This folder holds the files that the automatic tests and the pipeline's own checks read. Nothing here is meant to be read or edited by hand. The review reports are in `NFL/maintainer/qa/`.

| Folder | What it holds | Read by |
|---|---|---|
| `fixtures/` | Hand-checked expected values: a golden sample of player-games, the rules each league had when its values were made, ESPN's reported points, row-count and long-touchdown baselines | The pipeline's checks ([`../CONTRACTS.md`](../CONTRACTS.md) §5.5 and §6) and the tests |
| `evidence/` | ESPN Fantasy game logs in one league's scoring, kept verbatim: the Arizona, Indianapolis and New York Jets D/ST and one running back (Arizona), 2026. They show how ESPN counts points allowed and the long-touchdown bonuses ([`../CONTRACTS.md`](../CONTRACTS.md) §3, metric `dst_points_allowed_excl_def`). | The tests and the ESPN check |

Values that come from nflverse data are covered by the attribution in [`/DATA-LICENSE.md`](../../DATA-LICENSE.md). The ESPN values are not nflverse data.
