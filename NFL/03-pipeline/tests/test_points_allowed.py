"""ESPN points allowed: ``dst_points_allowed_excl_def`` (CONTRACTS.md section 3, decision D-038).

The opponent's final score minus the points the opponent's DEFENSE scored against this team's
offense (interception and fumble return touchdowns, safeties, two-point returns on a two-point
try). Special-teams touchdowns, an offense recovering its own fumble in the end zone and the
extra point after a defensive touchdown all still count. Never below 0; blank (None) until the
game is final and while the play-by-play has no plays for the game.
"""

import gzip

import miniverse
from miniverse import PBP_HEADER, csv_text, read_table
from nflpipe.derive import DefensiveScores, TEAM_STAT_COLUMNS, scan_pbp, team_dst_rows
from nflpipe.scoring import LeagueRules, score_row

TYPES = ("REG", "POST")
GID = "2026_04_ARI_NYG"
GAME = {"game_id": GID, "season": "2026", "game_type": "REG", "week": "4",
        "away_team": "ARI", "away_score": "24", "home_team": "NYG", "home_score": "36"}


def play(**kw):
    """One play-by-play row; ARI has the ball against NYG unless told otherwise."""
    base = {"game_id": GID, "season": 2026, "week": 4, "season_type": "REG", "touchdown": 0, "pass_touchdown": 0,
            "rush_touchdown": 0, "yards_gained": 0, "play_type": "pass", "posteam": "ARI", "defteam": "NYG"}
    base.update(kw)
    return [base.get(c, "") for c in PBP_HEADER]


def pbp_path(tmp_path, *plays, gz=True):
    data = csv_text(PBP_HEADER, [play()] + list(plays))      # the game always has at least one play
    path = tmp_path / ("pbp.csv.gz" if gz else "pbp.csv")
    path.write_bytes(gzip.compress(data) if gz else data)
    return path


def team_path(tmp_path, nyg=None, ari=None):
    header = ["season", "week", "season_type", "game_id", "team", "opponent_team"] + TEAM_STAT_COLUMNS
    rows = []
    for team, opp, stats in (("ARI", "NYG", ari or {}), ("NYG", "ARI", nyg or {})):
        rows.append([2026, 4, "REG", GID, team, opp] + [stats.get(c, 0) for c in TEAM_STAT_COLUMNS])
    path = tmp_path / "team.csv"
    path.write_bytes(csv_text(header, rows))
    return path


def ari_row(tmp_path, *plays, game=GAME, pbp=True, nyg=None):
    scan = scan_pbp(pbp_path(tmp_path, *plays), TYPES) if pbp else None
    rows = {r["team"]: r for r in team_dst_rows(team_path(tmp_path, nyg=nyg), [game] if game else [], TYPES, scan)}
    return rows["ARI"]


PICK_SIX = dict(touchdown=1, interception=1, td_team="NYG")                       # NYG defense scores
FUMBLE_SIX = dict(touchdown=1, td_team="NYG", play_type="run")                    # fumble returned by NYG


# ---- the rule ------------------------------------------------------------------------------

def test_no_defensive_touchdown_keeps_the_full_score(tmp_path):
    row = ari_row(tmp_path, play(touchdown=1, pass_touchdown=1, posteam="NYG", defteam="ARI", td_team="NYG"))
    assert row["dst_points_allowed"] == 36 and row["dst_points_allowed_excl_def"] == 36


def test_one_interception_return_touchdown_is_left_out(tmp_path):
    """ESPN, ARI week 4 2026: the Giants scored 36 with a pick-six against Arizona's offense; ESPN PA 30."""
    row = ari_row(tmp_path, play(**PICK_SIX))
    assert row["dst_points_allowed"] == 36 and row["dst_points_allowed_excl_def"] == 30


def test_two_defensive_touchdowns_interception_and_fumble_are_both_left_out(tmp_path):
    row = ari_row(tmp_path, play(**PICK_SIX), play(**FUMBLE_SIX))
    assert row["dst_points_allowed_excl_def"] == 24


def test_special_teams_touchdowns_still_count(tmp_path):
    kick_return = play(touchdown=1, play_type="kickoff", posteam="NYG", defteam="ARI", td_team="NYG")
    punt_return = play(touchdown=1, play_type="punt", posteam="ARI", defteam="NYG", td_team="NYG")
    blocked_fg = play(touchdown=1, play_type="field_goal", posteam="ARI", defteam="NYG", td_team="NYG")
    row = ari_row(tmp_path, kick_return, punt_return, blocked_fg)
    assert row["dst_points_allowed_excl_def"] == 36


def test_offense_recovering_its_own_fumble_in_the_end_zone_still_counts(tmp_path):
    """ESPN, ARI week 8 2026: Dallas's 30 included such a touchdown (nflverse counts it in
    fumble_recovery_tds); ESPN PA 30."""
    own_recovery = play(touchdown=1, play_type="run", posteam="NYG", defteam="ARI", td_team="NYG")
    row = ari_row(tmp_path, own_recovery, nyg={"fumble_recovery_tds": 1})
    assert row["dst_points_allowed_excl_def"] == 36
    assert row["dst_points_allowed_excl_def_st"] == 30          # the old reference column subtracts it


def test_extra_point_after_a_defensive_touchdown_still_counts(tmp_path):
    pat = play(play_type="extra_point", posteam="NYG", defteam="ARI")
    row = ari_row(tmp_path, play(**PICK_SIX), pat, game={**GAME, "home_score": "7"})
    assert row["dst_points_allowed_excl_def"] == 1


def test_safety_against_the_offense_is_left_out_but_not_one_on_a_kick(tmp_path):
    scrimmage = play(safety=1, play_type="run", defteam_score=10, defteam_score_post=12)
    penalty = play(safety=1, play_type="no_play", defteam_score=12, defteam_score_post=14)
    on_punt = play(safety=1, play_type="punt", posteam="NYG", defteam="ARI", defteam_score=0, defteam_score_post=0)
    assert ari_row(tmp_path, scrimmage, penalty, on_punt)["dst_points_allowed_excl_def"] == 32


def test_safety_scored_by_the_offense_after_a_turnover_is_not_the_defense(tmp_path):
    # NYG intercepts and is tackled in its own end zone: ARI (posteam) scores, NYG's score is unchanged.
    turnover = play(safety=1, play_type="pass", interception=1, defteam_score=14, defteam_score_post=14)
    assert ari_row(tmp_path, turnover)["dst_points_allowed_excl_def"] == 36


def test_two_point_return_counts_only_on_a_two_point_try(tmp_path):
    on_try = play(defensive_two_point_conv=1, two_point_attempt=1, play_type="pass")
    blocked_pat = play(defensive_two_point_conv=1, play_type="extra_point")
    assert ari_row(tmp_path, on_try, blocked_pat)["dst_points_allowed_excl_def"] == 34


def test_unfinished_game_leaves_both_blank_never_zero(tmp_path):
    for game in ({**GAME, "home_score": "", "away_score": ""}, None):
        row = ari_row(tmp_path, play(**PICK_SIX), game=game)
        assert row["dst_points_allowed"] is None and row["dst_points_allowed_excl_def"] is None


def test_blank_when_the_play_by_play_is_missing_or_lacks_the_game(tmp_path):
    assert ari_row(tmp_path, pbp=False)["dst_points_allowed_excl_def"] is None
    other_game = {**GAME, "game_id": "2026_04_XXX_YYY"}
    rows = team_dst_rows(team_path(tmp_path), [other_game], TYPES, scan_pbp(pbp_path(tmp_path), TYPES))
    assert all(r["dst_points_allowed_excl_def"] is None for r in rows)        # no final score for GID either
    scan = scan_pbp(pbp_path(tmp_path, play(game_id="2026_04_XXX_YYY")), TYPES)
    scan.games.discard(GID)
    rows = {r["team"]: r for r in team_dst_rows(team_path(tmp_path), [GAME], TYPES, scan)}
    assert rows["ARI"]["dst_points_allowed"] == 36 and rows["ARI"]["dst_points_allowed_excl_def"] is None


def test_never_below_zero(tmp_path):
    row = ari_row(tmp_path, play(**PICK_SIX), play(**FUMBLE_SIX), game={**GAME, "home_score": "6"})
    assert row["dst_points_allowed_excl_def"] == 0


def test_scores_are_per_game_and_per_scoring_team(tmp_path):
    ari_pick_six = play(touchdown=1, interception=1, posteam="NYG", defteam="ARI", td_team="ARI")
    other = play(game_id="2026_04_DAL_PHI", posteam="DAL", defteam="PHI", touchdown=1, interception=1, td_team="PHI")
    scan = scan_pbp(pbp_path(tmp_path, play(**PICK_SIX), ari_pick_six, other), TYPES)
    assert scan.defense[(GID, "NYG")] == DefensiveScores(int_tds=1)
    assert scan.defense[(GID, "ARI")] == DefensiveScores(int_tds=1)
    assert scan.defense[("2026_04_DAL_PHI", "PHI")].points == 6
    assert scan.games == {GID, "2026_04_DAL_PHI"}


def test_season_types_outside_the_window_are_ignored(tmp_path):
    scan = scan_pbp(pbp_path(tmp_path, play(**PICK_SIX, season_type="POST")), ("REG",))
    assert (GID, "NYG") not in scan.defense


def test_espn_band_uses_the_new_metric(tmp_path):
    """ARI week 4 2026 in miniature: PA 30 earns the 28-34 band (-1), the full 36 would earn -3."""
    row = ari_row(tmp_path, play(**PICK_SIX))
    bands = [("dst_points_allowed_excl_def", 28.0, 34.0, -1.0, frozenset({"DST"})),
             ("dst_points_allowed_excl_def", 35.0, 45.0, -3.0, frozenset({"DST"}))]
    assert score_row(row, LeagueRules("ESPN", [], bands), 2) == -1
    old = [(m.replace("_excl_def", ""), lo, hi, pts, g) for m, lo, hi, pts, g in bands]
    assert score_row(row, LeagueRules("ESPN", [], old), 2) == -3


# ---- end to end and the gates (miniature upstream) --------------------------------------------

def test_published_and_listed_in_the_dictionary(mini):
    dst = {(r["season"], r["week"], r["player_id"]): r
           for r in read_table(mini.data / "player_week" / f"player_week_{miniverse.P}.csv")
           if r["player_id"].startswith("DST_")}
    kc = dst[(str(miniverse.P), "1", "DST_KC")]
    assert (kc["dst_points_allowed"], kc["dst_points_allowed_excl_def"]) == ("17", "11")   # LV pick-six left out
    lv = dst[(str(miniverse.P), "1", "DST_LV")]
    assert (lv["dst_points_allowed"], lv["dst_points_allowed_excl_def"]) == ("20", "20")
    dictionary = {r["metric"]: r for r in read_table(mini.data / "dictionary.csv")}
    assert dictionary["dst_points_allowed_excl_def"]["source"] == "derived:team_dst"


def test_finished_game_missing_from_play_by_play_holds(mini, upstream):
    games = miniverse.games_file().replace(f"{miniverse.C},REG,2,KC,,OAK,".encode(),
                                           f"{miniverse.C},REG,2,KC,21,OAK,14".encode())
    upstream.put("schedules/games.csv", games, f"{miniverse.C}-04-01T00:00:00Z")
    before = miniverse.snapshot(mini.data)
    assert mini.run("--seasons", "current") == 4
    assert miniverse.snapshot(mini.data) == before
    gates = {r["gate_id"]: r for r in read_table(mini.report / "checks" / "gates.csv")}
    assert gates["G-DST"]["result"] == "FAIL" and "blank dst_points_allowed_excl_def" in gates["G-DST"]["detail"]


def test_play_by_play_disagreeing_with_stats_team_holds(mini, upstream):
    team = miniverse.team_file(miniverse.P)
    header, *rows = [line.split(",") for line in team.decode().strip().split("\n")]
    i = header.index("def_tds")
    for r in rows:
        r[i] = "0"                                                   # stats_team forgets LV's pick-six
    upstream.put(f"stats_team/stats_team_week_{miniverse.P}.csv",
                 ("\n".join(",".join(r) for r in [header] + rows) + "\n").encode(), f"{miniverse.Y}-03-01T00:00:00Z")
    assert mini.run() == 4
    gates = {r["gate_id"]: r for r in read_table(mini.report / "checks" / "gates.csv")}
    assert gates["G-DST"]["result"] == "FAIL"
    assert "interception-return TDs 1 in play-by-play, 0 in stats_team" in gates["G-DST"]["detail"]


def test_espn_stat_columns_are_checked_exactly_and_hold_on_a_difference(mini):
    stats = read_table(mini.data / "checks" / "espn_dst_stats.csv")
    pa = next(r for r in stats if r["stat"] == "PA")
    assert (pa["espn_value"], pa["our_value"], pa["status"]) == ("10", "10", "MATCH")
    fixture = mini.fixtures / "espn_dst_stats.csv"
    fixture.write_text(fixture.read_text().replace(",0,0,10,test row", ",0,0,11,test row"))
    assert mini.run() == 4
    gates = {r["gate_id"]: r for r in read_table(mini.report / "checks" / "gates.csv")}
    assert gates["G-ESPN"]["result"] == "FAIL" and "PA ESPN 11 ours 10" in gates["G-ESPN"]["detail"]


def test_check_command_rejects_an_impossible_value(mini):
    from miniverse import rewrite
    path = mini.data / "player_week" / f"player_week_{miniverse.P}.csv"

    def change(header, rows):
        i, j = header.index("player_id"), header.index("dst_points_allowed_excl_def")
        for r in rows:
            if r[i] == "DST_KC" and r[j]:
                r[j] = "99"                                          # more than the final score of 17
        return rows
    rewrite(path, change)
    from nflpipe import check, gates
    context = check.build_context(mini.data, mini.fixtures)
    (result,), _ = gates.evaluate(context, ["G-DST"])
    assert result.result == "FAIL" and "impossible" in result.detail


def test_banding_two_versions_of_points_allowed_is_flagged(mini):
    bonus = mini.config / "bonus_rules.csv"
    bonus.write_text(bonus.read_text() + "Custom,dst_points_allowed_excl_def,0,6,1,DST,\n")
    mini.run()
    gates = {r["gate_id"]: r for r in read_table(mini.report / "checks" / "gates.csv")}
    assert gates["G-OVERLAP"]["result"] == "WARN"
    assert "dst_points_allowed and dst_points_allowed_excl_def" in gates["G-OVERLAP"]["detail"]
