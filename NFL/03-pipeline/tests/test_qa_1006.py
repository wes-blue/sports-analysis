"""Regression tests for the QA findings on 1.006 (the independent QA review of version 1.006), one block per finding.

Each test fails on the 1.006 code (pipeline 1.0.0) and passes from pipeline 1.1.0.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import miniverse
from miniverse import C, P, QB1, read_table, rewrite, snapshot
from nflpipe import gates, publish
from nflpipe import run as run_module
from nflpipe.config import ConfigError, load_config, normalize_csv, resolve_window
from nflpipe.publish import PublishError, Stage, sync
from nflpipe.scoring import LeagueRules, round_half_away, score_row


def gate_results(folder):
    return {r["gate_id"]: r for r in read_table(folder / "checks" / "gates.csv")}


def set_weight(config_dir, metric, league, value):
    def change(header, rows):
        i, m = header.index(league), header.index("Metric")
        for r in rows:
            if r[m] == metric:
                r[i] = value
        return rows
    rewrite(config_dir / "scoring_weights.csv", change)


def set_setting(config_dir, name, value):
    def change(header, rows):
        for r in rows:
            if r[0] == name:
                r[1] = value
        return rows
    rewrite(config_dir / "pipeline_config.csv", change)


def rename_league(config_dir, old, new):
    for name, column in (("leagues.csv", None), ("bonus_rules.csv", None)):
        path = config_dir / name
        path.write_text("\n".join(
            ",".join(new if cell == old else cell for cell in line.split(","))
            for line in path.read_text().splitlines()) + "\n")
    path = config_dir / "scoring_weights.csv"
    lines = path.read_text().splitlines()
    lines[0] = lines[0].replace(f",{old},", f",{new},")
    path.write_text("\n".join(lines) + "\n")


# ---- C-01: a scoring change must not hold every publish -------------------------------------------

NOT_APPLICABLE = "not applicable: rules for Custom changed since the expected values were made"


def test_c01_weight_change_publishes_with_a_plain_warning(mini):
    set_weight(mini.config, "receptions", "Custom", "1")          # QA edit 1 (0.5 -> 1)
    assert mini.run() == 0                                          # was HOLD, exit 4
    g = gate_results(mini.data)
    assert g["G-GOLDEN"]["result"] == "WARN" and NOT_APPLICABLE in g["G-GOLDEN"]["detail"]
    assert "nothing is wrong" in g["G-GOLDEN"]["detail"]
    assert "Standard, PPR were checked: all 10 golden values reproduced" in g["G-GOLDEN"]["detail"]
    assert g["G-ESPN"]["result"] == "WARN" and NOT_APPLICABLE in g["G-ESPN"]["detail"]
    golden = read_table(mini.data / "checks" / "golden.csv")
    assert {r["status"] for r in golden if r["league"] == "Custom"} == {"NOT_APPLICABLE"}
    assert {r["status"] for r in golden if r["league"] != "Custom"} == {"MATCH"}
    assert mini.check() == 0


def test_c01_extra_band_publishes(mini):
    path = mini.config / "bonus_rules.csv"                          # QA edit 2: one extra band
    path.write_text(path.read_text() + "Custom,receiving_yards,100,,3,,\n")
    assert mini.run() == 0
    assert NOT_APPLICABLE in gate_results(mini.data)["G-GOLDEN"]["detail"]


def test_c01_round_decimals_change_publishes(mini):
    set_setting(mini.config, "RoundDecimals", "0")                  # QA edit 3
    assert mini.run() == 0
    detail = gate_results(mini.data)["G-GOLDEN"]["detail"]
    assert "rules for Standard, PPR, Custom changed" in detail and "RoundDecimals 2 -> 0" in detail
    assert gate_results(mini.data)["G-GOLDEN"]["result"] == "WARN"


def test_c01_metric_typo_still_holds(mini):
    before = snapshot(mini.data)
    set_weight(mini.config, "receptions", "Custom", "1")
    path = mini.config / "scoring_weights.csv"                      # QA control edit: a metric typo
    path.write_text(path.read_text().replace("receiving_yards,", "recieving_yards,"))
    assert mini.run() == 4
    assert snapshot(mini.data) == before


def test_c01_unchanged_league_still_holds_on_a_mismatch(mini):
    before = snapshot(mini.data)
    set_weight(mini.config, "receptions", "Custom", "1")            # Custom changed: not applicable ...
    golden = mini.fixtures / "golden_sample.csv"                    # ... but Standard is unchanged and wrong
    golden.write_text(golden.read_text().replace(f"{QB1},Q. Back,20.4,", f"{QB1},Q. Back,20.5,"))
    assert mini.run() == 4
    assert snapshot(mini.data) == before
    detail = gate_results(mini.report)["G-GOLDEN"]["detail"]
    assert "FF_" not in detail and "Standard expected 20.5" in detail and "Also not applicable" in detail


def test_c01_renamed_league_with_same_rules_is_checked_under_its_new_name(mini):
    rename_league(mini.config, "Custom", "Mine")
    assert mini.run() == 0
    g = gate_results(mini.data)
    assert g["G-GOLDEN"]["result"] == "PASS" and "Custom renamed to Mine" in g["G-GOLDEN"]["detail"]
    assert "all 15 golden values reproduced" in g["G-GOLDEN"]["detail"]
    assert g["G-ESPN"]["result"] == "PASS"


def test_c01_renamed_league_with_new_rules_is_reported(mini):
    rename_league(mini.config, "Custom", "Mine")
    set_weight(mini.config, "receptions", "Mine", "1")
    assert mini.run() == 0
    detail = gate_results(mini.data)["G-GOLDEN"]["detail"]
    assert "Custom is no longer in leagues.csv" in detail and "no expected values exist for Mine" in detail


def test_c01_inactive_league_is_reported_not_silent(mini):
    path = mini.config / "leagues.csv"
    path.write_text(path.read_text().replace("Custom,Custom league,Yes", "Custom,Custom league,No"))
    assert mini.run() == 0
    g = gate_results(mini.data)["G-GOLDEN"]
    assert g["result"] == "WARN" and "Custom is set to Active = No" in g["detail"]


def test_c01_new_league_is_named(mini):
    for name, add in (("leagues.csv", "Extra,New,Yes,,\n"),):
        (mini.config / name).write_text((mini.config / name).read_text() + add)
    path = mini.config / "scoring_weights.csv"
    lines = path.read_text().splitlines()
    lines = [lines[0].replace(",Custom,", ",Custom,Extra,")] + [
        ",".join(parts[:6] + [parts[5]] + parts[6:]) for parts in (ln.split(",") for ln in lines[1:])]
    path.write_text("\n".join(lines) + "\n")
    assert mini.run() == 0
    g = gate_results(mini.data)["G-GOLDEN"]
    assert g["result"] == "PASS" and "no expected values exist for Extra (new league)" in g["detail"]


def test_c01_missing_fixture_contracts_fails_loudly(mini):
    (mini.fixtures / "fixture_contracts.csv").unlink()
    assert mini.run("--force") == 4
    assert "fixture_contracts.csv is missing" in gate_results(mini.report)["G-GOLDEN"]["detail"]


def test_c01_fixture_contracts_tool_matches_the_gate_rows(tmp_path):
    import subprocess
    import sys
    project = miniverse.Project(tmp_path / "p")
    target = project.fixtures / "fixture_contracts.csv"
    target.unlink()
    tool = Path(__file__).resolve().parents[1] / "tools" / "write_fixture_contracts.py"
    done = subprocess.run([sys.executable, str(tool), "--config-dir", str(project.config),
                           "--fixtures-dir", str(project.fixtures)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert target.read_bytes() == miniverse.fixture_contracts_bytes()


def test_c01_shipped_fixture_contracts_cover_every_fixture_league():
    fixtures = Path(__file__).resolve().parents[2] / "06-qa" / "fixtures"
    recorded = read_table(fixtures / "fixture_contracts.csv")
    assert list(recorded[0]) == gates.FIXTURE_CONTRACTS_HEADER
    names = {r["league"] for r in recorded}
    golden = read_table(fixtures / "golden_sample.csv")
    assert {c[3:] for c in golden[0] if c.startswith("FF_")} <= names
    assert {r["league"] for r in read_table(fixtures / "espn_actuals.csv")} <= names
    assert all(len(r["rules_sha256"]) == 64 and r["round_decimals"].isdigit() for r in recorded)


# ---- M-02: a future EndSeason is clamped, not an error --------------------------------------------

def test_m02_future_end_season_publishes_and_names_unpublished_seasons(mini):
    set_setting(mini.config, "EndSeason", str(C + 4))
    assert mini.run() == 0                                          # was ERROR, exit 1
    g = gate_results(mini.data)["G-WINDOW"]
    assert g["result"] == "WARN" and g["severity"] == "advisory"
    assert f"EndSeason {C + 4} is after the newest season nflverse has published ({C})" in g["detail"]
    assert f"{C + 1}-{C + 4} not published yet" in g["detail"] and "Nothing is wrong" in g["detail"]
    status = {r["key"]: r["value"] for r in read_table(mini.data / "status.csv")}
    assert status["window_end"] == str(C)


def test_m02_rolling_start_stays_ten_seasons():
    config = load_config(miniverse.write_config(Path(os.environ.get("PYTEST_TMP", ".")) / ".tmp-m02"))
    config.settings.update(StartSeason="Latest-9", EndSeason="2030")
    assert resolve_window(config, 2026) == (2017, 2026)            # was (2017, 2030)
    config.settings.update(StartSeason="2030", EndSeason="2030")
    with pytest.raises(ConfigError, match="after the newest season nflverse has published"):
        resolve_window(config, 2026)
    config.settings.update(StartSeason="2020", EndSeason="2024")
    assert resolve_window(config, 2026) == (2020, 2024)


@pytest.fixture(autouse=True)
def _tmp_cwd_for_config(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTEST_TMP", str(tmp_path))


# ---- M-03: a failure while publishing leaves 04-data unchanged ----------------------------------

def changed_mini(mini):
    """Make the next run publish (a scoring change rewrites scored files, the index and the checks)."""
    set_weight(mini.config, "receptions", "Custom", "1")


def content(folder):
    return {k: v[0] for k, v in snapshot(folder).items()}


def test_m03_locked_file_stops_before_anything_changes(mini, monkeypatch, capsys):
    changed_mini(mini)
    before = content(mini.data)
    locked = mini.data / "scored" / f"scored_{C}.csv"
    real_open = open

    def fake_open(path, mode="r", *args, **kwargs):
        if Path(path) == locked and mode != "rb" and mode != "r":
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(publish, "open", fake_open, raising=False)
    assert mini.run() == 1
    err = capsys.readouterr().err
    assert str(locked) in err and "Close that file and run the same command again" in err
    assert content(mini.data) == before
    assert not list(mini.data.rglob("*.nflpipe-tmp"))


def test_m03_replace_failing_part_way_restores_everything(mini, monkeypatch, capsys):
    changed_mini(mini)
    before = content(mini.data)
    real_replace = os.replace
    calls = []

    def flaky_replace(src, dst, *args, **kwargs):
        calls.append(Path(dst).name)
        if len(calls) == 3:                                        # third file: as if Excel held it
            raise PermissionError(13, "being used by another process", str(dst))
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(publish.os, "replace", flaky_replace)
    assert mini.run() == 1
    assert content(mini.data) == before, "04-data must be exactly as before the failed publish"
    assert not list(mini.data.rglob("*.nflpipe-tmp"))
    assert not (mini.cache.parent / "publish-backup").exists()
    err = capsys.readouterr().err
    assert calls[2] in err and "Nothing in the data folder was changed" in err
    monkeypatch.setattr(publish.os, "replace", real_replace)
    assert mini.run() == 0 and mini.check() == 0                    # the next run publishes normally


def test_n4_failed_restore_does_not_claim_nothing_changed(mini, monkeypatch, capsys):
    """QA re-test N-4: when the rollback itself fails, the message must say the folder is mixed and how to repair it."""
    changed_mini(mini)
    real_replace = os.replace
    calls = []

    def broken_replace(src, dst, *args, **kwargs):
        calls.append(Path(dst).name)
        if len(calls) >= 3:                                        # the third replace fails, and so does every restore
            raise PermissionError(13, "being used by another process", str(dst))
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(publish.os, "replace", broken_replace)
    assert mini.run() == 1
    err = capsys.readouterr().err
    assert "restoring the old files also failed" in err
    assert "Nothing in the data folder was changed" not in err
    assert "py -m nflpipe run --seasons all" in err and "python -m nflpipe" not in err
    monkeypatch.setattr(publish.os, "replace", real_replace)
    assert mini.run() == 0 and mini.check() == 0                    # the next run repairs the folder


def test_m03_index_files_are_written_last(tmp_path):
    order = publish.publish_order(["status.csv", "scored/scored_2026.csv", "manifest.csv", "seasons.csv",
                                   "checks/gates.csv", "player_week/player_week_2026.csv", "run_log.csv"])
    assert order[-1] == "manifest.csv" and order[-2] == "status.csv"
    assert order.index("seasons.csv") > order.index("scored/scored_2026.csv")
    assert order.index("checks/gates.csv") < order.index("seasons.csv")


def test_m03_removed_files_come_back_on_failure(tmp_path, monkeypatch):
    data, stage_dir = tmp_path / "data", tmp_path / "stage"
    (data / "scored").mkdir(parents=True)
    (data / "scored" / "scored_2016.csv").write_text("old\n")       # leaves the window
    (data / "manifest.csv").write_text("old manifest\n")
    stage = Stage(stage_dir)
    stage.write("manifest.csv", b"new manifest\n")
    stage.write("seasons.csv", b"new seasons\n")
    real_unlink = Path.unlink

    def failing_unlink(self, *args, **kwargs):
        if self.name == "scored_2016.csv" and self.parent.name == "scored" and self.parent.parent == data:
            raise PermissionError(13, "locked", str(self))
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    with pytest.raises(PublishError, match="scored_2016.csv"):
        sync(stage, data, backup_dir=tmp_path / "backup")
    monkeypatch.setattr(Path, "unlink", real_unlink)
    assert (data / "manifest.csv").read_text() == "old manifest\n"
    assert not (data / "seasons.csv").exists()
    assert (data / "scored" / "scored_2016.csv").read_text() == "old\n"
    assert not list(data.rglob("*.nflpipe-tmp"))


def test_m03_leftover_temp_files_are_cleaned(mini):
    (mini.data / "status.csv.nflpipe-tmp").write_text("half written\n")
    changed_mini(mini)
    assert mini.run() == 0
    assert not list(mini.data.rglob("*.nflpipe-tmp"))


# ---- m-01: the user's own SeasonTypes change is not an upstream correction -----------------------

def test_m01_season_types_change_is_not_a_restatement(mini):
    set_setting(mini.config, "SeasonTypes", "REG")
    assert mini.run() == 0
    g = gate_results(mini.data)["G-RESTATE"]
    assert g["result"] == "PASS" and "no values changed" in g["detail"]
    assert "SeasonTypes changed by you from REG+POST to REG" in g["detail"]
    assert read_table(mini.data / "checks" / "restatements.csv") == []
    assert {r["season_type"] for r in read_table(mini.data / "seasons.csv")} == {"REG"}


def test_m01_real_corrections_are_still_found_after_a_season_types_change(mini, upstream):
    set_setting(mini.config, "SeasonTypes", "REG")
    rows = miniverse.player_rows(P)
    rows[0]["passing_yards"] = 309                                  # nflverse corrects a finished game
    upstream.put(f"stats_player/stats_player_week_{P}.csv", miniverse.player_file(P, rows))
    golden = mini.fixtures / "golden_sample.csv"                    # 1 yard less = 0.04 points less
    golden.write_text(golden.read_text().replace(f"{QB1},Q. Back,20.4,20.4,24.4", f"{QB1},Q. Back,20.36,20.36,24.36"))
    assert mini.run() == 0
    found = read_table(mini.data / "checks" / "restatements.csv")
    assert [(r["column"], r["old_value"], r["new_value"]) for r in found if r["column"] == "passing_yards"] \
        == [("passing_yards", "310", "309")]
    assert all(r["season_type"] == "REG" for r in found)


# ---- m-02: round to 9 decimals, then half away from zero ----------------------------------------

@pytest.mark.parametrize("value,decimals,expected", [
    (13.499999999999998, 0, 14.0),          # QA example: exact sum 13.5
    (-13.499999999999998, 0, -14.0),
    (2.4999999999999996, 0, 3.0),
    (1.005, 2, 1.01), (2.675, 2, 2.68), (0.125, 2, 0.13), (-0.125, 2, -0.13),
    (13.4999, 0, 13.0), (12.344999, 2, 12.34), (0.0, 2, 0.0),
])
def test_m02_rounding(value, decimals, expected):
    assert round_half_away(value, decimals) == expected


def test_m02_float_sum_on_a_half_rounds_away_from_zero():
    """Real case from the published data: 2024 week 6, 00-0036251, Standard at RoundDecimals 0.
    13 rushing yards x 0.1 + 2 receiving yards x 0.1 - 2 for a fumble lost = -0.5 exactly, but the
    float sum can come out as -0.49999999999999994 (Python 3.12 and later add floats that way; 3.11
    gives -0.5), which 1.0.0 published as 0 instead of -1. The raw sum is deliberately not asserted
    here, because it depends on the Python version; the rounded score must not."""
    rules = LeagueRules("Standard", [("rushing_yards", 0.1, frozenset()), ("receiving_yards", 0.1, frozenset()),
                                     ("rushing_fumbles_lost", -2.0, frozenset())], [])
    row = {"position": "RB", "position_group": "RB", "rushing_yards": 13, "receiving_yards": 2,
           "rushing_fumbles_lost": 1}
    assert score_row(row, rules, 0) == -1.0
    assert score_row(row, rules, 2) == -0.5


# ---- m-03: Excel-saved config copies are normalized and do not trigger a rebuild ---------------

def excel_save(path: Path) -> None:
    """What Excel does on File > Save As > CSV UTF-8: BOM, CRLF, empty trailing column and row."""
    lines = path.read_text(encoding="utf-8").splitlines()
    width = lines[0].count(",") + 2
    out = [ln + "," for ln in lines] + ["," * (width - 1)]
    path.write_bytes(b"\xef\xbb\xbf" + "\r\n".join(out).encode("utf-8") + b"\r\n")


def test_m03_config_resaved_by_excel_does_not_rebuild(mini):
    sha_before = load_config(mini.config).sha256
    for name in ("leagues.csv", "scoring_weights.csv", "bonus_rules.csv", "pipeline_config.csv"):
        excel_save(mini.config / name)
    assert load_config(mini.config).sha256 == sha_before
    before = snapshot(mini.data)
    assert mini.run("--seasons", "current") == 3
    assert snapshot(mini.data) == before


def test_m03_published_config_copies_are_normalized(mini):
    set_weight(mini.config, "receptions", "Custom", "1")            # a real change, saved by Excel
    for name in ("leagues.csv", "scoring_weights.csv", "bonus_rules.csv", "pipeline_config.csv"):
        excel_save(mini.config / name)
    assert mini.run() == 0
    for name in ("leagues.csv", "scoring_weights.csv", "bonus_rules.csv", "pipeline_config.csv"):
        data = (mini.data / "config" / name).read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data and data.endswith(b"\n")
        assert not data.split(b"\n")[0].endswith(b","), "the empty trailing column must be gone"
        assert data == normalize_csv((mini.config / name).read_bytes())
    assert (mini.data / "config" / "leagues.csv").read_bytes() == miniverse.LEAGUES
    assert (mini.data / "config" / "bonus_rules.csv").read_bytes() == miniverse.BONUS


def test_m03_normalize_keeps_values_and_quoting():
    raw = b'\xef\xbb\xbfA,B,,\r\n"x, y",2,,\r\n,,,\r\n'
    assert normalize_csv(raw) == b'A,B\n"x, y",2\n'
    assert normalize_csv(b"A,B\n1,\n") == b"A,B\n1,\n"              # an empty value inside the table stays


# ---- hardening: a Windows (CRLF) checkout of 04-data passes check and does not hold a run ------

def to_crlf(folder: Path) -> None:
    for path in folder.rglob("*.csv"):
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))


def test_crlf_checkout_passes_check(mini, capsys):
    to_crlf(mini.data)
    to_crlf(mini.config)
    assert mini.check() == 0
    assert "Windows line endings" in capsys.readouterr().out


def test_crlf_checkout_skips_instead_of_holding(mini):
    to_crlf(mini.data)
    to_crlf(mini.config)
    before = snapshot(mini.data)
    assert mini.run("--seasons", "current") == 3
    assert snapshot(mini.data) == before


def test_c01_control_league_rule_change_warns_instead_of_holding(mini):
    set_weight(mini.config, "receptions", "Standard", "0.5")       # Standard no longer equals fantasy_points
    assert mini.run() == 0
    g = gate_results(mini.data)["G-RECON"]
    assert g["result"] == "WARN" and "rules for Standard changed" in g["detail"]
    assert "PPR vs fantasy_points_ppr: 10 of 10 rows" in g["detail"]


def test_c01_round_decimals_zero_widens_the_reconciliation_tolerance(mini):
    set_setting(mini.config, "RoundDecimals", "0")
    assert mini.run() == 0
    g = gate_results(mini.data)["G-RECON"]
    assert g["result"] == "PASS" and "tolerance 0.5 because RoundDecimals is 0" in g["detail"]


def test_c01_unchanged_control_league_still_holds(mini):
    before = snapshot(mini.data)
    from nflpipe import scoring
    real = scoring.score_row

    def broken(row, league, decimals):                              # a scoring bug in the Standard league
        value = real(row, league, decimals)
        return value + 1 if league.name == "Standard" and row.get("position") != "DST" else value

    import nflpipe.run as r
    mp = pytest.MonkeyPatch()
    mp.setattr(r, "score_row", broken)
    try:
        assert mini.run() == 4
    finally:
        mp.undo()
    assert snapshot(mini.data) == before
    assert gate_results(mini.report)["G-RECON"]["result"] == "FAIL"


def test_m07_new_pipeline_version_is_recorded_even_when_no_data_changes(mini, monkeypatch):
    status = mini.data / "status.csv"
    from nflpipe import pipeline_version
    assert f"pipeline_version,{pipeline_version}" in status.read_text()
    status.write_text(status.read_text().replace(f"pipeline_version,{pipeline_version}", "pipeline_version,1.0.0"))
    manifest = mini.data / "manifest.csv"                            # keep check consistent with the edit
    rows = read_table(manifest)
    import hashlib
    for r in rows:
        if r["file"] == "status.csv":
            r["sha256"] = hashlib.sha256(status.read_bytes()).hexdigest()
            r["size_bytes"] = str(status.stat().st_size)
    manifest.write_bytes(miniverse.csv_text(list(rows[0]), [list(r.values()) for r in rows]))
    assert mini.run("--seasons", "current") == 0                     # was SKIP: version never recorded
    assert {r["key"]: r["value"] for r in read_table(status)}["pipeline_version"] == pipeline_version
    assert mini.run("--seasons", "current") == 3
