"""Publish gates (CONTRACTS.md section 6) and the check files (section 5.5).

Owner: B2 Gates and Test Engineer (first version by B1, which implemented G-CONFIG,
G-GRAIN and G-RECON; the interface below is unchanged).

Interface
---------
``run_gates(context) -> list[GateResult]`` runs every gate, writes the check files into
``context.stage_dir/checks/`` and returns the results. ``run.py`` holds the run (exit 4,
04-data untouched) when any result has ``severity == "blocking"`` and ``result == "FAIL"``.
``evaluate(context, gate_ids)`` runs a chosen set of gates without writing anything
(used by the read-only ``check`` command).

The context (``GateContext``) describes one run:

* ``stage_dir`` is the COMPLETE candidate 04-data: every season file of the window is
  there (rebuilt seasons freshly written, the other seasons copied unchanged from
  ``data_dir``), plus seasons.csv, sources.csv, dictionary.csv and config/. Gates read
  the candidate only from here and write their check files to ``stage_dir/checks/``.
  status.csv, run_log.csv and manifest.csv are written AFTER the gates, so the manifest
  part of G-INDEX runs in ``check`` and, during a run, through ``manifest_problems`` on the
  stage right after the manifest is written (run.py).
* ``data_dir`` is what is published now (the previous run). Read-only. G-SHRINK and
  G-RESTATE compare against it; ``previous(relative)`` gives the published path or None.
* ``refreshed`` lists the seasons rebuilt from upstream this run. Every other season in
  ``seasons`` is byte-identical to ``data_dir``.
* ``season_status`` is this run's status per season (from games.csv);
  ``previous_status`` is what the last published seasons.csv said.
* ``known_metrics`` is the set of metric names that exist.
* ``games`` (optional) are the schedule rows of games.csv; ``team_files`` (optional) maps a
  refreshed season to its downloaded stats_team_week file and ``pbp_scans`` (optional) to the
  defensive scores found in its play-by-play (``derive.PbpScan``). G-DST uses all three; without
  them (``check``) it runs its structural part only.

Every gate is wrapped: a gate that cannot run (missing fixture, unreadable file) is a
FAIL of that gate, never a silent pass. Every ``detail`` is one line a person can act on.
"""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .publish import csv_bytes, format_number, lf_bytes, read_csv, season_file, sha256_file

# ---- check-file headers (CONTRACTS.md 5.5) --------------------------------------------------
GATES_HEADER = ["gate_id", "gate", "severity", "result", "detail", "checked_utc"]
RECON_HEADER = ["league", "reconcile_to", "season", "rows_compared", "rows_matched", "max_abs_diff", "match_pct"]
ROW_COUNTS_HEADER = ["season", "season_type", "baseline_rows", "actual_rows", "difference", "status"]
GOLDEN_HEADER = ["season", "week", "season_type", "player_id", "player_display_name", "league", "expected",
                 "actual", "difference", "status"]
ESPN_HEADER = ["season", "week", "season_type", "player_id", "player_display_name", "league", "espn_points",
               "our_points", "difference", "tolerance", "status", "note"]
RESTATE_HEADER = ["detected_utc", "season", "week", "season_type", "player_id", "column", "old_value", "new_value"]

FIXTURE_CONTRACTS = "fixture_contracts.csv"
FIXTURE_CONTRACTS_HEADER = ["league", "rules_sha256", "round_decimals"]
ESPN_FIXTURE_COLUMNS = ["season", "week", "season_type", "player_id", "player_display_name", "league",
                        "espn_points", "tolerance", "row_expected", "note"]
# ESPN game-log stat columns of a D/ST (06-qa/fixtures/espn_dst_stats.csv) and the player_week
# column(s) each one is compared with, exactly. They test the derived D/ST inputs themselves, so
# they apply whatever the league rules are (unlike the points in espn_actuals.csv).
ESPN_DST_STATS = "espn_dst_stats.csv"
ESPN_DST_STAT_MAP = [
    ("TD", "espn_td", ["dst_int_tds", "dst_fumble_tds", "dst_st_tds"]),
    ("INT", "espn_int", ["dst_interceptions"]),
    ("FR", "espn_fr", ["dst_fumble_recoveries"]),
    ("SCK", "espn_sck", ["dst_sacks"]),
    ("SFTY", "espn_sfty", ["dst_safeties"]),
    ("BLK", "espn_blk", ["dst_blocked_kicks"]),
    ("PA", "espn_pa", ["dst_points_allowed_excl_def"]),
]
ESPN_DST_FIXTURE_COLUMNS = (["season", "week", "season_type", "player_id", "player_display_name"]
                            + [c for _, c, _ in ESPN_DST_STAT_MAP] + ["note"])
ESPN_DST_HEADER = ["season", "week", "season_type", "player_id", "player_display_name", "stat", "espn_value",
                   "our_value", "our_columns", "status", "note"]
LONG_TD_BASELINE = [  # (baseline column, long_td column, count games instead of touchdowns)
    ("pass_td_40plus", "pass_td_40", False), ("pass_td_50plus", "pass_td_50", False),
    ("rush_td_40plus", "rush_td_40", False), ("rush_td_50plus", "rush_td_50", False),
    ("receiving_td_40plus", "rec_td_40", False), ("receiving_td_50plus", "rec_td_50", False),
    ("passer_games_40plus", "pass_td_40", True), ("passer_games_50plus", "pass_td_50", True),
    ("rusher_games_40plus", "rush_td_40", True), ("rusher_games_50plus", "rush_td_50", True),
    ("receiver_games_40plus", "rec_td_40", True), ("receiver_games_50plus", "rec_td_50", True),
]

# A league that weights both a total and its parts counts the same event twice (G-OVERLAP).
FG_RANGES = ["0_19", "20_29", "30_39", "40_49", "50_59", "60_"]
OVERLAPS = [
    ("fumbles_lost_total", ["sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost"]),
    ("fg_missed", [f"fg_missed_{r}" for r in FG_RANGES]),
    ("fg_made", [f"fg_made_{r}" for r in FG_RANGES]),
    # three versions of one figure: a league should band only one of them
    ("dst_points_allowed", ["dst_points_allowed_excl_def", "dst_points_allowed_excl_def_st"]),
    ("dst_points_allowed_excl_def", ["dst_points_allowed_excl_def_st"]),
    ("dst_yards_allowed", ["dst_yards_allowed_gross"]),
]

VALID_SEASON_TYPES = ("REG", "POST")
RECON_MIN_PCT = 99.9
SHRINK_MAX_PCT = 1.0
RESTATE_CAP = 5000
FLOAT_SLACK = 1e-9           # absorbs binary noise when comparing a difference with the tolerance
SCHEDULE_TEAM_CODES = {"OAK": "LV", "SD": "LAC", "STL": "LA"}    # same mapping as derive.py
ROW_MARK = "(row)"           # restatements.csv column for a row key that appeared or disappeared


class GateInputError(Exception):
    """An input a gate needs is missing or unreadable (the gate then FAILs)."""


@dataclass
class GateResult:
    gate_id: str          # e.g. 'G-GRAIN'
    gate: str             # short readable name
    severity: str         # 'blocking' or 'advisory'
    result: str           # 'PASS', 'WARN' or 'FAIL'
    detail: str           # one line a person can act on


@dataclass
class GateContext:
    config: Config
    stage_dir: Path
    data_dir: Path
    fixtures_dir: Path
    seasons: list[int]
    refreshed: list[int]
    season_status: dict[int, str]
    previous_status: dict[int, str]
    known_metrics: set[str]
    checked_utc: str
    notes: list[str] = field(default_factory=list)      # gates may add run-log notes here
    games: list[dict] | None = None                      # games.csv rows (run only)
    team_files: dict[int, Path] = field(default_factory=dict)   # refreshed season -> stats_team file
    pbp_scans: dict = field(default_factory=dict)        # refreshed season -> derive.PbpScan (G-DST)
    verify_manifest: bool = False                        # G-INDEX also hashes manifest.csv (check)
    previous_season_types: str = ""                      # status.csv season_types of the last publish
    latest_season: int | None = None                     # newest published nflverse season (run only)
    unpublished_seasons: list[int] = field(default_factory=list)  # EndSeason years after it (G-WINDOW)
    _cache: dict = field(default_factory=dict, repr=False)

    def staged(self, relative: str) -> Path:
        return Path(self.stage_dir) / relative

    def previous(self, relative: str) -> Path | None:
        path = Path(self.data_dir) / relative
        return path if path.is_file() else None

    @staticmethod
    def season_file(kind: str, season: int) -> str:
        return season_file(kind, season)


# ---- small helpers ---------------------------------------------------------------------------

def _num(text: str | None) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _fmt(value) -> str:
    return "" if value is None else format_number(float(value))


def _examples(items: list, n: int = 3) -> str:
    more = f" (+{len(items) - n} more)" if len(items) > n else ""
    return ", ".join(str(i) for i in items[:n]) + more


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def _read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    if not Path(path).is_file():
        raise GateInputError(f"{Path(path).name} is missing")
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header is None:
                raise GateInputError(f"{Path(path).name} is empty")
            return header, list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise GateInputError(f"{Path(path).name} cannot be read ({exc})") from exc


def _read_fixture(context: GateContext, name: str, required: list[str]) -> list[dict[str, str]]:
    path = Path(context.fixtures_dir) / name
    header, rows = _read_rows(path)
    header = [h.strip() for h in header]
    missing = [c for c in required if c not in header]
    if missing:
        raise GateInputError(f"fixture {name} lacks column(s) {', '.join(missing)}")
    return [dict(zip(header, (v.strip() for v in r))) for r in rows if any(v.strip() for v in r)]


Key = tuple[str, str, str, str]   # season, week, season_type, player_id as published text


# ---- one pass over each season's files (cached per context) ----------------------------------

@dataclass
class PlayerWeekScan:
    keys: list[Key]
    counts: dict[str, list[int]]           # season_type -> [player rows, D/ST rows]
    codes: set[str]                         # positions and position groups (upper case)
    dst: dict[Key, tuple[str, str, str, str | None]]   # D/ST key -> (team, opponent_team,
    #                                         dst_points_allowed text, dst_points_allowed_excl_def text or
    #                                         None when the column is not published)
    order_error: str
    bad_types: set[str]


def pw_scan(context: GateContext, season: int) -> PlayerWeekScan:
    cache_key = ("pw", season)
    if cache_key in context._cache:
        return context._cache[cache_key]
    relative = season_file("player_week", season)
    header, rows = _read_rows(context.staged(relative))
    try:
        ix = {c: header.index(c) for c in ("season", "week", "season_type", "player_id", "position",
                                           "position_group", "team", "opponent_team")}
    except ValueError as exc:
        raise GateInputError(f"{relative}: {exc}") from exc
    pa = header.index("dst_points_allowed") if "dst_points_allowed" in header else None
    pa_excl = header.index("dst_points_allowed_excl_def") if "dst_points_allowed_excl_def" in header else None
    keys, counts, codes, dst, bad_types = [], defaultdict(lambda: [0, 0]), set(), {}, set()
    order_error, last = "", None
    for line_no, r in enumerate(rows, start=2):
        key = (r[ix["season"]], r[ix["week"]], r[ix["season_type"]], r[ix["player_id"]])
        keys.append(key)
        if key[2] not in VALID_SEASON_TYPES:
            bad_types.add(key[2])
        is_dst = key[3].startswith("DST_") and r[ix["position"]] == "DST"
        counts[key[2]][1 if is_dst else 0] += 1
        codes.add(r[ix["position"]].upper())
        codes.add(r[ix["position_group"]].upper())
        if is_dst:
            dst[key] = (r[ix["team"]], r[ix["opponent_team"]], r[pa] if pa is not None else "",
                        r[pa_excl] if pa_excl is not None else None)
        try:
            sort_key = (int(key[0]), int(key[1]), key[2], key[3])
        except ValueError:
            sort_key = None
            order_error = order_error or f"{relative} line {line_no} has a non-numeric season or week"
        if sort_key is not None and last is not None and sort_key < last and not order_error:
            order_error = f"{relative} line {line_no} ({'/'.join(key)}) is out of order"
        last = sort_key or last
    scan = PlayerWeekScan(keys, dict(counts), codes, dst, order_error, bad_types)
    context._cache[cache_key] = scan
    return scan


@dataclass
class ScoredScan:
    header: list[str]
    keys: list[Key]
    recon: dict[str, list]                  # league -> [compared, matched, max_diff]
    wanted: dict[Key, dict[str, str]]       # rows the golden / ESPN fixtures ask for


def wanted_keys(context: GateContext) -> set[Key]:
    """Keys the golden and ESPN fixtures look up (unreadable fixtures are reported by their gate)."""
    if "wanted" not in context._cache:
        keys = set()
        for name in ("golden_sample.csv", "espn_actuals.csv"):
            try:
                for r in _read_fixture(context, name, ["season", "week", "season_type", "player_id"]):
                    keys.add((r["season"], r["week"], r["season_type"], r["player_id"]))
            except GateInputError:
                pass
        context._cache["wanted"] = keys
    return context._cache["wanted"]


def scored_scan(context: GateContext, season: int) -> ScoredScan:
    cache_key = ("scored", season)
    if cache_key in context._cache:
        return context._cache[cache_key]
    relative = season_file("scored", season)
    header, rows = _read_rows(context.staged(relative))
    try:
        k = [header.index(c) for c in ("season", "week", "season_type", "player_id")]
    except ValueError as exc:
        raise GateInputError(f"{relative}: {exc}") from exc
    leagues = [(lg.name, header.index(lg.reconcile_to) if lg.reconcile_to in header else None,
                header.index("FF_" + lg.name) if "FF_" + lg.name in header else None)
               for lg in context.config.control_leagues]
    recon = {name: [0, 0, 0.0] for name, _, _ in leagues}
    tolerance = recon_tolerance(context.config) + FLOAT_SLACK
    want = wanted_keys(context)
    keys, wanted = [], {}
    for r in rows:
        key = (r[k[0]], r[k[1]], r[k[2]], r[k[3]])
        keys.append(key)
        if key in want:
            wanted[key] = dict(zip(header, r))
        for name, ref_i, ours_i in leagues:
            if ref_i is None or ours_i is None:
                continue
            reference, ours = r[ref_i], r[ours_i]
            if reference == "" or ours == "":
                continue                            # D/ST rows have no nflverse reference
            diff = abs(float(ours) - float(reference))
            entry = recon[name]
            entry[0] += 1
            entry[1] += diff <= tolerance
            entry[2] = max(entry[2], diff)
    scan = ScoredScan(header, keys, recon, wanted)
    context._cache[cache_key] = scan
    return scan


def scored_value(context: GateContext, key: Key, league: str) -> tuple[bool, str]:
    """(row exists, FF_<league> text) for one published key."""
    try:
        season = int(key[0])
    except ValueError:
        return False, ""
    if season not in context.seasons:
        return False, ""
    row = scored_scan(context, season).wanted.get(key)
    if row is None:
        return False, ""
    return True, row.get("FF_" + league, "")


def published_max_week(context: GateContext) -> dict[tuple[int, str], int]:
    """(season, season_type) -> highest week in the staged player_week files."""
    if "maxweek" not in context._cache:
        out = {}
        for season in context.seasons:
            for key in pw_scan(context, season).keys:
                try:
                    slot = (int(key[0]), key[2])
                    out[slot] = max(out.get(slot, 0), int(key[1]))
                except ValueError:
                    continue
        context._cache["maxweek"] = out
    return context._cache["maxweek"]


# ---- G-CONFIG --------------------------------------------------------------------------------

def config_problems(context: GateContext) -> list[str]:
    """Every G-CONFIG problem: structural ones from loading plus metrics that do not exist."""
    config = context.config
    problems = list(config.problems)
    order = [lg.name for lg in config.leagues if lg.name in config.weight_league_columns]
    found = [c for c in config.weight_league_columns if c in order]
    if order != found:
        problems.append("scoring_weights.csv: league columns are not in the same order as leagues.csv "
                        f"({', '.join(found)} vs {', '.join(order)})")
    if context.known_metrics:
        for w in config.weights:
            if w.metric and w.metric not in context.known_metrics:
                problems.append(f"scoring_weights.csv: metric '{w.metric}' is neither an nflverse column nor derived")
        for b in config.bands:
            if b.metric and b.metric not in context.known_metrics:
                problems.append(f"bonus_rules.csv: metric '{b.metric}' is neither an nflverse column nor derived")
        extra = config.extra_columns_setting
        if extra and extra.upper() != "ALL":
            for name in (c.strip() for c in extra.split(",")):
                if name and name not in context.known_metrics:
                    problems.append(f"pipeline_config.csv: PublishExtraColumns '{name}' is not an nflverse column")
    return problems


def gate_config(context: GateContext) -> GateResult:
    problems = config_problems(context)
    if problems:
        return GateResult("G-CONFIG", "Config is valid", "blocking", "FAIL",
                          "Fix 02-config: " + "; ".join(problems[:3])
                          + (f" (+{len(problems) - 3} more)" if len(problems) > 3 else ""))
    return GateResult("G-CONFIG", "Config is valid", "blocking", "PASS",
                      f"{len(context.config.active_leagues)} active leagues, {len(context.config.weights)} metrics, "
                      f"{len(context.config.bands)} bands")


# ---- G-GRAIN ---------------------------------------------------------------------------------

def gate_grain(context: GateContext) -> GateResult:
    duplicates, total = [], 0
    for season in context.seasons:
        seen = set()
        for key in pw_scan(context, season).keys:
            total += 1
            if key in seen:
                duplicates.append("/".join(key))
            seen.add(key)
    if duplicates:
        return GateResult("G-GRAIN", "One row per player-game", "blocking", "FAIL",
                          f"{len(duplicates)} duplicate season/week/type/player keys, e.g. {_examples(duplicates)}; "
                          "the upstream file or the build repeated rows; do not publish until it is fixed upstream")
    return GateResult("G-GRAIN", "One row per player-game", "blocking", "PASS",
                      f"{total} rows in {len(context.seasons)} seasons, all keys unique")


# ---- G-RECON ---------------------------------------------------------------------------------

def reconciliation_rows(context: GateContext) -> list[list]:
    """Control league vs nflverse reference, per season and for ALL (from the staged scored files)."""
    out = []
    for lg in context.config.control_leagues:
        per_season = {s: scored_scan(context, s).recon[lg.name] for s in context.seasons}
        for season in context.seasons:
            out.append(_recon_line(lg.name, lg.reconcile_to, str(season), *per_season[season]))
        compared = sum(v[0] for v in per_season.values())
        matched = sum(v[1] for v in per_season.values())
        max_diff = max((v[2] for v in per_season.values()), default=0.0)
        out.append(_recon_line(lg.name, lg.reconcile_to, "ALL", compared, matched, max_diff))
    return out


def _recon_line(league, reference, season, compared, matched, max_diff) -> list:
    pct = round(100.0 * matched / compared, 4) if compared else None
    return [league, reference, season, compared, matched, round(max_diff, 6), pct]


def recon_tolerance(config: Config) -> float:
    """ReconcileTolerance, widened to half a unit of RoundDecimals when fewer than 2 decimals are kept.

    nflverse's fantasy points have 2 decimals; a control league rounded to 0 or 1 decimals can
    differ from them by up to half its last unit without any scoring error (QA finding C-01).
    """
    tolerance = config.tolerance
    if config.round_decimals < 2:
        tolerance = max(tolerance, 0.5 * 10 ** -config.round_decimals)
    return tolerance


def recon_changed_leagues(context: GateContext) -> dict[str, str]:
    """Control leagues whose weights or bands differ from the rules recorded in fixture_contracts.csv.

    Those no longer use nflverse's scoring, so comparing them with fantasy_points proves nothing and
    must not hold a publish. A league with no recorded rules (or no fixture file) is compared as before.
    """
    out = {}
    try:
        recorded = fixture_contracts(context)
    except GateInputError:
        return out
    for lg in context.config.control_leagues:
        if lg.name in recorded and context.config.league_contract_hash(lg.name) != recorded[lg.name][0]:
            out[lg.name] = lg.reconcile_to
    return out


def gate_recon(context: GateContext, recon: list[list]) -> GateResult:
    name = "Control leagues match nflverse"
    totals = [r for r in recon if r[2] == "ALL"]
    if not totals:
        return GateResult("G-RECON", name, "blocking", "WARN",
                          "no league has Reconcile_To set, so nothing checks the scoring against nflverse; "
                          "set Reconcile_To on a Standard or PPR league in leagues.csv")
    changed = recon_changed_leagues(context)
    compared = [r for r in totals if r[0] not in changed]
    failing = [r for r in compared if r[3] == 0 or r[6] is None or r[6] < RECON_MIN_PCT]
    detail = "; ".join(f"{r[0]} vs {r[1]}: {r[4]} of {r[3]} rows ({format_number(r[6])}%), max diff "
                       f"{format_number(r[5])}" for r in compared)
    if context.config.round_decimals < 2 and compared:
        detail += (f" (tolerance {format_number(recon_tolerance(context.config))} because RoundDecimals is "
                   f"{context.config.round_decimals})")
    if failing:
        detail += f"; below {format_number(RECON_MIN_PCT)}%: check that league's weights in scoring_weights.csv"
    if changed:
        note = (f"not applicable: rules for {', '.join(changed)} changed since the expected values were made, so "
                f"{'it' if len(changed) == 1 else 'they'} no longer follow nflverse's scoring and cannot be "
                f"compared with {', '.join(dict.fromkeys(changed.values()))}; {CHANGED_TAIL} (to silence this, "
                "clear Reconcile_To for that league in leagues.csv)")
        detail = f"{detail}; {note}" if detail else note
    result = "FAIL" if failing else ("WARN" if changed else "PASS")
    return GateResult("G-RECON", name, "blocking", result, detail)


# ---- fixture applicability (G-GOLDEN, G-ESPN; QA finding C-01) -----------------------------

CHANGED_TAIL = ("this is expected after you change 02-config and nothing is wrong: the change was noticed "
                "and these expected values no longer apply")


def fixture_contract_rows(config: Config) -> list[list]:
    """fixture_contracts.csv rows for a config: one per Active league (rules hash, RoundDecimals).

    Written next to the expected values whenever they are (re)made, so the gates can tell later
    whether a league's rules are still the ones the expected values were computed with.
    """
    return [[lg.name, config.league_contract_hash(lg.name), config.round_decimals] for lg in config.active_leagues]


def fixture_contracts(context: GateContext) -> dict[str, tuple[str, str]]:
    """league -> (rules hash, RoundDecimals text) recorded with the expected values."""
    if "fixture_contracts" not in context._cache:
        if not (Path(context.fixtures_dir) / FIXTURE_CONTRACTS).is_file():
            raise GateInputError(f"fixture {FIXTURE_CONTRACTS} is missing (it records the rules the expected values "
                                 "were made with; restore it from git, or recreate it with "
                                 "tools/write_fixture_contracts.py right after remaking the expected values)")
        rows = _read_fixture(context, FIXTURE_CONTRACTS, FIXTURE_CONTRACTS_HEADER)
        context._cache["fixture_contracts"] = {r["league"]: (r["rules_sha256"], r["round_decimals"]) for r in rows}
    return context._cache["fixture_contracts"]


@dataclass
class Applicability:
    """How the expected values of one fixture league apply to the current config."""
    fixture_league: str
    league: str | None       # current league to compare with, or None (not applicable)
    reason: str = ""          # why not applicable, or a note (renamed)
    kind: str = ""            # 'changed', 'decimals', 'missing', 'inactive', 'unrecorded', 'renamed', ''


def applicability(context: GateContext, fixture_league: str) -> Applicability:
    """Decide whether one fixture league's expected values can be checked (CONTRACTS.md 6, G-GOLDEN).

    * same name, same rules hash and same RoundDecimals: checked;
    * same name but changed rules or RoundDecimals: not applicable (WARN, never holds);
    * name gone, but exactly one Active league that has no expected values of its own carries
      exactly the recorded rules: the league was renamed, checked under its new name;
    * inactive, removed, or no rules recorded: not applicable.
    """
    cache = context._cache.setdefault("applicability", {})
    if fixture_league in cache:
        return cache[fixture_league]
    config = context.config
    recorded = fixture_contracts(context).get(fixture_league)
    decimals_now = str(config.round_decimals)
    active = {lg.name for lg in config.active_leagues}
    if recorded is None:
        result = Applicability(fixture_league, None,
                               f"no rules recorded for {fixture_league} in 06-qa/fixtures/{FIXTURE_CONTRACTS}",
                               "unrecorded")
    elif fixture_league in active:
        rules_same = config.league_contract_hash(fixture_league) == recorded[0]
        decimals_same = decimals_now == recorded[1]
        if rules_same and decimals_same:
            result = Applicability(fixture_league, fixture_league)
        elif not decimals_same:
            result = Applicability(fixture_league, None, f"RoundDecimals {recorded[1]} -> {decimals_now}", "decimals")
        else:
            result = Applicability(fixture_league, None, "weights or bonus bands edited", "changed")
    else:
        fixture_names = set(fixture_contracts(context))
        twins = [lg.name for lg in config.active_leagues if lg.name not in fixture_names
                 and config.league_contract_hash(lg.name) == recorded[0] and decimals_now == recorded[1]]
        if len(twins) == 1:
            result = Applicability(fixture_league, twins[0], f"{fixture_league} renamed to {twins[0]}", "renamed")
        elif any(lg.name == fixture_league for lg in config.leagues):
            result = Applicability(fixture_league, None, f"{fixture_league} is set to Active = No", "inactive")
        else:
            result = Applicability(fixture_league, None,
                                   f"{fixture_league} is no longer in leagues.csv (renamed with other rules, "
                                   "or removed)", "missing")
    cache[fixture_league] = result
    return result


def not_applicable_text(skipped: list[Applicability], counts: dict[str, int]) -> str:
    """The WARN wording for leagues whose expected values no longer apply."""
    changed = [a for a in skipped if a.kind in ("changed", "decimals")]
    other = [a for a in skipped if a.kind not in ("changed", "decimals")]
    parts = []
    if changed:
        names = ", ".join(a.fixture_league for a in changed)
        why = "; ".join(dict.fromkeys(a.reason for a in changed))
        parts.append(f"not applicable: rules for {names} changed since the expected values were made ({why}); "
                     f"{sum(counts.get(a.fixture_league, 0) for a in changed)} value(s) skipped; {CHANGED_TAIL}")
    for a in other:
        parts.append(f"not applicable: {a.reason}; {counts.get(a.fixture_league, 0)} value(s) skipped")
    return "; ".join(parts)


def renamed_text(applied: list[Applicability]) -> str:
    renamed = [a.reason for a in applied if a.kind == "renamed"]
    return f"; {', '.join(renamed)} (same rules, checked under the new name)" if renamed else ""


# ---- G-GOLDEN --------------------------------------------------------------------------------

def golden_rows(context: GateContext) -> list[list]:
    fixture = _read_fixture(context, "golden_sample.csv",
                            ["season", "week", "season_type", "player_id", "player_display_name"])
    if not fixture:
        raise GateInputError("fixture golden_sample.csv has no rows")
    leagues = [c[3:] for c in fixture[0] if c.startswith("FF_")]
    if not leagues:
        raise GateInputError("fixture golden_sample.csv has no FF_<League> columns")
    applies = {league: applicability(context, league) for league in leagues}
    skipped_counts: dict[str, int] = defaultdict(int)
    out = []
    for r in fixture:
        key = (r["season"], r["week"], r["season_type"], r["player_id"])
        for league in leagues:
            expected = r.get("FF_" + league, "")
            if expected == "":
                continue
            base = [r["season"], r["week"], r["season_type"], r["player_id"], r["player_display_name"], league,
                    expected]
            if int(r["season"]) not in context.seasons:
                out.append(base + ["", "", "NOT_APPLICABLE"])
                continue
            target = applies[league].league
            if target is None:
                skipped_counts[league] += 1
                out.append(base + ["", "", "NOT_APPLICABLE"])
                continue
            found, actual = scored_value(context, key, target)
            if not found or actual == "":
                out.append(base + ["", "", "MISSING"])
                continue
            diff = float(actual) - float(expected)
            out.append(base + [actual, _fmt(round(diff, 6)), "MATCH" if abs(diff) <= FLOAT_SLACK else "MISMATCH"])
    context._cache["golden_applies"] = (list(applies.values()), dict(skipped_counts))
    return out


def _fixture_summary(context: GateContext, cache_key: str) -> tuple[list[Applicability], list[Applicability], str]:
    """(checked, skipped, tail about new leagues) for the gate wording."""
    applies, counts = context._cache.get(cache_key, ([], {}))
    skipped = [a for a in applies if a.league is None and counts.get(a.fixture_league)]
    checked = [a for a in applies if a.league is not None]
    covered = {a.league for a in checked} | {a.fixture_league for a in applies}
    new = [lg.name for lg in context.config.active_leagues if lg.name not in covered]
    tail = (f"; no expected values exist for {', '.join(new)} (new league), so it is not checked here"
            if new and cache_key == "golden_applies" else "")
    return checked, skipped, tail


def gate_golden(context: GateContext, rows: list[list]) -> GateResult:
    name = "Golden sample reproduced"
    bad = [r for r in rows if r[9] in ("MISMATCH", "MISSING")]
    compared = [r for r in rows if r[9] in ("MATCH", "MISMATCH", "MISSING")]
    na = len(rows) - len(compared)
    checked, skipped, tail = _fixture_summary(context, "golden_applies")
    counts = context._cache.get("golden_applies", ([], {}))[1]
    skipped_text = not_applicable_text(skipped, counts)
    order = [lg.name for lg in context.config.leagues]
    leagues_checked = sorted({r[5] for r in compared}, key=lambda n: (order.index(n) if n in order else len(order), n))
    if bad:
        ex = [f"{r[4]} {r[0]} wk{r[1]} {r[5]} expected {r[6]} got {r[7] or 'nothing'}" for r in bad]
        return GateResult("G-GOLDEN", name, "blocking", "FAIL",
                          f"{len(bad)} of {len(compared)} golden values differ: {_examples(ex, 2)}; the rules of "
                          f"{', '.join(sorted({r[5] for r in bad}))} are unchanged since the expected values were made, "
                          "so the scoring or the data changed; see checks/golden.csv"
                          + (f". Also {skipped_text}" if skipped_text else ""))
    if skipped:
        done = (f"the other league(s) {', '.join(leagues_checked)} were checked: all {len(compared)} golden values "
                "reproduced exactly" if compared else "no league is left to check")
        return GateResult("G-GOLDEN", name, "blocking", "WARN",
                          f"{skipped_text}; {done}{renamed_text(checked)}{tail}")
    if not compared:
        return GateResult("G-GOLDEN", name, "blocking", "WARN",
                          f"not applicable: none of the {len(rows)} golden values is in the window or an active league; "
                          "add golden rows for a season in the window to 06-qa/fixtures/golden_sample.csv")
    return GateResult("G-GOLDEN", name, "blocking", "PASS",
                      f"all {len(compared)} golden values reproduced exactly"
                      + (f" ({na} not applicable)" if na else "") + renamed_text(checked) + tail)


# ---- G-ESPN ----------------------------------------------------------------------------------

def espn_rows(context: GateContext) -> list[list]:
    fixture = _read_fixture(context, "espn_actuals.csv", ESPN_FIXTURE_COLUMNS)
    if not fixture:
        raise GateInputError("fixture espn_actuals.csv has no rows")
    max_week = published_max_week(context)
    applies: dict[str, Applicability] = {}
    skipped_counts: dict[str, int] = defaultdict(int)
    out = []
    for r in fixture:
        key = (r["season"], r["week"], r["season_type"], r["player_id"])
        espn, tol = _num(r["espn_points"]), _num(r["tolerance"])
        if espn is None or tol is None:
            raise GateInputError(f"espn_actuals.csv: {r['player_display_name']} has a non-numeric "
                                 "espn_points or tolerance")
        base = [r["season"], r["week"], r["season_type"], r["player_id"], r["player_display_name"], r["league"],
                r["espn_points"]]
        season, week = int(r["season"]), int(r["week"])
        if r["league"] not in applies:
            applies[r["league"]] = applicability(context, r["league"])
        target = applies[r["league"]].league
        reason = ""
        if season not in context.seasons:
            reason = f"season {season} is outside the window"
        elif week > max_week.get((season, r["season_type"]), 0):
            reason = f"{season} {r['season_type']} week {week} is not published yet"
        elif target is None:
            a = applies[r["league"]]
            skipped_counts[r["league"]] += 1
            reason = (f"rules for {r['league']} changed since the expected values were made ({a.reason})"
                      if a.kind in ("changed", "decimals") else a.reason)
        if reason:
            out.append(base + ["", "", r["tolerance"], "NOT_APPLICABLE", f"{reason}; {r['note']}"])
            continue
        found, ours_text = scored_value(context, key, target)
        note = r["note"]
        if not found:
            if r["row_expected"].strip().lower() == "no":
                ours_text, note = "0", f"no row, counts as 0; {note}"
            else:
                out.append(base + ["", "", r["tolerance"], "MISSING", f"no published row for this player-game; {note}"])
                continue
        ours = _num(ours_text)
        if ours is None:
            out.append(base + ["", "", r["tolerance"], "MISSING", f"FF_{target} is blank; {note}"])
            continue
        diff = round(ours - espn, 6)
        status = "MATCH" if abs(diff) <= FLOAT_SLACK else (
            "WITHIN_TOLERANCE" if abs(diff) <= tol + FLOAT_SLACK else "MISMATCH")
        out.append(base + [_fmt(ours), _fmt(diff), r["tolerance"], status, note])
    context._cache["espn_applies"] = (list(applies.values()), dict(skipped_counts))
    context._cache["espn_dst_stats"] = espn_dst_stat_rows(context)
    return out


def _player_week_values(context: GateContext, season: int, keys: set[Key]) -> dict[Key, dict[str, str]]:
    """Published player_week values (column -> text) of the given keys of one season."""
    header, rows = _read_rows(context.staged(season_file("player_week", season)))
    k = [header.index(c) for c in ("season", "week", "season_type", "player_id")]
    out = {}
    for r in rows:
        key = (r[k[0]], r[k[1]], r[k[2]], r[k[3]])
        if key in keys:
            out[key] = dict(zip(header, r))
    return out


def espn_dst_stat_rows(context: GateContext) -> list[list]:
    """checks/espn_dst_stats.csv rows: each ESPN game-log stat of a D/ST against our derived columns.

    Exact comparison, no tolerance, independent of the league rules: these are the inputs the
    points-allowed bands and the per-unit D/ST weights are applied to.
    """
    fixture = _read_fixture(context, ESPN_DST_STATS, ESPN_DST_FIXTURE_COLUMNS)
    max_week = published_max_week(context)
    by_season: dict[int, set[Key]] = defaultdict(set)
    for r in fixture:
        if int(r["season"]) in context.seasons:
            by_season[int(r["season"])].add((r["season"], r["week"], r["season_type"], r["player_id"]))
    values: dict[Key, dict[str, str]] = {}
    for season, keys in by_season.items():
        values.update(_player_week_values(context, season, keys))
    out = []
    for r in fixture:
        key = (r["season"], r["week"], r["season_type"], r["player_id"])
        season, week = int(r["season"]), int(r["week"])
        reason = ""
        if season not in context.seasons:
            reason = f"season {season} is outside the window"
        elif week > max_week.get((season, r["season_type"]), 0):
            reason = f"{season} {r['season_type']} week {week} is not published yet"
        row = values.get(key)
        for stat, fixture_column, columns in ESPN_DST_STAT_MAP:
            espn_text = r[fixture_column]
            base = [r["season"], r["week"], r["season_type"], r["player_id"], r["player_display_name"], stat,
                    espn_text]
            if reason:
                out.append(base + ["", "+".join(columns), "NOT_APPLICABLE", f"{reason}; {r['note']}"])
                continue
            espn = _num(espn_text)
            if espn is None:
                raise GateInputError(f"{ESPN_DST_STATS}: {r['player_display_name']} {r['season']} week {r['week']} "
                                     f"has a non-numeric {fixture_column}")
            if row is None:
                out.append(base + ["", "+".join(columns), "MISSING", f"no published D/ST row; {r['note']}"])
                continue
            missing = [c for c in columns if c not in row]
            if missing:
                out.append(base + ["", "+".join(columns), "NOT_APPLICABLE",
                                   f"column {', '.join(missing)} is not published (not listed in "
                                   f"scoring_weights.csv); {r['note']}"])
                continue
            parts = [_num(row[c]) for c in columns]
            if any(v is None for v in parts):
                out.append(base + ["", "+".join(columns), "MISSING", f"our value is blank; {r['note']}"])
                continue
            ours = sum(parts)
            status = "MATCH" if abs(ours - espn) <= FLOAT_SLACK else "MISMATCH"
            out.append(base + [_fmt(ours), "+".join(columns), status, r["note"]])
    return out


def espn_stats_text(context: GateContext) -> tuple[str, list[list]]:
    """(summary for the G-ESPN detail, rows that failed) of the ESPN D/ST stat check."""
    rows = context._cache.get("espn_dst_stats", [])
    bad = [r for r in rows if r[9] in ("MISMATCH", "MISSING")]
    compared = [r for r in rows if r[9] in ("MATCH", "MISMATCH", "MISSING")]
    stats = "/".join(dict.fromkeys(r[5] for r in compared)) or "none"
    if bad:
        ex = [f"{r[4]} {r[0]} wk{r[1]} {r[5]} ESPN {r[6]} ours {r[7] or 'nothing'}" for r in bad]
        return (f"ESPN D/ST stat columns: {len(bad)} of {len(compared)} differ ({_examples(ex, 2)}); a derived "
                "D/ST input no longer matches ESPN's game log; see checks/espn_dst_stats.csv"), bad
    if not compared:
        return "ESPN D/ST stat columns: none in the window yet", bad
    return f"ESPN D/ST stat columns: all {len(compared)} equal ({stats})", bad


def gate_espn(context: GateContext, rows: list[list]) -> GateResult:
    result = _gate_espn_points(context, rows)
    stats_text, stats_bad = espn_stats_text(context)
    if stats_bad and result.result != "FAIL":
        result.result = "FAIL"
        result.detail = f"{stats_text}. Points: {result.detail}"
    else:
        result.detail = f"{result.detail}; {stats_text}"
    return result


def _gate_espn_points(context: GateContext, rows: list[list]) -> GateResult:
    name = "ESPN actuals reproduced"
    bad = [r for r in rows if r[10] in ("MISMATCH", "MISSING")]
    exact = sum(r[10] == "MATCH" for r in rows)
    within = sum(r[10] == "WITHIN_TOLERANCE" for r in rows)
    na = [r for r in rows if r[10] == "NOT_APPLICABLE"]
    checked, skipped, _ = _fixture_summary(context, "espn_applies")
    counts = context._cache.get("espn_applies", ([], {}))[1]
    skipped_text = not_applicable_text(skipped, counts)
    if bad:
        ex = [f"{r[4]} ESPN {r[6]} ours {r[7] or 'nothing'}" for r in bad]
        return GateResult("G-ESPN", name, "blocking", "FAIL",
                          f"{len(bad)} of {len(rows) - len(na)} ESPN values not reproduced: {_examples(ex, 2)}; "
                          "that league's rules are unchanged since the ESPN values were recorded, so the scoring "
                          "or the data changed; see checks/espn_reconciliation.csv"
                          + (f". Also {skipped_text}" if skipped_text else ""))
    if skipped:
        done = (f"; {exact + within} ESPN value(s) of other leagues reproduced" if exact or within else "")
        return GateResult("G-ESPN", name, "blocking", "WARN", f"{skipped_text}{done}{renamed_text(checked)}")
    if not exact and not within:
        why = na[0][11].split(";")[0] if na else "no rows"
        return GateResult("G-ESPN", name, "blocking", "WARN",
                          f"not applicable: the ESPN check did not run ({why}); add a recent ESPN week to "
                          "06-qa/fixtures/espn_actuals.csv")
    return GateResult("G-ESPN", name, "blocking", "PASS",
                      f"{exact + within} of {len(rows) - len(na)} ESPN values reproduced: {exact} exact, "
                      f"{within} within tolerance (D/ST: the row's tolerance, 1 or 2)" + (f", {len(na)} not applicable" if na else "")
                      + renamed_text(checked))


# ---- G-DST -----------------------------------------------------------------------------------

def _expected_team_games(context: GateContext, season: int) -> set[tuple[str, str, str]] | None:
    """(week, season_type, team) of every team-game in the season's stats_team file, or None."""
    path = context.team_files.get(season)
    if not path:
        return None
    from .ingest import iter_columns, to_number      # local: keeps gates importable on its own
    types = context.config.season_types
    out = set()
    for t in iter_columns(path, ["season", "week", "season_type", "team"]):
        season_n, week_n = to_number(t["season"]), to_number(t["week"])
        if t["team"].strip() and t["season_type"] in types and season_n is not None and week_n is not None:
            out.add((str(int(week_n)), t["season_type"], t["team"]))
    return out


def _schedule_index(context: GateContext) -> dict[tuple[int, int, str], tuple[bool, float | None]]:
    """(season, week, team in current codes) -> (finished, opponent's final score)."""
    if "schedule" not in context._cache:
        index = {}
        for g in context.games or []:
            season, week = _num(g.get("season")), _num(g.get("week"))
            if season is None or week is None:
                continue
            home = SCHEDULE_TEAM_CODES.get(g["home_team"], g["home_team"])
            away = SCHEDULE_TEAM_CODES.get(g["away_team"], g["away_team"])
            hs, as_ = _num(g.get("home_score")), _num(g.get("away_score"))
            finished = hs is not None and as_ is not None
            index[(int(season), int(week), home)] = (finished, as_)
            index[(int(season), int(week), away)] = (finished, hs)
        context._cache["schedule"] = index
    return context._cache["schedule"]


def _excl_def_problem(pa_text: str, excl_text: str | None) -> str:
    """Why a dst_points_allowed_excl_def value is impossible next to its dst_points_allowed, or ''."""
    if excl_text is None:
        return ""                                       # column not published: nothing to check
    if pa_text == "" and excl_text != "":
        return f"{excl_text} for a game without a final score"
    if pa_text != "" and excl_text != "":
        pa, excl = _num(pa_text), _num(excl_text)
        if pa is None or excl is None or excl < 0 or excl > pa:
            return f"{excl_text} next to a final score of {pa_text}"
    return ""


def _defense_disagreements(context: GateContext, season: int) -> list[str]:
    """Team-games whose play-by-play defensive scores disagree with stats_team (refreshed seasons).

    The interception-return touchdowns must equal ``def_tds``; fumble-return touchdowns cannot
    exceed ``fumble_recovery_tds`` (which also counts an offense recovering its own fumble in the
    end zone) and safeties cannot exceed ``def_safeties`` (which also counts safeties on kicks).
    """
    path, scan = context.team_files.get(season), context.pbp_scans.get(season)
    if not path or scan is None:
        return []
    from .ingest import iter_columns, to_number      # local: keeps gates importable on its own
    types = context.config.season_types
    problems = []
    for t in iter_columns(path, ["game_id", "week", "season_type", "team", "def_tds", "fumble_recovery_tds",
                                 "def_safeties"]):
        if not t["team"].strip() or t["season_type"] not in types:
            continue
        key = (t["game_id"], t["team"])
        mine = scan.defense.get(key)
        int_tds, fum_tds, safeties = (mine.int_tds, mine.fumble_tds, mine.safeties) if mine else (0, 0, 0)
        n = lambda col: int(to_number(t[col]) or 0)                       # noqa: E731
        label = f"{t['team']} {season} wk{t['week']}"
        if int_tds != n("def_tds"):
            problems.append(f"{label} interception-return TDs {int_tds} in play-by-play, {n('def_tds')} in stats_team")
        if fum_tds > n("fumble_recovery_tds"):
            problems.append(f"{label} fumble-return TDs {fum_tds} in play-by-play, at most "
                            f"{n('fumble_recovery_tds')} in stats_team")
        if safeties > n("def_safeties"):
            problems.append(f"{label} safeties {safeties} in play-by-play, {n('def_safeties')} in stats_team")
    return problems


def gate_dst(context: GateContext) -> GateResult:
    name = "Every team-game has a D/ST row"
    missing, extra, no_pa, bad_pa, wrong_pa, unpaired, checked = [], [], [], [], [], [], 0
    no_excl, bad_excl, defense = [], [], []
    schedule = _schedule_index(context) if context.games is not None else None
    refreshed_checked = 0
    for season in context.seasons:
        scan = pw_scan(context, season)
        have = {(k[1], k[2], v[0]): k for k, v in scan.dst.items()}
        checked += len(have)
        expected = _expected_team_games(context, season) if season in context.refreshed else None
        if expected is not None:
            refreshed_checked += 1
            missing += [f"{season} wk{w} {t} {team}" for w, t, team in sorted(expected - set(have))]
            extra += [f"{season} wk{w} {t} {team}" for w, t, team in sorted(set(have) - expected)]
        if season in context.refreshed:
            defense += _defense_disagreements(context, season)
        for (week, stype, team), key in have.items():
            pa_text, excl_text = scan.dst[key][2], scan.dst[key][3]
            label = f"{team} {season} wk{week}"
            problem = _excl_def_problem(pa_text, excl_text)
            if problem:
                bad_excl.append(f"{label} ({problem})")
            elif excl_text == "" and pa_text != "":
                no_excl.append(label)
            if schedule is None:
                opp = scan.dst[key][1]
                partner = have.get((week, stype, opp))
                if partner is None or (scan.dst[partner][2] == "") != (pa_text == ""):
                    unpaired.append(label)
                continue
            game = schedule.get((season, int(week), team))
            if game is None:
                extra.append(f"{label} (not in the schedule)")
                continue
            finished, opp_score = game
            if finished and pa_text == "":
                no_pa.append(label)
            elif not finished and pa_text != "":
                bad_pa.append(f"{label} ({pa_text})")
            elif finished and season in context.refreshed and _num(pa_text) != opp_score:
                wrong_pa.append(f"{label} ({pa_text} vs {format_number(opp_score)})")
    problems = []
    if missing:
        problems.append(f"{len(missing)} team-games in stats_team have no D/ST row ({_examples(missing)})")
    if extra:
        problems.append(f"{len(extra)} D/ST rows have no matching team-game ({_examples(extra)})")
    if no_pa:
        problems.append(f"{len(no_pa)} finished games have blank points allowed ({_examples(no_pa)})")
    if bad_pa:
        problems.append(f"{len(bad_pa)} unfinished games have points allowed filled in ({_examples(bad_pa)})")
    if wrong_pa:
        problems.append(f"{len(wrong_pa)} points-allowed values differ from the final score ({_examples(wrong_pa)})")
    if unpaired:
        problems.append(f"{len(unpaired)} D/ST rows lack a matching opponent row ({_examples(unpaired)})")
    if no_excl:
        problems.append(f"{len(no_excl)} finished games have blank dst_points_allowed_excl_def, so the play-by-play "
                        f"has no plays for them yet ({_examples(no_excl)})")
    if bad_excl:
        problems.append(f"{len(bad_excl)} dst_points_allowed_excl_def values are impossible ({_examples(bad_excl)})")
    if defense:
        problems.append(f"{len(defense)} team-games where play-by-play and stats_team disagree on defensive scores "
                        f"({_examples(defense)})")
    if problems:
        return GateResult("G-DST", name, "blocking", "FAIL",
                          "; ".join(problems) + "; team D/ST rows are missing or wrong and would mis-score team defenses")
    scope = (f"checked against stats_team for {refreshed_checked} rebuilt season(s) and against games.csv"
             if schedule is not None else "structural check: every D/ST row has its opponent's row")
    if context.pbp_scans:
        scope += (f"; defensive scores in play-by-play agree with stats_team for {len(context.pbp_scans)} "
                  "rebuilt season(s)")
    return GateResult("G-DST", name, "blocking", "PASS", f"{checked} D/ST rows, {scope}")


# ---- G-SHRINK --------------------------------------------------------------------------------

def _fast_type_counts(path: Path) -> dict[str, int]:
    """Rows per season_type of a published player_week file (season_type is the 3rd column;
    no earlier column can hold a comma or a quoted newline)."""
    counts: dict[str, int] = defaultdict(int)
    with open(path, "r", encoding="utf-8", newline="") as handle:
        next(handle, None)
        for line in handle:
            parts = line.split(",", 3)
            if len(parts) > 2:
                counts[parts[2]] += 1
    return counts


def gate_shrink(context: GateContext) -> GateResult:
    name = "No season shrank"
    shrunk, compared = [], 0
    for season in context.refreshed:
        previous = context.previous(season_file("player_week", season))
        if previous is None:
            continue
        before = _fast_type_counts(previous)
        now = pw_scan(context, season).counts
        for stype in context.config.season_types:
            old = before.get(stype, 0)
            if not old:
                continue
            compared += 1
            new = sum(now.get(stype, [0, 0]))
            lost = 100.0 * (old - new) / old
            if lost > SHRINK_MAX_PCT:
                shrunk.append(f"{season} {stype} {old} -> {new} rows (-{lost:.1f}%)")
    if shrunk:
        return GateResult("G-SHRINK", name, "blocking", "FAIL",
                          f"{_examples(shrunk)} lost more than {format_number(SHRINK_MAX_PCT)}% of its rows since the "
                          "last publish; nflverse may have published a partial file, so the publish is held "
                          "(re-run later)")
    if not compared:
        return GateResult("G-SHRINK", name, "blocking", "PASS", "no previously published season was rebuilt")
    return GateResult("G-SHRINK", name, "blocking", "PASS",
                      f"{compared} rebuilt season/type(s) compared with the last publish, none lost more than "
                      f"{format_number(SHRINK_MAX_PCT)}%")


# ---- G-ROWS ----------------------------------------------------------------------------------

def row_count_rows(context: GateContext) -> list[list]:
    fixture = _read_fixture(context, "row_count_baseline.csv", ["season", "season_type", "expected_stats_raw_rows"])
    baseline = {(r["season"], r["season_type"]): r["expected_stats_raw_rows"] for r in fixture}
    out = []
    for season in context.seasons:
        counts = pw_scan(context, season).counts
        for stype in sorted(counts):
            actual = counts[stype][0]
            base = baseline.get((str(season), stype), "")
            if context.season_status.get(season) != "complete":
                status = "IN_PROGRESS"
            elif base == "":
                status = "NO_BASELINE"
            else:
                status = "MATCH" if int(base) == actual else "DIFFERENT"
            diff = actual - int(base) if base != "" else ""
            out.append([season, stype, base, actual, diff, status])
    return out


def gate_rows(context: GateContext, rows: list[list]) -> GateResult:
    name = "Completed seasons match the row-count baseline"
    different = [r for r in rows if r[5] == "DIFFERENT"]
    matched = sum(r[5] == "MATCH" for r in rows)
    no_base = [f"{r[0]} {r[1]}" for r in rows if r[5] == "NO_BASELINE"]
    tail = (f"; no baseline yet for {_examples(no_base)} (add it to row_count_baseline.csv after checking)"
            if no_base else "")
    if different:
        ex = [f"{r[0]} {r[1]} {r[3]} vs {r[2]}" for r in different]
        return GateResult("G-ROWS", name, "advisory", "WARN",
                          f"{len(different)} completed season/type(s) differ from the baseline: {_examples(ex)}; "
                          "nflverse changed a finished season, look at checks/row_counts.csv" + tail)
    return GateResult("G-ROWS", name, "advisory", "PASS",
                      f"{matched} completed season/type(s) match the baseline (in-progress seasons are not compared)"
                      + tail)


# ---- G-LONGTD --------------------------------------------------------------------------------

def gate_longtd(context: GateContext) -> GateResult:
    name = "Completed-season long-TD totals match"
    fixture = _read_fixture(context, "long_td_baseline.csv", ["season"] + [b for b, _, _ in LONG_TD_BASELINE])
    if set(context.config.season_types) != {"REG", "POST"}:
        return GateResult("G-LONGTD", name, "advisory", "PASS",
                          "not compared: the baseline counts REG+POST and SeasonTypes is "
                          f"{context.config.season_types_text}")
    baseline = {r["season"]: r for r in fixture}
    different, matched, no_base = [], 0, []
    for season in context.seasons:
        if context.season_status.get(season) != "complete":
            continue
        base = baseline.get(str(season))
        if base is None:
            no_base.append(str(season))
            continue
        header, rows = _read_rows(context.staged(season_file("long_td", season)))
        ix = {c: header.index(c) for c in {c for _, c, _ in LONG_TD_BASELINE}}
        diffs = []
        for base_col, col, games in LONG_TD_BASELINE:
            values = [int(float(r[ix[col]] or 0)) for r in rows]
            actual = sum(1 for v in values if v > 0) if games else sum(values)
            if str(actual) != base[base_col]:
                diffs.append(f"{base_col} {actual} vs {base[base_col]}")
        if diffs:
            different.append(f"{season}: {', '.join(diffs[:2])}")
        else:
            matched += 1
    tail = f"; no baseline yet for {', '.join(no_base)}" if no_base else ""
    if different:
        return GateResult("G-LONGTD", name, "advisory", "WARN",
                          f"{len(different)} completed season(s) differ from long_td_baseline.csv: "
                          f"{_examples(different, 2)}; nflverse changed a finished season's play-by-play, "
                          "look at checks/restatements.csv" + tail)
    return GateResult("G-LONGTD", name, "advisory", "PASS",
                      f"{matched} completed season(s) match the long-TD baseline exactly" + tail)


# ---- G-RESTATE -------------------------------------------------------------------------------

def _keyed(header: list[str], rows: list[list[str]]) -> dict[Key, list[str]]:
    k = [header.index(c) for c in ("season", "week", "season_type", "player_id")]
    return {(r[k[0]], r[k[1]], r[k[2]], r[k[3]]): r for r in rows}


def season_types_change(context: GateContext) -> tuple[set[str], str]:
    """(season types kept by both the last publish and this run, text describing the change or '').

    Rows of a season type the user added or dropped in SeasonTypes are the user's own change,
    not an upstream correction (QA finding m-01), so G-RESTATE compares only the shared types.
    """
    now = set(context.config.season_types)
    before_text = (context.previous_season_types or "").strip().upper()
    before = {t for t in before_text.split("+") if t in VALID_SEASON_TYPES}
    if not before or before == now:
        return now, ""
    return now & before, f"SeasonTypes changed by you from {before_text} to {context.config.season_types_text}"


def restatements(context: GateContext) -> tuple[list[list], int, int, list[int]]:
    """Changes in refreshed seasons that were published as complete.

    Returns (rows, true count, rows removed, seasons compared). Cell changes are compared on the
    columns both versions have (a config change can add or drop metric columns), and only for the
    season types both versions keep (a SeasonTypes change is the user's, not nflverse's). A key
    that disappeared is logged with column '(row)', old 'present', new 'absent'; a new key the
    other way round.
    """
    shared_types, _ = season_types_change(context)
    rows, count, removed, compared = [], 0, 0, []
    for season in sorted(context.refreshed):
        if context.previous_status.get(season) != "complete":
            continue
        relative = season_file("player_week", season)
        previous = context.previous(relative)
        if previous is None:
            continue
        compared.append(season)
        staged = context.staged(relative)
        if lf_bytes(previous.read_bytes()) == staged.read_bytes():
            continue
        old_header, old_rows = _read_rows(previous)
        new_header, new_rows = _read_rows(staged)
        old, new = _keyed(old_header, old_rows), _keyed(new_header, new_rows)
        old = {k: v for k, v in old.items() if k[2] in shared_types}
        new = {k: v for k, v in new.items() if k[2] in shared_types}
        ids = {"season", "week", "season_type", "player_id"}
        common = [(c, old_header.index(c), new_header.index(c)) for c in new_header if c in old_header and c not in ids]
        found = []
        for key, new_row in new.items():
            old_row = old.get(key)
            if old_row is None:
                found.append(list(key) + [ROW_MARK, "absent", "present"])
                continue
            for column, oi, ni in common:
                if old_row[oi] != new_row[ni]:
                    found.append(list(key) + [column, old_row[oi], new_row[ni]])
        for key in old.keys() - new.keys():
            found.append(list(key) + [ROW_MARK, "present", "absent"])
            removed += 1
        found.sort(key=lambda r: (int(r[0]), int(r[1]), r[2], r[3], r[4]))
        count += len(found)
        for r in found:
            if len(rows) < RESTATE_CAP:
                rows.append([context.checked_utc] + r)
    return rows, count, removed, compared


def restatement_file_rows(context: GateContext, new_rows: list[list]) -> list[list]:
    """restatements.csv keeps earlier detections (seasons still in the window) and appends this run's."""
    kept = []
    previous = context.previous("checks/restatements.csv")
    if previous is not None:
        header, rows = _read_rows(previous)
        if header == RESTATE_HEADER:
            window = {str(s) for s in context.seasons}
            kept = [r for r in rows if len(r) == len(RESTATE_HEADER) and r[1] in window]
    return kept + new_rows


def gate_restate(context: GateContext, result: tuple[list[list], int, int, list[int]]) -> GateResult:
    name = "Back-corrections in finished seasons"
    rows, count, removed, compared = result
    _, types_change = season_types_change(context)
    own = (f"; rows of season types you added or removed are not counted ({types_change}: your change, "
           "not an nflverse correction)" if types_change else "")
    if not compared:
        return GateResult("G-RESTATE", name, "advisory", "PASS",
                          "no previously complete season was rebuilt in this run" + own)
    if not count:
        return GateResult("G-RESTATE", name, "advisory", "PASS",
                          f"no values changed in {len(compared)} previously complete season(s)" + own)
    seasons = sorted({r[1] for r in rows})
    message = (f"{count} change(s) upstream in finished season(s) {', '.join(map(str, seasons))}"
               + (f", including {removed} row(s) removed" if removed else "")
               + f"; {len(rows)} logged in checks/restatements.csv"
               + (f" (capped at {RESTATE_CAP})" if count > RESTATE_CAP else ""))
    message += own
    context.notes.append(f"G-RESTATE: {count} change(s) restated in {', '.join(map(str, seasons))}")
    if removed or count > RESTATE_CAP:
        return GateResult("G-RESTATE", name, "advisory", "WARN",
                          message + "; this is a large correction, compare a few rows with nflverse before relying "
                          "on those seasons")
    return GateResult("G-RESTATE", name, "advisory", "PASS",
                      message + " (routine nflverse correction, already applied)")


# ---- G-WINDOW --------------------------------------------------------------------------------

def gate_window(context: GateContext) -> GateResult:
    """Advisory: the season window asks only for published seasons (QA finding M-02)."""
    name = "Season window asks only for published seasons"
    first, last = context.seasons[0], context.seasons[-1]
    span = f"window {first}-{last} ({len(context.seasons)} season(s))"
    if context.unpublished_seasons:
        missing = context.unpublished_seasons
        years = f"{missing[0]}" if len(missing) == 1 else f"{missing[0]}-{missing[-1]}"
        return GateResult("G-WINDOW", name, "advisory", "WARN",
                          f"EndSeason {missing[-1]} is after the newest season nflverse has published "
                          f"({context.latest_season}); {years} not published yet, so the {span} stops at "
                          f"{last} for now and grows by itself when nflverse publishes the next season. "
                          "Nothing is wrong; set EndSeason to Latest in pipeline_config.csv to remove this note")
    return GateResult("G-WINDOW", name, "advisory", "PASS",
                      f"{span}, all published" + (f" (newest published season {context.latest_season})"
                                                  if context.latest_season else ""))


# ---- G-OVERLAP -------------------------------------------------------------------------------

def gate_overlap(context: GateContext) -> GateResult:
    name = "No double-counted metrics; valid position gates"
    config = context.config
    findings = []
    for lg in config.active_leagues:
        used = {w.metric for w in config.weights if w.weights.get(lg.name, 0.0)}
        used |= {b.metric for b in config.bands if b.league == lg.name}
        for total, parts in OVERLAPS:
            both = [p for p in parts if p in used]
            if total in used and both:
                findings.append(f"{lg.name} scores both {total} and {', '.join(both)}")
    codes = set()
    for season in context.seasons:
        codes |= pw_scan(context, season).codes
    gates_used = {}
    for w in config.weights:
        for c in (w.applies_to or "").upper().replace(" ", "").split(","):
            if c:
                gates_used.setdefault(c, f"scoring_weights.csv {w.metric}")
    for b in config.bands:
        for c in (b.applies_to or "").upper().replace(" ", "").split(","):
            if c:
                gates_used.setdefault(c, f"bonus_rules.csv {b.league} {b.metric}")
    for code, where in sorted(gates_used.items()):
        if code not in codes:
            findings.append(f"Applies_To code '{code}' ({where}) matches no position or position group in the data")
    if findings:
        return GateResult("G-OVERLAP", name, "advisory", "WARN",
                          f"{_examples(findings, 2)}; set one of the weights to 0 or fix the Applies_To code")
    return GateResult("G-OVERLAP", name, "advisory", "PASS",
                      f"no league weights a total and its parts; Applies_To codes {', '.join(sorted(gates_used))} "
                      "all exist in the data")


# ---- G-INDEX ---------------------------------------------------------------------------------

def _matches(path: Path, size: str, sha: str, crlf: list[str] | None, relative: str) -> bool:
    """True when ``path`` holds the recorded content. A copy that differs only by Windows line
    endings (a Git for Windows checkout) matches too and is listed in ``crlf``."""
    if str(path.stat().st_size) == size and sha256_file(path) == sha:
        return True
    if hashlib.sha256(lf_bytes(path.read_bytes())).hexdigest() == sha:
        if crlf is not None:
            crlf.append(relative)
        return True
    return False


def manifest_problems(folder: Path, crlf: list[str] | None = None) -> tuple[int, list[str]]:
    """(files checked, problems) for manifest.csv against the files in ``folder``.

    Files whose only difference is CRLF line endings are not problems; they are added to ``crlf``.
    """
    folder = Path(folder)
    header, rows = _read_rows(folder / "manifest.csv")
    try:
        fi, si, hi = header.index("file"), header.index("size_bytes"), header.index("sha256")
    except ValueError as exc:
        raise GateInputError(f"manifest.csv: {exc}") from exc
    problems, listed = [], set()
    for r in rows:
        relative = r[fi]
        listed.add(relative)
        path = folder / relative
        if not path.is_file():
            problems.append(f"{relative} is missing")
        elif not _matches(path, r[si], r[hi], crlf, relative):
            problems.append(f"{relative} was changed after publishing")
    for path in sorted(folder.rglob("*.csv")):
        relative = path.relative_to(folder).as_posix()
        if relative != "manifest.csv" and relative not in listed:
            problems.append(f"{relative} is not in manifest.csv")
    return len(rows), problems


def kept_file_problems(context: GateContext) -> tuple[int, list[str]]:
    """During a run: season files copied unchanged from 04-data must still match the published
    manifest, otherwise a hand-edited file would be re-published under a fresh hash."""
    previous = context.previous("manifest.csv")
    kept = [season_file(kind, s) for s in context.seasons if s not in context.refreshed
            for kind in ("player_week", "scored", "long_td")]
    if previous is None or not kept:
        return 0, []
    recorded = {r["file"]: r["sha256"] for r in read_csv(previous)}
    problems = []
    for relative in kept:
        path = context.staged(relative)
        if relative not in recorded:
            problems.append(f"{relative} is not in the published manifest.csv")
        elif path.is_file() and sha256_file(path) != recorded[relative]:
            problems.append(f"04-data/{relative} was edited after it was published")
        # (kept files are staged with CRLF turned into LF, so a Windows checkout matches here)
    return len(kept), problems


def gate_index(context: GateContext) -> GateResult:
    name = "Index files agree with the data"
    problems = []
    header, rows = _read_rows(context.staged("seasons.csv"))
    idx = {c: header.index(c) for c in ("season", "season_type", "player_rows", "dst_rows")}
    listed = {}
    for r in rows:
        listed[(r[idx["season"]], r[idx["season_type"]])] = (int(r[idx["player_rows"]]), int(r[idx["dst_rows"]]))
        if r[idx["season_type"]] not in VALID_SEASON_TYPES:
            problems.append(f"seasons.csv has season_type '{r[idx['season_type']]}'")
    actual = {}
    for season in context.seasons:
        scan = pw_scan(context, season)
        for stype, (players, dst) in scan.counts.items():
            actual[(str(season), stype)] = (players, dst)
        if scan.bad_types:
            problems.append(f"player_week_{season}.csv has season_type {', '.join(sorted(scan.bad_types))} "
                            "(only REG or POST allowed)")
        if scan.order_error:
            problems.append(scan.order_error)
        scored = scored_scan(context, season)
        if scored.keys != scan.keys:
            where = next((i for i, (a, b) in enumerate(zip(scored.keys, scan.keys)) if a != b),
                         min(len(scored.keys), len(scan.keys)))
            problems.append(f"scored_{season}.csv rows differ from player_week_{season}.csv "
                            f"({len(scored.keys)} vs {len(scan.keys)} rows, first difference at data row {where + 1})")
        lt_header, lt_rows = _read_rows(context.staged(season_file("long_td", season)))
        ti = lt_header.index("season_type")
        bad_lt = {r[ti] for r in lt_rows if r[ti] not in VALID_SEASON_TYPES}
        if bad_lt:
            problems.append(f"long_td_{season}.csv has season_type {', '.join(sorted(bad_lt))}")
    for slot in sorted(set(listed) | set(actual)):
        if listed.get(slot) != actual.get(slot):
            got = actual.get(slot)
            problems.append(f"seasons.csv says {slot[0]} {slot[1]} has {listed.get(slot, 'no row')} "
                            f"(player, D/ST) rows but player_week has {got if got else 'none'}")
    extra_seasons = {int(s) for s, _ in listed} - set(context.seasons)
    if extra_seasons:
        problems.append(f"seasons.csv lists season(s) {sorted(extra_seasons)} outside the window")
    if context.verify_manifest:
        crlf: list[str] = []
        checked, manifest = manifest_problems(context.stage_dir, crlf)
        problems += manifest
        manifest_note = f", {checked} manifest hashes verified"
        if crlf:
            manifest_note += (f" ({len(crlf)} file(s) have Windows line endings from a git checkout, content "
                              "identical; the next publish rewrites them with Unix line endings)")
    else:
        kept, edited = kept_file_problems(context)
        problems += edited
        manifest_note = (f"; {kept} season files kept from the last publish match its manifest"
                         if kept else "")
    if problems:
        return GateResult("G-INDEX", name, "blocking", "FAIL",
                          f"{len(problems)} problem(s): {_examples(problems, 2)}; the workbook would read "
                          "inconsistent files: restore 04-data from git or run `python -m nflpipe run --seasons all`")
    return GateResult("G-INDEX", name, "blocking", "PASS",
                      f"seasons.csv counts match {len(actual)} season/type(s); scored keys and order match "
                      f"player_week; season types REG/POST only{manifest_note}")


# ---- running the gates -----------------------------------------------------------------------

GATE_TABLE = [  # (id, name, severity) in gates.csv order
    ("G-CONFIG", "Config is valid", "blocking"),
    ("G-GRAIN", "One row per player-game", "blocking"),
    ("G-RECON", "Control leagues match nflverse", "blocking"),
    ("G-GOLDEN", "Golden sample reproduced", "blocking"),
    ("G-ESPN", "ESPN actuals reproduced", "blocking"),
    ("G-DST", "Every team-game has a D/ST row", "blocking"),
    ("G-SHRINK", "No season shrank", "blocking"),
    ("G-INDEX", "Index files agree with the data", "blocking"),
    ("G-ROWS", "Completed seasons match the row-count baseline", "advisory"),
    ("G-LONGTD", "Completed-season long-TD totals match", "advisory"),
    ("G-RESTATE", "Back-corrections in finished seasons", "advisory"),
    ("G-WINDOW", "Season window asks only for published seasons", "advisory"),
    ("G-OVERLAP", "No double-counted metrics; valid position gates", "advisory"),
]
ALL_GATES = [g for g, _, _ in GATE_TABLE]


def _guarded(gate_id: str, action):
    """Run one gate; any error becomes a FAIL of that gate with a readable reason."""
    _, name, severity = next(row for row in GATE_TABLE if row[0] == gate_id)
    try:
        result = action()
    except (GateInputError, OSError, ValueError, KeyError, IndexError, csv.Error) as exc:
        reason = str(exc) if isinstance(exc, GateInputError) else f"{type(exc).__name__}: {exc}"
        return GateResult(gate_id, name, severity, "FAIL",
                          f"could not run this check: {reason}; fix or restore the file and run again"), None
    if isinstance(result, tuple):
        gate_result, payload = result
    else:
        gate_result, payload = result, None
    gate_result.detail = _one_line(gate_result.detail)
    return gate_result, payload


def evaluate(context: GateContext, gate_ids: list[str] | None = None) -> tuple[list[GateResult], dict[str, list]]:
    """Run the chosen gates (default: all). Returns (results, check-file rows by file name). Writes nothing."""
    wanted = gate_ids or ALL_GATES
    results, files = [], {}

    def with_rows(compute, gate):
        def action():
            rows = compute(context)
            return gate(context, rows), rows
        return action

    actions = {
        "G-CONFIG": lambda: gate_config(context),
        "G-GRAIN": lambda: gate_grain(context),
        "G-RECON": with_rows(reconciliation_rows, gate_recon),
        "G-GOLDEN": with_rows(golden_rows, gate_golden),
        "G-ESPN": with_rows(espn_rows, gate_espn),
        "G-DST": lambda: gate_dst(context),
        "G-SHRINK": lambda: gate_shrink(context),
        "G-INDEX": lambda: gate_index(context),
        "G-ROWS": with_rows(row_count_rows, gate_rows),
        "G-LONGTD": lambda: gate_longtd(context),
        "G-RESTATE": with_rows(restatements, gate_restate),
        "G-WINDOW": lambda: gate_window(context),
        "G-OVERLAP": lambda: gate_overlap(context),
    }
    payload_file = {"G-RECON": "reconciliation.csv", "G-GOLDEN": "golden.csv", "G-ESPN": "espn_reconciliation.csv",
                    "G-ROWS": "row_counts.csv", "G-RESTATE": "restatements.csv"}
    for gate_id in ALL_GATES:
        if gate_id not in wanted:
            continue
        result, payload = _guarded(gate_id, actions[gate_id])
        results.append(result)
        if gate_id in payload_file:
            if gate_id == "G-RESTATE":
                payload = restatement_file_rows(context, payload[0] if payload else [])
            files[payload_file[gate_id]] = payload or []
        if gate_id == "G-ESPN":
            files[ESPN_DST_STATS] = context._cache.get("espn_dst_stats", [])
    return results, files


CHECK_FILE_HEADERS = {"reconciliation.csv": RECON_HEADER, "golden.csv": GOLDEN_HEADER,
                      "espn_reconciliation.csv": ESPN_HEADER, "row_counts.csv": ROW_COUNTS_HEADER,
                      "restatements.csv": RESTATE_HEADER, ESPN_DST_STATS: ESPN_DST_HEADER}


def write_gates(context: GateContext, results: list[GateResult]) -> None:
    """checks/gates.csv in the stage folder."""
    target = context.staged("checks/gates.csv")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(csv_bytes(GATES_HEADER, [[r.gate_id, r.gate, r.severity, r.result, r.detail,
                                                 context.checked_utc] for r in results]))


def run_config_gate_only(context: GateContext) -> list[GateResult]:
    """G-CONFIG alone, used before any download when the config is already known to be broken."""
    results = [gate_config(context)]
    write_gates(context, results)
    return results


def run_gates(context: GateContext) -> list[GateResult]:
    """Run every gate and write checks/gates.csv plus the other check files into the stage."""
    results, files = evaluate(context)
    for name, header in CHECK_FILE_HEADERS.items():
        target = context.staged(f"checks/{name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(csv_bytes(header, files.get(name, [])))
    write_gates(context, results)
    return results


def blocking_failures(results: list[GateResult]) -> list[GateResult]:
    return [r for r in results if r.severity == "blocking" and r.result == "FAIL"]
