"""Derived metrics: long-touchdown counts and team D/ST rows (CONTRACTS.md section 3).

Ported without changing the arithmetic from the verified 1.x code (the Excel-era project, kept in
the owner's private repository and not published here):
* long TDs: ``build_long_td_static.py`` and ``LongTD.pq``;
* team D/ST: ``engine105.py`` and ``Team_DST.pq`` (reconciled to ESPN, decision D-021),
  including the ``.pq``'s schedule team-code mapping (OAK -> LV, SD -> LAC, STL -> LA),
  which the Python mirror lacked and which matters for 2017-2019 Raiders games.

New in pipeline 1.2.0 (decision D-038): ``dst_points_allowed_excl_def``, ESPN's points allowed,
which leaves out the points the opponent's defense scored against the D/ST's own offense. The
play-by-play pass that counts long touchdowns also finds those scores (``scan_pbp``), because
the team stats file cannot tell a defensive fumble-return touchdown from an offense recovering
its own fumble in the end zone (both are in ``fumble_recovery_tds``).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .ingest import iter_columns, to_number

LONG_TD_COLUMNS = ["pass_td_40", "pass_td_50", "rush_td_40", "rush_td_50", "rec_td_40", "rec_td_50"]
THRESHOLDS = (40, 50)

DST_COLUMNS = [
    "dst_sacks", "dst_tackles", "dst_blocked_kicks", "dst_interceptions", "dst_fumble_recoveries",
    "dst_fumbles_forced", "dst_safeties", "dst_kr_yards", "dst_pr_yards", "dst_int_tds", "dst_fumble_tds",
    "dst_st_tds", "dst_2pt_returns", "dst_points_allowed", "dst_points_allowed_excl_def",
    "dst_points_allowed_excl_def_st", "dst_yards_allowed", "dst_yards_allowed_gross",
]
DERIVED_SOURCES = {**{c: "derived:long_td" for c in LONG_TD_COLUMNS}, **{c: "derived:team_dst" for c in DST_COLUMNS}}

# games.csv still uses the old codes for relocated teams; the stats files use the current ones.
SCHEDULE_TEAM_CODES = {"OAK": "LV", "SD": "LAC", "STL": "LA"}

Key = tuple[int, int, str, str]       # (season, week, season_type, player_id)

# Play types on which the offense is on the field (scrimmage downs). A "no_play" is a down
# wiped out by a penalty; it can still end in a safety (offensive holding in the end zone).
SCRIMMAGE_PLAYS = {"pass", "run", "qb_kneel", "qb_spike"}


# ---- long touchdowns ---------------------------------------------------------------------

def _is_one(text: str) -> bool:
    return to_number(text) == 1


@dataclass
class DefensiveScores:
    """Points one team's DEFENSE scored in one game while the opponent's offense had the ball.

    ``int_tds`` and ``fumble_tds``: touchdowns on scrimmage plays where the scoring team was the
    defense (``td_team == defteam``): interception and fumble returns. ``safeties``: safeties the
    defense scored on scrimmage plays (penalty plays included). ``two_point_returns``: a failed
    two-point try returned by the defense for 2 points. Kick and punt plays are special teams and
    are never counted here, and neither is the extra point after a defensive touchdown.
    """
    int_tds: int = 0
    fumble_tds: int = 0
    safeties: int = 0
    two_point_returns: int = 0

    @property
    def points(self) -> int:
        return 6 * (self.int_tds + self.fumble_tds) + 2 * (self.safeties + self.two_point_returns)


@dataclass
class PbpScan:
    """What one pass over a play-by-play file yields."""
    long_td: dict[Key, dict[str, int]]
    defense: dict[tuple[str, str], DefensiveScores]     # (game_id, scoring team) -> scores
    games: set[str]                                       # every game_id the file has plays for


PBP_COLUMNS = ["game_id", "season", "week", "season_type", "play_type", "posteam", "defteam", "td_team",
               "touchdown", "pass_touchdown", "rush_touchdown", "interception", "safety", "two_point_attempt",
               "defensive_two_point_conv", "defteam_score", "defteam_score_post", "td_player_id",
               "passer_player_id", "yards_gained"]


def _safety_by_defense(play: dict[str, str]) -> bool:
    """True when the defense scored the safety. The score columns decide; without them the
    defense is assumed (the only exception is a turnover returned into the returner's own end zone)."""
    before, after = to_number(play["defteam_score"]), to_number(play["defteam_score_post"])
    if before is None or after is None:
        return True
    return after - before == 2


def scan_pbp(pbp_path: Path, season_types: tuple[str, ...]) -> PbpScan:
    """One pass over a play-by-play file: long-TD counts and defensive scores per game.

    Long TDs: plays with touchdown = 1 and pass_touchdown = 1 or rush_touchdown = 1; length is
    yards_gained. Pass TD: the passer gets pass_td_*, the scorer (td_player_id, so laterals
    are credited correctly) gets rec_td_*. Rush TD: the scorer gets rush_td_*. Counts are
    cumulative (a 55-yard TD adds 1 to _40 and _50). Plays without a player id are skipped
    (as LongTD.pq does).

    Defensive scores: see ``DefensiveScores``. Verified against stats_team for 2017-2026: the
    interception-return touchdowns equal ``def_tds`` and the safeties equal ``def_safeties`` in
    every one of the 5,288 team-games (gate G-DST repeats this check on every run).
    """
    counts: dict[Key, dict[str, int]] = defaultdict(lambda: dict.fromkeys(LONG_TD_COLUMNS, 0))
    defense: dict[tuple[str, str], DefensiveScores] = defaultdict(DefensiveScores)
    games: set[str] = set()
    for play in iter_columns(pbp_path, PBP_COLUMNS):
        if play["season_type"] not in season_types:
            continue
        game_id = play["game_id"].strip()
        if game_id:
            games.add(game_id)
            _count_defense(play, game_id, defense)
        if not _is_one(play["touchdown"]):
            continue
        is_pass, is_rush = _is_one(play["pass_touchdown"]), _is_one(play["rush_touchdown"])
        if not (is_pass or is_rush):
            continue
        length = to_number(play["yards_gained"]) or 0
        if length < THRESHOLDS[0]:
            continue
        season, week = to_number(play["season"]), to_number(play["week"])
        if season is None or week is None:
            continue
        base = (int(season), int(week), play["season_type"])
        credits = ([("passer_player_id", "pass_td"), ("td_player_id", "rec_td")] if is_pass
                   else [("td_player_id", "rush_td")])
        for id_column, prefix in credits:
            player_id = play[id_column].strip()
            if not player_id:
                continue
            for threshold in THRESHOLDS:
                if length >= threshold:
                    counts[base + (player_id,)][f"{prefix}_{threshold}"] += 1
    return PbpScan(dict(counts), dict(defense), games)


def _count_defense(play: dict[str, str], game_id: str, defense: dict) -> None:
    """Add one play's defensive score, if any, to ``defense``."""
    play_type, defteam = play["play_type"].strip(), play["defteam"].strip()
    if not defteam:
        return
    if (_is_one(play["touchdown"]) and play_type in SCRIMMAGE_PLAYS
            and play["td_team"].strip() == defteam):
        scores = defense[(game_id, defteam)]
        if _is_one(play["interception"]):
            scores.int_tds += 1
        else:
            scores.fumble_tds += 1
    if _is_one(play["safety"]) and (play_type in SCRIMMAGE_PLAYS or play_type == "no_play") \
            and _safety_by_defense(play):
        defense[(game_id, defteam)].safeties += 1
    if _is_one(play["defensive_two_point_conv"]) and _is_one(play["two_point_attempt"]) \
            and play_type in SCRIMMAGE_PLAYS:
        defense[(game_id, defteam)].two_point_returns += 1


def long_td_counts(pbp_path: Path, season_types: tuple[str, ...]) -> dict[Key, dict[str, int]]:
    """Per player-game counts of 40+ and 50+ yard touchdowns from one play-by-play file."""
    return scan_pbp(pbp_path, season_types).long_td


# ---- team D/ST ---------------------------------------------------------------------------

def _points_allowed_by_game(games: list[dict[str, str]]) -> dict[str, tuple[str, float, float]]:
    """game_id -> (home team in current codes, home score, away score) for games with a final score."""
    finals = {}
    for g in games:
        home_score, away_score = to_number(g["home_score"]), to_number(g["away_score"])
        if home_score is None or away_score is None:
            continue                                   # not played yet: points allowed stays blank
        home = SCHEDULE_TEAM_CODES.get(g["home_team"], g["home_team"])
        finals[g["game_id"]] = (home, home_score, away_score)
    return finals


TEAM_STAT_COLUMNS = [
    "def_sacks", "def_tackles_solo", "def_tackle_assists", "def_tackles_with_assist", "def_punt_blocks",
    "def_pat_blocks", "def_fg_blocks", "def_interceptions", "fumble_recovery_opp", "def_fumbles_forced",
    "def_safeties", "kickoff_return_yards", "punt_return_yards", "def_tds", "fumble_recovery_tds",
    "special_teams_tds", "def_2pt_made", "passing_yards", "rushing_yards", "sack_yards_lost",
]


def team_dst_rows(team_path: Path, games: list[dict[str, str]], season_types: tuple[str, ...],
                  pbp: PbpScan | None = None) -> list[dict]:
    """One D/ST row per team-game of a stats_team_week file, shaped like a player row.

    Counting stats treat a blank as 0 (as engine105 and Team_DST.pq do). Points allowed is
    the opponent's full final score from games.csv and stays None until the game is final.
    ``dst_points_allowed_excl_def`` (ESPN's points allowed, D-038) is that score minus the
    points the opponent's defense scored (``DefensiveScores.points``), never below 0; it is
    None until the game is final, and also when no play-by-play is given or the play-by-play
    has no plays for the game yet (missing is never zero).
    Yards allowed is the opponent's passing + rushing yards plus sack yards lost (net); it is
    None when the opponent's row or its passing yards are missing (Team_DST.pq rule).
    """
    teams = [t for t in iter_columns(team_path, ["season", "week", "season_type", "game_id", "team", "opponent_team"]
                                     + TEAM_STAT_COLUMNS)
             if t["team"].strip() and t["season_type"] in season_types
             and to_number(t["season"]) is not None and to_number(t["week"]) is not None]
    by_game_team = {(t["game_id"], t["team"]): t for t in teams}
    finals = _points_allowed_by_game(games)

    rows = []
    for t in teams:
        opp = by_game_team.get((t["game_id"], t["opponent_team"]))
        n = lambda col: to_number(t[col]) or 0.0                          # noqa: E731  own stat, blank = 0
        o = lambda col: (to_number(opp[col]) or 0.0) if opp else 0.0     # noqa: E731  opponent stat, blank = 0

        points_allowed = None
        final = finals.get(t["game_id"])
        if final is not None:
            home, home_score, away_score = final
            points_allowed = away_score if t["team"] == home else home_score
        gross = None
        if opp is not None and to_number(opp["passing_yards"]) is not None:
            gross = o("passing_yards") + o("rushing_yards")
        opp_def_st_tds = o("def_tds") + o("special_teams_tds") + o("fumble_recovery_tds")
        excl_def = None
        if points_allowed is not None and pbp is not None and t["game_id"] in pbp.games:
            scored = pbp.defense.get((t["game_id"], t["opponent_team"]), DefensiveScores())
            excl_def = max(0.0, points_allowed - scored.points)

        rows.append({
            "season": int(to_number(t["season"])), "week": int(to_number(t["week"])),
            "season_type": t["season_type"], "player_id": "DST_" + t["team"],
            "player_display_name": t["team"] + " D/ST", "position": "DST", "position_group": "DST",
            "team": t["team"], "opponent_team": t["opponent_team"],
            "dst_sacks": n("def_sacks"),
            "dst_tackles": n("def_tackles_solo") + n("def_tackle_assists") + n("def_tackles_with_assist"),
            "dst_blocked_kicks": n("def_punt_blocks") + n("def_pat_blocks") + n("def_fg_blocks"),
            "dst_interceptions": n("def_interceptions"),
            "dst_fumble_recoveries": n("fumble_recovery_opp"),
            "dst_fumbles_forced": n("def_fumbles_forced"),
            "dst_safeties": n("def_safeties"),
            "dst_kr_yards": n("kickoff_return_yards"),
            "dst_pr_yards": n("punt_return_yards"),
            "dst_int_tds": n("def_tds"),
            "dst_fumble_tds": n("fumble_recovery_tds"),
            "dst_st_tds": n("special_teams_tds"),
            "dst_2pt_returns": n("def_2pt_made"),
            "dst_points_allowed": points_allowed,
            "dst_points_allowed_excl_def": excl_def,
            "dst_points_allowed_excl_def_st": None if points_allowed is None else points_allowed - 6 * opp_def_st_tds,
            "dst_yards_allowed": None if gross is None else gross + o("sack_yards_lost"),
            "dst_yards_allowed_gross": gross,
        })
    return rows
