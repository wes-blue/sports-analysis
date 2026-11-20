"""Decision table for ``nflpipe resolve`` and unit tests for ``nflpipe.freshness``.

No network: the schedule is a fixture string and every HTTP call goes through a fake opener.
"""

from __future__ import annotations

import datetime as dt
import io
import urllib.error

import pytest

from nflpipe import freshness as fr
from nflpipe import resolve

UTC = dt.timezone.utc

HEADER = "game_id,season,game_type,week,gameday,weekday,gametime,away_team,away_score,home_team,home_score"
GAMES = [
    # season, type, week, ET date, ET time, scored
    (2025, "REG", 1, "2025-09-04", "20:20", True), (2025, "REG", 1, "2025-09-07", "13:00", True),
    (2025, "REG", 1, "2025-09-08", "20:15", True),
    (2025, "REG", 2, "2025-09-11", "20:15", True), (2025, "REG", 2, "2025-09-15", "20:15", True),
    (2025, "WC", 19, "2026-01-10", "16:30", True), (2025, "WC", 19, "2026-01-12", "20:15", True),
    (2025, "DIV", 20, "2026-01-17", "16:30", True), (2025, "DIV", 20, "2026-01-18", "18:30", True),
    (2025, "CON", 21, "2026-01-25", "15:00", True),
    (2025, "SB", 22, "2026-02-08", "18:30", True),
    (2026, "REG", 1, "2026-09-10", "20:20", True), (2026, "REG", 1, "2026-09-13", "13:00", True),
    (2026, "REG", 1, "2026-09-14", "20:15", True),
    (2026, "REG", 2, "2026-09-17", "20:15", False), (2026, "REG", 2, "2026-09-20", "13:00", False),
    (2026, "REG", 2, "2026-09-21", "20:15", False),
    (2026, "REG", 3, "2026-09-24", "20:15", False), (2026, "REG", 3, "2026-09-28", "20:15", False),
]


def schedule_text() -> str:
    lines = [HEADER]
    for i, (season, gtype, week, day, time_, scored) in enumerate(GAMES):
        score = "20" if scored else ""
        lines.append(f"{season}_{week:02d}_{i},{season},{gtype},{week},{day},X,{time_},AAA,{score},BBB,{score}")
    return "\n".join(lines) + "\n"


def t(text: str) -> dt.datetime:
    return fr.parse_utc(text)


LM = t("2026-09-15T18:00:00Z")            # upstream stats_player Last-Modified in most cases
LM_TEAM = t("2026-09-15T18:00:05Z")


def probe(when, kind="stats_player"):
    return fr.Probe(url=f"https://x/{kind}", last_modified=when, size_bytes=1, etag="", method="HEAD")


def write_state(folder, season=None, week=None, stype="REG", player_lm=None, team_lm=None,
                generated="2026-09-15T19:00:00Z", lm_season=None):
    folder.mkdir(parents=True, exist_ok=True)
    rows = ["key,value", "outcome,PUBLISH", f"generated_utc,{generated}"]
    if season is not None:
        rows += [f"latest_season,{season}", f"latest_week,{week}", f"latest_season_type,{stype}"]
    (folder / "status.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    src = ["season,kind,url,last_modified,size_bytes,sha256,fetched_utc",
           f",schedules,u,2026-09-15T01:00:00Z,1,x,{generated}"]
    s = lm_season if lm_season is not None else season
    if player_lm:
        src.append(f"{s},stats_player,u,{player_lm},1,x,{generated}")
    if team_lm:
        src.append(f"{s},stats_team,u,{team_lm},1,x,{generated}")
    (folder / "sources.csv").write_text("\n".join(src) + "\n", encoding="utf-8")
    return str(folder)


def run_decide(now, data_dir, player=LM, team=LM_TEAM):
    now = t(now)
    state = fr.season_state(fr.parse_schedule(schedule_text()), now)
    probes = {"stats_player": probe(player) if player else None,
              "stats_team": probe(team, "stats_team") if team else None}
    return resolve.decide(state, now, fr.read_published(data_dir), probes)


# ---------------------------------------------------------------------------
# Decision table
# ---------------------------------------------------------------------------

def test_first_run_empty_dir(tmp_path):
    (tmp_path / "d").mkdir()
    d = run_decide("2026-09-16T15:17:00Z", str(tmp_path / "d"))
    assert (d.action, d.exit_code, d.season, d.week, d.season_type) == ("run", 0, 2026, 1, "REG")
    assert "first run" in d.reason
    assert d.upstream_last_modified == "2026-09-15T18:00:00Z"


def test_first_run_missing_dir(tmp_path):
    d = run_decide("2026-09-16T15:17:00Z", str(tmp_path / "nope"))
    assert d.action == "run" and "first run" in d.reason


def test_skip_when_upstream_unchanged_and_week_published(tmp_path):
    dd = write_state(tmp_path / "d", 2026, 1, player_lm="2026-09-15T18:00:00Z", team_lm="2026-09-15T18:00:05Z")
    d = run_decide("2026-09-17T10:17:00Z", dd)
    assert (d.action, d.exit_code) == ("skip", 3)
    assert "upstream not updated since last publish" in d.reason
    assert d.published_through == "2026-W01-REG"


def test_run_when_upstream_newer(tmp_path):
    dd = write_state(tmp_path / "d", 2026, 1, player_lm="2026-09-15T12:00:00Z", team_lm="2026-09-15T18:00:05Z")
    d = run_decide("2026-09-17T10:17:00Z", dd)
    assert d.action == "run" and "upstream updated since last publish" in d.reason
    assert "stats_player 2026-09-15T18:00:00Z vs recorded 2026-09-15T12:00:00Z" in d.reason


def test_skip_when_week_finished_but_upstream_not_moved(tmp_path):
    dd = write_state(tmp_path / "d", 2026, 1, player_lm="2026-09-15T18:00:00Z", team_lm="2026-09-15T18:00:05Z")
    d = run_decide("2026-09-23T10:17:00Z", dd)          # week 2 settled 2026-09-22T06:15Z
    assert (d.action, d.week) == ("skip", 2)
    assert "week 2 REG finished but nflverse has not updated" in d.reason


def test_run_when_week_finished_and_upstream_moved(tmp_path):
    dd = write_state(tmp_path / "d", 2026, 1, player_lm="2026-09-15T18:00:00Z", team_lm="2026-09-15T18:00:05Z")
    d = run_decide("2026-09-23T10:17:00Z", dd, player=t("2026-09-22T17:00:00Z"))
    assert (d.action, d.week) == ("run", 2)
    assert "week 2 REG finished and not yet published" in d.reason


def test_run_when_only_stats_team_moved(tmp_path):
    dd = write_state(tmp_path / "d", 2026, 1, player_lm="2026-09-15T18:00:00Z", team_lm="2026-09-15T10:00:00Z")
    d = run_decide("2026-09-17T10:17:00Z", dd)
    assert d.action == "run" and "stats_team" in d.reason and "stats_player" not in d.reason


def test_stats_team_missing_is_ignored(tmp_path):
    dd = write_state(tmp_path / "d", 2026, 1, player_lm="2026-09-15T18:00:00Z")
    d = run_decide("2026-09-17T10:17:00Z", dd, team=None)
    assert d.action == "skip"


def test_skip_when_season_file_not_published_upstream(tmp_path):
    dd = write_state(tmp_path / "d", 2025, 22, "POST", player_lm="2026-02-10T00:00:00Z", lm_season=2025)
    d = run_decide("2026-09-15T15:17:00Z", dd, player=None, team=None)
    assert d.action == "skip" and "has not published stats_player_week_2026.csv" in d.reason


def test_new_season_with_nothing_recorded_runs(tmp_path):
    dd = write_state(tmp_path / "d", 2025, 22, "POST", player_lm="2026-02-10T00:00:00Z",
                     team_lm="2026-02-10T00:00:00Z", lm_season=2025)
    d = run_decide("2026-09-15T15:17:00Z", dd)
    assert d.action == "run" and "recorded none" in d.reason


def test_unreadable_status_runs(tmp_path):
    folder = tmp_path / "d"
    folder.mkdir()
    (folder / "status.csv").write_text("garbage\n\"x\n", encoding="utf-8")
    d = run_decide("2026-09-17T10:17:00Z", str(folder))
    assert d.action == "run" and "missing columns" in d.reason


def test_bad_timestamp_in_sources_runs(tmp_path):
    dd = write_state(tmp_path / "d", 2026, 1, player_lm="not-a-date", team_lm="2026-09-15T18:00:05Z")
    d = run_decide("2026-09-17T10:17:00Z", dd)
    assert d.action == "run" and "bad last_modified" in d.reason


def test_week_in_progress_skips(tmp_path):
    dd = write_state(tmp_path / "d", 2025, 22, "POST", player_lm="2026-02-10T00:00:00Z", lm_season=2025)
    d = run_decide("2026-09-12T12:00:00Z", dd)           # Thursday opener played, week 1 not settled
    assert d.action == "skip" and d.week is None and "no week of the 2026 season has finished" in d.reason


def test_thursday_game_does_not_advance_the_week(tmp_path):
    dd = write_state(tmp_path / "d", 2026, 1, player_lm="2026-09-15T18:00:00Z", team_lm="2026-09-15T18:00:05Z")
    d = run_decide("2026-09-18T10:17:00Z", dd)           # week 2 Thursday game settled, Monday not
    assert d.week == 1 and d.action == "skip"


def test_playoff_week_resolves_as_post(tmp_path):
    dd = write_state(tmp_path / "d", 2025, 2, player_lm="2026-01-06T00:00:00Z",
                     team_lm="2026-01-06T00:00:00Z", lm_season=2025)
    d = run_decide("2026-01-13T15:17:00Z", dd, player=t("2026-01-13T12:00:00Z"), team=t("2026-01-13T12:00:00Z"))
    assert (d.action, d.season, d.week, d.season_type) == ("run", 2025, 19, "POST")


def test_super_bowl_published_skips_as_off_season(tmp_path):
    dd = write_state(tmp_path / "d", 2025, 22, "POST", player_lm="2026-02-09T18:00:00Z",
                     team_lm="2026-02-09T18:00:00Z", lm_season=2025)
    d = run_decide("2026-02-11T10:17:00Z", dd, player=t("2026-02-09T18:00:00Z"), team=t("2026-02-09T18:00:00Z"))
    assert d.action == "skip" and d.reason.startswith("off-season") and "complete and published" in d.reason


def test_summer_skips_with_next_season_start(tmp_path):
    dd = write_state(tmp_path / "d", 2025, 22, "POST", player_lm="2026-02-09T18:00:00Z",
                     team_lm="2026-02-09T18:00:00Z", lm_season=2025)
    d = run_decide("2026-07-01T12:00:00Z", dd, player=t("2026-02-09T18:00:00Z"), team=t("2026-02-09T18:00:00Z"))
    assert d.action == "skip" and "next season starts 2026-09-11T00:20:00Z" in d.reason


def test_off_season_back_correction_runs(tmp_path):
    dd = write_state(tmp_path / "d", 2025, 22, "POST", player_lm="2026-02-09T18:00:00Z",
                     team_lm="2026-02-09T18:00:00Z", lm_season=2025)
    d = run_decide("2026-07-01T12:00:00Z", dd, player=t("2026-06-30T18:00:00Z"), team=t("2026-02-09T18:00:00Z"))
    assert d.action == "run"


# ---------------------------------------------------------------------------
# main(): outputs, exit codes, HTTP behaviour (fake opener)
# ---------------------------------------------------------------------------

class FakeResp:
    def __init__(self, headers, body=b""):
        self.headers = headers
        self._body = io.BytesIO(body)
        self.status = 200

    def read(self, n=-1):
        return self._body.read(n)

    def close(self):
        pass


def make_opener(player_lm="Tue, 15 Sep 2026 18:00:00 GMT", head_has_lm=True, fail=None, missing=()):
    calls = []

    def opener(req, timeout):
        url = req.full_url
        calls.append((req.get_method(), url))
        if fail and fail in url:
            raise urllib.error.HTTPError(url, 500, "boom", {}, None)
        if any(m in url for m in missing):
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        if url.endswith("games.csv"):
            return FakeResp({}, schedule_text().encode())
        headers = {"Content-Length": "10"}
        if req.get_method() == "GET":
            headers = {"Content-Range": "bytes 0-0/10", "Last-Modified": player_lm}
        elif head_has_lm:
            headers["Last-Modified"] = player_lm
        return FakeResp(headers, b"x")

    opener.calls = calls
    return opener


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(fr.time, "sleep", lambda s: None)


def test_main_run_writes_github_output(tmp_path, monkeypatch, capsys):
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    rc = resolve.main(["--data-dir", str(tmp_path / "none"), "--now", "2026-09-16T15:17:00Z"], opener=make_opener())
    assert rc == 0
    text = out.read_text()
    for key in ("action=run", "season=2026", "week=1", "season_type=REG",
                "upstream_last_modified=2026-09-15T18:00:00Z", "published_through=", "reason=first run"):
        assert key in text
    assert "action=run" in capsys.readouterr().out


def test_main_skip_exit_3(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    dd = write_state(tmp_path / "d", 2026, 1, player_lm="2026-09-15T18:00:00Z", team_lm="2026-09-15T18:00:00Z")
    rc = resolve.main(["--data-dir", dd, "--now", "2026-09-17T10:17:00Z"], opener=make_opener())
    assert rc == 3


def test_main_upstream_error_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    rc = resolve.main(["--data-dir", str(tmp_path), "--now", "2026-09-17T10:17:00Z"],
                      opener=make_opener(fail="stats_player"))
    assert rc == 1


def test_main_schedule_error_fails_closed(tmp_path, monkeypatch, capsys):
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    rc = resolve.main(["--data-dir", str(tmp_path), "--now", "2026-09-17T10:17:00Z"],
                      opener=make_opener(fail="games.csv"))
    assert rc == 1
    assert "action=error" in out.read_text()


def test_main_404_season_file_is_a_skip(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    rc = resolve.main(["--data-dir", str(tmp_path / "none"), "--now", "2026-09-16T15:17:00Z"],
                      opener=make_opener(missing=("stats_player", "stats_team")))
    assert rc == 3


def test_probe_falls_back_to_ranged_get():
    op = make_opener(head_has_lm=False)
    p = fr.probe_last_modified("https://example.test/stats_player_week_2026.csv", opener=op)
    assert p.method == "GET-range" and p.size_bytes == 10
    assert [m for m, _ in op.calls] == ["HEAD", "GET"]


def test_probe_retries_then_fails():
    op = make_opener(fail="stats")
    with pytest.raises(fr.FreshnessError):
        fr.probe_last_modified("https://example.test/stats_player_week_2026.csv", opener=op)
    assert len(op.calls) == 6   # 3 HEAD attempts, then 3 ranged GET attempts


def test_output_values_cannot_inject_lines(tmp_path, monkeypatch):
    out = tmp_path / "o"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    fr.write_outputs([("reason", "a\nevil=1")], stream=io.StringIO())
    assert out.read_text() == "reason=a evil=1\n"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("day,hhmm,expected", [
    ("2026-09-14", "20:15", "2026-09-15T00:15:00Z"),   # EDT
    ("2026-11-16", "20:15", "2026-11-17T01:15:00Z"),   # EST
    ("2026-11-01", "13:00", "2026-11-01T18:00:00Z"),   # first Sunday of November: already EST
    ("2026-03-08", "13:00", "2026-03-08T17:00:00Z"),   # second Sunday of March: already EDT
    ("2027-01-10", "16:30", "2027-01-10T21:30:00Z"),
])
def test_eastern_to_utc(day, hhmm, expected):
    assert fr.iso_utc(fr.eastern_to_utc(dt.date.fromisoformat(day), hhmm)) == expected


@pytest.mark.parametrize("text", ["2026-09-15T18:00:00Z", "2026-09-15T18:00:00+00:00", "2026-09-15 18:00:00",
                                  "2026-09-15T14:00:00-04:00", "Tue, 15 Sep 2026 18:00:00 GMT"])
def test_parse_utc_formats(text):
    assert fr.parse_utc(text) == dt.datetime(2026, 9, 15, 18, 0, tzinfo=UTC)


def test_parse_utc_blank_and_bad():
    assert fr.parse_utc("") is None
    with pytest.raises(ValueError):
        fr.parse_utc("yesterday")


def test_schedule_ignores_unknown_game_types_and_rejects_missing_columns():
    games = fr.parse_schedule(schedule_text() + "x,2026,PRE,0,2026-08-01,X,19:00,A,,B,\n")
    assert all(g.game_type != "PRE" for g in games)
    with pytest.raises(fr.FreshnessError):
        fr.parse_schedule("a,b\n1,2\n")


# ---------------------------------------------------------------------------
# QA findings M-07 (a pushed config change runs) and m-04 (package-relative defaults)
# ---------------------------------------------------------------------------

def write_config_state(folder, config_dir, sha=None, version=None):
    """A published state that says 2026 week 1 is published and upstream has not moved."""
    from nflpipe import pipeline_version
    from nflpipe.config import load_config
    dd = write_state(folder, 2026, 1, player_lm="2026-09-15T18:00:00Z", team_lm="2026-09-15T18:00:05Z")
    status = folder / "status.csv"
    status.write_text(status.read_text()
                      + f"pipeline_version,{version or pipeline_version}\n"
                      + f"config_sha256,{sha or load_config(config_dir).sha256}\n")
    return dd


@pytest.fixture
def config_dir(tmp_path):
    import miniverse
    return miniverse.write_config(tmp_path / "cfg")


def test_m07_unchanged_config_still_skips(tmp_path, config_dir):
    dd = write_config_state(tmp_path / "d", config_dir)
    change = resolve.local_change(fr.read_published(dd), config_dir)
    assert change == ""
    now = t("2026-09-17T10:17:00Z")
    state = fr.season_state(fr.parse_schedule(schedule_text()), now)
    d = resolve.decide(state, now, fr.read_published(dd), {"stats_player": probe(LM),
                                                         "stats_team": probe(LM_TEAM, "stats_team")}, change)
    assert d.action == "skip"


def test_m07_config_change_runs_even_when_upstream_is_unchanged(tmp_path, config_dir):
    dd = write_config_state(tmp_path / "d", config_dir)
    weights = config_dir / "scoring_weights.csv"
    weights.write_text(weights.read_text().replace("receptions,Receiving,,0,1,0.5", "receptions,Receiving,,0,1,1"))
    change = resolve.local_change(fr.read_published(dd), config_dir)
    assert "config in 02-config differs" in change
    now = t("2026-09-17T10:17:00Z")
    state = fr.season_state(fr.parse_schedule(schedule_text()), now)
    d = resolve.decide(state, now, fr.read_published(dd), {"stats_player": probe(LM),
                                                         "stats_team": probe(LM_TEAM, "stats_team")}, change)
    assert (d.action, d.exit_code) == ("run", 0) and "instead of waiting for nflverse" in d.reason


def test_m07_config_change_runs_in_the_off_season(tmp_path, config_dir):
    dd = write_config_state(tmp_path / "d", config_dir, sha="0" * 64)
    now = t("2026-07-01T11:23:00Z")
    state = fr.season_state(fr.parse_schedule(schedule_text()), now)
    published = fr.read_published(dd)
    d = resolve.decide(state, now, published, {"stats_player": None, "stats_team": None},
                       resolve.local_change(published, config_dir))
    assert d.action == "run"


def test_m07_pipeline_version_change_runs(tmp_path, config_dir):
    dd = write_config_state(tmp_path / "d", config_dir, version="1.0.0")
    change = resolve.local_change(fr.read_published(dd), config_dir)
    assert "pipeline version 1.0.0 -> " in change


def test_m07_excel_resave_is_not_a_change(tmp_path, config_dir):
    dd = write_config_state(tmp_path / "d", config_dir)
    for path in config_dir.glob("*.csv"):
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes().replace(b"\n", b",\r\n"))
    assert resolve.local_change(fr.read_published(dd), config_dir) == ""


def test_m07_main_reads_config_dir(tmp_path, config_dir, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    argv = ["--config-dir", str(config_dir), "--now", "2026-09-17T10:17:00Z"]
    same = write_config_state(tmp_path / "same", config_dir)
    assert resolve.main(["--data-dir", same] + argv, opener=make_opener()) == 3
    other = write_config_state(tmp_path / "other", config_dir, sha="f" * 64)
    assert resolve.main(["--data-dir", other] + argv, opener=make_opener()) == 0


def test_m04_defaults_are_package_relative(monkeypatch, tmp_path):
    from pathlib import Path
    from nflpipe import watchdog
    project = Path(resolve.__file__).resolve().parents[2]
    monkeypatch.chdir(tmp_path)
    args = resolve.build_parser().parse_args([])
    assert Path(args.data_dir) == project / "04-data" and Path(args.config_dir) == project / "02-config"
    assert Path(watchdog.build_parser().parse_args(["--max-age-hours", "1"]).data_dir) == project / "04-data"
