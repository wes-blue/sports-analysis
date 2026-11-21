"""Tests for ``python -m nflpipe export`` (CONTRACTS.md section 13), offline.

Two kinds of data: the miniature publish from ``miniverse`` (a real ``04-data`` layout) and tiny
hand-written ``04-data`` folders for the cases that need exact values (hostile text, rounding,
limits). The workbook is read back with ``openpyxl``, which only the test job installs.
"""

from __future__ import annotations

import csv
import re
import shutil
import zipfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from nflpipe import __main__ as dispatcher  # noqa: E402
from nflpipe import export_xlsx  # noqa: E402

from miniverse import csv_text  # noqa: E402

TEXT_COLS = {"season_type", "player_id", "player_display_name", "position", "position_group", "team", "opponent_team"}
IDENT = ["season", "week", "season_type", "player_id", "player_display_name", "position", "position_group", "team",
         "opponent_team"]


# --------------------------------------------------------------------------------------------
# helpers

def export(data_dir: Path, out: Path) -> int:
    return export_xlsx.main(["--data-dir", str(data_dir), "--out", str(out)])


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]


def expected_cell(col: str, text: str):
    if text == "":
        return None
    if col in TEXT_COLS or not re.fullmatch(r"-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?", text):
        return text
    return int(text) if re.fullmatch(r"-?\d+", text) else float(text)


def sheet_rows(wb, name: str, first: int = 1) -> list[tuple]:
    return list(wb[name].iter_rows(min_row=first, values_only=True))


def write(path: Path, header, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(csv_text(header, rows))


def tiny_data(root: Path, players: list[list[str]], scored_values: list[list[str]], *, leagues=("Alpha", "Beta"),
              decimals: int = 2, metrics=("passing_yards", "receptions"), season: int = 2024,
              extra_seasons: dict | None = None, in_progress: bool = False) -> Path:
    """Hand-written minimal ``04-data``. ``players`` rows: week, season_type, player_id, name, position, team.
    ``scored_values`` has one list of league values per player row."""
    data = root / "04-data"
    write(data / "status.csv", ["key", "value"], [
        ["run_id", "RUN-1"], ["generated_utc", "2026-01-02T03:04:05Z"], ["pipeline_version", "1.2.1"],
        ["data_contract_version", "1"], ["outcome", "PUBLISH"], ["window_start", str(season)], ["window_end", str(season)],
        ["season_types", "REG+POST"], ["latest_season", str(season)], ["latest_week", "3"], ["latest_season_type", "REG"],
        ["gates_pass", "13"], ["gates_warn", "0"], ["gates_fail", "0"],
        ["data_source", "nflverse, https://github.com/nflverse/nflverse-data"], ["data_license", "CC BY 4.0"]])
    write(data / "config" / "leagues.csv", ["League", "Description", "Active", "Reconcile_To", "Notes"],
          [[n, f"{n} league", "Yes", "", ""] for n in leagues] + [["Off", "inactive", "No", "", ""]])
    write(data / "config" / "scoring_weights.csv", ["Metric", "Category", "Description", *leagues, "Off", "Notes", "Applies_To"],
          [[m, "Cat", m, *(["1"] * len(leagues)), "0", "", ""] for m in metrics])
    write(data / "config" / "bonus_rules.csv", ["League", "Metric", "Lower", "Upper", "Points", "Applies_To", "Notes"], [])
    write(data / "config" / "pipeline_config.csv", ["Setting", "Value", "Allowed_Values", "Description"],
          [["RoundDecimals", str(decimals), "0-6", "d"]])
    write(data / "checks" / "gates.csv", ["gate_id", "gate", "severity", "result", "detail", "checked_utc"],
          [["G-X", "A gate", "blocking", "PASS", "13", "2026-01-02T03:04:05Z"]])
    write(data / "seasons.csv", ["season", "season_type", "player_rows", "dst_rows", "max_week", "season_status", "refreshed_utc"],
          [[str(season), "REG", "1", "0", "3", "in_progress" if in_progress else "complete", "2026-01-02T03:04:05Z"]])
    write(data / "dictionary.csv", ["metric", "category", "description", "source", "applies_to"],
          [[m, "Cat", m, "nflverse", ""] for m in metrics])
    seasons = {season: (players, scored_values)}
    seasons.update(extra_seasons or {})
    for s, (prows, srows) in seasons.items():
        header = IDENT + list(metrics) + ["fantasy_points", "fantasy_points_ppr"]
        pw = [[str(s), p[0], p[1], p[2], p[3], p[4], p[4], p[5], "OPP", *["10"] * len(metrics), "1.5", "2.5"] for p in prows]
        write(data / "player_week" / f"player_week_{s}.csv", header, pw)
        sheader = ["season", "week", "season_type", "player_id", "player_display_name", "position", "team",
                   "fantasy_points", "fantasy_points_ppr", *[f"FF_{n}" for n in leagues]]
        sc = [[str(s), p[0], p[1], p[2], p[3], p[4], p[5], "1.5", "2.5", *v] for p, v in zip(prows, srows)]
        write(data / "scored" / f"scored_{s}.csv", sheader, sc)
    return data


FRONT = ["season", "week", "season_type", "player_display_name", "position", "team", "opponent_team"]
BACK = ["player_id", "position_group", "fantasy_points", "fantasy_points_ppr"]


def active_leagues(data: Path) -> list[str]:
    with open(data / "config" / "leagues.csv", encoding="utf-8") as handle:
        return [r["League"] for r in csv.DictReader(handle) if r["Active"].lower() == "yes"]


def expected_player_games(data: Path) -> tuple[list[str], list[list]]:
    """Written independently of the exporter: header and rows, newest first, scored values matched by key."""
    active = active_leagues(data)
    header = None
    rows = []
    for pw_file in sorted((data / "player_week").glob("player_week_*.csv"), reverse=True):
        pw_header, pw_rows = read_csv(pw_file)
        sc_header, sc_rows = read_csv(data / "scored" / pw_file.name.replace("player_week", "scored"))
        scored = {tuple(r[sc_header.index(k)] for k in ("season", "week", "season_type", "player_id")): dict(zip(sc_header, r))
                  for r in sc_rows}
        assert len(scored) == len(sc_rows)
        metrics = [c for c in pw_header[9:] if c not in BACK]
        header = FRONT + [f"FF_{n}" for n in active] + BACK + metrics
        part = []
        for r in pw_rows:
            full = dict(zip(pw_header, r))
            full.update({f"FF_{n}": scored[(full["season"], full["week"], full["season_type"], full["player_id"])][f"FF_{n}"]
                         for n in active})
            part.append([expected_cell(c, full[c]) for c in header])
        part.sort(key=lambda row: -row[1])                       # week descending; sort is stable
        rows += part
    return header, rows


def one_player(name: str, pid: str = "00-1", week: str = "1") -> list[str]:
    return [week, "REG", pid, name, "QB", "NE"]


# --------------------------------------------------------------------------------------------
# the miniature publish: every sheet, every column, every cell

def test_mini_publish_workbook(mini, tmp_path):
    out = tmp_path / "w" / "NFL-Analysis.xlsx"
    assert export(mini.data, out) == 0
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["About", "PlayerGames", "SeasonTotals", "Leagues", "Scoring", "Bonus", "Checks", "Dictionary"]

    # PlayerGames: newest first, league columns up front, scored values matched by key; every cell checked
    header, expected_rows = expected_player_games(mini.data)
    active = active_leagues(mini.data)
    assert header[:7] == FRONT and header[7:7 + len(active)] == [f"FF_{n}" for n in active]
    assert header[7 + len(active):11 + len(active)] == BACK
    assert expected_rows, "the mini publish should have player rows"
    got = sheet_rows(wb, "PlayerGames")
    assert list(got[0]) == header
    assert len(got) - 1 == len(expected_rows)
    for g, e in zip(got[1:], expected_rows):
        assert list(g) == e
    seasons = [r[0] for r in got[1:]]
    assert seasons == sorted(seasons, reverse=True)
    ws = wb["PlayerGames"]
    assert ws.freeze_panes == "E2"                   # through player_display_name
    assert list(ws.tables) == ["tblPlayerGames"]
    assert ws.tables["tblPlayerGames"].ref == f"A1:{openpyxl.utils.get_column_letter(len(header))}{len(expected_rows) + 1}"
    assert ws.tables["tblPlayerGames"].autoFilter is not None
    assert [c.name for c in ws.tables["tblPlayerGames"].tableColumns] == header

    # small sheets equal their CSVs
    for sheet, rel, first in (("Leagues", "config/leagues.csv", 2), ("Scoring", "config/scoring_weights.csv", 2),
                              ("Bonus", "config/bonus_rules.csv", 2), ("Checks", "checks/gates.csv", 1)):
        csv_header, csv_rows = read_csv(mini.data / rel)
        rows = sheet_rows(wb, sheet, first)
        assert list(rows[0]) == csv_header
        body = [r for r in rows[1:] if any(v is not None for v in r)]
        assert len(body) == len(csv_rows)
        for r, c in zip(body, csv_rows):
            for v, t in zip(r, c):
                if t == "":
                    assert v is None
                else:
                    assert v == t or (isinstance(v, (int, float)) and float(v) == float(t))
        assert wb[sheet].tables
    assert "edit" in str(wb["Leagues"]["A1"].value) and "NFL/02-config" in str(wb["Leagues"]["A1"].value)
    assert "edit" not in str(wb["Checks"]["A1"].value)
    assert wb["Scoring"].freeze_panes == "A3"
    assert set(wb["Checks"].tables) == {"tblGates"}


def test_mini_about_and_properties(mini, tmp_path):
    out = tmp_path / "x.xlsx"
    assert export(mini.data, out) == 0
    wb = openpyxl.load_workbook(out)
    about = {r[0]: r[1] for r in sheet_rows(wb, "About", 5) if r[0]}
    status = {r[0]: r[1] for r in csv.reader(open(mini.data / "status.csv", encoding="utf-8"))}
    assert about["Workbook version"] == "3.002"
    assert status["latest_season"] in about["Data through"] and f"week {status['latest_week']}" in about["Data through"]
    assert about["Generated (UTC)"] == status["generated_utc"]
    assert about["Data run id"] == status["run_id"]
    assert about["Data source"] == status["data_source"]
    assert about["Data licence"] == status["data_license"]
    assert about["Latest file"].endswith("/releases/download/nfl-workbook/NFL-Analysis.xlsx")
    assert "NFL/02-config" in about["How to change scoring"]
    for name in wb.sheetnames:
        assert about[f"Sheet {name}"]
    props = wb.properties
    assert props.title == "NFL-Analysis 3.002"
    assert props.creator == "NFL-Analysis pipeline"
    assert props.created.strftime("%Y-%m-%dT%H:%M:%SZ") == status["generated_utc"]


def test_mini_season_totals_match_recomputation(mini, tmp_path):
    out = tmp_path / "x.xlsx"
    assert export(mini.data, out) == 0
    wb = openpyxl.load_workbook(out)
    active = active_leagues(mini.data)
    sums, games = {}, {}
    last = {}
    for f in sorted((mini.data / "scored").glob("scored_*.csv")):
        for r in csv.DictReader(open(f, encoding="utf-8", newline="")):
            k = (int(r["season"]), r["season_type"], r["player_id"])
            games[k] = games.get(k, 0) + 1
            if k not in last or float(r["week"]) >= last[k][0]:
                last[k] = (float(r["week"]), r["team"], r["player_display_name"], r["position"])
            for n in active:
                sums[k, n] = sums.get((k, n), Decimal(0)) + Decimal(r[f"FF_{n}"])
    got = sheet_rows(wb, "SeasonTotals")
    leagues = [c for n in active for c in (f"FF_{n}_total", f"FF_{n}_avg")]
    assert list(got[0]) == ["season", "season_type", "player_display_name", "position", "team", "games", *leagues, "player_id"]
    assert len(got) - 1 == len(games)
    q = Decimal("0.01")

    def total(k, n):
        return float(sums[k, n].quantize(q, ROUND_HALF_UP))
    expected_order = sorted(games, key=lambda k: (-k[0], 0 if k[1] == "REG" else 1, -total(k, active[0]), k[2]))
    assert [(r[0], r[1], r[-1]) for r in got[1:]] == expected_order
    for r in got[1:]:
        k = (r[0], r[1], r[-1])
        assert r[2:5] == (last[k][2], last[k][3], last[k][1])
        assert r[5] == games[k]
        for i, n in enumerate(active):
            t = sums[k, n].quantize(q, ROUND_HALF_UP)
            assert r[6 + 2 * i] == pytest.approx(float(t), abs=1e-9)
            assert r[7 + 2 * i] == pytest.approx(float((t / games[k]).quantize(q, ROUND_HALF_UP)), abs=1e-9)
    assert wb["SeasonTotals"].freeze_panes == "D2"          # through player_display_name


def test_dispatcher_wiring(mini, tmp_path):
    out = tmp_path / "d.xlsx"
    assert dispatcher.main(["export", "--data-dir", str(mini.data), "--out", str(out)]) == 0
    assert out.stat().st_size > 1000
    assert "export" in dispatcher.USAGE


# --------------------------------------------------------------------------------------------
# cell rules

def test_number_blank_text_rules(tmp_path):
    data = tiny_data(tmp_path, [one_player("Plain")], [["1.5", "0"]])
    # make some metric values blank, zero, fractional and text-like
    pw = data / "player_week" / "player_week_2024.csv"
    header, rows = read_csv(pw)
    rows[0][header.index("passing_yards")] = ""
    rows[0][header.index("receptions")] = "0"
    rows[0][header.index("opponent_team")] = ""
    rows[0][header.index("player_id")] = "00123"          # numeric-looking identity stays text
    rows[0][header.index("position_group")] = "007"
    write(pw, header, rows)
    sc = data / "scored" / "scored_2024.csv"
    sh, srows = read_csv(sc)
    srows[0][sh.index("player_id")] = "00123"
    write(sc, sh, srows)
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    ws = openpyxl.load_workbook(out)["PlayerGames"]
    row = {c.value: ws.cell(row=2, column=i + 1) for i, c in enumerate(ws[1])}
    assert row["passing_yards"].value is None
    assert row["opponent_team"].value is None
    assert row["receptions"].value == 0 and row["receptions"].data_type == "n"
    assert row["season"].value == 2024 and isinstance(row["season"].value, int)
    assert row["week"].value == 1
    assert row["player_id"].value == "00123" and row["player_id"].data_type == "s"
    assert row["position_group"].value == "007" and row["position_group"].data_type == "s"
    assert row["FF_Alpha"].value == 1.5
    assert row["fantasy_points"].value == 1.5
    with zipfile.ZipFile(out) as z:
        sheet = z.read("xl/worksheets/sheet2.xml").decode()
    assert "<f>" not in sheet and "<f " not in sheet
    assert "inlineStr" not in sheet


def test_hostile_text_stays_text_and_valid_xml(tmp_path):
    names = ["=1+1", "+cmd|' /C calc'!A0", "-2+3", "@SUM(A1)", "A&B <x> \"q\" 'z'", "Zoë 日本語 \U0001f600",
             "ctrl\x00\x07\x1bchars", "_x0041_ literal", "two\nlines", "  padded  ", "</t></si><script>", "tab\there"]
    players = [one_player(n, pid=f"00-{i}", week=str(i + 1)) for i, n in enumerate(names)]
    data = tiny_data(tmp_path, players, [["1", "2"]] * len(names))
    out = tmp_path / "h.xlsx"
    assert export(data, out) == 0
    wb = openpyxl.load_workbook(out)
    got = [r[3] for r in sheet_rows(wb, "PlayerGames", 2)]
    expect = [re.sub("[\x00-\x08\x0b\x0c\x0e-\x1f]", "", n) for n in names]
    assert got == expect[::-1]                       # newest week first
    for cell in wb["PlayerGames"]["D"][1:]:
        assert cell.data_type == "s"           # a string, never a formula
    with zipfile.ZipFile(out) as z:
        import xml.etree.ElementTree as ET
        for n in z.namelist():
            if n.endswith((".xml", ".rels")):
                ET.fromstring(z.read(n))       # every part is well-formed
        sst = z.read("xl/sharedStrings.xml").decode()
        assert "\x00" not in sst and "\x07" not in sst
        assert "<script>" not in sst
    # SeasonTotals carries the same names
    assert [r[2] for r in sheet_rows(wb, "SeasonTotals", 2)] == [expect[names.index(n)] for n in
                                                                 sorted(names, key=lambda n: f"00-{names.index(n)}")]


def test_hostile_header_and_config_text(tmp_path):
    data = tiny_data(tmp_path, [one_player("X")], [["1", "2"]], leagues=("=Evil&Co", "B<b>"))
    out = tmp_path / "e.xlsx"
    assert export(data, out) == 0
    wb = openpyxl.load_workbook(out)
    hdr = [c.value for c in wb["PlayerGames"][1]]
    assert "FF_=Evil&Co" in hdr and "FF_B<b>" in hdr
    assert [c.name for c in wb["PlayerGames"].tables["tblPlayerGames"].tableColumns] == hdr
    assert wb["Leagues"]["A3"].value == "=Evil&Co" and wb["Leagues"]["A3"].data_type == "s"


# --------------------------------------------------------------------------------------------
# SeasonTotals arithmetic

@pytest.mark.parametrize("decimals, values, total, avg", [
    (2, ["1.005", "0"], "1.01", "0.51"),                  # half rounds up; avg of 1.01 over 2 games = 0.505 -> 0.51
    (2, ["-1.005", "0"], "-1.01", "-0.51"),               # half away from zero for negatives
    (2, ["0.1", "0.1", "0.1"], "0.3", "0.1"),             # binary float noise would give 0.30000000000000004
    (2, ["10", "0", "0"], "10", "3.33"),
    (2, ["0.03", "0.02"], "0.05", "0.03"),                # 0.025 -> 0.03
    (0, ["12.5", "0"], "13", "7"),                        # 12.5 -> 13; 13/2 = 6.5 -> 7
    (0, ["-12.5", "0"], "-13", "-7"),
    (3, ["1.0005", "1"], "2.001", "1"),                   # total 2.0005 -> 2.001; avg 1.0005 -> 1.001? see below
])
def test_season_totals_rounding(tmp_path, decimals, values, total, avg):
    games = len(values)
    players = [one_player("P", week=str(i + 1)) for i in range(games)]
    data = tiny_data(tmp_path, players, [[v, "0"] for v in values], decimals=decimals)
    out = tmp_path / "r.xlsx"
    assert export(data, out) == 0
    wb = openpyxl.load_workbook(out)
    rows = sheet_rows(wb, "SeasonTotals", 2)
    assert len(rows) == 1
    t = Decimal(sum(Decimal(v) for v in values)).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)
    a = (t / games).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)
    assert rows[0][5] == games
    assert rows[0][6] == pytest.approx(float(t), abs=1e-12)
    assert rows[0][7] == pytest.approx(float(a), abs=1e-12)
    if decimals != 3:
        assert rows[0][6] == pytest.approx(float(Decimal(total)), abs=1e-12)
        assert rows[0][7] == pytest.approx(float(Decimal(avg)), abs=1e-12)
    assert rows[0][8:10] == (0, 0)                        # the second league: zeros stay numbers
    assert rows[0][10] == "00-1"                          # player_id is the last column


def test_season_totals_groups_and_last_team(tmp_path):
    # Same player on two teams in one season; the later week decides team. POST is a separate row.
    players = [["1", "REG", "00-9", "Mover", "WR", "AAA"], ["5", "REG", "00-9", "Mover", "WR", "BBB"],
               ["2", "REG", "00-8", "Other", "WR", "CCC"], ["1", "POST", "00-9", "Mover", "WR", "BBB"]]
    data = tiny_data(tmp_path, players, [["1", "1"], ["2", "2"], ["4", "4"], ["8", "8"]])
    out = tmp_path / "g.xlsx"
    assert export(data, out) == 0
    rows = sheet_rows(openpyxl.load_workbook(out), "SeasonTotals", 2)
    # REG before POST; within REG the higher Alpha total first; team of the later week
    assert [(r[0], r[1], r[10], r[4], r[5], r[6], r[7]) for r in rows] == [
        (2024, "REG", "00-8", "CCC", 1, 4, 4), (2024, "REG", "00-9", "BBB", 2, 3, 1.5), (2024, "POST", "00-9", "BBB", 1, 8, 8)]


def test_multiple_seasons_newest_first(tmp_path):
    first = ([one_player("Old")], [["1", "1"]])
    data = tiny_data(tmp_path, [one_player("New")], [["2", "2"]], season=2024, extra_seasons={2023: first})
    out = tmp_path / "m.xlsx"
    assert export(data, out) == 0
    wb = openpyxl.load_workbook(out)
    assert [(r[0], r[3]) for r in sheet_rows(wb, "PlayerGames", 2)] == [(2024, "New"), (2023, "Old")]
    assert [r[0] for r in sheet_rows(wb, "SeasonTotals", 2)] == [2024, 2023]


def test_empty_bonus_table_still_valid(tmp_path):
    data = tiny_data(tmp_path, [one_player("X")], [["1", "2"]])
    out = tmp_path / "b.xlsx"
    assert export(data, out) == 0
    ws = openpyxl.load_workbook(out)["Bonus"]
    assert ws.tables["tblBonus"].ref == "A2:G3"           # header plus one empty data row


# --------------------------------------------------------------------------------------------
# limits, determinism, failure path

def test_deterministic_bytes(mini, tmp_path):
    a, b = tmp_path / "a" / "w.xlsx", tmp_path / "b" / "w.xlsx"
    assert export(mini.data, a) == 0 and export(mini.data, b) == 0
    assert a.read_bytes() == b.read_bytes()
    with zipfile.ZipFile(a) as z:
        assert {i.date_time for i in z.infolist()} == {(1980, 1, 1, 0, 0, 0)}
        assert z.namelist()[0] == "[Content_Types].xml"


def test_data_dir_never_changed(mini, tmp_path):
    from miniverse import snapshot
    before = snapshot(mini.data)
    assert export(mini.data, tmp_path / "x.xlsx") == 0
    assert snapshot(mini.data) == before


def no_leftovers(out: Path) -> None:
    assert not out.exists()
    assert not list(out.parent.glob("*.tmp")) if out.parent.exists() else True


def test_row_limit_is_an_error(tmp_path, monkeypatch, capsys):
    data = tiny_data(tmp_path, [one_player("A"), one_player("B", pid="00-2")], [["1", "1"]] * 2)
    monkeypatch.setattr(export_xlsx, "MAX_DATA_ROWS", 1)
    out = tmp_path / "o" / "x.xlsx"
    assert export(data, out) == 1
    assert "data rows" in capsys.readouterr().err
    no_leftovers(out)


def test_column_limit_is_an_error(tmp_path, monkeypatch, capsys):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "1"]])
    monkeypatch.setattr(export_xlsx, "MAX_COLUMNS", 10)
    out = tmp_path / "o" / "x.xlsx"
    assert export(data, out) == 1
    assert "columns" in capsys.readouterr().err
    no_leftovers(out)


def test_long_text_is_an_error_not_truncated(tmp_path, capsys):
    data = tiny_data(tmp_path, [one_player("N" * 32_768)], [["1", "1"]])
    out = tmp_path / "o" / "x.xlsx"
    assert export(data, out) == 1
    assert "32,767" in capsys.readouterr().err
    no_leftovers(out)
    ok = tiny_data(tmp_path / "ok", [one_player("N" * 32_767)], [["1", "1"]])      # exactly the limit is fine
    assert export(ok, tmp_path / "ok.xlsx") == 0
    assert len(sheet_rows(openpyxl.load_workbook(tmp_path / "ok.xlsx"), "PlayerGames", 2)[0][3]) == 32_767


@pytest.mark.parametrize("damage, message", [
    ("no_scored", "scored"),
    ("no_status", "status.csv"),
    ("no_generated", "generated_utc"),
    ("bad_round", "RoundDecimals"),
    ("key_mismatch", "has no row for"),
    ("short_scored", "different row counts"),
    ("ragged", "values but"),
    ("no_active", "Active"),
    ("bad_number", "not a number"),
    ("no_data_dir", "not found"),
])
def test_failure_leaves_no_partial_file(tmp_path, capsys, damage, message):
    data = tiny_data(tmp_path, [one_player("A"), one_player("B", pid="00-2", week="2")], [["1", "1"], ["2", "2"]])
    out = tmp_path / "o" / "x.xlsx"
    if damage == "no_scored":
        (data / "scored" / "scored_2024.csv").unlink()
    elif damage == "no_status":
        (data / "status.csv").unlink()
    elif damage == "no_generated":
        write(data / "status.csv", ["key", "value"], [["run_id", "R"], ["data_contract_version", "1"], ["latest_season", "2024"]])
    elif damage == "bad_round":
        write(data / "config" / "pipeline_config.csv", ["Setting", "Value", "Allowed_Values", "Description"], [["RoundDecimals", "9", "", ""]])
    elif damage == "key_mismatch":
        h, r = read_csv(data / "scored" / "scored_2024.csv")
        r[1][3] = "00-OTHER"
        write(data / "scored" / "scored_2024.csv", h, r)
    elif damage == "short_scored":
        h, r = read_csv(data / "scored" / "scored_2024.csv")
        write(data / "scored" / "scored_2024.csv", h, r[:1])
    elif damage == "ragged":
        h, r = read_csv(data / "player_week" / "player_week_2024.csv")
        r[0] = r[0][:5]
        write(data / "player_week" / "player_week_2024.csv", h, r)
    elif damage == "no_active":
        h, r = read_csv(data / "config" / "leagues.csv")
        write(data / "config" / "leagues.csv", h, [[*x[:2], "No", *x[3:]] for x in r])
    elif damage == "bad_number":
        h, r = read_csv(data / "scored" / "scored_2024.csv")
        r[1][h.index("FF_Alpha")] = "n/a"
        write(data / "scored" / "scored_2024.csv", h, r)
    elif damage == "no_data_dir":
        data = tmp_path / "nowhere"
    assert export(data, out) == 1
    assert message in capsys.readouterr().err
    no_leftovers(out)


def test_failure_after_writing_started_removes_temp_file(tmp_path, capsys):
    # The bad value is on the second row, after the big sheet has begun streaming.
    data = tiny_data(tmp_path, [one_player("A"), one_player("B", pid="00-2", week="2")], [["1", "1"], ["2", "x"]])
    out = tmp_path / "o" / "x.xlsx"
    assert export(data, out) == 1
    assert list(out.parent.iterdir()) == []


def test_existing_file_survives_a_failed_run(tmp_path):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "1"]])
    out = tmp_path / "o" / "x.xlsx"
    assert export(data, out) == 0
    good = out.read_bytes()
    (data / "scored" / "scored_2024.csv").unlink()
    assert export(data, out) == 1
    assert out.read_bytes() == good
    assert [p.name for p in out.parent.iterdir()] == ["x.xlsx"]


# --------------------------------------------------------------------------------------------
# package structure (what Excel checks before it opens a file)

def test_package_is_consistent(mini, tmp_path):
    import posixpath
    import xml.etree.ElementTree as ET
    out = tmp_path / "p.xlsx"
    assert export(mini.data, out) == 0
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert len(names) == len(set(names))
        ct = ET.fromstring(z.read("[Content_Types].xml"))
        over = {o.get("PartName").lstrip("/") for o in ct if o.tag.endswith("Override")}
        assert over <= set(names)
        for n in names:
            if n != "[Content_Types].xml" and n not in over:
                assert n.endswith((".rels", ".xml"))
        for n in names:                                                     # every relationship resolves
            if n.endswith(".rels"):
                base = posixpath.dirname(posixpath.dirname(n))
                for rel in ET.fromstring(z.read(n)):
                    if rel.get("TargetMode") != "External":
                        assert posixpath.normpath(posixpath.join(base, rel.get("Target"))) in names
        # shared string counts agree with the cells
        refs = sum(len(re.findall(rb't="s"', z.read(n))) for n in names if n.startswith("xl/worksheets/sheet"))
        sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
        assert int(sst.get("count")) == refs and int(sst.get("uniqueCount")) == len(sst)
        # unique table ids and names; ranges and column counts agree with the sheet
        tables = [ET.fromstring(z.read(n)) for n in names if n.startswith("xl/tables/")]
        assert len({t.get("id") for t in tables}) == len(tables) == 7
        assert len({t.get("name").lower() for t in tables}) == len(tables)
        for t in tables:
            cols = t.find("{*}tableColumns")
            assert int(cols.get("count")) == len(cols)
            assert t.find("{*}autoFilter").get("ref") == t.get("ref")
        workbook = z.read("xl/workbook.xml").decode()
        assert "definedName" not in workbook and "externalReference" not in workbook
        assert not [n for n in names if "vbaProject" in n or "connections" in n or "customXml" in n or "queryTable" in n]
        for n in names:
            if n.startswith("xl/worksheets/sheet"):
                assert b"<f>" not in z.read(n) and b"<f " not in z.read(n)


def test_xml_character_helpers():
    assert export_xlsx.clean_text("a\x00b\x0bc￾퟿d") == "abc퟿d"
    assert export_xlsx.esc("a_x0041_b & <c>") == "a_x005F_x0041_b &amp; &lt;c&gt;"
    assert export_xlsx.col_letter(1) == "A" and export_xlsx.col_letter(27) == "AA" and export_xlsx.col_letter(16384) == "XFD"
    assert [export_xlsx.is_number(v) for v in ("0", "-1.5", "1e5", "007", "+1", "1,5", "nan", "inf", "1e999", ".5", "")] == \
        [True, True, True, False, False, False, False, False, False, False, False]


def test_copy_of_mini_is_not_modified(mini, tmp_path):
    shutil.copytree(mini.data, tmp_path / "copy")
    assert export(tmp_path / "copy", tmp_path / "c.xlsx") == 0


@pytest.mark.parametrize("value", ["2", "", None])
def test_unknown_data_contract_version_is_refused(tmp_path, capsys, value):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "1"]])
    h, r = read_csv(data / "status.csv")
    r = [x for x in r if x[0] != "data_contract_version"]
    if value is not None:
        r.append(["data_contract_version", value])
    write(data / "status.csv", h, r)
    out = tmp_path / "o" / "x.xlsx"
    assert export(data, out) == 1
    err = capsys.readouterr().err
    assert "data_contract_version" in err and "understands version '1'" in err
    assert (repr(value) if value is not None else "is missing") in err
    no_leftovers(out)


# ============================================================================================
# Revision 2 (contract 13.2 / 13.3 as revised; findings A1-01..A1-18, R1-m1..m6, R2-04, R2-13, R2-14)
# ============================================================================================

NSM = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def raw_header_vs_table(path: Path) -> int:
    """For every table: the raw (still _xHHHH_ escaped) text of each header cell equals the tableColumn name,
    the names are unique the way Excel compares them, and `ref` covers the header and every row. Returns the
    number of tables checked."""
    import xml.etree.ElementTree as ET
    checked = 0
    with zipfile.ZipFile(path) as z:
        sst = ["".join(t.text or "" for t in si.iter(NSM + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        for i in range(1, 9):
            rel = f"xl/worksheets/_rels/sheet{i}.xml.rels"
            m = re.search(r"table(\d+)\.xml", z.read(rel).decode()) if rel in z.namelist() else None
            if not m:
                continue
            table = ET.fromstring(z.read(f"xl/tables/table{m.group(1)}.xml"))
            ref = table.get("ref")
            first, last = (int(re.sub("[A-Z]", "", x)) for x in ref.split(":"))
            rows = {int(r.get("r")): r for r in ET.fromstring(z.read(f"xl/worksheets/sheet{i}.xml")).iter(NSM + "row")}
            header = [sst[int(c.find(NSM + "v").text)] for c in rows[first]]
            names = [c.get("name") for c in table.find(NSM + "tableColumns")]
            assert header == names
            assert len(names) <= 16384 and all(0 < len(n) <= 255 for n in names)
            keys = [" ".join(n.split()).casefold() for n in names]
            assert len(set(keys)) == len(keys)
            assert ref.split(":")[1].rstrip("0123456789") == export_xlsx.col_letter(len(names))
            assert max(rows) == last
            checked += 1
    return checked


def two_season_data(tmp_path: Path, **kw) -> Path:
    older = ([one_player("Old", pid="00-1", week="1"), one_player("Old", pid="00-1", week="2")], [["7", "70"], ["8", "80"]])
    return tiny_data(tmp_path, [one_player("New", pid="00-1", week="1"), one_player("Other", pid="00-2", week="1")],
                     [["1", "10"], ["2", "20"]], season=2024, extra_seasons={2023: older}, **kw)


def played(path: Path) -> dict:
    """{(season, week, season_type, player_id): {column: value}} of PlayerGames."""
    rows = sheet_rows(openpyxl.load_workbook(path), "PlayerGames")
    return {(r[0], r[1], r[2], r[rows[0].index("player_id")]): dict(zip(rows[0], r)) for r in rows[1:]}


# --- layout (13.2) ---------------------------------------------------------------------------

def test_player_games_layout_order_and_freeze(tmp_path):
    # POST weeks (19+) sort above REG; same week keeps the published order; seasons newest first.
    players = [["1", "REG", "00-1", "A", "QB", "NE"], ["19", "POST", "00-2", "B", "QB", "NE"],
               ["2", "REG", "00-3", "C", "QB", "NE"], ["19", "POST", "00-4", "D", "QB", "NE"], ["2", "REG", "00-5", "E", "QB", "NE"]]
    older = ([["3", "REG", "00-9", "Z", "QB", "NE"]], [["5", "5"]])
    data = tiny_data(tmp_path, players, [["1", "1"]] * 5, extra_seasons={2023: older})
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    wb = openpyxl.load_workbook(out)
    rows = sheet_rows(wb, "PlayerGames")
    assert list(rows[0]) == FRONT + ["FF_Alpha", "FF_Beta"] + BACK + ["passing_yards", "receptions"]
    assert [(r[0], r[1], r[3]) for r in rows[1:]] == [(2024, 19, "B"), (2024, 19, "D"), (2024, 2, "C"), (2024, 2, "E"),
                                                      (2024, 1, "A"), (2023, 3, "Z")]
    assert wb["PlayerGames"].freeze_panes == "E2" and wb["SeasonTotals"].freeze_panes == "D2"


def test_season_totals_order_newest_first_reg_before_post_then_total_then_id(tmp_path):
    players = [["1", "REG", "00-B", "B", "QB", "NE"], ["1", "REG", "00-A", "A", "QB", "NE"], ["1", "REG", "00-C", "C", "QB", "NE"],
               ["1", "REG", "00-D", "D", "QB", "NE"], ["19", "POST", "00-A", "A", "QB", "NE"]]
    older = ([["1", "REG", "00-Z", "Z", "QB", "NE"]], [["99", "0"]])
    data = tiny_data(tmp_path, players, [["5", "0"], ["5", "0"], ["9", "0"], ["-3", "0"], ["100", "0"]], extra_seasons={2023: older})
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    rows = sheet_rows(openpyxl.load_workbook(out), "SeasonTotals", 2)
    assert [(r[0], r[1], r[-1]) for r in rows] == [(2024, "REG", "00-C"), (2024, "REG", "00-A"), (2024, "REG", "00-B"),
                                                   (2024, "REG", "00-D"), (2024, "POST", "00-A"), (2023, "REG", "00-Z")]


def test_dictionary_has_one_row_per_player_games_column(mini, tmp_path):
    out = tmp_path / "d.xlsx"
    assert export(mini.data, out) == 0
    wb = openpyxl.load_workbook(out)
    header = [c.value for c in wb["PlayerGames"][1]]
    d = sheet_rows(wb, "Dictionary")
    with open(mini.data / "dictionary.csv", encoding="utf-8") as handle:
        file_rows = list(csv.reader(handle))[1:]
    metrics_in_file = file_rows
    assert list(d[0]) == ["metric", "category", "description", "source", "applies_to"]
    assert [r[0] for r in d[1:]] == header                  # every column, in the sheet's order
    assert all(r[2] for r in d[1:1 + len(header) - len(metrics_in_file)])     # every column the exporter writes has a description
    leagues = {r["League"]: r["Description"] for r in csv.DictReader(open(mini.data / "config" / "leagues.csv", encoding="utf-8"))}
    for r in d[1:]:
        if r[0].startswith("FF_"):
            assert r[0][3:] in r[2] and leagues[r[0][3:]] in r[2]
    assert [[x or "" for x in r[:4]] for r in d[1 + len(header) - len(file_rows):]] == [r[:4] for r in file_rows]


def test_about_rows_leagues_in_progress_and_links(tmp_path):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "2"]], in_progress=True)
    out = tmp_path / "a.xlsx"
    assert export(data, out) == 0
    wb = openpyxl.load_workbook(out)
    ws = wb["About"]
    rows = [(r[0], r[1]) for r in ws.iter_rows(min_row=5, values_only=True) if r[0]]
    items = [i for i, _ in rows]
    assert items == ["Workbook version", "Leagues scored", "Column FF_Alpha", "Column FF_Beta", "Data through", "Latest week",
                     "Opening this file", "Generated (UTC)", "Data run id", "Pipeline version", "Data contract version", "Seasons",
                     "Gates passed", "Gates warned", "Gates failed", "Data source", "Data licence", "nflverse address",
                     "Licence address", "Latest file", "How to change scoring", "Guide",
                     *[f"Sheet {n}" for n in wb.sheetnames]]
    about = dict(rows)
    assert "Alpha, Beta" in about["Leagues scored"]
    assert "FF_Alpha" in about["Column FF_Alpha"] or "Alpha" in about["Column FF_Alpha"]
    assert "incomplete" in about["Latest week"] and "week 3" in about["Latest week"]
    links = {c.value: c.hyperlink.target for r in ws.iter_rows(min_row=5) for c in r if c.hyperlink}
    assert links[export_xlsx.RELEASE_URL] == export_xlsx.RELEASE_URL
    assert links[export_xlsx.AUTOMATION_URL] == export_xlsx.AUTOMATION_URL
    assert set(links) == {export_xlsx.NFLVERSE_URL, export_xlsx.LICENSE_URL, export_xlsx.RELEASE_URL, export_xlsx.AUTOMATION_URL}
    done = tiny_data(tmp_path / "done", [one_player("A")], [["1", "2"]], in_progress=False)
    assert export(done, tmp_path / "b.xlsx") == 0
    assert "Latest week" not in [r[0] for r in openpyxl.load_workbook(tmp_path / "b.xlsx")["About"].iter_rows(min_row=5, values_only=True)]


# --- A1-01: scored values by key and column name ----------------------------------------------

def edit_scored(data: Path, season: int, fn) -> None:
    path = data / "scored" / f"scored_{season}.csv"
    h, r = read_csv(path)
    h, r = fn(h, r)
    write(path, h, r)


def test_scored_extra_column_before_a_league_changes_nothing(tmp_path):
    """A1-01 reproduction: an inserted column before FF_Alpha used to shift every value in that season."""
    data = two_season_data(tmp_path)
    clean = tmp_path / "clean.xlsx"
    assert export(data, clean) == 0
    edit_scored(data, 2024, lambda h, r: (h[:7] + ["FF_New"] + h[7:], [x[:7] + ["999"] + x[7:] for x in r]))
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    assert played(out) == played(clean)
    assert played(out)[(2024, 1, "REG", "00-1")]["FF_Alpha"] == 1


def test_scored_columns_swapped_and_rows_reordered_still_match_by_key(tmp_path):
    data = two_season_data(tmp_path)
    clean = tmp_path / "clean.xlsx"
    assert export(data, clean) == 0

    def shuffle(h, r):
        i, j = h.index("FF_Alpha"), h.index("FF_Beta")
        h[i], h[j] = h[j], h[i]
        for x in r:
            x[i], x[j] = x[j], x[i]
        return h, r[::-1]
    for season in (2023, 2024):
        edit_scored(data, season, shuffle)
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    assert played(out) == played(clean)
    pg = played(out)
    assert pg[(2023, 2, "REG", "00-1")]["FF_Alpha"] == 8 and pg[(2023, 2, "REG", "00-1")]["FF_Beta"] == 80


def test_totals_use_the_same_matched_values(tmp_path):
    data = two_season_data(tmp_path)
    edit_scored(data, 2023, lambda h, r: (h[:7] + ["FF_New"] + h[7:], [x[:7] + ["999"] + x[7:] for x in r]))
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    rows = {(r[0], r[-1]): r for r in sheet_rows(openpyxl.load_workbook(out), "SeasonTotals", 2)}
    assert rows[(2023, "00-1")][6] == 15 and rows[(2023, "00-1")][8] == 150


@pytest.mark.parametrize("damage, message", [
    ("drop_league_col", "missing column 'FF_Beta'"),
    ("drop_key_col", "missing column 'player_id'"),
    ("duplicate_league_col", "appears twice"),
    ("extra_scored_row", "different row counts"),
    ("missing_scored_row", "different row counts"),
    ("other_key", "has no row for"),
    ("wrong_week", "has no row for"),
    ("empty_scored", "is empty"),
])
def test_scored_that_does_not_match_player_week_is_an_error(tmp_path, capsys, damage, message):
    data = two_season_data(tmp_path)
    if damage == "drop_league_col":
        edit_scored(data, 2023, lambda h, r: (h[:-1], [x[:-1] for x in r]))
    elif damage == "drop_key_col":
        edit_scored(data, 2023, lambda h, r: (h[:3] + h[4:], [x[:3] + x[4:] for x in r]))
    elif damage == "duplicate_league_col":
        edit_scored(data, 2023, lambda h, r: (h + ["FF_Alpha"], [x + ["1"] for x in r]))
    elif damage == "extra_scored_row":
        edit_scored(data, 2023, lambda h, r: (h, r + [["2023", "9", "REG", "00-7", "X", "QB", "NE", "1", "1", "1", "1"]]))
    elif damage == "missing_scored_row":
        edit_scored(data, 2024, lambda h, r: (h, r[:1]))
    elif damage == "other_key":
        edit_scored(data, 2024, lambda h, r: (h, [r[0], [r[1][0], r[1][1], r[1][2], "00-7", *r[1][4:]]]))
    elif damage == "wrong_week":
        edit_scored(data, 2024, lambda h, r: (h, [[x[0], "5", *x[2:]] for x in r]))
    elif damage == "empty_scored":
        (data / "scored" / "scored_2023.csv").write_bytes(b"")
    out = tmp_path / "o" / "x.xlsx"
    assert export(data, out) == 1
    err = capsys.readouterr().err
    assert message in err and "Traceback" not in err
    no_leftovers(out)


def test_week_tie_keeps_the_later_published_row(tmp_path):
    """The last-game rule: highest week; on a tie the later published row. (Only reachable with a repeated key,
    which published data never has, so the matching of repeated keys is tested here too.)"""
    players = [["3", "REG", "00-1", "Early", "WR", "AAA"], ["3", "REG", "00-1", "Late", "TE", "BBB"], ["2", "REG", "00-1", "Wk2", "QB", "CCC"]]
    data = tiny_data(tmp_path, players, [["1", "1"], ["2", "2"], ["4", "4"]])
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    wb = openpyxl.load_workbook(out)
    (row,) = sheet_rows(wb, "SeasonTotals", 2)
    assert (row[2], row[3], row[4], row[5]) == ("Late", "TE", "BBB", 3)
    assert row[6] == 7                                        # 1 + 2 + 4: repeated keys matched in published order
    assert [r[3] for r in sheet_rows(wb, "PlayerGames", 2)] == ["Early", "Late", "Wk2"]
    assert [r[7] for r in sheet_rows(wb, "PlayerGames", 2)] == [1, 2, 4]
    edit_scored(data, 2024, lambda h, r: (h, r + [r[0]]))      # one scored row too many for a repeated key
    assert export(data, tmp_path / "x.xlsx") == 1


def test_inactive_league_between_active_ones_and_config_order(tmp_path):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "2"]], leagues=("Alpha", "Beta"))
    h, r = read_csv(data / "config" / "leagues.csv")
    write(data / "config" / "leagues.csv", h, [["Beta", "b", "Yes", "", ""], ["Mid", "m", "No", "", ""], ["Alpha", "a", "Yes", "", ""]])
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    wb = openpyxl.load_workbook(out)
    hdr = [c.value for c in wb["PlayerGames"][1]]
    assert hdr[7:9] == ["FF_Beta", "FF_Alpha"] and "FF_Mid" not in hdr          # the owner's order, inactive left out
    row = sheet_rows(wb, "PlayerGames", 2)[0]
    assert row[7] == 2 and row[8] == 1                                          # values follow the names, not the file order
    st = [c.value for c in wb["SeasonTotals"][1]]
    assert st[6:10] == ["FF_Beta_total", "FF_Beta_avg", "FF_Alpha_total", "FF_Alpha_avg"] and st[-1] == "player_id"
    assert [r[0] for r in sheet_rows(wb, "Dictionary", 2)][7:9] == ["FF_Beta", "FF_Alpha"]


def test_dst_rows(tmp_path):
    data = tiny_data(tmp_path, [["1", "REG", "DST_ARI", "ARI D/ST", "DST", "ARI"], ["2", "REG", "DST_ARI", "ARI D/ST", "DST", "ARI"]],
                     [["3.5", "4"], ["-1", "0"]])
    pw = data / "player_week" / "player_week_2024.csv"
    h, r = read_csv(pw)
    for x in r:
        x[h.index("passing_yards")] = x[h.index("receptions")] = ""             # a team defense has no player stats
    write(pw, h, r)
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    wb = openpyxl.load_workbook(out)
    rows = sheet_rows(wb, "PlayerGames", 2)
    ix = {n: i for i, n in enumerate(c.value for c in wb["PlayerGames"][1])}
    assert [r[ix["player_id"]] for r in rows] == ["DST_ARI", "DST_ARI"] and rows[0][ix["position"]] == "DST"
    assert all(r[ix["passing_yards"]] is None and r[ix["receptions"]] is None for r in rows)
    assert [r[ix["FF_Alpha"]] for r in rows] == [-1, 3.5]
    (tot,) = sheet_rows(wb, "SeasonTotals", 2)
    assert (tot[2], tot[3], tot[4], tot[5], tot[6], tot[7], tot[-1]) == ("ARI D/ST", "DST", "ARI", 2, 2.5, 1.25, "DST_ARI")


@pytest.mark.parametrize("decimals, fmt", [(0, "0"), (2, "0.00"), (3, "0.000"), (6, "0.000000")])
def test_points_number_format_follows_round_decimals(tmp_path, decimals, fmt):
    data = tiny_data(tmp_path, [one_player("A")], [["1.5", "2"]], decimals=decimals)
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    wb = openpyxl.load_workbook(out)
    pg, st = wb["PlayerGames"], wb["SeasonTotals"]
    hx = {c.value: c.column - 1 for c in pg[1]}
    assert pg.cell(row=2, column=hx["FF_Alpha"] + 1).number_format == fmt
    assert pg.cell(row=2, column=hx["fantasy_points"] + 1).number_format == fmt
    assert pg.cell(row=2, column=hx["season"] + 1).number_format == "0"
    assert pg.cell(row=2, column=hx["passing_yards"] + 1).number_format == "General"
    assert st["G2"].number_format == fmt and st["H2"].number_format == fmt and st["F2"].number_format == "0"


@pytest.mark.parametrize("values, total, avg", [
    (["-2"] + ["0"] * 15, "-2", "-0.13"),                  # -2 / 16 = -0.125, half away from zero
    (["-0.62", "0", "0", "0"], "-0.62", "-0.16"),          # -0.155
    (["-0.08"] + ["0"] * 15, "-0.08", "-0.01"),            # -0.005
])
def test_negative_average_half_ties_over_many_games(tmp_path, values, total, avg):
    players = [one_player("P", week=str(i + 1)) for i in range(len(values))]
    data = tiny_data(tmp_path, players, [[v, "0"] for v in values])
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    (row,) = sheet_rows(openpyxl.load_workbook(out), "SeasonTotals", 2)
    assert row[5] == len(values) and row[6] == pytest.approx(float(total)) and row[7] == pytest.approx(float(avg))


def test_theme_is_not_used_anywhere(mini, tmp_path):
    out = tmp_path / "t.xlsx"
    assert export(mini.data, out) == 0
    with zipfile.ZipFile(out) as z:
        assert not [n for n in z.namelist() if "theme" in n]
        for n in z.namelist():
            if n.endswith(".xml") and n != "xl/worksheets/sheet2.xml":
                assert b"theme" not in z.read(n).lower().replace(b"tablestyle", b""), n
        assert b"theme=" not in z.read("xl/worksheets/sheet2.xml")


# --- A1-02 / A1-03 / A1-07 / A1-08 / A1-12: column names ---------------------------------------

def rename_scoring_headers(data: Path, mapping: dict) -> None:
    h, r = read_csv(data / "config" / "scoring_weights.csv")
    write(data / "config" / "scoring_weights.csv", [mapping.get(c, c) for c in h], r)


@pytest.mark.parametrize("name", ["Not_x0041_es", "_x005F_x0041_", "a_x0041__x0042_b", "_x0041_", "x_x005F_y_x005F_"])
def test_x_escape_syntax_is_protected_in_header_cells_and_table_columns(tmp_path, name):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "2"]])
    rename_scoring_headers(data, {"Notes": name})
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    assert raw_header_vs_table(out) == 7
    with zipfile.ZipFile(out) as z:
        decoded = re.sub(r"_x([0-9A-Fa-f]{4})_", lambda m: chr(int(m.group(1), 16)), z.read("xl/tables/table4.xml").decode())
    assert f'name="{name}"' in decoded                       # what Excel decodes is exactly the text we meant
    assert openpyxl.load_workbook(out)["Scoring"].tables["tblScoring"] is not None


@pytest.mark.parametrize("a, b", [("A B", "A\nB"), ("A B", "A\tB"), ("A B", "A  B"), ("Alpha", "ALPHA"), ("x", " x"), ("a\r\nb", "A B")])
def test_names_that_are_the_same_to_excel_are_refused(tmp_path, capsys, a, b):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "2"]], leagues=(a, b))
    out = tmp_path / "o" / "x.xlsx"
    assert export(data, out) == 1
    err = capsys.readouterr().err
    assert "duplicate column name" in err and "Traceback" not in err
    no_leftovers(out)


def test_scoring_header_duplicates_after_normalisation_name_the_sheet(tmp_path, capsys):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "2"]])
    rename_scoring_headers(data, {"Category": "NOTES", "Metric": "Metric"})
    assert export(data, tmp_path / "x.xlsx") == 1
    err = capsys.readouterr().err
    assert "Scoring" in err and "duplicate column name" in err and "xl/worksheets" not in err


def test_long_header_is_refused_and_255_is_allowed(tmp_path, capsys):
    ok = tiny_data(tmp_path / "ok", [one_player("A")], [["1", "2"]], leagues=("L" * 251, "B"))     # "FF_" + 251 = 254 ... plus _total below
    assert export(ok, tmp_path / "ok.xlsx") == 1                       # FF_<251>_total is 260 characters
    assert "255" in capsys.readouterr().err
    fits = tiny_data(tmp_path / "fits", [one_player("A")], [["1", "2"]], leagues=("L" * 240, "B"))  # FF_ + 240 + _total = 249
    assert export(fits, tmp_path / "fits.xlsx") == 0
    assert raw_header_vs_table(tmp_path / "fits.xlsx") == 7
    with zipfile.ZipFile(tmp_path / "fits.xlsx") as z:
        widths = [float(w) for w in re.findall(r'width="([0-9.]+)"', z.read("xl/worksheets/sheet2.xml").decode())]
        assert max(widths) <= 255
    too = tiny_data(tmp_path / "too", [one_player("A")], [["1", "2"]], leagues=("L" * 300, "B"))
    assert export(too, tmp_path / "too.xlsx") == 1
    assert "255" in capsys.readouterr().err


def test_empty_column_name_is_refused(tmp_path, capsys):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "2"]])
    rename_scoring_headers(data, {"Notes": " \t "})
    assert export(data, tmp_path / "x.xlsx") == 1
    assert "no name" in capsys.readouterr().err


# --- A1-04 / R1-m6: generated_utc and file properties ------------------------------------------

def set_status(data: Path, key: str, value: str) -> None:
    h, r = read_csv(data / "status.csv")
    write(data / "status.csv", h, [[k, value if k == key else v] for k, v in r])


@pytest.mark.parametrize("value", ["yesterday", "2026&<", "2026-01-02T03:04:05Z\x01", "2026-13-45T99:99:99Z", "2026-01-02 03:04:05",
                                   "2026-01-02T03:04:05", "2026-01-02T03:04:05+00:00", "0001-01-01T00:00:00Z", "2026-01-02T03:04:05Z\n"])
def test_generated_utc_must_be_an_iso_utc_timestamp(tmp_path, capsys, value):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "2"]])
    set_status(data, "generated_utc", value)
    out = tmp_path / "o" / "x.xlsx"
    assert export(data, out) == 1
    err = capsys.readouterr().err
    assert "generated_utc" in err and "\x01" not in err
    no_leftovers(out)


def test_file_properties_are_clean_and_readable(mini, tmp_path):
    import xml.etree.ElementTree as ET
    out = tmp_path / "p.xlsx"
    assert export(mini.data, out) == 0
    with zipfile.ZipFile(out) as z:
        core = ET.fromstring(z.read("docProps/core.xml"))
        app = z.read("docProps/app.xml").decode()
    text = ET.tostring(core, encoding="unicode")
    assert "NFL-Analysis pipeline" in text and "NFL-Analysis 3.002" in text
    assert "NFL-Analysis pipeline" in app
    props = openpyxl.load_workbook(out).properties
    assert props.creator == "NFL-Analysis pipeline" and props.lastModifiedBy == "NFL-Analysis pipeline"
    assert props.modified.year == 2026 or props.modified.year >= 2020


# --- A1-05 / A1-09 / A1-13: numbers ------------------------------------------------------------

@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-inf", "Infinity", "-Infinity", "1e400", "1e-400", "1e999999999999", "1e60", "5e-324", "1e301"])
def test_unusable_league_numbers_name_file_line_and_column(tmp_path, capsys, value):
    data = tiny_data(tmp_path, [one_player("A"), one_player("B", pid="00-2", week="2")], [["1", "1"], ["2", "2"]])
    edit_scored(data, 2024, lambda h, r: (h, [r[0], [*r[1][:9], value, r[1][10]]]))
    out = tmp_path / "o" / "x.xlsx"
    assert export(data, out) == 1
    err = capsys.readouterr().err
    assert "scored_2024.csv line 3" in err and "FF_Alpha" in err and value[:40] in err
    assert "InvalidOperation" not in err and "Traceback" not in err
    no_leftovers(out)


@pytest.mark.parametrize("value", ["nan", "inf", "-Infinity", "1e400", "1e-400"])
def test_unusable_metric_numbers_are_errors_not_text(tmp_path, capsys, value):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "1"]])
    pw = data / "player_week" / "player_week_2024.csv"
    h, r = read_csv(pw)
    r[0][h.index("receptions")] = value
    write(pw, h, r)
    assert export(data, tmp_path / "x.xlsx") == 1
    err = capsys.readouterr().err
    assert "player_week_2024.csv line 2" in err and "receptions" in err and "Traceback" not in err


@pytest.mark.parametrize("value", ["+3", ".5", " 7", "12.5 ", "1_0", "n/a", "٣", "0x10", "1,5", "007"])
def test_league_values_must_be_plain_numbers_in_both_sheets(tmp_path, capsys, value):
    data = tiny_data(tmp_path, [one_player("A")], [[value, "1"]])
    assert export(data, tmp_path / "x.xlsx") == 1               # one parser: no "text in PlayerGames, summed in SeasonTotals"
    assert "FF_Alpha" in capsys.readouterr().err


def test_number_problem_rules():
    for ok in ("0", "-0", "1.5", "1e5", "1E-5", "1e300", "1e-300", "123456789012345678"):
        assert export_xlsx.number_problem(ok) is None and export_xlsx.is_number(ok)
    for bad in ("nan", "+Inf", "-infinity", "1e301", "1e-301", "1e-400"):
        assert export_xlsx.number_problem(bad) and not export_xlsx.is_number(bad)
    for text in ("abc", "007", "+1", ".5", ""):
        assert export_xlsx.number_problem(text) is None and not export_xlsx.is_number(text)


def test_league_value_with_many_digits_is_kept_exactly(tmp_path):
    data = tiny_data(tmp_path, [one_player("A")], [["0.30000000000000004", "1e-9"]])
    out = tmp_path / "o.xlsx"
    assert export(data, out) == 0
    row = sheet_rows(openpyxl.load_workbook(out), "PlayerGames", 2)[0]
    assert row[7] == 0.30000000000000004 and row[8] == 1e-9


# --- A1-06: blank lines --------------------------------------------------------------------------

def test_blank_lines_are_ignored_in_every_csv(tmp_path):
    data = two_season_data(tmp_path)
    clean = tmp_path / "clean.xlsx"
    assert export(data, clean) == 0
    for f in [p for p in data.rglob("*.csv")]:
        raw = f.read_bytes().decode("utf-8")
        head, _, rest = raw.partition("\n")
        f.write_bytes((head + "\n\n" + rest + "\n\n").encode("utf-8"))     # a blank line after the header and at the end
    messy = tmp_path / "messy.xlsx"
    assert export(data, messy) == 0
    assert messy.read_bytes() == clean.read_bytes()


# --- R1-m1 / R1-m2 / R1-m4 and the error paths ---------------------------------------------------

@pytest.mark.parametrize("week", ["x", "1.5", "-1", "", "٣"])
def test_non_numeric_week_is_an_error(tmp_path, capsys, week):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "1"]])
    pw = data / "player_week" / "player_week_2024.csv"
    h, r = read_csv(pw)
    r[0][1] = week
    write(pw, h, r)
    assert export(data, tmp_path / "x.xlsx") == 1
    err = capsys.readouterr().err
    assert "player_week_2024.csv line 2" in err and "week" in err and "whole number" in err


def test_season_in_a_row_must_match_its_file(tmp_path, capsys):
    data = two_season_data(tmp_path)
    pw = data / "player_week" / "player_week_2023.csv"
    h, r = read_csv(pw)
    r[1][0] = "2031"
    write(pw, h, r)
    assert export(data, tmp_path / "x.xlsx") == 1
    assert "player_week_2023.csv line 3" in capsys.readouterr().err


def test_output_folder_that_cannot_be_made_is_a_clear_error(tmp_path, capsys):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "1"]])
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert export(data, blocker / "sub" / "x.xlsx") == 1
    err = capsys.readouterr().err
    assert "cannot create the folder" in err and "Traceback" not in err and "[Errno" not in err


def test_os_error_while_writing_is_reported_with_the_path(tmp_path, capsys, monkeypatch):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "1"]])
    out = tmp_path / "o" / "x.xlsx"

    def boom(*a, **k):
        raise PermissionError(13, "Permission denied", str(out))
    monkeypatch.setattr(export_xlsx.os, "replace", boom)
    assert export(data, out) == 1
    err = capsys.readouterr().err
    assert "cannot write" in err and str(out) in err and "Permission denied" in err
    no_leftovers(out)


def test_unexpected_exception_is_one_line_and_leaves_nothing(tmp_path, capsys, monkeypatch):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "1"]])
    out = tmp_path / "o" / "x.xlsx"
    monkeypatch.setattr(export_xlsx, "season_totals", lambda *a: 1 / 0)
    assert export(data, out) == 1
    err = capsys.readouterr().err
    assert "unexpected ZeroDivisionError" in err and "Traceback" not in err and err.count("\n") == 1
    no_leftovers(out)


def test_unreadable_data_file_is_a_clear_error(tmp_path, capsys):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "1"]])
    (data / "config" / "bonus_rules.csv").unlink()
    (data / "config" / "bonus_rules.csv").mkdir()           # a folder where a file should be
    assert export(data, tmp_path / "x.xlsx") == 1
    err = capsys.readouterr().err
    assert "bonus_rules.csv" in err and "Traceback" not in err


def test_empty_season_file_says_empty(tmp_path, capsys):
    data = two_season_data(tmp_path)
    (data / "player_week" / "player_week_2023.csv").write_bytes(b"")
    assert export(data, tmp_path / "x.xlsx") == 1
    assert "player_week_2023.csv is empty" in capsys.readouterr().err


def test_missing_seasons_csv_is_refused(tmp_path, capsys):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "1"]])
    (data / "seasons.csv").unlink()
    assert export(data, tmp_path / "x.xlsx") == 1
    assert "seasons.csv" in capsys.readouterr().err


def test_text_length_is_counted_in_utf16_units(tmp_path, capsys):
    ok = tiny_data(tmp_path / "ok", [one_player("\U0001f600" * 16_383)], [["1", "1"]])        # 32,766 units
    assert export(ok, tmp_path / "ok.xlsx") == 0
    bad = tiny_data(tmp_path / "bad", [one_player("\U0001f600" * 20_000)], [["1", "1"]])      # 40,000 units, 20,000 code points
    assert export(bad, tmp_path / "bad.xlsx") == 1
    err = capsys.readouterr().err
    assert "40,000" in err and "player_week_2024.csv line 2" in err


def test_note_row_counts_against_the_row_limit(tmp_path, monkeypatch, capsys):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "1"]])
    monkeypatch.setattr(export_xlsx, "MAX_DATA_ROWS", 3)       # Leagues has 3 rows under a note row: one too many
    assert export(data, tmp_path / "x.xlsx") == 1
    assert "Leagues" in capsys.readouterr().err


def test_no_temporary_file_is_left_after_success(tmp_path):
    data = tiny_data(tmp_path, [one_player("A")], [["1", "1"]])
    out = tmp_path / "o" / "x.xlsx"
    assert export(data, out) == 0
    assert [p.name for p in out.parent.iterdir()] == ["x.xlsx"]


# --- determinism, defaults, package checks ------------------------------------------------------

def test_same_bytes_when_file_timestamps_change(mini, tmp_path):
    import os
    a, b = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    assert export(mini.data, a) == 0
    for i, p in enumerate(sorted(mini.data.rglob("*"))):
        os.utime(p, (1_000_000_000 + i * 7919, 1_100_000_000 + i * 104729))
    assert export(mini.data, b) == 0
    assert a.read_bytes() == b.read_bytes()


def test_default_paths(mini, tmp_path, monkeypatch):
    project = tmp_path / "NFL"
    shutil.copytree(mini.data, project / "04-data")
    monkeypatch.setattr(export_xlsx, "PROJECT", project)
    assert export_xlsx.main([]) == 0
    default = project / ".work" / "workbook" / "NFL-Analysis.xlsx"
    assert default.is_file() and openpyxl.load_workbook(default).sheetnames[0] == "About"
    other = tmp_path / "other.xlsx"
    assert export_xlsx.main(["--out", str(other)]) == 0
    assert other.read_bytes() == default.read_bytes()



def test_package_headers_match_tables_in_every_sheet(mini, tmp_path):
    out = tmp_path / "p.xlsx"
    assert export(mini.data, out) == 0
    assert raw_header_vs_table(out) == 7


# --------------------------------------------------------------------------------------------
# cell references (CONTRACTS.md 13.3, design version 3.002, D-047)

def a1_index(ref: str) -> int:
    """'AB12' -> 28 (1-based column number)."""
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n


def std_grid(path: Path, part: str) -> list[list]:
    """An independent standard-library reader: a cell without ``r`` goes in the column after the previous cell,
    columns restart at every ``<row>``. Returns one list per row, with None for empty cells and the row's
    ``r`` number checked to climb."""
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(path) as z:
        sst = ["".join(t.text or "" for t in si.iter(NSM + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        root = ET.fromstring(z.read(f"xl/worksheets/{part}.xml"))
    grid, last_row = [], 0
    for row in root.iter(NSM + "row"):
        rn = int(row.get("r"))
        assert rn > last_row
        last_row = rn
        cells: dict[int, object] = {}
        col = 0
        for c in row:
            col = a1_index(c.get("r")) if c.get("r") else col + 1
            assert col not in cells                                   # never two cells in one column
            v = c.find(NSM + "v")
            if v is None:
                cells[col] = None
            elif c.get("t") == "s":
                cells[col] = sst[int(v.text)]
            else:
                cells[col] = int(v.text) if re.fullmatch(r"-?\d+", v.text) else float(v.text)
        width = max(cells, default=0)
        while len(grid) < rn - 1:
            grid.append([])
        grid.append([cells.get(i + 1) for i in range(width)])
    return grid


def sheet_xml(path: Path, part: str) -> str:
    with zipfile.ZipFile(path) as z:
        return z.read(f"xl/worksheets/{part}.xml").decode()


def raw_rows(xml: str) -> dict[int, list[tuple[str | None, str]]]:
    """{row number: [(r or None, cell text), ...]} straight from the text, no XML parser involved."""
    out = {}
    for m in re.finditer(r'<row r="(\d+)"[^>]*>(.*?)</row>', xml, re.S):
        out[int(m.group(1))] = [(re.match(r'<c(?: r="([A-Z]+\d+)")?', c).group(1), c)
                                for c in re.findall(r"<c[ >].*?</c>", m.group(2))]
    return out


def padded(grid: list[list], width: int) -> list[list]:
    """Pad every row with None to ``width`` and drop empty rows at the end."""
    out = [(list(r) + [None] * width)[:width] for r in grid]
    while out and not any(v is not None for v in out[-1]):
        out.pop()
    return out


def emit(cols: int, rows: list[list[str]], first: int = 2) -> list[str]:
    sst = export_xlsx.SharedStrings()
    em = export_xlsx.Emitter(sst, [export_xlsx.Col(f"c{i}") for i in range(cols)], compact=True)
    return [em.row(first + i, r) for i, r in enumerate(rows)]


def test_data_cells_follow_the_cell_reference_rule_at_xml_level():
    cols = 30                                                     # past column Z, so letters are two long
    full = [f"v{i}" for i in range(cols)]
    cases = {
        "all": full,
        "one blank": full[:5] + [""] + full[6:],
        "three blanks": full[:5] + ["", "", ""] + full[8:],
        "leading blanks": ["", ""] + full[2:],
        "first blank only": [""] + full[1:],
        "last column": [""] * 29 + ["x"],
        "trailing blanks": full[:3] + [""] * 27,
        "single cell": ["x"] + [""] * 29,
        "single cell middle": [""] * 14 + ["x"] + [""] * 15,
        "all blank": [""] * 30,
        "alternate": [("v" if i % 2 == 0 else "") for i in range(cols)],
    }
    emitted = dict(zip(cases, emit(cols, list(cases.values()))))
    for name, vals in cases.items():
        xml = emitted[name]
        cells = re.findall(r"<c[ >].*?</c>", xml)
        written = [i for i, v in enumerate(vals) if v != ""]
        assert len(cells) == len(written), name
        prev = None
        for c, i in zip(cells, written):
            has_r = c.startswith("<c r=")
            if prev is not None and i == prev + 1:
                assert not has_r, (name, i)                       # directly after the previous written cell
            else:
                assert has_r, (name, i)                           # first cell, or first after a blank
            if has_r:
                assert c.startswith(f'<c r="{export_xlsx.col_letter(i + 1)}{2 + list(cases).index(name)}"'), (name, c)
            prev = i
        assert xml.startswith(f'<row r="{2 + list(cases).index(name)}">') and xml.endswith("</row>")
    assert emitted["all blank"] == '<row r="11"></row>'
    assert emitted["single cell"].count("<c") == 1 and emitted["single cell"].count(" r=") == 2   # row + cell
    assert emitted["all"].count(" r=") == 2                       # the row and the first cell only
    assert emitted["last column"].count(" r=") == 2 and 'r="AD7"' in emitted["last column"]
    assert emitted["leading blanks"].count(" r=") == 2 and 'r="C' in emitted["leading blanks"]
    assert emitted["three blanks"].count(" r=") == 3              # row, first cell, cell after the gap


def test_header_row_and_numbers_keep_their_text_after_dropping_r():
    sst = export_xlsx.SharedStrings()
    em = export_xlsx.Emitter(sst, [export_xlsx.Col("a"), export_xlsx.Col("b", text=True), export_xlsx.Col("c")], compact=True)
    row = em.row(5, ["1", "007", "2.5"])
    assert row == '<row r="5"><c r="A5"><v>1</v></c><c t="s"><v>0</v></c><c><v>2.5</v></c></row>'
    assert em.header(1).count('r="') == 4                         # the row and all three cells
    plain = export_xlsx.Emitter(export_xlsx.SharedStrings(), [export_xlsx.Col("a"), export_xlsx.Col("b")])
    assert plain.row(5, ["1", "2"]).count('r="') == 3             # small sheets: every cell keeps r
    assert sst.count == 1 + 3                                     # one text data cell plus three header cells


@pytest.fixture
def gappy(tmp_path):
    """Five players with blanks in many places: a blank in the middle, two blanks, a blank at the end."""
    players = [one_player("P1", "00-1", "1"), one_player("P2", "00-2", "1"), one_player("P3", "00-3", "1"),
               one_player("P4", "00-4", "1"), one_player("P5", "00-5", "1")]
    data = tiny_data(tmp_path, players, [["1", "2"], ["3", "4"], ["5", "6"], ["7", "8"], ["9", "10"]])
    pw = data / "player_week" / "player_week_2024.csv"
    header, rows = read_csv(pw)
    blank = lambda r, *names: [r.__setitem__(header.index(n), "") for n in names]
    blank(rows[1], "opponent_team")                               # one blank in the middle
    blank(rows[2], "team", "opponent_team")                       # two blanks in a row
    blank(rows[3], "passing_yards", "receptions")                 # blanks through the last column
    blank(rows[4], "position", "position_group", "opponent_team", "receptions")  # several gaps and a last blank
    write(pw, header, rows)
    return data


def test_gappy_workbook_xml_and_readback(gappy, tmp_path):
    out = tmp_path / "g.xlsx"
    assert export(gappy, out) == 0
    xml = sheet_xml(out, "sheet2")
    rows = raw_rows(xml)
    header, expected = expected_player_games(gappy)
    assert set(rows) == set(range(1, len(expected) + 2))
    assert all(r is not None for r, _ in rows[1])                 # header: every cell keeps r
    for i, vals in enumerate(expected):
        rn = i + 2
        written = [k for k, v in enumerate(vals) if v is not None]
        cells = rows[rn]
        assert len(cells) == len(written)
        prev = None
        for (ref, text), k in zip(cells, written):
            if prev is not None and k == prev + 1:
                assert ref is None, (rn, k)
            else:
                assert ref == f"{export_xlsx.col_letter(k + 1)}{rn}", (rn, k, ref)
            prev = k
    # at least one of each case really occurred
    assert any(r is None for rs in list(rows.values())[1:] for r, _ in rs)
    # read-back with openpyxl: every value in the right cell
    ws = openpyxl.load_workbook(out)["PlayerGames"]
    width = len(header)
    got = padded([list(r) for r in ws.iter_rows(min_row=2, values_only=True)], width)
    assert got == expected
    ro = openpyxl.load_workbook(out, read_only=True)["PlayerGames"]
    assert padded([list(r) for r in ro.iter_rows(min_row=2, values_only=True)], width) == expected
    # and the independent reader agrees
    grid = std_grid(out, "sheet2")
    assert grid[0] == header
    assert padded(grid[1:], width) == expected
    assert padded(grid[1:], width) == got


def test_gappy_season_totals_and_small_sheets_readback(gappy, tmp_path):
    out = tmp_path / "g.xlsx"
    assert export(gappy, out) == 0
    wb = openpyxl.load_workbook(out)
    for part, name in (("sheet3", "SeasonTotals"), ("sheet1", "About"), ("sheet4", "Leagues"), ("sheet5", "Scoring"),
                       ("sheet6", "Bonus"), ("sheet7", "Checks"), ("sheet8", "Dictionary")):
        assert wb[name].title == name
        grid = std_grid(out, part)
        mat = [list(r) for r in wb[name].iter_rows(values_only=True)]
        width = max(len(r) for r in mat)
        assert padded(grid, width) == padded(mat, width), name
    # small sheets: r on every cell and every row
    for part in ("sheet1", "sheet4", "sheet5", "sheet6", "sheet7", "sheet8"):
        xml = sheet_xml(out, part)
        assert len(re.findall(r"<c[ >]", xml)) == len(re.findall(r"<c r=", xml)), part
    # SeasonTotals: header keeps r everywhere; the data rows follow the rule
    rows = raw_rows(sheet_xml(out, "sheet3"))
    std_totals = std_grid(out, "sheet3")
    assert all(r is not None for r, _ in rows[1])
    for rn, cells in rows.items():
        if rn > 1:
            cols = [i for i, v in enumerate(std_totals[rn - 1]) if v is not None]
            gaps = [k for prev, k in zip(cols, cols[1:]) if k != prev + 1]
            assert cells[0][0] == f"A{rn}"
            assert sum(r is not None for r, _ in cells) == 1 + len(gaps)    # first cell and each cell after a gap


def test_season_totals_with_a_blank_keeps_r_after_it(tmp_path):
    data = tiny_data(tmp_path, [one_player("P1")], [["1", "2"]])
    pw = data / "player_week" / "player_week_2024.csv"
    header, rows = read_csv(pw)
    rows[0][header.index("team")] = ""
    write(pw, header, rows)
    sc = data / "scored" / "scored_2024.csv"
    sh, srows = read_csv(sc)
    srows[0][sh.index("team")] = ""
    write(sc, sh, srows)
    out = tmp_path / "t.xlsx"
    assert export(data, out) == 0
    cells = raw_rows(sheet_xml(out, "sheet3"))[2]
    refs = [r for r, _ in cells]
    assert refs[0] == "A2" and refs[1] is None and refs[2] is None and refs[3] is None and refs[4] == "F2"   # team (E) blank
    assert refs[5:] == [None] * (len(refs) - 5)
    wb = openpyxl.load_workbook(out)
    row = [c.value for c in wb["SeasonTotals"][2]]
    assert row[4] is None and row[3] == "QB" and row[5] == 1
    assert std_grid(out, "sheet3")[1][:6] == row[:6]


def test_two_exports_give_the_same_sha256(gappy, tmp_path):
    import hashlib
    a, b = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    assert export(gappy, a) == 0 and export(gappy, b) == 0
    assert hashlib.sha256(a.read_bytes()).hexdigest() == hashlib.sha256(b.read_bytes()).hexdigest()


def test_version_is_3002_everywhere(mini, tmp_path):
    import xml.etree.ElementTree as ET
    assert export_xlsx.WORKBOOK_VERSION == "3.002"
    out = tmp_path / "v.xlsx"
    assert export(mini.data, out) == 0
    wb = openpyxl.load_workbook(out)
    about = {r[0]: r[1] for r in sheet_rows(wb, "About") if r[0]}
    assert about["Workbook version"] == "3.002"
    assert wb["About"]["A1"].value == "NFL-Analysis 3.002"
    assert wb.properties.title == "NFL-Analysis 3.002"
    with zipfile.ZipFile(out) as z:
        assert "NFL-Analysis 3.002" in z.read("docProps/core.xml").decode()
        assert "3.001" not in z.read("docProps/core.xml").decode()
