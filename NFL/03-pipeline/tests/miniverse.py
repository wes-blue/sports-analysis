"""A miniature, fabricated nflverse upstream plus config and fixtures for offline tests.

Two seasons, relative to the current UTC year Y (``run`` looks for "Latest" in this year):

* P = Y-1, complete: week 1 REG KC at OAK (20-17; the schedule still says OAK, the stats
  files say LV), week 2 the Super Bowl (POST) OAK at KC (3-30).
* C = Y, in progress: week 1 REG OAK at KC (10-24), week 2 REG KC at OAK not finished yet
  (stats_team already has the rows, games.csv has no score).

Players: QB1 and WR1 (KC), RB1 and K1 (LV), plus a placeholder row with an empty player_id.
Play-by-play for P week 1: a 55-yard pass TD QB1 -> WR1, a 41-yard pass TD caught by WR1 and
lateraled to RB1 (td_player_id RB1), a 40-yard rush TD by RB1, a 39-yard TD and a 60-yard
non-TD run (neither counts), and an LV interception return TD against KC's offense (so KC's
dst_points_allowed is 17 but dst_points_allowed_excl_def is 11). Every finished game has at
least one play, so dst_points_allowed_excl_def is known for it.

``Upstream`` replaces ``nflpipe.run.fetch`` / ``head_last_modified`` so no test touches the network.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path

from nflpipe.derive import TEAM_STAT_COLUMNS
from nflpipe.http import BASE_URL, Fetched, NotPublished

Y = datetime.now(timezone.utc).year
P, C = Y - 1, Y
QB1, WR1, RB1, K1 = "00-0000001", "00-0000002", "00-0000003", "00-0000004"

NFL_METRICS = ["passing_yards", "passing_tds", "rushing_yards", "rushing_tds", "receptions",
               "receiving_yards", "receiving_tds", "fg_made"]
PLAYER_HEADER = (["player_id", "player_name", "player_display_name", "position", "position_group", "headshot_url",
                  "season", "week", "season_type", "team", "opponent_team"] + NFL_METRICS
                 + ["fantasy_points", "fantasy_points_ppr"])
PEOPLE = {QB1: ("Q. Back", "QB", "QB"), WR1: ("W. Ide", "WR", "WR"), RB1: ("R. Unner", "RB", "RB"),
          K1: ("K. Icker", "K", "SPEC")}


def csv_text(header, rows) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def fantasy(stats: dict) -> tuple[float, float]:
    g = lambda k: stats.get(k, 0) or 0                                   # noqa: E731
    std = 0.04 * g("passing_yards") + 4 * g("passing_tds") + 0.1 * g("rushing_yards") + 6 * g("rushing_tds") \
        + 0.1 * g("receiving_yards") + 6 * g("receiving_tds")
    return round(std, 2), round(std + g("receptions"), 2)


def player_rows(season: int) -> list[dict]:
    """Player-game stats per season (dicts of the stats; identity added by player_file)."""
    if season == P:
        return [
            dict(pid=QB1, week=1, st="REG", team="KC", opp="LV", passing_yards=310, passing_tds=2),
            dict(pid=WR1, week=1, st="REG", team="KC", opp="LV", receptions=6, receiving_yards=130, receiving_tds=1),
            dict(pid=RB1, week=1, st="REG", team="LV", opp="KC", rushing_yards=52, rushing_tds=1, receptions=2,
                 receiving_yards=10),
            dict(pid=K1, week=1, st="REG", team="LV", opp="KC", fg_made=1),
            dict(pid="", week=1, st="REG", team="LV", opp="KC"),                     # placeholder: dropped
            dict(pid=QB1, week=2, st="POST", team="KC", opp="LV", passing_yards=200, passing_tds=1),
            dict(pid=RB1, week=2, st="POST", team="LV", opp="KC", rushing_yards=30),
        ]
    return [
        dict(pid=QB1, week=1, st="REG", team="KC", opp="LV", passing_yards=250, passing_tds=1),
        dict(pid=WR1, week=1, st="REG", team="KC", opp="LV", receptions=4, receiving_yards=60, receiving_tds=1),
        dict(pid=RB1, week=1, st="REG", team="LV", opp="KC", rushing_yards=80),
        dict(pid=QB1, week=2, st="REG", team="KC", opp="LV", passing_yards=100),
    ]


def player_file(season: int, rows: list[dict] | None = None) -> bytes:
    out = []
    for r in rows if rows is not None else player_rows(season):
        name, pos, group = PEOPLE.get(r["pid"], ("", "", ""))
        fp, ppr = fantasy(r)
        out.append([r["pid"], name, name, pos, group, "", season, r["week"], r["st"], r["team"], r["opp"]]
                   + [r.get(m, 0) for m in NFL_METRICS] + [fp, ppr])
    return csv_text(PLAYER_HEADER, out)


def team_file(season: int) -> bytes:
    header = ["season", "week", "season_type", "game_id", "team", "opponent_team"] + TEAM_STAT_COLUMNS
    base = dict.fromkeys(TEAM_STAT_COLUMNS, 0)

    def row(week, st, gid, team, opp, **kw):
        values = {**base, **kw}
        return [season, week, st, gid, team, opp] + [values[c] for c in TEAM_STAT_COLUMNS]

    if season == P:
        rows = [row(1, "REG", f"{P}_01_KC_LV", "KC", "LV", def_sacks=3, def_tackles_solo=25, passing_yards=310,
                    rushing_yards=0, sack_yards_lost=-7),
                row(1, "REG", f"{P}_01_KC_LV", "LV", "KC", def_sacks=2, def_tackles_solo=30, def_tackle_assists=10,
                    def_tackles_with_assist=1, def_interceptions=1, def_tds=1, passing_yards=0, rushing_yards=52,
                    sack_yards_lost=-15),
                row(2, "POST", f"{P}_02_LV_KC", "KC", "LV", def_sacks=1, passing_yards=200, rushing_yards=0),
                row(2, "POST", f"{P}_02_LV_KC", "LV", "KC", passing_yards=0, rushing_yards=30)]
    else:
        rows = [row(1, "REG", f"{C}_01_LV_KC", "KC", "LV", def_sacks=1, def_tackles_solo=20, def_tackle_assists=5,
                    passing_yards=250, rushing_yards=0),
                row(1, "REG", f"{C}_01_LV_KC", "LV", "KC", passing_yards=0, rushing_yards=80, sack_yards_lost=-4),
                row(2, "REG", f"{C}_02_KC_LV", "KC", "LV", passing_yards=100, rushing_yards=0),
                row(2, "REG", f"{C}_02_KC_LV", "LV", "KC", passing_yards=0, rushing_yards=0)]
    return csv_text(header, rows)


GAMES_HEADER = ["game_id", "season", "game_type", "week", "away_team", "away_score", "home_team", "home_score"]


def games_file() -> bytes:
    return csv_text(GAMES_HEADER, [
        [f"{P}_01_KC_LV", P, "REG", 1, "KC", 20, "OAK", 17],
        [f"{P}_02_LV_KC", P, "SB", 2, "OAK", 3, "KC", 30],
        [f"{C}_01_LV_KC", C, "REG", 1, "OAK", 10, "KC", 24],
        [f"{C}_02_KC_LV", C, "REG", 2, "KC", "", "OAK", ""],
    ])


# The first 11 columns are the long-TD ones; the rest identify defensive scores (derive.scan_pbp).
# Rows may stop after the first 11 columns: the reader pads short lines with blanks.
PBP_HEADER = ["game_id", "season", "week", "season_type", "touchdown", "pass_touchdown", "rush_touchdown",
              "td_player_id", "passer_player_id", "receiver_player_id", "yards_gained",
              "play_type", "posteam", "defteam", "td_team", "interception", "safety", "two_point_attempt",
              "defensive_two_point_conv", "defteam_score", "defteam_score_post"]


def pbp_file(season: int) -> bytes:
    if season == P:
        g1, g2 = f"{P}_01_KC_LV", f"{P}_02_LV_KC"
        rows = [
            [g1, P, 1, "REG", 1, 1, 0, WR1, QB1, WR1, 55, "pass", "KC", "LV", "KC"],   # pass TD 55: both columns
            [g1, P, 1, "REG", 1, 1, 0, RB1, QB1, WR1, 41, "pass", "KC", "LV", "KC"],   # lateral: RB1 gets rec_td_40
            [g1, P, 1, "REG", 1, 0, 1, RB1, "", "", 40, "run", "LV", "KC", "LV"],      # rush TD exactly 40
            [g1, P, 1, "REG", 1, 0, 1, RB1, "", "", 39, "run", "LV", "KC", "LV"],      # too short
            [g1, P, 1, "REG", 0, 0, 0, "", "", "", 60, "run", "KC", "LV", ""],         # long run, no TD
            [g1, P, 1, "REG", 1, 0, 0, "", "", "", -3, "pass", "KC", "LV", "LV", 1],   # LV pick-six vs KC's offense
            [g2, P, 2, "POST", 0, 0, 0, "", "", "", 4, "run", "KC", "LV", ""],
        ]
    else:
        rows = [[f"{C}_01_LV_KC", C, 1, "REG", 1, 1, 0, WR1, QB1, WR1, 30, "pass", "KC", "LV", "KC"]]
    return gzip.compress(csv_text(PBP_HEADER, rows), mtime=0)


# ---- config and fixtures ---------------------------------------------------------------------

LEAGUES = b"""League,Description,Active,Reconcile_To,Notes
Standard,Control,Yes,fantasy_points,
PPR,Control,Yes,fantasy_points_ppr,
Custom,Custom league,Yes,,
"""
WEIGHTS = b"""Metric,Category,Description,Standard,PPR,Custom,Notes,Applies_To
passing_yards,Passing,,0.04,0.04,0.04,,
passing_tds,Passing,,4,4,4,,
rushing_yards,Rushing,,0.1,0.1,0.1,,
rushing_tds,Rushing,,6,6,6,,
receptions,Receiving,,0,1,0.5,,
receiving_yards,Receiving,,0.1,0.1,0.1,,
receiving_tds,Receiving,,6,6,6,,
fg_made,Kicking,,0,0,3,,K
pass_td_40,Long TD,,0,0,1,,
pass_td_50,Long TD,,0,0,1,,
rush_td_40,Long TD,,0,0,1,,
rush_td_50,Long TD,,0,0,1,,
rec_td_40,Long TD,,0,0,1,,
rec_td_50,Long TD,,0,0,1,,
dst_sacks,DST,,0,0,1,,DST
dst_tackles,DST,,0,0,1,,DST
dst_points_allowed,DST,,0,0,0,,DST
dst_points_allowed_excl_def,DST,,0,0,0,,DST
dst_yards_allowed,DST,,0,0,0,,DST
"""
BONUS = b"""League,Metric,Lower,Upper,Points,Applies_To,Notes
Custom,passing_yards,300,399,1,,
Custom,passing_yards,400,,2,,
Custom,dst_points_allowed,0,13,3,DST,
Custom,dst_points_allowed,14,,-1,DST,
"""
SETTINGS = b"""Setting,Value,Allowed_Values,Description
StartSeason,Latest-1,,
EndSeason,Latest,,
SeasonTypes,REG+POST,,
RoundDecimals,2,,
PublishExtraColumns,,,
ReconcileTolerance,0.005,,
"""

# Hand-computed (see module docstring): QB1 P wk1 = 12.4 + 8 = 20.4; Custom adds pass_td_40 x2,
# pass_td_50 x1 and the 300-399 band = 24.4. WR1 = 13 + 6 = 19; PPR 25; Custom 19 + 3 + 2 = 24.
# RB1 = 5.2 + 6 + 1 = 12.2; PPR 14.2; Custom 13.2 + rush_td_40 + rec_td_40 = 15.2. LV D/ST P wk1:
# sacks 2 + tackles 41 (30 + 10 + 1) + band 14+ (-1) = 42. K1: fg_made 1 x 3 = 3 (K gate).
GOLDEN = f"""season,week,season_type,player_id,player_display_name,FF_Standard,FF_PPR,FF_Custom
{P},1,REG,{QB1},Q. Back,20.4,20.4,24.4
{P},1,REG,{WR1},W. Ide,19,25,24
{P},1,REG,{RB1},R. Unner,12.2,14.2,15.2
{P},1,REG,DST_LV,LV D/ST,0,0,42
{P},1,REG,{K1},K. Icker,0,0,3
""".encode()
# C wk1: QB1 = 10 + 4 = 14 (30-yard TD: no bonus). KC D/ST: 1 + 25 + band 0-13 (+3) = 29; "ESPN" says 30.
ESPN = f"""season,week,season_type,player_id,player_display_name,team,position,league,espn_points,tolerance,row_expected,note
{C},1,REG,{QB1},Q. Back,KC,QB,Custom,14,0,Yes,test row
{C},1,REG,DST_KC,KC D/ST,KC,DST,Custom,30,1,Yes,feed differs by one
{C},1,REG,00-0000099,N. Oshow,KC,RB,Custom,0,0,No,did not play
""".encode()
# KC D/ST C wk1 as an "ESPN game log" shows it: 1 sack, LV scored 10 (no defensive score).
ESPN_DST = f"""season,week,season_type,player_id,player_display_name,espn_td,espn_int,espn_fr,espn_sck,espn_sfty,espn_blk,espn_pa,note
{C},1,REG,DST_KC,KC D/ST,0,0,0,1,0,0,10,test row
""".encode()
ROW_BASELINE = f"""season,season_type,rows,placeholder_rows,expected_stats_raw_rows,distinct_players,max_week
{P},POST,2,0,2,2,2
{P},REG,5,1,4,4,1
""".encode()
LONGTD_BASELINE = (
    "season,pass_td,pass_td_40plus,pass_td_50plus,rush_td,rush_td_40plus,rush_td_50plus,receiving_td_40plus,"
    "receiving_td_50plus,passer_games_40plus,passer_games_50plus,rusher_games_40plus,rusher_games_50plus,"
    f"receiver_games_40plus,receiver_games_50plus\n{P},3,2,1,2,1,0,2,1,1,1,1,0,2,1\n").encode()


def write_config(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in (("leagues.csv", LEAGUES), ("scoring_weights.csv", WEIGHTS), ("bonus_rules.csv", BONUS),
                       ("pipeline_config.csv", SETTINGS)):
        (folder / name).write_bytes(data)
    return folder


def fixture_contracts_bytes() -> bytes:
    """fixture_contracts.csv for the config above (the rules GOLDEN and ESPN were computed with)."""
    import tempfile
    from nflpipe.config import load_config
    from nflpipe.gates import FIXTURE_CONTRACTS_HEADER, fixture_contract_rows
    from nflpipe.publish import csv_bytes
    with tempfile.TemporaryDirectory() as tmp:
        config = load_config(write_config(Path(tmp)))
        return csv_bytes(FIXTURE_CONTRACTS_HEADER, fixture_contract_rows(config))


def write_fixtures(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in (("golden_sample.csv", GOLDEN), ("espn_actuals.csv", ESPN), ("espn_dst_stats.csv", ESPN_DST),
                       ("row_count_baseline.csv", ROW_BASELINE), ("long_td_baseline.csv", LONGTD_BASELINE),
                       ("fixture_contracts.csv", fixture_contracts_bytes())):
        (folder / name).write_bytes(data)
    return folder


# ---- the fake downloader ---------------------------------------------------------------------

class Upstream:
    """In-memory nflverse release: relative path -> (bytes, Last-Modified)."""

    def __init__(self):
        self.files: dict[str, tuple[bytes, str]] = {}
        self.calls = 0
        for season in (P, C):
            self.put(f"stats_player/stats_player_week_{season}.csv", player_file(season))
            self.put(f"stats_team/stats_team_week_{season}.csv", team_file(season))
            self.put(f"pbp/play_by_play_{season}.csv.gz", pbp_file(season))
        self.put("schedules/games.csv", games_file())

    def put(self, relative: str, data: bytes, last_modified: str = f"{Y}-01-01T00:00:00Z") -> None:
        self.files[relative] = (data, last_modified)

    def fetch(self, relative_path: str, cache_dir: Path, force: bool = False) -> Fetched:
        self.calls += 1
        if relative_path not in self.files:
            raise NotPublished(BASE_URL + relative_path)
        data, last_modified = self.files[relative_path]
        path = Path(cache_dir) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return Fetched(BASE_URL + relative_path, path, last_modified, len(data), hashlib.sha256(data).hexdigest(),
                       f"{Y}-01-02T00:00:00Z", False)

    def head_last_modified(self, url: str) -> str:
        self.calls += 1
        relative = url[len(BASE_URL):]
        if relative not in self.files:
            raise NotPublished(url)
        return self.files[relative][1]

    def install(self, monkeypatch) -> "Upstream":
        from nflpipe import run
        monkeypatch.setattr(run, "fetch", self.fetch)
        monkeypatch.setattr(run, "head_last_modified", self.head_last_modified)
        return self


class Project:
    """Temp folders laid out like the real project, plus helpers to run commands."""

    def __init__(self, root: Path, write: bool = True):
        self.root = root
        self.config = write_config(root / "02-config") if write else root / "02-config"
        self.data = root / "04-data"
        self.fixtures = write_fixtures(root / "06-qa" / "fixtures") if write else root / "06-qa" / "fixtures"
        self.cache = root / ".work" / "cache"
        self.report = root / ".work" / "last-run"

    def args(self, *extra: str) -> list[str]:
        return [*extra, "--config-dir", str(self.config), "--data-dir", str(self.data),
                "--fixtures-dir", str(self.fixtures), "--cache-dir", str(self.cache), "--report-dir", str(self.report)]

    def run(self, *extra: str) -> int:
        from nflpipe import run
        return run.main(self.args("--seasons", "all", *extra) if not any(e == "--seasons" for e in extra)
                        else self.args(*extra))

    def check(self) -> int:
        from nflpipe import check
        return check.main(["--data-dir", str(self.data), "--fixtures-dir", str(self.fixtures)])


def snapshot(folder: Path) -> dict[str, tuple[bytes, int]]:
    """Every file's bytes and mtime_ns (to prove a folder was left untouched)."""
    folder = Path(folder)
    if not folder.exists():
        return {}
    return {p.relative_to(folder).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(folder.rglob("*")) if p.is_file()}


def read_table(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def rewrite(path: Path, change) -> None:
    """Apply ``change(header, rows) -> rows`` to a CSV file in place (published format)."""
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = list(reader)
    rows = change(header, rows)
    path.write_bytes(csv_text(header, rows))
