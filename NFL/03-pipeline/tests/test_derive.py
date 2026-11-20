"""Derived metrics: long touchdowns and team D/ST rows (CONTRACTS.md section 3)."""

import gzip

from miniverse import PBP_HEADER, csv_text
from nflpipe.derive import TEAM_STAT_COLUMNS, long_td_counts, team_dst_rows

TYPES = ("REG", "POST")


def pbp(tmp_path, rows, gz=False):
    data = csv_text(PBP_HEADER, rows)
    path = tmp_path / ("pbp.csv.gz" if gz else "pbp.csv")
    path.write_bytes(gzip.compress(data) if gz else data)
    return path


def play(td=1, pass_td=0, rush_td=0, scorer="", passer="", receiver="", yards=0, week=1, st="REG"):
    return ["g", 2025, week, st, td, pass_td, rush_td, scorer, passer, receiver, yards]


def counts(tmp_path, *plays, gz=False):
    return long_td_counts(pbp(tmp_path, list(plays), gz), TYPES)


# ---- long touchdowns -------------------------------------------------------------------------

def test_40_and_50_yard_boundaries(tmp_path):
    c = counts(tmp_path,
               play(rush_td=1, scorer="A", yards=39),
               play(rush_td=1, scorer="B", yards=40),
               play(rush_td=1, scorer="C", yards=49),
               play(rush_td=1, scorer="D", yards=50))
    assert ("A" not in {k[3] for k in c})
    assert c[(2025, 1, "REG", "B")]["rush_td_40"] == 1 and c[(2025, 1, "REG", "B")]["rush_td_50"] == 0
    assert c[(2025, 1, "REG", "C")]["rush_td_50"] == 0
    assert c[(2025, 1, "REG", "D")]["rush_td_40"] == 1 and c[(2025, 1, "REG", "D")]["rush_td_50"] == 1


def test_55_yard_pass_td_counts_in_both_columns_for_passer_and_scorer(tmp_path):
    c = counts(tmp_path, play(pass_td=1, scorer="WR", passer="QB", receiver="WR", yards=55), gz=True)
    qb, wr = c[(2025, 1, "REG", "QB")], c[(2025, 1, "REG", "WR")]
    assert (qb["pass_td_40"], qb["pass_td_50"], qb["rec_td_40"]) == (1, 1, 0)
    assert (wr["rec_td_40"], wr["rec_td_50"], wr["pass_td_40"]) == (1, 1, 0)


def test_lateral_is_credited_to_the_scorer_not_the_receiver(tmp_path):
    c = counts(tmp_path, play(pass_td=1, scorer="RB", passer="QB", receiver="WR", yards=45))
    assert c[(2025, 1, "REG", "RB")]["rec_td_40"] == 1
    assert (2025, 1, "REG", "WR") not in c


def test_long_play_without_a_touchdown_is_not_counted(tmp_path):
    c = counts(tmp_path,
               play(td=0, scorer="", passer="QB", receiver="WR", yards=80),
               play(td=1, pass_td=0, rush_td=0, scorer="KR", yards=99))   # return TD: neither pass nor rush
    assert c == {}


def test_counts_add_up_per_player_game_and_respect_season_types(tmp_path):
    c = long_td_counts(pbp(tmp_path, [play(rush_td=1, scorer="R", yards=60), play(rush_td=1, scorer="R", yards=41),
                                      play(rush_td=1, scorer="R", yards=70, week=19, st="POST")]), ("REG",))
    assert c == {(2025, 1, "REG", "R"): {"pass_td_40": 0, "pass_td_50": 0, "rush_td_40": 2, "rush_td_50": 1,
                                        "rec_td_40": 0, "rec_td_50": 0}}


# ---- team D/ST -------------------------------------------------------------------------------

def team_file(tmp_path, rows):
    header = ["season", "week", "season_type", "game_id", "team", "opponent_team"] + TEAM_STAT_COLUMNS
    out = []
    for r in rows:
        values = {c: r.get(c, 0) for c in TEAM_STAT_COLUMNS}
        out.append([r["season"], r["week"], r.get("season_type", "REG"), r["game_id"], r["team"], r["opp"]]
                   + [values[c] for c in TEAM_STAT_COLUMNS])
    path = tmp_path / "team.csv"
    path.write_bytes(csv_text(header, out))
    return path


GAME = {"game_id": "2019_01_KC_OAK", "season": "2019", "game_type": "REG", "week": "1",
        "away_team": "KC", "away_score": "28", "home_team": "OAK", "home_score": "10"}


def by_team(rows):
    return {r["team"]: r for r in rows}


def test_oak_in_schedule_maps_to_lv_in_stats(tmp_path):
    path = team_file(tmp_path, [dict(season=2019, week=1, game_id="2019_01_KC_OAK", team="KC", opp="LV"),
                                dict(season=2019, week=1, game_id="2019_01_KC_OAK", team="LV", opp="KC")])
    rows = by_team(team_dst_rows(path, [GAME], TYPES))
    assert rows["LV"]["dst_points_allowed"] == 28        # LV is the home team (OAK in games.csv)
    assert rows["KC"]["dst_points_allowed"] == 10
    assert rows["LV"]["player_id"] == "DST_LV" and rows["LV"]["position"] == "DST"
    assert rows["LV"]["player_display_name"] == "LV D/ST"


def test_points_allowed_blank_never_zero_when_game_not_final(tmp_path):
    path = team_file(tmp_path, [dict(season=2019, week=1, game_id="2019_01_KC_OAK", team="KC", opp="LV"),
                                dict(season=2019, week=1, game_id="2019_01_KC_OAK", team="LV", opp="KC")])
    unfinished = {**GAME, "away_score": "", "home_score": ""}
    for games in ([unfinished], []):
        rows = team_dst_rows(path, games, TYPES)
        assert all(r["dst_points_allowed"] is None for r in rows)
        assert all(r["dst_points_allowed_excl_def_st"] is None for r in rows)


def test_net_yards_tackles_and_returns(tmp_path):
    path = team_file(tmp_path, [
        dict(season=2019, week=1, game_id="2019_01_KC_OAK", team="KC", opp="LV", passing_yards=247, rushing_yards=95,
             sack_yards_lost=-9, def_tackles_solo=25, def_tackle_assists=47, def_tackles_with_assist=1,
             def_punt_blocks=1, def_fg_blocks=1, kickoff_return_yards=66, punt_return_yards=22),
        dict(season=2019, week=1, game_id="2019_01_KC_OAK", team="LV", opp="KC", passing_yards=209, rushing_yards=82,
             sack_yards_lost=-33, special_teams_tds=1)])
    rows = by_team(team_dst_rows(path, [GAME], TYPES))
    assert rows["LV"]["dst_yards_allowed"] == 247 + 95 - 9            # net: opponent KC's yards
    assert rows["LV"]["dst_yards_allowed_gross"] == 342
    assert rows["KC"]["dst_yards_allowed"] == 258
    assert rows["KC"]["dst_tackles"] == 73
    assert rows["KC"]["dst_blocked_kicks"] == 2
    assert (rows["KC"]["dst_kr_yards"], rows["KC"]["dst_pr_yards"]) == (66, 22)
    assert rows["KC"]["dst_points_allowed_excl_def_st"] == 10 - 6     # LV's special-teams TD removed


def test_yards_allowed_blank_when_opponent_row_missing(tmp_path):
    path = team_file(tmp_path, [dict(season=2019, week=1, game_id="2019_01_KC_OAK", team="KC", opp="LV")])
    (row,) = team_dst_rows(path, [GAME], TYPES)
    assert row["dst_yards_allowed"] is None and row["dst_points_allowed"] == 10
