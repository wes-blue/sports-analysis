"""``run`` end to end on the miniature upstream: exit codes and what reaches 04-data."""

import gzip

import miniverse
from miniverse import C, P, QB1, read_table, rewrite, snapshot
from nflpipe import run as run_module


def gate_results(folder):
    return {r["gate_id"]: r for r in read_table(folder / "checks" / "gates.csv")}


def test_first_run_publishes_every_contract_file(project):
    assert project.run() == 0
    files = set(snapshot(project.data))
    for season in (P, C):
        for kind, prefix in (("player_week", "player_week_"), ("scored", "scored_"), ("long_td", "long_td_")):
            assert f"{kind}/{prefix}{season}.csv" in files
    for name in ("seasons.csv", "sources.csv", "manifest.csv", "status.csv", "run_log.csv", "dictionary.csv",
                 "config/leagues.csv", "checks/gates.csv", "checks/reconciliation.csv", "checks/row_counts.csv",
                 "checks/golden.csv", "checks/espn_reconciliation.csv", "checks/restatements.csv"):
        assert name in files, name
    gates = gate_results(project.data)
    assert len(gates) == 13 and all(g["result"] == "PASS" for g in gates.values()), gates
    status = {r["key"]: r["value"] for r in read_table(project.data / "status.csv")}
    assert status["outcome"] == "PUBLISH" and status["gates_pass"] == "13" and status["gates_fail"] == "0"
    assert project.check() == 0


def test_second_run_skips_and_leaves_data_byte_identical(mini):
    before = snapshot(mini.data)
    assert mini.run() == 3
    assert snapshot(mini.data) == before


def test_dry_run_changes_nothing(project):
    assert project.run("--dry-run") == 0
    assert snapshot(project.data) == {}
    assert (project.report / "checks" / "gates.csv").is_file()


def test_hold_leaves_data_untouched_and_reports_the_gate(mini):
    rewrite(mini.fixtures / "golden_sample.csv",
            lambda h, rows: [r[:-1] + ["99"] if r[3] == QB1 else r for r in rows])
    before = snapshot(mini.data)
    assert mini.run() == 4
    assert snapshot(mini.data) == before
    assert gate_results(mini.report)["G-GOLDEN"]["result"] == "FAIL"
    summary = {r["key"]: r["value"] for r in read_table(mini.report / "run_summary.csv")}
    assert summary["outcome"] == "HOLD" and "G-GOLDEN" in summary["detail"]


def test_broken_config_holds_before_any_download(project, upstream):
    path = project.config / "pipeline_config.csv"
    path.write_text(path.read_text().replace("RoundDecimals,2", "RoundDecimals,9"))
    assert project.run() == 4
    assert upstream.calls == 0
    assert not project.data.exists()
    assert gate_results(project.report)["G-CONFIG"]["result"] == "FAIL"


def test_no_upstream_is_an_error(project, upstream):
    upstream.files.clear()
    assert project.run() == 1
    assert not project.data.exists()


def test_only_changed_season_is_rewritten(mini, upstream):
    rows = miniverse.player_rows(C)
    rows[3]["passing_yards"] = 101                       # week 2 (not an ESPN fixture row)
    upstream.put(f"stats_player/stats_player_week_{C}.csv", miniverse.player_file(C, rows), f"{C}-02-01T00:00:00Z")
    before = snapshot(mini.data)
    assert mini.run("--seasons", "current") == 0
    after = snapshot(mini.data)
    assert after[f"player_week/player_week_{C}.csv"] != before[f"player_week/player_week_{C}.csv"]
    for kind, prefix in (("player_week", "player_week_"), ("scored", "scored_"), ("long_td", "long_td_")):
        assert after[f"{kind}/{prefix}{P}.csv"] == before[f"{kind}/{prefix}{P}.csv"]   # bytes and mtime
    assert after[f"long_td/long_td_{C}.csv"] == before[f"long_td/long_td_{C}.csv"]
    log = read_table(mini.data / "run_log.csv")
    assert len(log) == 2 and log[-1]["seasons_refreshed"] == str(C)
    assert mini.check() == 0


def test_current_picks_up_a_drifted_finished_season_and_logs_restatements(mini, upstream):
    rows = miniverse.player_rows(P)
    rows[6]["rushing_yards"] = 31                          # nflverse back-corrects RB1's Super Bowl
    upstream.put(f"stats_player/stats_player_week_{P}.csv", miniverse.player_file(P, rows), f"{C}-03-01T00:00:00Z")
    assert mini.run("--seasons", "current") == 0
    restated = read_table(mini.data / "checks" / "restatements.csv")
    changed = {(r["week"], r["player_id"], r["column"]): (r["old_value"], r["new_value"]) for r in restated}
    assert changed == {("2", miniverse.RB1, "rushing_yards"): ("30", "31"),
                       ("2", miniverse.RB1, "fantasy_points"): ("3", "3.1"),
                       ("2", miniverse.RB1, "fantasy_points_ppr"): ("3", "3.1")}
    gate = gate_results(mini.data)["G-RESTATE"]
    assert gate["result"] == "PASS" and "change(s) upstream" in gate["detail"]
    assert "G-RESTATE" in read_table(mini.data / "run_log.csv")[-1]["notes"]
    # The next run finds nothing new: restatements.csv keeps its rows and the run skips.
    assert mini.run() == 3


def test_a_season_that_lost_rows_is_held(mini, upstream):
    rows = [r for r in miniverse.player_rows(P) if r["pid"] != miniverse.K1]
    upstream.put(f"stats_player/stats_player_week_{P}.csv", miniverse.player_file(P, rows), f"{C}-03-01T00:00:00Z")
    before = snapshot(mini.data)
    assert mini.run() == 4
    assert snapshot(mini.data) == before
    gates = gate_results(mini.report)
    assert gates["G-SHRINK"]["result"] == "FAIL"
    assert gates["G-RESTATE"]["result"] == "WARN"           # a row disappeared from a finished season


def test_points_allowed_fill_in_when_the_game_finishes(mini, upstream):
    games = miniverse.games_file().replace(f"{C},REG,2,KC,,OAK,".encode(), f"{C},REG,2,KC,21,OAK,".encode())
    games = games.replace(b",OAK,\n", b",OAK,14\n")
    upstream.put("schedules/games.csv", games, f"{C}-04-01T00:00:00Z")
    # nflverse publishes the game's plays with its score; ESPN points allowed needs them (D-038)
    pbp = gzip.decompress(miniverse.pbp_file(C)) + f"{C}_02_KC_LV,{C},2,REG,0,0,0,,,,3,run,KC,LV\n".encode()
    upstream.put(f"pbp/play_by_play_{C}.csv.gz", gzip.compress(pbp, mtime=0), f"{C}-04-01T00:00:00Z")
    assert mini.run("--seasons", "current") == 0
    dst = {r["player_id"]: r for r in read_table(mini.data / "player_week" / f"player_week_{C}.csv")
           if r["week"] == "2" and r["player_id"].startswith("DST_")}
    assert dst["DST_KC"]["dst_points_allowed"] == "14" and dst["DST_LV"]["dst_points_allowed"] == "21"
    assert dst["DST_KC"]["dst_points_allowed_excl_def"] == "14" and dst["DST_LV"]["dst_points_allowed_excl_def"] == "21"


def test_unexpected_error_exits_1_and_touches_nothing(mini, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(run_module, "build_season", boom)
    before = snapshot(mini.data)
    assert mini.run() == 1
    assert snapshot(mini.data) == before
