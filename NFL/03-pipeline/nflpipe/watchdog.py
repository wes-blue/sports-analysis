"""``python -m nflpipe watchdog --max-age-hours N``: did a publish land? (CONTRACTS.md section 7)

Stale (exit 5) when, during the season, an NFL week finished (kickoff + 6 h of
its last game) more than N hours ago and no PUBLISH covers it. "Covers" means
``status.csv`` ``latest_season/latest_week/latest_season_type`` has reached that
week; when status.csv carries no week, the last PUBLISH time (``generated_utc``
in status.csv, ``finished_utc`` in run_log.csv) must be after the week settled.
So a publish that did not add the new week (for example the monthly rebuild)
does not hide a missing week. Healthy (exit 0) otherwise, and always in the
off-season. Errors (schedule download, unreadable published state) exit 1.

Prints ``key=value`` lines (``status``, ``reason``, ...) and appends them to
``$GITHUB_OUTPUT`` when that variable is set.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass, field

from pathlib import Path

from . import freshness as fr

PROJECT = Path(__file__).resolve().parent.parent.parent          # the sport folder, NFL/

EXIT_HEALTHY = 0
EXIT_ERROR = 1
EXIT_STALE = 5


@dataclass
class Verdict:
    status: str          # "healthy" or "stale"
    reason: str
    extras: list[tuple[str, str]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return EXIT_STALE if self.status == "stale" else EXIT_HEALTHY

    def pairs(self) -> list[tuple[str, str]]:
        return [("status", self.status), ("reason", self.reason)] + self.extras


def judge(state: fr.SeasonState, now: dt.datetime, published: fr.Published, max_age_hours: float) -> Verdict:
    """Pure decision."""
    latest = state.latest_finished
    last = published.last_publish_utc()
    through = published.through()
    extras = [
        ("now_utc", fr.iso_utc(now)),
        ("last_publish_utc", fr.iso_utc(last)),
        ("published_through", fr.week_label(*through) if through else ""),
        ("latest_finished_week", latest.label() if latest else ""),
        ("latest_finished_settled_utc", fr.iso_utc(latest.settle_utc) if latest else ""),
        ("max_age_hours", f"{max_age_hours:g}"),
    ]
    if not state.in_season(now):
        return Verdict("healthy", f"off-season (season {state.season}); nothing is expected", extras)
    assert latest is not None  # in_season implies a finished week
    if last is None:
        return Verdict("stale", f"in season and nothing has ever been published; "
                                f"week {latest.week} {latest.season_type} finished at {fr.iso_utc(latest.settle_utc)}",
                       extras)
    age_hours = (now - last).total_seconds() / 3600
    extras.append(("last_publish_age_hours", f"{age_hours:.1f}"))
    finished = [w for w in state.weeks if w.settle_utc <= now]
    if through is not None:
        tkey = fr.week_key(*through)
        uncovered = [w for w in finished if fr.week_key(w.season, w.week, w.season_type) > tkey]
        basis = f"published through {fr.week_label(*through)}"
    else:  # status.csv has no week: fall back to the publish time
        uncovered = [w for w in finished if w.settle_utc > last]
        basis = f"last publish {fr.iso_utc(last)}"
    if not uncovered:
        return Verdict("healthy", f"{basis} covers the latest finished week {latest.label()}", extras)
    oldest = min(uncovered, key=lambda w: w.settle_utc)
    since_settle = (now - oldest.settle_utc).total_seconds() / 3600
    extras.append(("oldest_unpublished_week", oldest.label()))
    if since_settle <= max_age_hours:
        return Verdict("healthy", f"week {oldest.label()} finished {since_settle:.1f} h ago and is not published "
                                  f"yet ({basis}); still inside the {max_age_hours:g} h limit", extras)
    return Verdict("stale", f"week {oldest.week} {oldest.season_type} finished {since_settle:.1f} h ago "
                            f"(limit {max_age_hours:g} h) and no publish covers it; {basis}, last publish "
                            f"{fr.iso_utc(last)} ({age_hours:.1f} h ago); {len(uncovered)} finished week(s) unpublished",
                   extras)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nflpipe watchdog", description="Fail when no publish landed in season.")
    p.add_argument("--max-age-hours", type=float, required=True)
    # Default found from where the package is, like `run` and `check` (QA finding m-04).
    p.add_argument("--data-dir", default=str(PROJECT / "04-data"))
    p.add_argument("--schedule-file", default=None, help="read games.csv from this file (testing)")
    p.add_argument("--now", default=None, help="pretend the time is this ISO 8601 UTC instant (testing)")
    for opt in ("--config-dir", "--fixtures-dir", "--cache-dir", "--report-dir"):
        p.add_argument(opt, default=None, help=argparse.SUPPRESS)
    return p


def main(argv: list[str] | None = None, *, opener=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.max_age_hours <= 0:
            raise ValueError("--max-age-hours must be positive")
        now = fr.parse_utc(args.now) if args.now else fr.utc_now()
        kwargs = {"opener": opener} if opener else {}
        state = fr.season_state(fr.load_schedule(args.schedule_file, **kwargs), now)
        published = fr.read_published(args.data_dir)
        verdict = judge(state, now, published, args.max_age_hours)
        if published.problems:
            raise fr.FreshnessError("published state unreadable: " + "; ".join(published.problems))
    except (fr.FreshnessError, ValueError) as exc:
        fr.write_outputs([("status", "error"), ("reason", f"watchdog failed: {exc}")])
        print(f"watchdog: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    fr.write_outputs(verdict.pairs())
    return verdict.exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
