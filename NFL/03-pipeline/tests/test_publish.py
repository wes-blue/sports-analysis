"""Publishing: file format, determinism and the copy into 04-data (CONTRACTS.md section 5)."""

import os

import pytest

from nflpipe.publish import Stage, changed_files, csv_bytes, format_number, sync


@pytest.mark.parametrize("value,text", [
    (None, ""), (0, "0"), (0.0, "0"), (-0.0, "0"), (12.0, "12"), (12, "12"), (0.04, "0.04"),
    (-2.35, "-2.35"), (1 / 3, "0.3333333333333333"), (True, "1"), (123456.0, "123456"),
])
def test_format_number(value, text):
    assert format_number(value) == text


def test_csv_bytes_format():
    data = csv_bytes(["a", "b", "c"], [[1.0, None, "x,y"], [0.5, 0, 'say "hi"']])
    assert data == b'a,b,c\n1,,"x,y"\n0.5,0,"say ""hi"""\n'
    assert not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data


def test_identical_input_gives_identical_bytes():
    rows = [[2025, 1, "REG", "00-1", 12.34], [2025, 2, "REG", "00-1", None]]
    assert csv_bytes(["s", "w", "t", "p", "v"], rows) == csv_bytes(["s", "w", "t", "p", "v"], [list(r) for r in rows])


def make_stage(root, files):
    stage = Stage(root)
    for relative, data in files.items():
        stage.write(relative, data)
    return stage


def test_sync_rewrites_only_changed_files_and_removes_obsolete(tmp_path):
    data = tmp_path / "data"
    first = make_stage(tmp_path / "s1", {"a.csv": b"1\n", "player_week/player_week_2016.csv": b"x\n",
                                         "player_week/player_week_2017.csv": b"y\n", "status.csv": b"t1\n"})
    sync(first, data)
    before = {p.name: p.stat().st_mtime_ns for p in data.rglob("*.csv")}
    os.utime(data / "a.csv", ns=(1, 1))                     # make a rewrite detectable
    second = make_stage(tmp_path / "s2", {"a.csv": b"1\n", "player_week/player_week_2017.csv": b"z\n",
                                          "status.csv": b"t2\n"})
    written, removed = sync(second, data)
    assert sorted(written) == ["player_week/player_week_2017.csv", "status.csv"]
    assert removed == ["player_week/player_week_2016.csv"]
    assert (data / "a.csv").stat().st_mtime_ns == 1         # unchanged file not touched
    assert (data / "player_week/player_week_2017.csv").read_bytes() == b"z\n"
    assert not list(data.rglob("*.nflpipe-tmp")) and before


def test_volatile_files_alone_do_not_count_as_a_change(tmp_path):
    data = tmp_path / "data"
    sync(make_stage(tmp_path / "s1", {"a.csv": b"1\n", "status.csv": b"t1\n", "checks/gates.csv": b"g1\n"}), data)
    stage = make_stage(tmp_path / "s2", {"a.csv": b"1\n", "status.csv": b"t2\n", "checks/gates.csv": b"g2\n"})
    assert changed_files(stage, data, include_volatile=False) == []
    assert changed_files(stage, data, include_volatile=True) == ["checks/gates.csv", "status.csv"]
