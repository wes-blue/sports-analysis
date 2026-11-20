"""``check``: read-only verification of a published folder."""

from miniverse import P, rewrite, snapshot
from nflpipe.__main__ import main as dispatch


def test_check_passes_and_writes_nothing(mini):
    before = snapshot(mini.data)
    assert mini.check() == 0
    assert snapshot(mini.data) == before


def test_check_fails_on_a_tampered_file(mini, capsys):
    path = mini.data / "scored" / f"scored_{P}.csv"
    rewrite(path, lambda h, rows: [r[:-1] + ["99"] if i == 0 else r for i, r in enumerate(rows)])
    assert mini.check() == 4
    out = capsys.readouterr().out
    assert "changed after publishing" in out and "G-INDEX" in out


def test_check_fails_on_an_unlisted_or_missing_file(mini, capsys):
    (mini.data / "player_week" / "player_week_1999.csv").write_text("season\n")
    (mini.data / "checks" / "golden.csv").unlink()
    assert mini.check() == 4
    out = capsys.readouterr().out
    assert "not in manifest.csv" in out and "golden.csv is missing" in out


def test_check_fails_when_nothing_is_published(tmp_path):
    assert dispatch(["check", "--data-dir", str(tmp_path / "empty")]) == 4


def test_dispatcher_runs_check(mini):
    assert dispatch(["check", "--data-dir", str(mini.data), "--fixtures-dir", str(mini.fixtures)]) == 0
