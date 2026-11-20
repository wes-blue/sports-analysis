"""Record which rules the expected values in ``06-qa/fixtures/`` were made with.

Writes ``06-qa/fixtures/fixture_contracts.csv`` (``league,rules_sha256,round_decimals``): one row
per Active league of the config, with the same rules hash as ``status.csv`` ``contract_<League>``
and the ``RoundDecimals`` setting. G-GOLDEN and G-ESPN compare a league's expected values only
while its current rules still have this hash and RoundDecimals (CONTRACTS.md section 6).

Run it ONLY right after the expected values (``golden_sample.csv``, ``espn_actuals.csv``) were
made or recomputed with the current config; otherwise the gates would compare values made with
other rules. From ``03-pipeline/``:

    python tools/write_fixture_contracts.py            (Windows: py tools\\write_fixture_contracts.py)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE))

from nflpipe.config import load_config  # noqa: E402
from nflpipe.gates import FIXTURE_CONTRACTS, FIXTURE_CONTRACTS_HEADER, fixture_contract_rows  # noqa: E402
from nflpipe.publish import csv_bytes  # noqa: E402

PROJECT = PIPELINE.parent


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config-dir", type=Path, default=PROJECT / "02-config")
    parser.add_argument("--fixtures-dir", type=Path, default=PROJECT / "06-qa" / "fixtures")
    args = parser.parse_args(argv)
    config = load_config(args.config_dir)
    if config.problems:
        print("config has problems, nothing written: " + "; ".join(config.problems[:3]), file=sys.stderr)
        return 1
    target = args.fixtures_dir / FIXTURE_CONTRACTS
    target.write_bytes(csv_bytes(FIXTURE_CONTRACTS_HEADER, fixture_contract_rows(config)))
    print(f"wrote {target} ({len(config.active_leagues)} leagues, RoundDecimals {config.round_decimals})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
