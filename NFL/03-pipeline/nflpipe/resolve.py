"""``python -m nflpipe resolve``: is there new data to process? (CONTRACTS.md section 7)

Reads the nflverse schedule for the latest *finished* week (kickoff + 6 h,
regular season and playoffs), the upstream ``Last-Modified`` of
``stats_player_week_<season>.csv`` (and ``stats_team_week_<season>.csv``), and
what ``--data-dir`` has published (``status.csv``, ``sources.csv``).

Prints ``key=value`` lines and appends them to ``$GITHUB_OUTPUT`` when set.
Keys: ``action``, ``season``, ``week``, ``season_type``, ``upstream_last_modified``,
``published_through``, ``reason`` (plus informational extras).

Exit codes: ``0`` run, ``3`` skip, ``1`` error.

Decision rules:
- Upstream errors (schedule download, probe failure other than 404) fail closed: exit 1.
- Local published state that is missing, empty or unreadable never causes a skip:
  the answer is ``run`` (prior-art B5, fail open on the skip decision).
- ``run`` when the config in ``--config-dir`` or the pipeline version differs from what
  ``status.csv`` records (``config_sha256``, ``pipeline_version``), so a scoring change pushed
  to GitHub is published at the next scheduled attempt, in season or not (QA finding M-07).
- ``run`` when the upstream file is newer than the ``last_modified`` that
  ``sources.csv`` recorded for it (or nothing is recorded for this season).
- ``skip`` otherwise, with a plain reason: week finished but nflverse has not
  updated yet, upstream not updated since last publish, or off-season.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import freshness as fr
from . import pipeline_version

PROJECT = Path(__file__).resolve().parent.parent.parent          # the sport folder, NFL/

EXIT_RUN = 0
EXIT_ERROR = 1
EXIT_SKIP = 3

#: Upstream kinds probed for change. ``stats_player`` is the contract's gate; ``stats_team``
#: is probed too so a late Team D/ST rebuild is not missed.
PROBED_KINDS = ("stats_player", "stats_team")


@dataclass
class Decision:
    action: str                      # "run" or "skip"
    reason: str
    season: int | None = None
    week: int | None = None
    season_type: str = ""
    upstream_last_modified: str = ""
    published_through: str = ""
    extras: list[tuple[str, str]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return EXIT_RUN if self.action == "run" else EXIT_SKIP

    def pairs(self) -> list[tuple[str, str]]:
        base = [
            ("action", self.action),
            ("season", "" if self.season is None else str(self.season)),
            ("week", "" if self.week is None else str(self.week)),
            ("season_type", self.season_type),
            ("upstream_last_modified", self.upstream_last_modified),
            ("published_through", self.published_through),
            ("reason", self.reason),
        ]
        return base + self.extras


def local_change(published: fr.Published, config_dir: Path | str | None,
                 version: str = pipeline_version) -> str:
    """Why the published data is stale for THIS config and pipeline, or '' (QA finding M-07).

    Compares ``status.csv`` ``pipeline_version`` and ``config_sha256`` (over the normalized config,
    CONTRACTS.md 5.4) with the running pipeline and ``config_dir``. Nothing published yet, or a
    status.csv without those keys, gives ''. A config that cannot be read counts as changed, so
    the run that follows reports the problem instead of the schedule silently skipping.
    """
    status = published.status
    if not status:
        return ""
    reasons = []
    recorded_version = status.get("pipeline_version", "")
    if recorded_version and recorded_version != version:
        reasons.append(f"pipeline version {recorded_version} -> {version}")
    recorded_sha = status.get("config_sha256", "")
    if recorded_sha and config_dir is not None:
        from .config import ConfigError, load_config      # local: resolve stays usable without a config
        try:
            current = load_config(Path(config_dir)).sha256
        except ConfigError as exc:
            reasons.append(f"the config in 02-config cannot be read ({exc})")
        else:
            if current != recorded_sha:
                reasons.append("the config in 02-config differs from the one last published (config_sha256)")
    return "; ".join(reasons)


def decide(
    state: fr.SeasonState,
    now: dt.datetime,
    published: fr.Published,
    probes: dict[str, fr.Probe | None],
    change: str = "",
) -> Decision:
    """Pure decision. ``probes[kind]`` is ``None`` when the upstream file is missing (404).

    ``change`` is ``local_change(...)``: a non-empty reason means the published data was made
    with another config or pipeline version, so the answer is ``run`` whatever upstream did.
    """
    latest = state.latest_finished
    season = state.season
    through = published.through()
    d = Decision(
        action="skip",
        reason="",
        season=season,
        week=latest.week if latest else None,
        season_type=latest.season_type if latest else "",
        published_through=fr.week_label(*through) if through else "",
    )
    player = probes.get("stats_player")
    d.upstream_last_modified = fr.iso_utc(player.last_modified) if player else ""
    if latest:
        d.extras.append(("finished_week_settled_utc", fr.iso_utc(latest.settle_utc)))
    d.extras.append(("now_utc", fr.iso_utc(now)))

    if change and not published.first_run and not published.problems:
        d.action = "run"
        d.reason = (f"{change}; running so the change is published now instead of waiting for nflverse "
                    "(every season in the window is rebuilt)")
        return d

    if latest is None:
        first = min(w.first_kickoff_utc for w in state.weeks)
        d.reason = (f"no week of the {season} season has finished yet "
                    f"(first kickoff {fr.iso_utc(first)})")
        return d

    if player is None:
        d.reason = (f"nflverse has not published stats_player_week_{season}.csv yet "
                    f"(week {latest.week} {latest.season_type} has finished)")
        return d

    if published.problems:
        d.action = "run"
        d.reason = ("published state unreadable (" + "; ".join(published.problems)
                    + "); running so the pipeline can rebuild it")
        return d

    if published.first_run:
        d.action = "run"
        d.reason = "first run: nothing published in the data folder yet"
        return d

    changed = []
    for kind in PROBED_KINDS:
        probe = probes.get(kind)
        if probe is None:
            continue
        recorded = published.recorded_last_modified(kind, season)
        if recorded is None or probe.last_modified > recorded:
            changed.append((kind, probe.last_modified, recorded))
    if published.problems:  # bad timestamps inside sources.csv
        d.action = "run"
        d.reason = "published state unreadable (" + "; ".join(published.problems) + "); running"
        return d

    behind = through is None or fr.week_key(*through) < fr.week_key(season, latest.week, latest.season_type)

    if changed:
        parts = []
        for kind, lm, rec in changed:
            parts.append(f"{kind} {fr.iso_utc(lm)} vs recorded {fr.iso_utc(rec) or 'none'}")
        d.action = "run"
        d.reason = "upstream updated since last publish (" + "; ".join(parts) + ")"
        if behind:
            d.reason += f"; week {latest.week} {latest.season_type} finished and not yet published"
        return d

    if behind:
        d.reason = (f"week {latest.week} {latest.season_type} finished but nflverse has not updated "
                    f"stats_player since last publish (Last-Modified {d.upstream_last_modified}); "
                    f"a later attempt will retry")
        return d

    if state.season_complete:
        if state.in_season(now):
            d.reason = (f"off-season: the {season} season is complete and published; "
                        f"upstream not updated since last publish")
        else:
            nxt = fr.iso_utc(state.next_season_start_utc) or "not yet scheduled"
            d.reason = f"off-season: the {season} season is complete; next season starts {nxt}"
        return d

    d.reason = (f"upstream not updated since last publish (Last-Modified {d.upstream_last_modified}); "
                f"published through {d.published_through}")
    return d


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nflpipe resolve", description="Decide whether there is new data to process.")
    # Defaults are found from where the package is, like `run` and `check` (QA finding m-04).
    p.add_argument("--data-dir", default=str(PROJECT / "04-data"))
    p.add_argument("--config-dir", default=str(PROJECT / "02-config"),
                   help="config compared with status.csv config_sha256")
    p.add_argument("--schedule-file", default=None,
                   help="read games.csv from this file instead of downloading it (testing)")
    p.add_argument("--now", default=None, help="pretend the time is this ISO 8601 UTC instant (testing)")
    # Common options from CONTRACTS.md section 7; accepted so the dispatcher can pass them, unused here.
    for opt in ("--fixtures-dir", "--cache-dir", "--report-dir"):
        p.add_argument(opt, default=None, help=argparse.SUPPRESS)
    return p


def probe_all(season: int, opener=None) -> dict[str, fr.Probe | None]:
    kwargs = {"opener": opener} if opener else {}
    probes: dict[str, fr.Probe | None] = {}
    for kind in PROBED_KINDS:
        try:
            probes[kind] = fr.probe_last_modified(fr.upstream_url(kind, season), **kwargs)
        except fr.UpstreamMissing:
            probes[kind] = None
    return probes


def main(argv: list[str] | None = None, *, opener=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        now = fr.parse_utc(args.now) if args.now else fr.utc_now()
        kwargs = {"opener": opener} if opener else {}
        games = fr.load_schedule(args.schedule_file, **kwargs)
        state = fr.season_state(games, now)
        published = fr.read_published(args.data_dir)
        probes = probe_all(state.season, opener)
        decision = decide(state, now, published, probes, local_change(published, args.config_dir))
    except (fr.FreshnessError, ValueError) as exc:
        fr.write_outputs([("action", "error"), ("reason", f"resolve failed: {exc}")])
        print(f"resolve: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    player = probes.get("stats_player")
    if player:
        decision.extras.append(("probe_method", player.method))
    fr.write_outputs(decision.pairs())
    return decision.exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
