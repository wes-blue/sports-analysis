"""``python -m nflpipe run``: ingest, derive, score, check and publish (CONTRACTS.md section 7).

Flow of one run
1. Load 02-config. Structural problems hold the run before anything is downloaded.
2. Find the newest published season ("Latest") and resolve the season window.
3. Decide which seasons to rebuild (``--seasons``; for ``current`` also drifted seasons).
4. Build the complete candidate 04-data in a staging folder: rebuilt seasons from
   upstream, the other seasons copied unchanged from 04-data.
5. Run the gates. A blocking failure is a HOLD: exit 4, 04-data untouched.
6. If no substantive file changed: SKIP, exit 3, 04-data untouched.
7. Otherwise write status.csv, run_log.csv and manifest.csv and copy the changed files
   into 04-data: PUBLISH, exit 0.

Exit codes: 0 PUBLISH, 3 SKIP, 4 HOLD, 1 error.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import data_contract_version, data_license, data_source, gates, pipeline_version
from .config import CONFIG_FILES, Config, ConfigError, load_config, requested_end, resolve_window
from .derive import DERIVED_SOURCES, DST_COLUMNS, LONG_TD_COLUMNS, scan_pbp, team_dst_rows
from .http import DownloadError, Fetched, NotPublished, fetch, head_last_modified, BASE_URL
from .ingest import REFERENCE_COLUMNS, TEXT_COLUMNS, ID_COLUMNS, read_games, read_header, read_player_rows, \
    season_status
from .publish import (LONG_TD_HEADER, SCORED_ID_COLUMNS, PublishError, Stage, changed_files, csv_bytes,
                      format_number, player_week_header, read_csv, row_sort_key, same_content, season_file,
                      sha256_file, sync)
from .scoring import build_rules, score_row

EXIT_PUBLISH, EXIT_ERROR, EXIT_SKIP, EXIT_HOLD = 0, 1, 3, 4
PROJECT = Path(__file__).resolve().parent.parent.parent          # the sport folder, NFL/

SEASON_KINDS = ("stats_player", "stats_team", "pbp")
SEASON_PATHS = {
    "stats_player": "stats_player/stats_player_week_{season}.csv",
    "stats_team": "stats_team/stats_team_week_{season}.csv",
    "pbp": "pbp/play_by_play_{season}.csv.gz",
}
SCHEDULES_PATH = "schedules/games.csv"

SEASONS_HEADER = ["season", "season_type", "player_rows", "dst_rows", "max_week", "season_status", "refreshed_utc"]
SOURCES_HEADER = ["season", "kind", "url", "last_modified", "size_bytes", "sha256", "fetched_utc"]
MANIFEST_HEADER = ["file", "kind", "season", "rows", "columns", "size_bytes", "sha256", "written_utc"]
RUN_LOG_HEADER = ["run_id", "started_utc", "finished_utc", "trigger", "seasons_requested", "seasons_refreshed",
                  "outcome", "latest_season", "latest_week", "latest_season_type", "gates_fail", "gates_warn",
                  "pipeline_version", "notes"]
DICTIONARY_HEADER = ["metric", "category", "description", "source", "applies_to"]


# ---- command line --------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m nflpipe run",
                                     description="Build, check and publish 04-data.")
    parser.add_argument("--seasons", default="current",
                        help="current (default), all, a year (2025) or a range (2017-2026)")
    parser.add_argument("--dry-run", action="store_true", help="do everything except change --data-dir")
    parser.add_argument("--force", action="store_true",
                        help="ignore the download cache and publish even when no data changed")
    parser.add_argument("--trigger", default="manual", help="free text recorded in run_log.csv")
    parser.add_argument("--config-dir", type=Path, default=PROJECT / "02-config")
    parser.add_argument("--data-dir", type=Path, default=PROJECT / "04-data")
    parser.add_argument("--fixtures-dir", type=Path, default=PROJECT / "06-qa" / "fixtures")
    parser.add_argument("--cache-dir", type=Path, default=PROJECT / ".work" / "cache")
    parser.add_argument("--report-dir", type=Path, default=PROJECT / ".work" / "last-run")
    return parser.parse_args(argv)


def say(message: str) -> None:
    print(message, flush=True)


# ---- state of one run ----------------------------------------------------------------------

@dataclass
class RunState:
    """Everything a run learns, gathered in one place so the steps stay small."""
    args: argparse.Namespace
    config: Config
    run_id: str
    started_utc: str
    stage: Stage
    latest_season: int = 0
    seasons: list[int] = field(default_factory=list)
    unpublished: list[int] = field(default_factory=list)    # EndSeason years after Latest (G-WINDOW)
    stale_reason: str = ""                                   # config/pipeline differs from status.csv
    refreshed: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    known_metrics: set[str] = field(default_factory=set)
    sources: list[list] = field(default_factory=list)       # sources.csv rows
    season_rows: list[list] = field(default_factory=list)   # seasons.csv rows
    status_by_season: dict[int, str] = field(default_factory=dict)
    games: list[dict] = field(default_factory=list)
    previous_sources: dict[str, dict] = field(default_factory=dict)   # url -> row
    previous_seasons: list[dict] = field(default_factory=list)
    previous_status: dict[str, str] = field(default_factory=dict)
    fetched: dict[tuple[str, int], Fetched] = field(default_factory=dict)
    pbp_scans: dict[int, object] = field(default_factory=dict)        # season -> derive.PbpScan (G-DST)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id() -> str:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    github_run = os.environ.get("GITHUB_RUN_ID", "").strip()
    return f"{run_id}-gh{github_run}" if github_run.isdigit() else run_id


# ---- step 2: latest season and window ------------------------------------------------------

def fetch_season_file(state: RunState, kind: str, season: int) -> Fetched:
    """Fetch one season file (at most once per run)."""
    key = (kind, season)
    if key not in state.fetched:
        state.fetched[key] = fetch(SEASON_PATHS[kind].format(season=season), state.args.cache_dir,
                                   force=state.args.force)
    return state.fetched[key]


def has_player_rows(path: Path) -> bool:
    """True when a stats_player file holds at least one real (non-placeholder) row."""
    from .ingest import iter_columns
    return any(r["player_id"].strip() for r in iter_columns(path, ["player_id"]))


def find_latest_season(state: RunState) -> int:
    """Newest season whose stats_player file is published and has data (Stats_Raw.pq rule):
    this calendar year if so, otherwise the year before."""
    year = datetime.now(timezone.utc).year
    for season in (year, year - 1):
        try:
            fetched = fetch_season_file(state, "stats_player", season)
        except NotPublished:
            continue
        if has_player_rows(fetched.path):
            return season
    raise DownloadError(f"no published nflverse stats_player season found for {year} or {year - 1}")


def parse_season_request(text: str, window: list[int]) -> list[int] | None:
    """--seasons value as a list of years; None means 'current' (decided later)."""
    text = text.strip().lower()
    if text == "current":
        return None
    if text == "all":
        return list(window)
    try:
        if "-" in text:
            first, last = (int(x) for x in text.split("-", 1))
        else:
            first = last = int(text)
    except ValueError:
        raise ConfigError(f"--seasons must be current, all, YYYY or YYYY-YYYY (found: {text})")
    requested = list(range(first, last + 1))
    outside = [s for s in requested if s not in window]
    if not requested or outside:
        raise ConfigError(f"--seasons {text}: season(s) {outside or text} are outside the window "
                          f"{window[0]}-{window[-1]} set in pipeline_config.csv")
    return requested


# ---- step 3: which seasons to rebuild ------------------------------------------------------

def season_published(data_dir: Path, season: int) -> bool:
    return all((data_dir / season_file(kind, season)).is_file() for kind in ("player_week", "scored", "long_td"))


def config_changed(state: RunState) -> str:
    """Why previously published seasons are stale for this config/pipeline, or ''."""
    prev = state.previous_status
    if not prev:
        return ""
    if prev.get("config_sha256") != state.config.sha256:
        return "config changed"
    if prev.get("pipeline_version") != pipeline_version:
        return "pipeline version changed"
    if prev.get("data_contract_version") != data_contract_version:
        return "data contract changed"
    if prev.get("season_types") != state.config.season_types_text:
        return "season types changed"
    return ""


def drifted(state: RunState, season: int) -> list[str]:
    """Upstream files of a season whose Last-Modified differs from sources.csv (D-029)."""
    kinds = []
    for kind in SEASON_KINDS:
        url = BASE_URL + SEASON_PATHS[kind].format(season=season)
        previous = state.previous_sources.get(url)
        try:
            upstream = head_last_modified(url)
        except NotPublished:
            upstream = ""
        if previous is None or previous.get("last_modified", "") != upstream:
            kinds.append(kind)
    return kinds


def choose_seasons(state: RunState, requested: list[int] | None) -> list[int]:
    """Seasons to rebuild. Unpublished seasons and a changed config always force a rebuild."""
    data_dir = state.args.data_dir
    stale_reason = state.stale_reason = config_changed(state)
    if stale_reason:
        state.notes.append(f"{stale_reason}: every season rebuilt")
        return list(state.seasons)
    chosen = set(requested) if requested is not None else {state.latest_season}
    for season in state.seasons:
        if season in chosen:
            continue
        if not season_published(data_dir, season):
            chosen.add(season)
            state.notes.append(f"{season} not yet published")
        elif requested is None:
            kinds = drifted(state, season)
            if kinds:
                chosen.add(season)
                state.notes.append(f"{season} drift: {'+'.join(kinds)}")
    return sorted(chosen)


# ---- step 4: build -------------------------------------------------------------------------

def metric_columns(config: Config, latest_header: list[str]) -> list[str]:
    """player_week metric columns in dictionary order (CONTRACTS.md 5.1)."""
    metrics = [w.metric for w in config.weights if w.metric]
    for b in config.bands:
        if b.metric and b.metric not in metrics:
            metrics.append(b.metric)
    extra = config.extra_columns_setting
    if extra.upper() == "ALL":
        skip = TEXT_COLUMNS | set(ID_COLUMNS) | set(REFERENCE_COLUMNS) | {"season", "week"}
        candidates = [c for c in latest_header if c not in skip]
    else:
        candidates = [c.strip() for c in extra.split(",") if c.strip()]
    for c in candidates:
        if c not in metrics:
            metrics.append(c)
    return list(dict.fromkeys(metrics))


def add_source(state: RunState, season: int | None, kind: str, fetched: Fetched) -> None:
    """Record an upstream file for sources.csv, keeping the earlier fetched_utc for identical bytes."""
    previous = state.previous_sources.get(fetched.url)
    fetched_utc = fetched.fetched_utc
    if previous and previous.get("sha256") == fetched.sha256 and previous.get("last_modified") == fetched.last_modified:
        fetched_utc = previous.get("fetched_utc") or fetched_utc
    state.sources.append(["" if season is None else season, kind, fetched.url, fetched.last_modified,
                          fetched.size_bytes, fetched.sha256, fetched_utc])


def build_season(state: RunState, season: int, rules) -> None:
    """Download, derive, score and stage the three files of one season."""
    config, types = state.config, state.config.season_types
    t0 = time.monotonic()
    files: dict[str, Fetched | None] = {}
    for kind in SEASON_KINDS:
        try:
            files[kind] = fetch_season_file(state, kind, season)
            add_source(state, season, kind, files[kind])
        except NotPublished:
            if kind == "stats_player":
                raise DownloadError(f"stats_player_week_{season}.csv is not published")
            files[kind] = None
            state.notes.append(f"{season}: {kind} not published yet")

    derived = set(DERIVED_SOURCES)
    nflverse_metrics = [m for m in state.metrics if m not in derived]
    players = read_player_rows(files["stats_player"].path, types, nflverse_metrics)
    scan = scan_pbp(files["pbp"].path, types) if files["pbp"] else None
    if scan is not None:
        state.pbp_scans[season] = scan
    long_td = scan.long_td if scan is not None else {}
    dst = team_dst_rows(files["stats_team"].path, state.games, types, scan) if files["stats_team"] else []

    zero = dict.fromkeys(LONG_TD_COLUMNS, 0)
    for row in players:
        key = (row["season"], row["week"], row["season_type"], row["player_id"])
        row.update(long_td.get(key, zero))
        for c in DST_COLUMNS:
            row[c] = None
    rows = sorted(players + dst, key=row_sort_key)

    header = player_week_header(state.metrics)
    state.stage.write_table(season_file("player_week", season), header,
                            ([row.get(c) for c in header] for row in rows))
    decimals = config.round_decimals
    scored_header = SCORED_ID_COLUMNS + [lg.column for lg in rules]
    state.stage.write_table(season_file("scored", season), scored_header,
                            ([row.get(c) for c in SCORED_ID_COLUMNS] + [score_row(row, lg, decimals) for lg in rules]
                             for row in rows))
    state.stage.write_table(season_file("long_td", season), LONG_TD_HEADER,
                            (list(key) + [long_td[key][c] for c in LONG_TD_COLUMNS] for key in sorted(long_td)))

    summary = defaultdict(lambda: [0, 0, 0])                 # season_type -> [players, dst, max_week]
    for row in rows:
        entry = summary[row["season_type"]]
        entry[1 if row["position"] == "DST" and row["player_id"].startswith("DST_") else 0] += 1
        entry[2] = max(entry[2], row["week"])
    unchanged = all(not_changed(state, season_file(kind, season)) for kind in ("player_week", "scored", "long_td"))
    for season_type in sorted(summary):
        players_n, dst_n, max_week = summary[season_type]
        refreshed_utc = previous_refreshed(state, season, season_type) if unchanged else ""
        state.season_rows.append([season, season_type, players_n, dst_n, max_week,
                                  state.status_by_season[season], refreshed_utc or state.started_utc])
    say(f"  {season}: {len(players)} player rows, {len(dst)} D/ST rows, {len(long_td)} long-TD player-games "
        f"({time.monotonic() - t0:.1f}s)")


def not_changed(state: RunState, relative: str) -> bool:
    return same_content(state.args.data_dir / relative, state.stage.path(relative))


def previous_refreshed(state: RunState, season: int, season_type: str) -> str:
    for row in state.previous_seasons:
        if row.get("season") == str(season) and row.get("season_type") == season_type:
            return row.get("refreshed_utc", "")
    return ""


def keep_season(state: RunState, season: int) -> None:
    """Copy an unchanged season's files and index rows from the published 04-data."""
    for kind in ("player_week", "scored", "long_td"):
        relative = season_file(kind, season)
        state.stage.copy_in(state.args.data_dir / relative, relative)
    for row in state.previous_seasons:
        if row.get("season") == str(season):
            state.season_rows.append([season, row["season_type"], int(row["player_rows"]), int(row["dst_rows"]),
                                      int(row["max_week"]), state.status_by_season[season], row["refreshed_utc"]])
    for url, row in state.previous_sources.items():
        if row.get("season") == str(season):
            state.sources.append([season, row["kind"], url, row["last_modified"], int(row["size_bytes"] or 0),
                                  row["sha256"], row["fetched_utc"]])


def write_index_files(state: RunState) -> None:
    """seasons.csv, sources.csv, dictionary.csv and the config copies."""
    stage, config = state.stage, state.config
    state.season_rows.sort(key=lambda r: (int(r[0]), r[1]))
    stage.write_table("seasons.csv", SEASONS_HEADER, state.season_rows)
    state.sources.sort(key=lambda r: (-1 if r[0] == "" else int(r[0]), r[1]))
    stage.write_table("sources.csv", SOURCES_HEADER, state.sources)

    by_metric = {w.metric: w for w in config.weights}
    rows = []
    for metric in state.metrics:
        w = by_metric.get(metric)
        source = DERIVED_SOURCES.get(metric, "nflverse")
        if w is not None:
            rows.append([metric, w.category, w.description, source, w.applies_to])
        elif any(b.metric == metric for b in config.bands):
            rows.append([metric, "Bonus band", "Used by bonus_rules.csv", source, ""])
        else:
            rows.append([metric, "Extra column", "Published via PublishExtraColumns", source, ""])
    stage.write_table("dictionary.csv", DICTIONARY_HEADER, rows)
    normalized = config.normalized                  # CONTRACTS.md 5.4: normalized copies
    for name in CONFIG_FILES:
        stage.write(f"config/{name}", normalized[name])


# ---- step 7: run files ---------------------------------------------------------------------

def latest_week(state: RunState) -> tuple[int, str]:
    rows = [r for r in state.season_rows if int(r[0]) == state.latest_season]
    if not rows:
        return 0, ""
    best = max(rows, key=lambda r: (int(r[4]), r[1] == "POST"))
    return int(best[4]), best[1]


def write_run_files(state: RunState, results: list[gates.GateResult], requested_text: str) -> None:
    """status.csv, run_log.csv (one appended row) and manifest.csv, in that order."""
    stage, config = state.stage, state.config
    week, week_type = latest_week(state)
    count = lambda value: sum(r.result == value for r in results)          # noqa: E731
    finished = utc_now()
    refreshed_text = ",".join(str(s) for s in state.refreshed)
    status = [
        ("run_id", state.run_id), ("generated_utc", finished), ("pipeline_version", pipeline_version),
        ("data_contract_version", data_contract_version), ("outcome", "PUBLISH"),
        ("window_start", state.seasons[0]), ("window_end", state.seasons[-1]),
        ("season_types", config.season_types_text), ("latest_season", state.latest_season),
        ("latest_week", week), ("latest_season_type", week_type),
        ("upstream_last_modified_max", max((r[3] for r in state.sources if r[3]), default="")),
        ("config_sha256", config.sha256), ("gates_pass", count("PASS")), ("gates_warn", count("WARN")),
        ("gates_fail", count("FAIL")), ("seasons_refreshed", refreshed_text),
        ("data_source", data_source), ("data_license", data_license),
    ] + [(f"contract_{lg.name}", config.league_contract_hash(lg.name)) for lg in config.active_leagues]
    stage.write_table("status.csv", ["key", "value"], status)

    log = read_csv(state.args.data_dir / "run_log.csv")
    log_rows = [[r.get(c, "") for c in RUN_LOG_HEADER] for r in log]
    log_rows.append([state.run_id, state.started_utc, finished, state.args.trigger, requested_text, refreshed_text,
                     "PUBLISH", state.latest_season, week, week_type, count("FAIL"), count("WARN"),
                     pipeline_version, "; ".join(state.notes)])
    stage.write_table("run_log.csv", RUN_LOG_HEADER, log_rows)
    write_manifest(state, finished)


def write_manifest(state: RunState, now: str) -> None:
    """One row per staged file except manifest.csv; written_utc is kept for unchanged files."""
    previous = {r["file"]: r for r in read_csv(state.args.data_dir / "manifest.csv")}
    rows = []
    for relative in state.stage.files():
        if relative == "manifest.csv":
            continue
        path = state.stage.path(relative)
        sha = sha256_file(path)
        data_rows, columns = csv_shape(path)
        kind, season = manifest_kind(relative)
        old = previous.get(relative)
        written = old["written_utc"] if old and old.get("sha256") == sha else now
        rows.append([relative, kind, season, data_rows, columns, path.stat().st_size, sha, written])
    state.stage.write_table("manifest.csv", MANIFEST_HEADER, rows)


def csv_shape(path: Path) -> tuple[int, int]:
    """(data rows, columns) of a published CSV; counted with the csv module (quoted newlines)."""
    import csv
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        return sum(1 for _ in reader), len(header)


def manifest_kind(relative: str) -> tuple[str, str]:
    """Manifest kind and season of a published file."""
    parts = relative.split("/")
    if len(parts) == 2 and parts[0] in ("player_week", "scored", "long_td"):
        return parts[0], parts[1].rsplit("_", 1)[1].split(".")[0]
    if parts[0] in ("config", "checks"):
        return parts[0], ""
    return relative.rsplit(".", 1)[0], ""


def write_report(state: RunState, outcome: str, detail: str) -> None:
    """Gate results and a short summary always go to --report-dir (even on HOLD or SKIP)."""
    report = state.args.report_dir
    if report.exists():
        shutil.rmtree(report)
    report.mkdir(parents=True)
    checks = state.stage.path("checks")
    if checks.is_dir():
        shutil.copytree(checks, report / "checks")
    for name in ("status.csv", "seasons.csv"):
        if state.stage.path(name).is_file():
            shutil.copyfile(state.stage.path(name), report / name)
    summary = [("run_id", state.run_id), ("outcome", outcome), ("detail", detail),
               ("seasons_refreshed", ",".join(str(s) for s in state.refreshed)), ("notes", "; ".join(state.notes))]
    (report / "run_summary.csv").write_bytes(csv_bytes(["key", "value"], summary))


# ---- the command ---------------------------------------------------------------------------

def gate_context(state: RunState) -> gates.GateContext:
    previous_status = {}
    for row in state.previous_seasons:
        previous_status[int(row["season"])] = row.get("season_status", "")
    return gates.GateContext(
        config=state.config, stage_dir=state.stage.root, data_dir=state.args.data_dir,
        fixtures_dir=state.args.fixtures_dir, seasons=list(state.seasons), refreshed=list(state.refreshed),
        season_status=dict(state.status_by_season), previous_status=previous_status,
        known_metrics=set(state.known_metrics), checked_utc=state.started_utc, notes=state.notes,
        previous_season_types=state.previous_status.get("season_types", ""),
        latest_season=state.latest_season or None, unpublished_seasons=list(state.unpublished),
        games=state.games, team_files={season: fetched.path for (kind, season), fetched in state.fetched.items()
                                       if kind == "stats_team" and season in state.refreshed},
        pbp_scans={season: scan for season, scan in state.pbp_scans.items() if season in state.refreshed})


def execute(args: argparse.Namespace) -> int:
    """One run; returns the exit code. Nothing in --data-dir changes before the final sync."""
    t0 = time.monotonic()
    config = load_config(args.config_dir)
    stage_root = args.cache_dir.parent / "stage"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True)
    state = RunState(args, config, new_run_id(), utc_now(), Stage(stage_root))
    state.previous_status = {r["key"]: r["value"] for r in read_csv(args.data_dir / "status.csv")}
    state.previous_seasons = read_csv(args.data_dir / "seasons.csv")
    state.previous_sources = {r["url"]: r for r in read_csv(args.data_dir / "sources.csv")}

    if config.problems:                                   # broken config: hold before downloading
        results = gates.run_config_gate_only(gate_context(state))
        write_report(state, "HOLD", results[0].detail)
        say(f"HOLD: {results[0].detail}")
        return EXIT_HOLD

    state.latest_season = find_latest_season(state)
    start, end = resolve_window(config, state.latest_season)
    state.seasons = list(range(start, end + 1))
    state.unpublished = list(range(end + 1, requested_end(config, state.latest_season) + 1))
    if state.unpublished:
        state.notes.append(f"EndSeason asks for unpublished season(s) {state.unpublished[0]}-{state.unpublished[-1]}"
                           f"; window ends at {end} for now")
    requested = parse_season_request(args.seasons, state.seasons)
    say(f"window {start}-{end} ({config.season_types_text}), latest season {state.latest_season}"
        + (f"; EndSeason {state.unpublished[-1]} is not published yet, so the window stops at {end}"
           if state.unpublished else ""))

    games = fetch(SCHEDULES_PATH, args.cache_dir, force=args.force)
    add_source(state, None, "schedules", games)
    state.games = read_games(games.path)
    state.status_by_season = {s: season_status(state.games, s) for s in state.seasons}

    latest_header = read_header(fetch_season_file(state, "stats_player", state.latest_season).path)
    state.metrics = metric_columns(config, latest_header)
    state.known_metrics = set(latest_header) | set(DERIVED_SOURCES)

    state.refreshed = choose_seasons(state, requested)
    say(f"rebuilding {len(state.refreshed)} season(s): {', '.join(map(str, state.refreshed))}")
    rules = build_rules(config)
    for season in state.seasons:
        if season in state.refreshed:
            build_season(state, season, rules)
        else:
            keep_season(state, season)
    write_index_files(state)

    # Hook for G-RESTATE (B2): refreshed seasons that were published as complete are compared
    # inside gates.run_gates via context.refreshed / previous_status / previous().
    results = gates.run_gates(gate_context(state))
    for r in results:
        say(f"  {r.gate_id:<9} {r.result:<4} {r.detail}")
    failures = gates.blocking_failures(results)
    if failures:
        detail = "; ".join(f"{r.gate_id}: {r.detail}" for r in failures)
        write_report(state, "HOLD", detail)
        say(f"HOLD ({time.monotonic() - t0:.0f}s): {detail}")
        return EXIT_HOLD

    changed = changed_files(state.stage, args.data_dir, include_volatile=False)
    # A new pipeline version or config must be recorded in status.csv even when no data file changed,
    # otherwise every later run (and `resolve`) would see it as changed again (QA finding M-07).
    if not changed and not args.force and not state.stale_reason:
        write_report(state, "SKIP", "no published file would change")
        say(f"SKIP ({time.monotonic() - t0:.0f}s): nothing changed")
        return EXIT_SKIP

    write_run_files(state, results, args.seasons)
    checked, manifest = gates.manifest_problems(state.stage.root)      # G-INDEX manifest part (B2)
    if manifest:
        detail = f"G-INDEX: staged manifest.csv disagrees with the files: {'; '.join(manifest[:3])}"
        write_report(state, "HOLD", detail)
        say(f"HOLD ({time.monotonic() - t0:.0f}s): {detail}")
        return EXIT_HOLD
    if args.dry_run:
        write_report(state, "PUBLISH (dry run)", f"{len(changed)} data file(s) changed")
        say(f"DRY RUN ({time.monotonic() - t0:.0f}s): would publish {len(changed)} changed data file(s)")
        return EXIT_PUBLISH
    try:
        written, removed = sync(state.stage, args.data_dir, backup_dir=args.cache_dir.parent / "publish-backup")
    except PublishError as exc:
        write_report(state, "ERROR", f"publishing failed, 04-data unchanged: {exc}")
        print(f"ERROR: publishing failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    write_report(state, "PUBLISH", f"{len(changed)} data file(s) changed")
    say(f"PUBLISH ({time.monotonic() - t0:.0f}s): {len(written)} file(s) written, {len(removed)} removed")
    return EXIT_PUBLISH


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    for name in ("config_dir", "data_dir", "fixtures_dir", "cache_dir", "report_dir"):
        setattr(args, name, Path(getattr(args, name)).resolve())
    try:
        return execute(args)
    except (ConfigError, DownloadError, NotPublished) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:                                   # unexpected: still exit 1, data untouched
        print(f"ERROR (unexpected): {type(exc).__name__}: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return EXIT_ERROR
