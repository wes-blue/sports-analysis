"""Scoring semantics (CONTRACTS.md section 4)."""

import pytest

from nflpipe.scoring import LeagueRules, allowed, gate_codes, round_half_away, score_row


def rules(weights=(), bands=()):
    return LeagueRules("L", [(m, w, gate_codes(g)) for m, w, g in weights],
                       [(m, lo, hi, pts, gate_codes(g)) for m, lo, hi, pts, g in bands])


def row(position="WR", group="WR", **values):
    return {"position": position, "position_group": group, **values}


# ---- position gate ---------------------------------------------------------------------------

def test_blank_gate_allows_every_row():
    assert allowed(gate_codes(""), "QB", "QB")
    assert allowed(gate_codes(None), "", "")


def test_gate_matches_position_or_group_case_insensitively():
    gate = gate_codes(" dl , LB,db")
    assert allowed(gate, "CB", "DB")          # by position group
    assert allowed(gate, "LB", "LB")          # by position
    assert not allowed(gate, "WR", "WR")


def test_gated_weight_only_scores_allowed_rows():
    r = rules(weights=[("fg_made", 3, "K"), ("receptions", 1, "")])
    assert score_row(row("K", "SPEC", fg_made=2, receptions=1), r, 2) == 7
    assert score_row(row("WR", "WR", fg_made=2, receptions=1), r, 2) == 1


def test_gated_band_only_scores_allowed_rows():
    r = rules(bands=[("dst_points_allowed", 0, 6, 4, "DST")])
    assert score_row(row("DST", "DST", dst_points_allowed=3), r, 2) == 4
    assert score_row(row("QB", "QB", dst_points_allowed=3), r, 2) == 0


# ---- bands -----------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [(299, 0), (300, 1), (350, 1), (399, 1), (399.5, 0), (400, 0)])
def test_band_bounds_are_inclusive(value, expected):
    r = rules(bands=[("passing_yards", 300, 399, 1, "")])
    assert score_row(row(passing_yards=value), r, 2) == expected


def test_open_bounds():
    r = rules(bands=[("passing_yards", 400, None, 2, ""), ("dst_yards_allowed", None, 99, 5, "")])
    assert score_row(row(passing_yards=10_000), r, 2) == 2
    assert score_row(row(passing_yards=399), r, 2) == 0
    assert score_row(row(dst_yards_allowed=-50), r, 2) == 5
    assert score_row(row(dst_yards_allowed=100), r, 2) == 0


def test_overlapping_bands_stack_and_disjoint_do_not():
    r = rules(bands=[("rushing_yards", 100, None, 1, ""), ("rushing_yards", 150, None, 2, ""),
                     ("rushing_yards", 300, 399, 10, "")])
    assert score_row(row(rushing_yards=160), r, 2) == 3


def test_null_never_satisfies_a_band_even_when_open():
    r = rules(bands=[("dst_points_allowed", None, 6, 4, ""), ("dst_points_allowed", None, None, 1, "")])
    assert score_row(row(dst_points_allowed=None), r, 2) == 0
    assert score_row(row(), r, 2) == 0                 # metric absent from the row
    assert score_row(row(dst_points_allowed=0), r, 2) == 5   # a real zero does


# ---- linear part -----------------------------------------------------------------------------

def test_null_counts_as_zero_in_the_linear_part():
    r = rules(weights=[("passing_yards", 0.04, ""), ("passing_tds", 4, "")])
    assert score_row(row(passing_yards=None, passing_tds=2), r, 2) == 8
    assert score_row(row(passing_tds=1), r, 2) == 4


def test_linear_sum():
    r = rules(weights=[("passing_yards", 0.04, ""), ("passing_tds", 4, ""), ("passing_interceptions", -2, "")])
    assert score_row(row(passing_yards=462, passing_tds=5, passing_interceptions=3), r, 2) == 32.48


# ---- rounding --------------------------------------------------------------------------------

@pytest.mark.parametrize("x,decimals,expected", [
    (2.345, 2, 2.35), (-2.345, 2, -2.35), (0.125, 2, 0.13), (-0.125, 2, -0.13),
    (0.5, 0, 1.0), (-0.5, 0, -1.0), (1.5, 0, 2.0), (2.5, 0, 3.0), (-2.5, 0, -3.0),
    (2.344, 2, 2.34), (-2.344, 2, -2.34), (1.0005, 3, 1.001), (7.0, 2, 7.0),
])
def test_round_half_away_from_zero(x, decimals, expected):
    assert round_half_away(x, decimals) == expected


def test_score_row_rounds_the_total():
    r = rules(weights=[("rushing_yards", 0.1, ""), ("fumbles_lost_total", -2, "")])
    # 0.1 * 5 - 2 = -1.5 -> -2 at 0 decimals (half away from zero, not banker's rounding)
    assert score_row(row(rushing_yards=5, fumbles_lost_total=1), r, 0) == -2
    assert score_row(row(rushing_yards=25), r, 0) == 3        # 2.5 -> 3


# ---- the published rules: a blocked field goal (ESPN counts it as a miss) ---------------------

def test_blocked_field_goal_costs_one_point_in_espn_league_only():
    from pathlib import Path
    from nflpipe.config import load_config
    from nflpipe.scoring import build_rules
    config = load_config(Path(__file__).resolve().parents[2] / "02-config")
    assert config.problems == []
    by_name = {r.name: r for r in build_rules(config)}
    kicker = row("K", "SPEC", fg_blocked=1)
    two_blocks = row("K", "SPEC", fg_blocked=2)
    assert score_row(kicker, by_name["ESPN_League"], config.round_decimals) == -1
    assert score_row(two_blocks, by_name["ESPN_League"], config.round_decimals) == -2
    for name, league in by_name.items():
        if name != "ESPN_League":
            assert score_row(kicker, league, config.round_decimals) == 0, name
    # the weight is gated to kickers: a non-kicker with the same column scores nothing
    assert score_row(row("WR", "WR", fg_blocked=1), by_name["ESPN_League"], config.round_decimals) == 0
