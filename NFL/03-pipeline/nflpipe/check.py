"""``python -m nflpipe check``: verify what is published, read-only (CONTRACTS.md section 7).

Checks ``--data-dir`` as it stands, without downloading anything and without writing:

* G-INDEX with the manifest part: every file in ``manifest.csv`` exists with the recorded
  size and SHA-256, every published CSV is listed, seasons.csv agrees with the
  player_week files, scored files have the same keys in the same order, season types
  are REG or POST only;
* G-GRAIN, G-RECON, G-GOLDEN, G-ESPN and the structural part of G-DST against the
  published files and the fixtures;
* G-CONFIG on the published config copies (``04-data/config/``), with the published
  dictionary as the list of known metrics;
* the advisory G-ROWS, G-LONGTD and G-OVERLAP.

G-SHRINK and G-RESTATE compare a new build with the last publish, so they belong to
``run`` only. Exit codes: 0 pass (advisory warnings allowed), 4 a blocking check failed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import gates
from .config import ConfigError, load_config
from .publish import read_csv

EXIT_PASS, EXIT_FAIL = 0, 4
PROJECT = Path(__file__).resolve().parent.parent.parent
CHECK_GATES = ["G-CONFIG", "G-GRAIN", "G-RECON", "G-GOLDEN", "G-ESPN", "G-DST", "G-INDEX",
               "G-ROWS", "G-LONGTD", "G-OVERLAP"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m nflpipe check",
                                     description="Verify the published 04-data (read-only).")
    parser.add_argument("--data-dir", type=Path, default=PROJECT / "04-data")
    parser.add_argument("--fixtures-dir", type=Path, default=PROJECT / "06-qa" / "fixtures")
    # Accepted for symmetry with `run`; check reads the config copies inside --data-dir.
    parser.add_argument("--config-dir", type=Path, default=PROJECT / "02-config")
    parser.add_argument("--cache-dir", type=Path, default=PROJECT / ".work" / "cache")
    parser.add_argument("--report-dir", type=Path, default=PROJECT / ".work" / "last-run")
    return parser.parse_args(argv)


def build_context(data_dir: Path, fixtures_dir: Path) -> gates.GateContext:
    """A gate context whose candidate is the published folder itself."""
    config = load_config(data_dir / "config")
    seasons_rows = read_csv(data_dir / "seasons.csv")
    if not seasons_rows:
        raise ConfigError(f"{data_dir / 'seasons.csv'} is missing or empty: nothing is published")
    seasons = sorted({int(r["season"]) for r in seasons_rows})
    status = {int(r["season"]): r.get("season_status", "") for r in seasons_rows}
    known = {r["metric"] for r in read_csv(data_dir / "dictionary.csv")}
    return gates.GateContext(config=config, stage_dir=data_dir, data_dir=data_dir, fixtures_dir=fixtures_dir,
                             seasons=seasons, refreshed=[], season_status=status, previous_status=status,
                             known_metrics=known, checked_utc="", games=None, verify_manifest=True)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    data_dir, fixtures_dir = args.data_dir.resolve(), args.fixtures_dir.resolve()
    try:
        context = build_context(data_dir, fixtures_dir)
    except (ConfigError, OSError, ValueError, KeyError) as exc:
        print(f"FAIL: cannot read the published data in {data_dir}: {exc}")
        return EXIT_FAIL
    results, _ = gates.evaluate(context, CHECK_GATES)
    for r in results:
        print(f"  {r.gate_id:<9} {r.result:<4} {r.detail}")
    failures = gates.blocking_failures(results)
    if failures:
        print(f"FAIL: {len(failures)} blocking check(s) failed: {', '.join(r.gate_id for r in failures)}")
        return EXIT_FAIL
    warns = sum(r.result == "WARN" for r in results)
    print(f"PASS: {len(results)} checks on {data_dir.name}" + (f" ({warns} warning(s))" if warns else ""))
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
