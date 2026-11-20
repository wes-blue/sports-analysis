"""Every gate of CONTRACTS.md section 6, passing and failing, on a copy of a mini publish."""

import shutil

import pytest

import miniverse
from miniverse import C, P, QB1, WR1, read_table, rewrite
from nflpipe import gates
from nflpipe.config import load_config
from nflpipe.derive import DERIVED_SOURCES
from nflpipe.ingest import read_games, read_header


@pytest.fixture
def stage(mini, tmp_path):
    """A candidate 04-data identical to what is published (the previous run)."""
    target = tmp_path / "stage"
    shutil.copytree(mini.data, target)
    return target


def context(mini, stage, **overrides):
    known = set(read_header(mini.cache / "stats_player" / f"stats_player_week_{C}.csv")) | set(DERIVED_SOURCES)
    values = dict(
        config=load_config(mini.config), stage_dir=stage, data_dir=mini.data, fixtures_dir=mini.fixtures,
        seasons=[P, C], refreshed=[P, C], season_status={P: "complete", C: "in_progress"},
        previous_status={P: "complete", C: "in_progress"}, known_metrics=known, checked_utc="2026-01-01T00:00:00Z",
        games=read_games(mini.cache / "schedules" / "games.csv"),
        team_files={s: mini.cache / "stats_team" / f"stats_team_week_{s}.csv" for s in (P, C)})
    values.update(overrides)
    return gates.GateContext(**values)


def result(mini, stage, gate_id, **overrides):
    results, files = gates.evaluate(context(mini, stage, **overrides), [gate_id])
    assert len(results) == 1
    r = results[0]
    assert "\n" not in r.detail and r.detail
    return r, files


def pw(stage, season=P):
    return stage / "player_week" / f"player_week_{season}.csv"


def scored(stage, season=P):
    return stage / "scored" / f"scored_{season}.csv"


def col(header, name):
    return header.index(name)


# ---- all gates on an untouched candidate -------------------------------------------------------

def test_every_gate_passes_on_a_good_candidate(mini, stage):
    results = gates.run_gates(context(mini, stage))
    assert [r.gate_id for r in results] == gates.ALL_GATES
    assert {r.result for r in results} == {"PASS"}, [(r.gate_id, r.detail) for r in results]
    for name in ("gates.csv", "reconciliation.csv", "row_counts.csv", "golden.csv", "espn_reconciliation.csv",
                 "restatements.csv"):
        assert (stage / "checks" / name).is_file()
    assert {r["gate_id"]: r["severity"] for r in read_table(stage / "checks" / "gates.csv")}["G-ROWS"] == "advisory"


# ---- G-CONFIG ----------------------------------------------------------------------------------

def test_config_fails_on_unknown_metric(mini, stage):
    path = mini.config / "scoring_weights.csv"
    path.write_text(path.read_text() + "made_up_metric,X,,1,1,1,,\n")
    r, _ = result(mini, stage, "G-CONFIG")
    assert r.result == "FAIL" and "made_up_metric" in r.detail


def test_config_fails_when_weight_columns_are_out_of_order(mini, stage):
    path = mini.config / "leagues.csv"
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[2], lines[1], lines[3]]) + "\n")
    r, _ = result(mini, stage, "G-CONFIG")
    assert r.result == "FAIL" and "same order" in r.detail


# ---- G-GRAIN -----------------------------------------------------------------------------------

def test_grain_fails_on_a_duplicated_row(mini, stage):
    rewrite(pw(stage), lambda h, rows: rows[:1] + rows)
    r, _ = result(mini, stage, "G-GRAIN")
    assert r.result == "FAIL" and f"{P}/1/REG/{QB1}" in r.detail


def test_grain_fails_when_a_season_file_is_missing(mini, stage):
    pw(stage, C).unlink()
    r, _ = result(mini, stage, "G-GRAIN")
    assert r.result == "FAIL" and "could not run" in r.detail and "missing" in r.detail


# ---- G-RECON -----------------------------------------------------------------------------------

def test_recon_fails_when_a_control_league_drifts(mini, stage):
    rewrite(scored(stage), lambda h, rows: [r[:col(h, "FF_Standard")] + [str(float(r[col(h, "FF_Standard")]) + 1)]
                                            + r[col(h, "FF_Standard") + 1:] if r[3] == QB1 else r for r in rows])
    r, files = result(mini, stage, "G-RECON")
    assert r.result == "FAIL" and "Standard vs fantasy_points: 8 of 10" in r.detail
    total = [row for row in files["reconciliation.csv"] if row[0] == "Standard" and row[2] == "ALL"][0]
    assert total[3:6] == [10, 8, 1.0]


def test_recon_within_tolerance_passes(mini, stage):
    rewrite(scored(stage), lambda h, rows: [r[:col(h, "FF_PPR")] + [str(float(r[col(h, "FF_PPR")]) + 0.004)]
                                            + r[col(h, "FF_PPR") + 1:] if r[3] == WR1 else r for r in rows])
    r, _ = result(mini, stage, "G-RECON")
    assert r.result == "PASS"


# ---- G-GOLDEN ----------------------------------------------------------------------------------

def test_golden_fails_on_a_changed_value(mini, stage):
    rewrite(mini.fixtures / "golden_sample.csv", lambda h, rows: [r[:-1] + ["24.41"] if r[3] == QB1 else r
                                                                  for r in rows])
    r, files = result(mini, stage, "G-GOLDEN")
    assert r.result == "FAIL" and "expected 24.41 got 24.4" in r.detail
    assert [row[9] for row in files["golden.csv"]].count("MISMATCH") == 1


def test_golden_fails_when_a_row_is_missing_from_the_data(mini, stage):
    rewrite(scored(stage), lambda h, rows: [r for r in rows if r[3] != QB1 or r[1] != "1"])
    r, _ = result(mini, stage, "G-GOLDEN")
    assert r.result == "FAIL" and "got nothing" in r.detail


def test_golden_fails_when_the_fixture_is_missing(mini, stage):
    (mini.fixtures / "golden_sample.csv").unlink()
    r, files = result(mini, stage, "G-GOLDEN")
    assert r.result == "FAIL" and "golden_sample.csv is missing" in r.detail
    assert files["golden.csv"] == []


def test_golden_outside_the_window_is_visible_not_silent(mini, stage):
    r, files = result(mini, stage, "G-GOLDEN", seasons=[C])
    assert r.result == "WARN" and "not applicable" in r.detail
    assert {row[9] for row in files["golden.csv"]} == {"NOT_APPLICABLE"}


# ---- G-ESPN ------------------------------------------------------------------------------------

def set_espn(mini, player_id, points):
    rewrite(mini.fixtures / "espn_actuals.csv",
            lambda h, rows: [r[:8] + [points] + r[9:] if r[3] == player_id else r for r in rows])


def test_espn_player_must_be_exact(mini, stage):
    set_espn(mini, QB1, "14.01")
    r, files = result(mini, stage, "G-ESPN")
    assert r.result == "FAIL" and "Q. Back ESPN 14.01 ours 14" in r.detail
    assert files["espn_reconciliation.csv"][0][10] == "MISMATCH"


def test_espn_dst_within_one_point_passes_and_two_fails(mini, stage):
    r, files = result(mini, stage, "G-ESPN")
    assert r.result == "PASS" and "2 exact, 1 within tolerance" in r.detail
    assert [row[10] for row in files["espn_reconciliation.csv"]] == ["MATCH", "WITHIN_TOLERANCE", "MATCH"]
    set_espn(mini, "DST_KC", "31")
    r, _ = result(mini, stage, "G-ESPN")
    assert r.result == "FAIL"


def test_espn_missing_row_fails_unless_no_row_is_expected(mini, stage):
    rewrite(scored(stage, C), lambda h, rows: [r for r in rows if r[3] != QB1])
    r, _ = result(mini, stage, "G-ESPN")
    assert r.result == "FAIL" and "ours nothing" in r.detail


def test_espn_not_applicable_when_week_not_published_or_outside_window(mini, stage):
    rewrite(mini.fixtures / "espn_actuals.csv", lambda h, rows: [r[:1] + ["9"] + r[2:] for r in rows])
    r, files = result(mini, stage, "G-ESPN")
    assert r.result == "WARN" and "not published yet" in r.detail
    assert {row[10] for row in files["espn_reconciliation.csv"]} == {"NOT_APPLICABLE"}
    r, _ = result(mini, stage, "G-ESPN", seasons=[P])
    assert r.result == "WARN" and "outside the window" in r.detail


def test_espn_fails_when_fixture_unreadable(mini, stage):
    (mini.fixtures / "espn_actuals.csv").write_text("player,points\nx,1\n")
    r, _ = result(mini, stage, "G-ESPN")
    assert r.result == "FAIL" and "lacks column" in r.detail


# ---- G-DST -------------------------------------------------------------------------------------

def set_pa(stage, season, team, week, value):
    def change(h, rows):
        i = col(h, "dst_points_allowed")
        return [r[:i] + [value] + r[i + 1:] if r[3] == f"DST_{team}" and r[1] == str(week) else r for r in rows]
    rewrite(pw(stage, season), change)


def test_dst_fails_when_a_dst_row_is_deleted(mini, stage):
    rewrite(pw(stage), lambda h, rows: [r for r in rows if not (r[3] == "DST_LV" and r[1] == "1")])
    r, _ = result(mini, stage, "G-DST")
    assert r.result == "FAIL" and "have no D/ST row" in r.detail and "LV" in r.detail


def test_dst_fails_when_unfinished_game_has_zero_points_allowed(mini, stage):
    set_pa(stage, C, "KC", 2, "0")
    r, _ = result(mini, stage, "G-DST")
    assert r.result == "FAIL" and "unfinished games have points allowed" in r.detail


def test_dst_fails_when_finished_game_has_blank_or_wrong_points_allowed(mini, stage):
    set_pa(stage, P, "KC", 1, "")
    r, _ = result(mini, stage, "G-DST")
    assert r.result == "FAIL" and "blank points allowed" in r.detail
    set_pa(stage, P, "KC", 1, "18")
    r, _ = result(mini, stage, "G-DST")
    assert r.result == "FAIL" and "differ from the final score" in r.detail


def test_dst_structural_check_without_upstream(mini, stage):
    r, _ = result(mini, stage, "G-DST", games=None, team_files={})
    assert r.result == "PASS" and "structural" in r.detail
    rewrite(pw(stage), lambda h, rows: [r for r in rows if not (r[3] == "DST_LV" and r[1] == "1")])
    r, _ = result(mini, stage, "G-DST", games=None, team_files={})
    assert r.result == "FAIL" and "opponent row" in r.detail


# ---- G-SHRINK ----------------------------------------------------------------------------------

def test_shrink_fails_when_a_season_loses_rows(mini, stage):
    rewrite(pw(stage), lambda h, rows: [r for r in rows if r[3] != miniverse.K1])
    r, _ = result(mini, stage, "G-SHRINK")
    assert r.result == "FAIL" and f"{P} REG 6 -> 5 rows" in r.detail


def test_shrink_ignores_seasons_not_rebuilt_and_growth(mini, stage):
    rewrite(pw(stage), lambda h, rows: [r for r in rows if r[3] != miniverse.K1])
    assert result(mini, stage, "G-SHRINK", refreshed=[C])[0].result == "PASS"
    rewrite(pw(stage, C), lambda h, rows: rows + [[str(C), "3", "REG", "00-9"] + r[4:] for r in rows[:1]])
    assert result(mini, stage, "G-SHRINK", refreshed=[C])[0].result == "PASS"


# ---- G-ROWS ------------------------------------------------------------------------------------

def test_rows_warns_when_a_completed_season_differs(mini, stage):
    rewrite(mini.fixtures / "row_count_baseline.csv",
            lambda h, rows: [r[:4] + ["5"] + r[5:] if r[1] == "REG" else r for r in rows])
    r, files = result(mini, stage, "G-ROWS")
    assert r.result == "WARN" and r.severity == "advisory" and f"{P} REG 4 vs 5" in r.detail
    assert [row[5] for row in files["row_counts.csv"]] == ["MATCH", "DIFFERENT", "IN_PROGRESS"]


def test_rows_in_progress_season_is_never_compared(mini, stage):
    r, files = result(mini, stage, "G-ROWS", season_status={P: "in_progress", C: "in_progress"})
    assert r.result == "PASS"
    assert {row[5] for row in files["row_counts.csv"]} == {"IN_PROGRESS"}


def test_rows_fails_when_baseline_missing(mini, stage):
    (mini.fixtures / "row_count_baseline.csv").unlink()
    r, _ = result(mini, stage, "G-ROWS")
    assert r.result == "FAIL" and "could not run" in r.detail


# ---- G-LONGTD ----------------------------------------------------------------------------------

def test_longtd_warns_when_totals_differ(mini, stage):
    rewrite(mini.fixtures / "long_td_baseline.csv", lambda h, rows: [r[:2] + ["3"] + r[3:] for r in rows])
    r, _ = result(mini, stage, "G-LONGTD")
    assert r.result == "WARN" and "pass_td_40plus 2 vs 3" in r.detail


def test_longtd_passes_and_skips_in_progress(mini, stage):
    r, _ = result(mini, stage, "G-LONGTD")
    assert r.result == "PASS" and "1 completed season" in r.detail


# ---- G-RESTATE ---------------------------------------------------------------------------------

def set_value(path, player_id, week, column, value):
    def change(h, rows):
        i = col(h, column)
        return [r[:i] + [value] + r[i + 1:] if r[3] == player_id and r[1] == str(week) else r for r in rows]
    rewrite(path, change)


def test_restate_logs_changed_cells_added_and_removed_rows(mini, stage):
    set_value(pw(stage), WR1, 1, "receiving_yards", "131")
    rewrite(pw(stage), lambda h, rows: [r for r in rows if r[3] != miniverse.K1]
            + [[str(P), "2", "POST", "00-0000077"] + rows[0][4:]])
    r, files = result(mini, stage, "G-RESTATE")
    rows = files["restatements.csv"]
    found = {(row[4], row[5]): (row[6], row[7]) for row in rows}
    assert found[(WR1, "receiving_yards")] == ("130", "131")
    assert found[(miniverse.K1, "(row)")] == ("present", "absent")
    assert found[("00-0000077", "(row)")] == ("absent", "present")
    assert all(row[0] == "2026-01-01T00:00:00Z" for row in rows)
    assert r.result == "WARN" and "1 row(s) removed" in r.detail


def test_restate_small_correction_is_visible_but_passes(mini, stage):
    set_value(pw(stage), WR1, 1, "receiving_yards", "131")
    r, files = result(mini, stage, "G-RESTATE")
    assert r.result == "PASS" and "1 change(s) upstream" in r.detail and len(files["restatements.csv"]) == 1


def test_restate_ignores_in_progress_and_unrefreshed_seasons(mini, stage):
    set_value(pw(stage), WR1, 1, "receiving_yards", "131")
    set_value(pw(stage, C), WR1, 1, "receiving_yards", "61")
    r, files = result(mini, stage, "G-RESTATE", refreshed=[C])
    assert r.result == "PASS" and "no previously complete season" in r.detail and files["restatements.csv"] == []


def test_restate_cap_keeps_true_count(mini, stage, monkeypatch):
    monkeypatch.setattr(gates, "RESTATE_CAP", 1)
    set_value(pw(stage), WR1, 1, "receiving_yards", "131")
    set_value(pw(stage), QB1, 1, "passing_yards", "311")
    r, files = result(mini, stage, "G-RESTATE")
    assert r.result == "WARN" and r.detail.startswith("2 change(s)") and "capped at 1" in r.detail
    assert len(files["restatements.csv"]) == 1


def test_restatements_file_keeps_earlier_detections(mini, stage):
    earlier = ["2025-12-01T00:00:00Z", str(P), "1", "REG", QB1, "passing_yards", "309", "310"]
    old_season = ["2025-12-01T00:00:00Z", str(P - 5), "1", "REG", QB1, "passing_yards", "1", "2"]
    (mini.data / "checks" / "restatements.csv").write_bytes(miniverse.csv_text(gates.RESTATE_HEADER,
                                                                               [earlier, old_season]))
    set_value(pw(stage), WR1, 1, "receiving_yards", "131")
    gates.run_gates(context(mini, stage))
    rows = read_table(stage / "checks" / "restatements.csv")
    assert [r["old_value"] for r in rows] == ["309", "130"]           # season out of the window dropped


# ---- G-OVERLAP ---------------------------------------------------------------------------------

def test_overlap_warns_on_total_and_components(mini, stage):
    path = mini.config / "scoring_weights.csv"
    path.write_text(path.read_text() + "fg_made_20_29,Kicking,,0,0,1,,K\n")
    r, _ = result(mini, stage, "G-OVERLAP")
    assert r.result == "WARN" and "Custom scores both fg_made and fg_made_20_29" in r.detail


def test_overlap_warns_on_unknown_applies_to_code(mini, stage):
    path = mini.config / "bonus_rules.csv"
    path.write_text(path.read_text() + "Custom,passing_yards,500,,3,QBX,\n")
    r, _ = result(mini, stage, "G-OVERLAP")
    assert r.result == "WARN" and "'QBX'" in r.detail and r.severity == "advisory"


# ---- G-INDEX -----------------------------------------------------------------------------------

def test_index_fails_when_seasons_csv_count_is_wrong(mini, stage):
    rewrite(stage / "seasons.csv", lambda h, rows: [r[:2] + [str(int(r[2]) + 1)] + r[3:] if r[1] == "POST" else r
                                                    for r in rows])
    r, _ = result(mini, stage, "G-INDEX")
    assert r.result == "FAIL" and "seasons.csv says" in r.detail


def test_index_fails_when_scored_order_differs(mini, stage):
    rewrite(scored(stage), lambda h, rows: [rows[1], rows[0]] + rows[2:])
    r, _ = result(mini, stage, "G-INDEX")
    assert r.result == "FAIL" and "first difference at data row 1" in r.detail


def test_index_fails_on_an_unknown_season_type(mini, stage):
    rewrite(pw(stage), lambda h, rows: [r[:2] + ["PRE"] + r[3:] if r[2] == "POST" else r for r in rows])
    r, _ = result(mini, stage, "G-INDEX")
    assert r.result == "FAIL" and "PRE" in r.detail


def test_index_fails_on_unsorted_rows(mini, stage):
    for path in (pw(stage), scored(stage)):
        rewrite(path, lambda h, rows: rows[::-1])
    r, _ = result(mini, stage, "G-INDEX")
    assert r.result == "FAIL" and "out of order" in r.detail


def test_index_manifest_part(mini, stage):
    r, _ = result(mini, stage, "G-INDEX", verify_manifest=True)
    assert r.result == "PASS" and "manifest hashes verified" in r.detail
    rewrite(stage / "long_td" / f"long_td_{P}.csv", lambda h, rows: [r[:4] + ["3"] + r[5:] for r in rows])
    r, _ = result(mini, stage, "G-INDEX", verify_manifest=True)
    assert r.result == "FAIL" and "changed after publishing" in r.detail


def test_blocking_failures_ignores_advisory():
    results = [gates.GateResult("G-ROWS", "x", "advisory", "WARN", "d"),
               gates.GateResult("G-ESPN", "x", "blocking", "WARN", "d"),
               gates.GateResult("G-GRAIN", "x", "blocking", "FAIL", "d")]
    assert [r.gate_id for r in gates.blocking_failures(results)] == ["G-GRAIN"]


def test_index_in_a_run_rejects_a_hand_edited_kept_season(mini, stage):
    r, _ = result(mini, stage, "G-INDEX", refreshed=[C])
    assert r.result == "PASS" and "3 season files kept" in r.detail
    for folder in (stage, mini.data):                    # edited in 04-data, then copied into the stage
        rewrite(scored(folder), lambda h, rows: [r[:-1] + ["99"] if r[3] == QB1 else r for r in rows])
    r, _ = result(mini, stage, "G-INDEX", refreshed=[C])
    assert r.result == "FAIL" and f"scored/scored_{P}.csv was edited after it was published" in r.detail
