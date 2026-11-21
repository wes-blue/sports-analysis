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
              extra_seasons: dict | None = None) -> Path:
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


def one_player(name: str, pid: str = "00-1", week: str = "1") -> list[str]:
    return [week, "REG", pid, name, "QB", "NE"]


# --------------------------------------------------------------------------------------------
# the miniature publish: every sheet, every column, every cell

def test_mini_publish_workbook(mini, tmp_path):
    out = tmp_path / "w" / "NFL-Analysis.xlsx"
    assert export(mini.data, out) == 0
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["About", "PlayerGames", "SeasonTotals", "Leagues", "Scoring", "Bonus", "Checks", "Dictionary"]

    # PlayerGames: identity, FF_ from scored, nflverse points, then the metrics; every cell checked
    active = [r["League"] for r in csv.DictReader(open(mini.data / "config" / "leagues.csv", encoding="utf-8"))
              if r["Active"].lower() == "yes"]
    expected_rows = []
    header = None
    for pw_file in sorted((mini.data / "player_week").glob("player_week_*.csv")):
        pw_header, pw_rows = read_csv(pw_file)
        sc_header, sc_rows = read_csv(mini.data / "scored" / pw_file.name.replace("player_week", "scored"))
        pts = ["fantasy_points", "fantasy_points_ppr"]
        header = pw_header[:9] + [f"FF_{n}" for n in active] + pts + [c for c in pw_header[9:] if c not in pts]
        for a, b in zip(pw_rows, sc_rows):
            full = dict(zip(pw_header, a))
            full.update(dict(zip(sc_header, b)))
            expected_rows.append([expected_cell(c, full[c]) for c in header])
    assert expected_rows, "the mini publish should have player rows"
    got = sheet_rows(wb, "PlayerGames")
    assert list(got[0]) == header
    assert len(got) - 1 == len(expected_rows)
    for g, e in zip(got[1:], expected_rows):
        assert list(g) == e
    ws = wb["PlayerGames"]
    assert ws.freeze_panes == "F2"
    assert list(ws.tables) == ["tblPlayerGames"]
    assert ws.tables["tblPlayerGames"].ref == f"A1:{openpyxl.utils.get_column_letter(len(header))}{len(expected_rows) + 1}"
    assert ws.tables["tblPlayerGames"].autoFilter is not None
    assert [c.name for c in ws.tables["tblPlayerGames"].tableColumns] == header

    # small sheets equal their CSVs
    for sheet, rel, first in (("Leagues", "config/leagues.csv", 2), ("Scoring", "config/scoring_weights.csv", 2),
                              ("Bonus", "config/bonus_rules.csv", 2), ("Checks", "checks/gates.csv", 1),
                              ("Dictionary", "dictionary.csv", 1)):
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
    assert about["Workbook version"] == "3.001"
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
    assert props.title == "NFL-Analysis 3.001"
    assert props.creator == "NFL-Analysis pipeline"
    assert props.created.strftime("%Y-%m-%dT%H:%M:%SZ") == status["generated_utc"]


def test_mini_season_totals_match_recomputation(mini, tmp_path):
    out = tmp_path / "x.xlsx"
    assert export(mini.data, out) == 0
    wb = openpyxl.load_workbook(out)
    active = [r["League"] for r in csv.DictReader(open(mini.data / "config" / "leagues.csv", encoding="utf-8"))
              if r["Active"].lower() == "yes"]
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
    assert got[0][:7] == ("season", "season_type", "player_id", "player_display_name", "position", "team", "games")
    assert len(got) - 1 == len(games)
    assert [tuple(r[:3]) for r in got[1:]] == sorted(games)
    for r in got[1:]:
        k = (r[0], r[1], r[2])
        assert r[3:6] == last[k][2:4] + (last[k][1],)
        assert r[6] == games[k]
        for i, n in enumerate(active):
            total = sums[k, n].quantize(Decimal("0.01"), ROUND_HALF_UP)
            assert r[7 + 2 * i] == pytest.approx(float(total), abs=1e-9)
            assert r[8 + 2 * i] == pytest.approx(float((total / games[k]).quantize(Decimal("0.01"), ROUND_HALF_UP)), abs=1e-9)
    assert wb["SeasonTotals"].freeze_panes == "E2"


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
    got = [r[4] for r in sheet_rows(wb, "PlayerGames", 2)]
    expect = [re.sub("[\x00-\x08\x0b\x0c\x0e-\x1f]", "", n) for n in names]
    assert got == expect
    for cell in wb["PlayerGames"]["E"][1:]:
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
    assert [r[3] for r in sheet_rows(wb, "SeasonTotals", 2)] == [expect[names.index(n)] for n in
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
    assert rows[0][6] == games
    assert rows[0][7] == pytest.approx(float(t), abs=1e-12)
    assert rows[0][8] == pytest.approx(float(a), abs=1e-12)
    if decimals != 3:
        assert rows[0][7] == pytest.approx(float(Decimal(total)), abs=1e-12)
        assert rows[0][8] == pytest.approx(float(Decimal(avg)), abs=1e-12)
    assert rows[0][9:] == (0, 0)                          # the second league: zeros stay numbers


def test_season_totals_groups_and_last_team(tmp_path):
    # Same player on two teams in one season; the later week decides team. POST is a separate row.
    players = [["1", "REG", "00-9", "Mover", "WR", "AAA"], ["5", "REG", "00-9", "Mover", "WR", "BBB"],
               ["2", "REG", "00-8", "Other", "WR", "CCC"], ["1", "POST", "00-9", "Mover", "WR", "BBB"]]
    data = tiny_data(tmp_path, players, [["1", "1"], ["2", "2"], ["4", "4"], ["8", "8"]])
    out = tmp_path / "g.xlsx"
    assert export(data, out) == 0
    rows = sheet_rows(openpyxl.load_workbook(out), "SeasonTotals", 2)
    assert [(r[0], r[1], r[2], r[5], r[6], r[7], r[8]) for r in rows] == [
        (2024, "POST", "00-9", "BBB", 1, 8, 8), (2024, "REG", "00-8", "CCC", 1, 4, 4), (2024, "REG", "00-9", "BBB", 2, 3, 1.5)]


def test_multiple_seasons_in_published_order(tmp_path):
    first = ([one_player("Old")], [["1", "1"]])
    data = tiny_data(tmp_path, [one_player("New")], [["2", "2"]], season=2024, extra_seasons={2023: first})
    out = tmp_path / "m.xlsx"
    assert export(data, out) == 0
    wb = openpyxl.load_workbook(out)
    assert [(r[0], r[4]) for r in sheet_rows(wb, "PlayerGames", 2)] == [(2023, "Old"), (2024, "New")]
    assert [r[0] for r in sheet_rows(wb, "SeasonTotals", 2)] == [2023, 2024]


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
    assert len(sheet_rows(openpyxl.load_workbook(tmp_path / "ok.xlsx"), "PlayerGames", 2)[0][4]) == 32_767


@pytest.mark.parametrize("damage, message", [
    ("no_scored", "scored"),
    ("no_status", "status.csv"),
    ("no_generated", "generated_utc"),
    ("bad_round", "RoundDecimals"),
    ("key_mismatch", "key differs"),
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
    assert (repr(value) if value is not None else "None") in err
    no_leftovers(out)
