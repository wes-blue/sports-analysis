"""Tests for the published tables (``export --tables-dir``) and the refresh workbook (CONTRACTS.md section 13.6), offline.

The two CSV files are written from the same row generator as the workbook's PlayerGames and SeasonTotals sheets;
these tests read both back and compare cell by cell. ``refresh-workbook`` is checked structurally (no Excel here).
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import posixpath
import re
import struct
import zipfile
from pathlib import Path
from xml.dom import minidom

import pytest

openpyxl = pytest.importorskip("openpyxl")

from nflpipe import __main__ as dispatcher  # noqa: E402
from nflpipe import export_xlsx, refresh_workbook  # noqa: E402

from test_export_xlsx import (export, gappy, one_player, read_csv, sheet_rows, tiny_data,  # noqa: E402,F401
                              two_season_data, write)

PLAYER, TOTALS = "NFL-PlayerGames.csv", "NFL-SeasonTotals.csv"
PREFIX = "https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/"
# The xlsx of two_season_data() built by the code before the generator refactor (3.005); a change to the workbook
# design must update this on purpose.
PINNED_FIXTURE_SHA256 = "0c223b1ceb815ecf86ff76e5f30099c22bc62122207994ad983319ab4e73201a"


def both(data: Path, tmp_path: Path, name: str = "run") -> tuple[Path, Path]:
    out, tables = tmp_path / name / "w.xlsx", tmp_path / name / "tables"
    assert export_xlsx.main(["--data-dir", str(data), "--out", str(out), "--tables-dir", str(tables)]) == 0
    return out, tables


def equal_to_sheet(xlsx: Path, sheet: str, csv_path: Path) -> int:
    """Every cell of the sheet equals the CSV field: numbers by value, text by string, blank by empty. Returns data rows."""
    ws = openpyxl.load_workbook(xlsx, read_only=True)[sheet]
    with open(csv_path, encoding="utf-8", newline="") as fh:
        crows = list(csv.reader(fh))
    xrows = [list(r) for r in ws.iter_rows(values_only=True)]
    while xrows and all(v is None for v in xrows[-1]):
        xrows.pop()
    assert len(xrows) == len(crows)
    for i, (c, x) in enumerate(zip(crows, xrows)):
        x = x + [None] * (len(c) - len(x))
        assert len(x) == len(c), (sheet, i)
        for k, (a, b) in enumerate(zip(c, x)):
            if a == "":
                assert b is None, (sheet, i, k, a, b)
            elif isinstance(b, (int, float)):
                assert float(a) == float(b), (sheet, i, k, a, b)
            else:
                assert a == b, (sheet, i, k, a, b)
    return len(crows) - 1


# 1. equality -----------------------------------------------------------------------------------------

def test_csvs_equal_the_sheets_on_the_mini_publish(mini, tmp_path):
    out, tables = both(mini.data, tmp_path)
    assert equal_to_sheet(out, "PlayerGames", tables / PLAYER) > 0
    assert equal_to_sheet(out, "SeasonTotals", tables / TOTALS) > 0


def test_csvs_equal_the_sheets_with_blanks_and_two_seasons(gappy, tmp_path):
    out, tables = both(gappy, tmp_path)
    assert equal_to_sheet(out, "PlayerGames", tables / PLAYER) == 5
    out2, tables2 = both(two_season_data(tmp_path / "two"), tmp_path, "two-run")
    assert equal_to_sheet(out2, "PlayerGames", tables2 / PLAYER) == 4
    assert equal_to_sheet(out2, "SeasonTotals", tables2 / TOTALS) == 3


# 2. refactor safety ----------------------------------------------------------------------------------

def test_workbook_bytes_are_unchanged_by_the_generator_refactor(tmp_path):
    data = two_season_data(tmp_path / "d")
    plain = tmp_path / "plain.xlsx"
    assert export(data, plain) == 0
    assert hashlib.sha256(plain.read_bytes()).hexdigest() == PINNED_FIXTURE_SHA256
    with_tables, _ = both(data, tmp_path)
    assert with_tables.read_bytes() == plain.read_bytes()            # --tables-dir never changes the workbook


# 3. columns ------------------------------------------------------------------------------------------

def test_headers_equal_the_sheet_headers_and_the_layout(mini, tmp_path):
    out, tables = both(mini.data, tmp_path)
    data = export_xlsx.Data(mini.data)
    layout = export_xlsx.Layout(data)
    wb = openpyxl.load_workbook(out, read_only=True)
    pg, _ = read_csv(tables / PLAYER)
    st, _ = read_csv(tables / TOTALS)
    assert pg == layout.names == [c for c in next(wb["PlayerGames"].iter_rows(values_only=True)) if c is not None]
    assert st == [c.name for c in export_xlsx.season_total_cols(data)] == \
        [c for c in next(wb["SeasonTotals"].iter_rows(values_only=True)) if c is not None]
    assert pg[:7] == list(export_xlsx.FRONT)
    active = ["FF_" + n for n in data.active]
    assert pg[7:7 + len(active)] == active
    assert [h for h in st if h.endswith("_total")] == [f"{n}_total" for n in active]


def test_an_active_league_adds_columns_to_both_files(tmp_path):
    rows, vals = [one_player("A")], [["1", "2", "3"]]
    two = tiny_data(tmp_path / "two", rows, [v[:2] for v in vals])
    three = tiny_data(tmp_path / "three", rows, vals, leagues=("Alpha", "Beta", "Gamma"))
    _, t2 = both(two, tmp_path, "r2")
    _, t3 = both(three, tmp_path, "r3")
    p2, p3 = read_csv(t2 / PLAYER)[0], read_csv(t3 / PLAYER)[0]
    assert "FF_Gamma" not in p2 and p3.index("FF_Gamma") == p3.index("FF_Beta") + 1
    assert len(p3) == len(p2) + 1
    s2, s3 = read_csv(t2 / TOTALS)[0], read_csv(t3 / TOTALS)[0]
    assert len(s3) == len(s2) + 2 and {"FF_Gamma_total", "FF_Gamma_avg"} <= set(s3)


# 4. format -------------------------------------------------------------------------------------------

def test_format_no_bom_lf_quoting_and_roundtrip(tmp_path):
    names = ['Smith, Jr.', 'Say "hi"', "Zoë Ångström", "A\nB"]
    players = [one_player(n, pid=f"00-{i}", week=str(i + 1)) for i, n in enumerate(names)]
    data = tiny_data(tmp_path / "d", players, [["1.5", "2"]] * 4)
    out, tables = both(data, tmp_path)
    for name in (PLAYER, TOTALS):
        raw = (tables / name).read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf") and raw.startswith(b"season,")
        assert b"\r" not in raw and raw.endswith(b"\n")
        raw.decode("utf-8")
        assert not re.search(rb"(?i),(nan|inf|infinity),", raw)
    header, rows = read_csv(tables / PLAYER)
    assert {len(r) for r in rows} == {len(header)}
    assert [r[header.index("player_display_name")] for r in rows] == list(reversed(names))     # week descending
    raw = (tables / PLAYER).read_text(encoding="utf-8")
    assert '"Smith, Jr."' in raw and '"Say ""hi"""' in raw and '"A\nB"' in raw and "Zoë Ångström" in raw
    assert equal_to_sheet(out, "PlayerGames", tables / PLAYER) == 4


def test_xml_illegal_characters_are_dropped_in_both(tmp_path):
    data = tiny_data(tmp_path / "d", [one_player("Bad\x01Name")], [["1", "1"]])
    out, tables = both(data, tmp_path)
    assert "BadName" in (tables / PLAYER).read_text(encoding="utf-8")
    assert equal_to_sheet(out, "PlayerGames", tables / PLAYER) == 1


def test_two_runs_give_the_same_bytes(gappy, tmp_path):
    _, a = both(gappy, tmp_path, "a")
    _, b = both(gappy, tmp_path, "b")
    for name in (PLAYER, TOTALS):
        assert (a / name).read_bytes() == (b / name).read_bytes()


# 5. errors -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("damage", ["non_finite", "no_scored_row", "late_bad_value"])
def test_errors_fail_the_csv_export_and_leave_nothing(tmp_path, capsys, damage):
    data = tiny_data(tmp_path / "d", [one_player("A"), one_player("B", pid="00-2", week="2")], [["1", "1"], ["2", "2"]])
    sc = data / "scored" / "scored_2024.csv"
    h, r = read_csv(sc)
    if damage == "non_finite":
        r[0][h.index("FF_Alpha")] = "nan"
    elif damage == "no_scored_row":
        r[1][3] = "00-OTHER"
    else:
        r[1][h.index("FF_Beta")] = "inf"                      # after the first rows were already streamed
    write(sc, h, r)
    out, tables = tmp_path / "o" / "w.xlsx", tmp_path / "o" / "tables"
    assert export_xlsx.main(["--data-dir", str(data), "--out", str(out), "--tables-dir", str(tables)]) == 1
    assert capsys.readouterr().err.startswith("nflpipe export: error:")
    assert not out.exists()
    assert not list(tables.glob("*")), list(tables.glob("*"))


def test_existing_tables_survive_a_failed_run(tmp_path):
    data = tiny_data(tmp_path / "d", [one_player("A")], [["1", "1"]])
    out, tables = both(data, tmp_path)
    good = {n: (tables / n).read_bytes() for n in (PLAYER, TOTALS)}
    (data / "scored" / "scored_2024.csv").unlink()
    assert export_xlsx.main(["--data-dir", str(data), "--out", str(out), "--tables-dir", str(tables)]) == 1
    assert {n: (tables / n).read_bytes() for n in (PLAYER, TOTALS)} == good
    assert sorted(p.name for p in tables.iterdir()) == sorted(good)


# 6. off by default -----------------------------------------------------------------------------------

def test_no_tables_without_the_option(mini, tmp_path):
    out = tmp_path / "o" / "w.xlsx"
    assert export(mini.data, out) == 0
    assert [p.name for p in out.parent.iterdir()] == ["w.xlsx"]
    assert not list(tmp_path.rglob("*.csv.tmp")) and not list(tmp_path.rglob(PLAYER))


def test_tables_version_constant_is_on_its_own_line():
    src = Path(export_xlsx.__file__).read_text(encoding="utf-8")
    assert re.search(r'^TABLES_VERSION = "1"', src, re.M)
    assert export_xlsx.TABLES_VERSION == "1"
    lines = src.splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith("WORKBOOK_VERSION = "))
    assert lines[i + 1].startswith('TABLES_VERSION = "')


# 7. Power Query text ---------------------------------------------------------------------------------

M_FILES = {"PlayerGames": PLAYER, "SeasonTotals": TOTALS}


@pytest.mark.parametrize("name", sorted(M_FILES))
def test_power_query_text_reads_only_the_release_asset(name):
    m = refresh_workbook.read_m(name + ".m")
    urls = re.findall(r"https?://[^\s\"')]+", m)
    assert urls == [PREFIX + M_FILES[name]]
    assert re.findall(r'Web\.Contents\(\s*"([^"]+)"\s*\)', m) == urls          # no options: no headers, no Query
    assert "Encoding = 65001" in m and "Table.PromoteHeaders" in m and "QuoteStyle.Csv" in m
    for banned in ("File.Contents", "Excel.CurrentWorkbook", "Sql.", "Odbc.", "OleDb", "Folder.", "Web.Page", "Json.Document",
                   "Headers =", "Query =", "RelativePath", "ApiKeyName", "Value.NativeQuery"):
        assert banned not in m, banned
    assert re.findall(r"\b(?:Web|Csv|Table|List|Binary|File|Sql|Odbc)\.[A-Za-z]+", m)  # something to scan
    assert set(re.findall(r"\b(?:Web|File|Sql|Odbc|Binary|Folder|Excel)\.[A-Za-z]+", m)) == {"Web.Contents"}


def test_type_lists_name_real_columns_and_the_rest_is_numeric(mini, tmp_path):
    _, tables = both(mini.data, tmp_path)
    for name, asset, whole, text in ((q[0], M_FILES[q[0]], q[3], q[4]) for q in refresh_workbook.QUERIES):
        header, rows = read_csv(tables / asset)
        m = refresh_workbook.read_m(name + ".m")
        for names in (whole, text):
            for col in names:
                assert f'"{col}"' in m
        assert whole <= set(header) and text <= set(header)
        for col in (set(header) - whole - text):
            k = header.index(col)
            for r in rows:
                if r[k]:
                    float(r[k])                             # numeric in every non-blank cell
        for col in whole:
            assert all(re.fullmatch(r"-?\d+", r[header.index(col)]) for r in rows)


# 8. the refresh workbook -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def refresh(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("rw") / "NFL-Analysis-Refresh.xlsx"
    assert dispatcher.main(["refresh-workbook", "--out", str(out)]) == 0
    return out


def mashup_parts(z: zipfile.ZipFile):
    raw = z.read("customXml/item1.xml")
    assert raw[:2] == b"\xff\xfe"
    txt = raw[2:].decode("utf-16-le")
    blob = base64.b64decode(re.search(r">([A-Za-z0-9+/=]+)</DataMashup>", txt).group(1))
    assert blob[:4] == b"\0\0\0\0"
    p, blocks = 4, []
    for _ in range(4):
        n = struct.unpack("<I", blob[p:p + 4])[0]
        blocks.append(blob[p + 4:p + 4 + n])
        p += 4 + n
    assert p == len(blob)
    return blocks


def test_refresh_workbook_structure(refresh):
    z = zipfile.ZipFile(refresh)
    assert z.testzip() is None
    names = z.namelist()
    assert names[0] == "[Content_Types].xml"
    for n in names:
        if n.endswith((".xml", ".rels")):
            data = z.read(n)
            if n == "customXml/item1.xml":
                data = data[2:].decode("utf-16-le").replace('encoding="utf-16"', 'encoding="utf-8"').encode()
            minidom.parseString(data)
    ct = minidom.parseString(z.read("[Content_Types].xml"))
    defaults = {e.getAttribute("Extension") for e in ct.getElementsByTagName("Default")}
    overrides = {e.getAttribute("PartName") for e in ct.getElementsByTagName("Override")}
    for n in names:
        assert n == "[Content_Types].xml" or "/" + n in overrides or n.rsplit(".", 1)[-1] in defaults, n
    assert all(o[1:] in names for o in overrides)
    for n in names:
        if n.endswith(".rels"):
            base = posixpath.dirname(posixpath.dirname(n))
            for r in minidom.parseString(z.read(n)).getElementsByTagName("Relationship"):
                assert posixpath.normpath(posixpath.join(base, r.getAttribute("Target"))) in names, (n, r.toxml())
    conn = {c.getAttribute("id"): c.getAttribute("name")
            for c in minidom.parseString(z.read("xl/connections.xml")).getElementsByTagName("connection")}
    assert sorted(conn.values()) == ["Query - PlayerGames", "Query - SeasonTotals"]
    tables = []
    for k, name in ((1, "PlayerGames"), (2, "SeasonTotals")):
        t = minidom.parseString(z.read(f"xl/tables/table{k}.xml")).documentElement
        q = minidom.parseString(z.read(f"xl/queryTables/queryTable{k}.xml")).documentElement
        tc = [c.getAttribute("name") for c in t.getElementsByTagName("tableColumn")]
        qf = [c.getAttribute("name") for c in q.getElementsByTagName("queryTableField")]
        assert t.getAttribute("name") == "tbl" + name and t.getAttribute("tableType") == "queryTable"
        assert tc == qf and len(set(tc)) == len(tc)
        assert conn[q.getAttribute("connectionId")] == f"Query - {name}"
        cells = minidom.parseString(z.read(f"xl/worksheets/sheet{k + 1}.xml")).getElementsByTagName("row")[0].getElementsByTagName("c")
        assert len(cells) == len(tc)
        tables.append(name)
    assert tables == ["PlayerGames", "SeasonTotals"]
    wb = openpyxl.load_workbook(refresh)
    assert wb.sheetnames == ["Start", "PlayerGames", "SeasonTotals"]
    assert all(v is None for ws in (wb["PlayerGames"], wb["SeasonTotals"]) for r in ws.iter_rows(min_row=2, values_only=True) for v in r)


def test_refresh_workbook_mashup_round_trip(refresh):
    z = zipfile.ZipFile(refresh)
    pkg, perm, meta, bindings = mashup_parts(z)
    pz = zipfile.ZipFile(io.BytesIO(pkg))
    assert sorted(pz.namelist()) == ["Config/Package.xml", "Formulas/Section1.m", "[Content_Types].xml"]
    section = pz.read("Formulas/Section1.m").decode("utf-8")
    assert section.startswith("section Section1;\r\n") and "\n" not in section.replace("\r\n", "")
    assert re.findall(r"^shared (\w+) = ", section, re.M) == ["PlayerGames", "SeasonTotals"]
    flat = section.replace("\r\n", "\n")
    for name in M_FILES:
        assert refresh_workbook.read_m(name + ".m").strip() in flat
    assert b"<FirewallEnabled>true</FirewallEnabled>" in perm
    ml = struct.unpack("<I", meta[4:8])[0]
    mx = meta[8:8 + ml].decode("utf-8-sig")
    minidom.parseString(mx.encode())
    assert re.findall(r"<ItemPath>(.*?)</ItemPath>", mx) == ["", "Section1/PlayerGames", "Section1/SeasonTotals"] or \
        re.findall(r"<ItemPath>(.*?)</ItemPath>", mx) == ["Section1/PlayerGames", "Section1/SeasonTotals"]
    assert bindings == b""
    item = z.read("customXml/itemProps1.xml").decode()
    assert "http://schemas.microsoft.com/DataMashup" in item


def test_refresh_workbook_is_deterministic_and_has_no_data_or_personal_data(refresh, tmp_path):
    again = tmp_path / "again.xlsx"
    assert refresh_workbook.main(["--out", str(again)]) == 0
    assert again.read_bytes() == refresh.read_bytes()
    z = zipfile.ZipFile(refresh)
    assert {i.date_time for i in z.infolist()} == {(1980, 1, 1, 0, 0, 0)}
    texts = []
    for n in z.namelist():
        d = z.read(n)
        if n == "customXml/item1.xml":
            pkg, perm, meta, bindings = mashup_parts(z)
            pz = zipfile.ZipFile(io.BytesIO(pkg))
            texts += [pz.read(x).decode("utf-8-sig") for x in pz.namelist()] + [perm.decode("utf-8-sig"), meta.decode("utf-8", "replace")]
            d = d[2:].decode("utf-16-le").encode()
        texts.append(d.decode("utf-8", "replace"))
    blob = "\n".join(texts)
    core = z.read("docProps/core.xml").decode()
    assert "<dc:creator>NFL-Analysis pipeline</dc:creator>" in core and "<cp:lastModifiedBy>NFL-Analysis pipeline</cp:lastModifiedBy>" in core
    for bad in ("/home/", "/Users/", "C:\\", "\\Users\\", "/tmp/", "@", "wes-blue/sports-analysis/archive"):
        assert bad not in blob.replace("wes-blue/sports-analysis/releases", ""), bad
    assert "Application>NFL-Analysis pipeline<" in z.read("docProps/app.xml").decode()


def test_refresh_workbook_failure_leaves_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(refresh_workbook, "read_m", lambda name: (_ for _ in ()).throw(export_xlsx.ExportError("boom")))
    out = tmp_path / "o" / "r.xlsx"
    assert refresh_workbook.main(["--out", str(out)]) == 1
    assert "refresh-workbook: error: boom" in capsys.readouterr().err
    assert not out.exists()


def test_refresh_workbook_unwritable_target_is_a_clear_error(tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert refresh_workbook.main(["--out", str(blocker / "r.xlsx")]) == 1
    assert "refresh-workbook: error: cannot write" in capsys.readouterr().err
    assert [p.name for p in tmp_path.iterdir()] == ["file"]
