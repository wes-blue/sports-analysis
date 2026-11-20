"""Decision table for ``nflpipe watchdog`` (no network)."""

from __future__ import annotations

import pytest

from nflpipe import freshness as fr
from nflpipe import watchdog

HEADER = "game_id,season,game_type,week,gameday,weekday,gametime,away_team,away_score,home_team,home_score"
GAMES = [
    (2025, "REG", 1, "2025-09-08", "20:15"),
    (2025, "WC", 19, "2026-01-12", "20:15"),
    (2025, "SB", 22, "2026-02-08", "18:30"),
    (2026, "REG", 1, "2026-09-10", "20:20"), (2026, "REG", 1, "2026-09-14", "20:15"),  # settles 2026-09-15T06:15Z
    (2026, "REG", 2, "2026-09-17", "20:15"), (2026, "REG", 2, "2026-09-21", "20:15"),  # settles 2026-09-22T06:15Z
    (2026, "REG", 3, "2026-09-28", "20:15"),                                           # settles 2026-09-29T06:15Z
]


def schedule_file(tmp_path):
    lines = [HEADER] + [f"g{i},{s},{gt},{w},{d},X,{tm},A,1,B,2" for i, (s, gt, w, d, tm) in enumerate(GAMES)]
    path = tmp_path / "games.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def state_dir(tmp_path, season=None, week=None, stype="REG", generated=None, run_log=(), outcome="PUBLISH"):
    folder = tmp_path / "data"
    folder.mkdir()
    rows = ["key,value", f"outcome,{outcome}"]
    if generated:
        rows.append(f"generated_utc,{generated}")
    if season is not None:
        rows += [f"latest_season,{season}", f"latest_week,{week}", f"latest_season_type,{stype}"]
    (folder / "status.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    if run_log:
        log = ["run_id,started_utc,finished_utc,trigger,seasons_requested,seasons_refreshed,outcome,latest_season,"
               "latest_week,latest_season_type,gates_fail,gates_warn,pipeline_version,notes"]
        for finished, oc in run_log:
            log.append(f"r,{finished},{finished},schedule,current,2026,{oc},2026,1,REG,0,0,0.1,")
        (folder / "run_log.csv").write_text("\n".join(log) + "\n", encoding="utf-8")
    return str(folder)


def judge(tmp_path, now, data_dir, max_age=72):
    state = fr.season_state(fr.parse_schedule(open(schedule_file(tmp_path)).read()), fr.parse_utc(now))
    return watchdog.judge(state, fr.parse_utc(now), fr.read_published(data_dir), max_age)


CASES = [
    # id, now, published (season, week, type, generated), expected status, reason fragment
    ("healthy-covered", "2026-09-18T14:41:00Z", (2026, 1, "REG", "2026-09-16T10:00:00Z"), "healthy", "covers"),
    ("grace", "2026-09-23T14:41:00Z", (2026, 1, "REG", "2026-09-16T10:00:00Z"), "healthy", "inside the 72 h"),
    ("stale-week-missed", "2026-09-25T14:41:00Z", (2026, 1, "REG", "2026-09-16T10:00:00Z"), "stale", "week 2 REG"),
    ("stale-many-weeks", "2026-09-30T14:41:00Z", (2025, 22, "POST", "2026-02-10T10:00:00Z"), "stale",
     "3 finished week(s)"),
    ("off-season-summer", "2026-07-01T00:00:00Z", (2025, 19, "POST", "2026-01-14T10:00:00Z"), "healthy",
     "off-season"),
    ("pre-first-week", "2026-09-12T00:00:00Z", (2025, 22, "POST", "2026-02-10T10:00:00Z"), "healthy",
     "off-season"),
    ("post-sb-tail", "2026-02-13T14:41:00Z", (2025, 19, "POST", "2026-01-14T10:00:00Z"), "stale", "week 22 POST"),
]


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_decision_table(tmp_path, case):
    _id, now, (season, week, stype, gen), expected, fragment = case
    v = judge(tmp_path, now, state_dir(tmp_path, season, week, stype, gen))
    assert v.status == expected, v.reason
    assert fragment in v.reason
    assert v.exit_code == (5 if expected == "stale" else 0)


def test_publish_without_new_week_does_not_hide_staleness(tmp_path):
    # e.g. the monthly rebuild published on 2026-09-24 but data still stops at week 1
    v = judge(tmp_path, "2026-09-25T14:41:00Z", state_dir(tmp_path, 2026, 1, "REG", "2026-09-24T11:23:00Z"))
    assert v.status == "stale"


def test_never_published_in_season_is_stale(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    v = judge(tmp_path, "2026-09-18T14:41:00Z", str(folder))
    assert v.status == "stale" and "nothing has ever been published" in v.reason


def test_falls_back_to_run_log_time_when_status_has_no_week(tmp_path):
    dd = state_dir(tmp_path, generated=None, run_log=[("2026-09-16T10:00:00Z", "PUBLISH")])
    assert judge(tmp_path, "2026-09-18T14:41:00Z", dd).status == "healthy"
    dd2 = tmp_path / "x"
    dd2.mkdir()
    (dd2 / "run_log.csv").write_text(open(dd + "/run_log.csv").read())
    assert judge(tmp_path, "2026-09-25T14:41:00Z", str(dd2)).status == "stale"


def test_non_publish_run_log_rows_are_ignored(tmp_path):
    dd = state_dir(tmp_path, generated=None, run_log=[("2026-09-16T10:00:00Z", "HOLD")], outcome="HOLD")
    v = judge(tmp_path, "2026-09-18T14:41:00Z", dd)
    assert v.status == "stale" and "nothing has ever been published" in v.reason


def test_main_exit_codes(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    sched = schedule_file(tmp_path)
    dd = state_dir(tmp_path, 2026, 1, "REG", "2026-09-16T10:00:00Z")
    base = ["--data-dir", dd, "--schedule-file", sched, "--max-age-hours", "72"]
    assert watchdog.main(base + ["--now", "2026-09-18T14:41:00Z"]) == 0
    assert watchdog.main(base + ["--now", "2026-09-25T14:41:00Z"]) == 5
    assert watchdog.main(base + ["--now", "2026-09-25T14:41:00Z", "--schedule-file", str(tmp_path / "no.csv")]) == 1
    assert watchdog.main(["--data-dir", dd, "--schedule-file", sched, "--max-age-hours", "0"]) == 1


def test_main_unreadable_state_is_an_error(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    folder = tmp_path / "bad"
    folder.mkdir()
    (folder / "status.csv").write_text("nope\n", encoding="utf-8")
    rc = watchdog.main(["--data-dir", str(folder), "--schedule-file", schedule_file(tmp_path),
                        "--max-age-hours", "72", "--now", "2026-09-18T14:41:00Z"])
    assert rc == 1
