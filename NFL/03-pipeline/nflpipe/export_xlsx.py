"""``python -m nflpipe export``: build the finished, values-only Excel workbook (CONTRACTS.md section 13).

Reads only the published files in ``--data-dir`` and writes one ``.xlsx`` file with the standard
library: the package is assembled with ``zipfile`` and XML text (decision D-025). The workbook has
no formulas, no queries and no connections; every cell is a number, a typed string or empty.

How the file is built, and why:

* **Streaming.** ``PlayerGames`` (about 180,000 rows by 100 columns) is written row by row as the
  CSV files are read, straight into the zip stream. Memory holds the shared-string table (a few
  tens of thousands of distinct strings) and the ``SeasonTotals`` sums, never the cells.
* **Shared strings.** Every text cell is ``t="s"`` pointing into ``xl/sharedStrings.xml``, so a value
  that starts with ``=``, ``+``, ``-`` or ``@`` can never be read as a formula. Most columns repeat
  a few thousand values, so one table is much smaller than inline strings.
* **Tables.** Each table part has a unique id and name, a ``ref`` that covers the header and every
  data row, an ``autoFilter`` over the same range, and one ``tableColumn`` per column whose name is
  exactly the header cell text. The sheet has no sheet-level autoFilter (it would conflict).
* **Deterministic.** Time stamps come from ``status.csv``; zip entries have a fixed date, fixed
  attributes and a fixed order; dictionaries keep insertion order.
* **All or nothing.** The file is written beside ``--out`` under a temporary name and renamed into
  place only when complete; on any error the temporary file is removed.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import sys
import zipfile
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from operator import itemgetter
from pathlib import Path

WORKBOOK_VERSION = "3.001"
DATA_CONTRACT_VERSION = "1"          # the data contract (CONTRACTS.md section 5) this exporter understands
AUTHOR = "NFL-Analysis pipeline"
MAX_DATA_ROWS = 1_048_575
MAX_COLUMNS = 16_384
MAX_CELL_CHARS = 32_767
RELEASE_URL = "https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx"
AUTOMATION_URL = "https://github.com/wes-blue/sports-analysis/blob/main/NFL/03-pipeline/AUTOMATION.md"
NFLVERSE_URL = "https://github.com/nflverse/nflverse-data"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

PROJECT = Path(__file__).resolve().parent.parent.parent
IDENTITY = ("season", "week", "season_type", "player_id", "player_display_name", "position",
            "position_group", "team", "opponent_team")
TEXT_IDENTITY = frozenset(IDENTITY) - {"season", "week"}
POINTS = ("fantasy_points", "fantasy_points_ppr")

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
REL_TYPE = NS_REL
XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

# Cell styles (indexes into cellXfs in styles.xml).
S_GENERAL, S_INT, S_POINTS, S_BOLD, S_TITLE, S_WRAP, S_NOTE, S_LINK, S_BOLD_TOP = range(9)

_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
_BAD_XML = re.compile("[^\u0009\u000a\u000d -퟿-�\U00010000-\U0010ffff]")
_X_ESCAPE = re.compile(r"_x([0-9A-Fa-f]{4})_")


class ExportError(Exception):
    """A problem the owner can understand; becomes the one-line error message (exit 1)."""


# ---------------------------------------------------------------------------------------------
# small helpers

def col_letter(n: int) -> str:
    """1 -> A, 27 -> AA."""
    letters = ""
    while n:
        n, r = divmod(n - 1, 26)
        letters = chr(65 + r) + letters
    return letters


def clean_text(s: str) -> str:
    """Remove characters XML 1.0 does not allow."""
    return _BAD_XML.sub("", s)


def esc(s: str) -> str:
    """Escape text for an XML text node (also protects Excel's ``_xHHHH_`` escape syntax)."""
    s = _X_ESCAPE.sub(r"_x005F_x\1_", s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\r", "&#13;")


def esc_attr(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            .replace("\r", "&#13;").replace("\n", "&#10;").replace("\t", "&#9;"))


def is_number(v: str) -> bool:
    """True when the CSV text is a plain finite number (leading zeros or '+' make it text)."""
    if not _NUMBER.match(v):
        return False
    try:
        return math.isfinite(float(v))
    except (ValueError, OverflowError):
        return False


def dec_text(d: Decimal) -> str:
    """Shortest plain text of a Decimal: whole numbers without a decimal point."""
    if d == 0:
        return "0"
    t = format(d, "f")
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t


def round_dec(d: Decimal, decimals: int) -> Decimal:
    """Round half away from zero (ROUND_HALF_UP in Decimal is away from zero)."""
    return d.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def read_csv_rows(path: Path):
    """Yield the rows of a published CSV (UTF-8, RFC 4180)."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            yield from csv.reader(handle)
    except FileNotFoundError:
        raise ExportError(f"missing file {path}") from None
    except UnicodeDecodeError as exc:
        raise ExportError(f"{path.name}: not valid UTF-8 ({exc})") from None
    except csv.Error as exc:
        raise ExportError(f"{path.name}: {exc}") from None


def read_table(path: Path) -> tuple[list[str], list[list[str]]]:
    rows = list(read_csv_rows(path))
    if not rows:
        raise ExportError(f"{path.name} is empty")
    header, body = rows[0], rows[1:]
    body = [r for r in body if any(c != "" for c in r)]
    for i, r in enumerate(body, start=2):
        if len(r) != len(header):
            raise ExportError(f"{path.name} row {i}: {len(r)} values but {len(header)} columns")
    return header, body


# ---------------------------------------------------------------------------------------------
# shared strings, columns, cell emitter

class SharedStrings:
    """The workbook's string table. ``count`` is the number of cells that point into it."""

    def __init__(self) -> None:
        self.index: dict[str, int] = {}
        self.count = 0

    def add(self, text: str) -> int:
        text = clean_text(text)
        if len(text) > MAX_CELL_CHARS:
            raise ExportError(f"a text value is {len(text):,} characters; Excel allows {MAX_CELL_CHARS:,} "
                              f"(starts: {text[:40]!r})")
        i = self.index.get(text)
        if i is None:
            i = self.index[text] = len(self.index)
        return i

    def xml(self) -> bytes:
        out = [XML_DECL, f'<sst xmlns="{NS_MAIN}" count="{self.count}" uniqueCount="{len(self.index)}">']
        for s in self.index:
            keep = ' xml:space="preserve"' if (s != s.strip() or "\n" in s or "\t" in s or "\r" in s) else ""
            out.append(f"<si><t{keep}>{esc(s)}</t></si>")
        out.append("</sst>")
        return "".join(out).encode("utf-8")


class Col:
    """One column: header text, whether values are forced to text, cell style and width."""

    def __init__(self, name: str, text: bool = False, style: int = S_GENERAL, width: float | None = None):
        self.name, self.text, self.style = name, text, style
        self.width = width if width is not None else min(max(len(name) + 4, 9), 28)


class Emitter:
    """Turns rows of CSV text into ``<row>`` XML, caching the cell text of repeated values."""

    def __init__(self, sst: SharedStrings, cols: list[Col]):
        self.sst, self.cols = sst, cols
        self.prefix = ['<c r="' + col_letter(i + 1) for i in range(len(cols))]
        self.caches: list[dict[str, str]] = [{} for _ in cols]

    def _make(self, k: int, v: str) -> str:
        col = self.cols[k]
        st = f' s="{col.style}"' if col.style else ""
        if col.text or not is_number(v):
            return f' t="s"{st}><v>{self.sst.add(v)}</v></c>'
        return f'{st}><v>{v}</v></c>'

    def row(self, rn: int, vals) -> str:
        rs = str(rn)
        parts = [f'<row r="{rs}">']
        sst = self.sst
        for k, v in enumerate(vals):
            if v == "":
                continue
            cache = self.caches[k]
            frag = cache.get(v)
            if frag is None:
                if len(cache) > 200_000:
                    cache.clear()
                frag = cache[v] = self._make(k, v)
            if frag[1] == "t":
                sst.count += 1
            parts.append(self.prefix[k])
            parts.append(rs)
            parts.append('"')
            parts.append(frag)
        parts.append("</row>")
        return "".join(parts)

    def header(self, rn: int) -> str:
        parts = [f'<row r="{rn}">']
        for k, col in enumerate(self.cols):
            self.sst.count += 1
            parts.append(f'{self.prefix[k]}{rn}" t="s"><v>{self.sst.add(col.name)}</v></c>')
        parts.append("</row>")
        return "".join(parts)


def check_columns(cols: list[Col], sheet: str) -> None:
    if len(cols) > MAX_COLUMNS:
        raise ExportError(f"{sheet}: {len(cols):,} columns; Excel allows {MAX_COLUMNS:,}")
    seen: set[str] = set()
    for c in cols:
        key = clean_text(c.name).lower()
        if not clean_text(c.name).strip():
            raise ExportError(f"{sheet}: a column has no name")
        if key in seen:
            raise ExportError(f"{sheet}: duplicate column name '{c.name}'")
        seen.add(key)
        c.name = re.sub(r"[\t\r\n]+", " ", clean_text(c.name))


# ---------------------------------------------------------------------------------------------
# package parts

class Package:
    """The zip file: deterministic entry dates, attributes and order."""

    def __init__(self, path: Path):
        self.zf = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED)

    def _info(self, name: str) -> zipfile.ZipInfo:
        zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.create_system = 0
        zi.external_attr = 0
        return zi

    def add(self, name: str, data: bytes | str) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.zf.writestr(self._info(name), data)

    def stream(self, name: str):
        return self.zf.open(self._info(name), "w")

    def close(self) -> None:
        self.zf.close()


class SheetOut:
    """Writes one worksheet part in chunks (head, rows, tail)."""

    def __init__(self, pkg: Package, name: str):
        self.w = pkg.stream(name)
        self.buf: list[str] = []
        self.size = 0

    def put(self, text: str) -> None:
        self.buf.append(text)
        self.size += len(text)
        if self.size > 1_000_000:
            self.flush()

    def flush(self) -> None:
        if self.buf:
            self.w.write("".join(self.buf).encode("utf-8"))
            self.buf, self.size = [], 0

    def close(self) -> None:
        self.flush()
        self.w.close()


def sheet_head(cols: list[Col], freeze_cols: int, freeze_rows: int, selected: bool) -> str:
    tab = ' tabSelected="1"' if selected else ""
    if freeze_cols or freeze_rows:
        top_left = f"{col_letter(freeze_cols + 1)}{freeze_rows + 1}"
        attrs = (f' xSplit="{freeze_cols}"' if freeze_cols else "") + (f' ySplit="{freeze_rows}"' if freeze_rows else "")
        if freeze_cols and freeze_rows:
            sel = (f'<selection pane="topRight" activeCell="{col_letter(freeze_cols + 1)}1" sqref="{col_letter(freeze_cols + 1)}1"/>'
                   f'<selection pane="bottomLeft" activeCell="A{freeze_rows + 1}" sqref="A{freeze_rows + 1}"/>'
                   f'<selection pane="bottomRight" activeCell="{top_left}" sqref="{top_left}"/>')
            pane = "bottomRight"
        elif freeze_rows:
            sel = f'<selection pane="bottomLeft" activeCell="A{freeze_rows + 1}" sqref="A{freeze_rows + 1}"/>'
            pane = "bottomLeft"
        else:
            sel = f'<selection pane="topRight" activeCell="{top_left}" sqref="{top_left}"/>'
            pane = "topRight"
        view = (f'<sheetViews><sheetView{tab} workbookViewId="0"><pane{attrs} topLeftCell="{top_left}" '
                f'activePane="{pane}" state="frozen"/>{sel}</sheetView></sheetViews>')
    else:
        view = f'<sheetViews><sheetView{tab} workbookViewId="0"/></sheetViews>'
    cols_xml = "<cols>" + "".join(
        f'<col min="{i}" max="{i}" width="{c.width:g}" customWidth="1"/>' for i, c in enumerate(cols, start=1)) + "</cols>"
    return (f'{XML_DECL}<worksheet xmlns="{NS_MAIN}" xmlns:r="{NS_REL}">{view}'
            f'<sheetFormatPr defaultRowHeight="15"/>{cols_xml}<sheetData>')


def sheet_tail(links: str = "", table: bool = False) -> str:
    return ("</sheetData>" + links + '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
            + ('<tableParts count="1"><tablePart r:id="rId1"/></tableParts>' if table else "") + "</worksheet>")


def table_xml(tid: int, name: str, cols: list[Col], first_row: int, last_row: int) -> str:
    ref = f"A{first_row}:{col_letter(len(cols))}{last_row}"
    cols_xml = "".join(f'<tableColumn id="{i}" name="{esc_attr(c.name)}"/>' for i, c in enumerate(cols, start=1))
    return (f'{XML_DECL}<table xmlns="{NS_MAIN}" id="{tid}" name="{name}" displayName="{name}" ref="{ref}" totalsRowShown="0">'
            f'<autoFilter ref="{ref}"/><tableColumns count="{len(cols)}">{cols_xml}</tableColumns>'
            '<tableStyleInfo name="TableStyleMedium2" showFirstColumn="0" showLastColumn="0" '
            'showRowStripes="1" showColumnStripes="0"/></table>')


def rels_xml(items: list[tuple[str, str, str, bool]]) -> str:
    """items: (id, type suffix or full type, target, external)."""
    out = [f'{XML_DECL}<Relationships xmlns="{NS_PKG_REL}">']
    for rid, rtype, target, external in items:
        mode = ' TargetMode="External"' if external else ""
        out.append(f'<Relationship Id="{rid}" Type="{rtype}" Target="{esc_attr(target)}"{mode}/>')
    out.append("</Relationships>")
    return "".join(out)


def styles_xml(decimals: int) -> str:
    if decimals == 0:
        pts_id, custom = 1, ""
    elif decimals == 2:
        pts_id, custom = 2, ""
    else:
        pts_id, custom = 164, f'<numFmts count="1"><numFmt numFmtId="164" formatCode="0.{"0" * decimals}"/></numFmts>'
    fonts = ('<fonts count="5"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
             '<font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
             '<font><b/><sz val="14"/><name val="Calibri"/><family val="2"/></font>'
             '<font><i/><sz val="11"/><color rgb="FF595959"/><name val="Calibri"/><family val="2"/></font>'
             '<font><u/><sz val="11"/><color rgb="FF0563C1"/><name val="Calibri"/><family val="2"/></font></fonts>')
    xfs = [
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>',
        '<xf numFmtId="1" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>',
        f'<xf numFmtId="{pts_id}" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>',
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>',
        '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>',
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>',
        '<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top"/></xf>',
    ]
    return (f'{XML_DECL}<styleSheet xmlns="{NS_MAIN}">{custom}{fonts}'
            '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '<dxfs count="0"/><tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>'
            "</styleSheet>")


# ---------------------------------------------------------------------------------------------
# reading the published data

class Data:
    """What the export needs from ``--data-dir``, validated."""

    def __init__(self, data_dir: Path):
        self.dir = data_dir
        if not data_dir.is_dir():
            raise ExportError(f"data directory not found: {data_dir}")
        self.status = self._status()
        found = self.status.get("data_contract_version")
        if found != DATA_CONTRACT_VERSION:
            raise ExportError(f"status.csv data_contract_version is {found!r}; this exporter understands "
                              f"version {DATA_CONTRACT_VERSION!r}")
        for key in ("generated_utc", "latest_season", "latest_week", "latest_season_type", "run_id"):
            if not self.status.get(key):
                raise ExportError(f"status.csv has no value for '{key}'")
        self.round_decimals = self._round_decimals()
        self.leagues_header, self.leagues_rows = read_table(data_dir / "config" / "leagues.csv")
        for need in ("League", "Active"):
            if need not in self.leagues_header:
                raise ExportError(f"config/leagues.csv has no '{need}' column")
        li, ai = self.leagues_header.index("League"), self.leagues_header.index("Active")
        self.active = [r[li] for r in self.leagues_rows if r[ai].strip().lower() == "yes"]
        if not self.active:
            raise ExportError("config/leagues.csv: no league is Active")
        self.seasons = self._season_files()

    def _status(self) -> dict[str, str]:
        rows = list(read_csv_rows(self.dir / "status.csv"))
        if not rows or rows[0][:2] != ["key", "value"]:
            raise ExportError("status.csv: expected the header 'key,value'")
        return {r[0]: r[1] for r in rows[1:] if len(r) >= 2}

    def _round_decimals(self) -> int:
        header, rows = read_table(self.dir / "config" / "pipeline_config.csv")
        for r in rows:
            if r[0] == "RoundDecimals":
                try:
                    n = int(r[1])
                except ValueError:
                    n = -1
                if 0 <= n <= 6:
                    return n
                raise ExportError(f"config/pipeline_config.csv: RoundDecimals '{r[1]}' is not a whole number from 0 to 6")
        raise ExportError("config/pipeline_config.csv has no RoundDecimals setting")

    def _season_files(self) -> list[tuple[int, Path, Path]]:
        found = []
        for p in (self.dir / "player_week").glob("player_week_*.csv"):
            m = re.fullmatch(r"player_week_(\d{4})\.csv", p.name)
            if m:
                found.append((int(m.group(1)), p))
        if not found:
            raise ExportError(f"no player_week files in {self.dir / 'player_week'}")
        out = []
        for season, p in sorted(found):
            scored = self.dir / "scored" / f"scored_{season}.csv"
            if not scored.is_file():
                raise ExportError(f"missing scored/scored_{season}.csv for {p.name}")
            out.append((season, p, scored))
        return out


def count_rows(path: Path) -> int:
    n = -1
    for _ in read_csv_rows(path):
        n += 1
    return max(n, 0)


# ---------------------------------------------------------------------------------------------
# sheets

SHEETS = [
    ("About", "Title, version, data date, licence and a guide to the sheets"),
    ("PlayerGames", "One row per player-game and team defense game: identity, your leagues' fantasy points, nflverse points and every stat"),
    ("SeasonTotals", "Per player, season and season type: games, and each league's total and average fantasy points"),
    ("Leagues", "The leagues these scores were made for (copy of NFL/02-config/leagues.csv)"),
    ("Scoring", "The scoring weights per league (copy of NFL/02-config/scoring_weights.csv)"),
    ("Bonus", "The bonus bands per league (copy of NFL/02-config/bonus_rules.csv)"),
    ("Checks", "The quality gates of the latest run (pass, warn, fail)"),
    ("Dictionary", "What every stat column in PlayerGames means"),
]
CONFIG_TEXT = frozenset({"league", "metric", "category", "description", "notes", "applies_to", "reconcile_to", "active",
                         "gate_id", "gate", "severity", "result", "detail", "checked_utc", "source"})


def about_rows(data: Data) -> list[tuple[str, str, str | None]]:
    """(item, value, link) rows for the About sheet."""
    st = data.status
    through = f"{st['latest_season']} week {st['latest_week']} ({st['latest_season_type']})"
    rows: list[tuple[str, str, str | None]] = [
        ("Workbook version", WORKBOOK_VERSION, None),
        ("Data through", through, None),
        ("Generated (UTC)", st["generated_utc"], None),
        ("Data run id", st["run_id"], None),
        ("Pipeline version", st.get("pipeline_version", ""), None),
        ("Data contract version", st.get("data_contract_version", ""), None),
        ("Seasons", f"{st.get('window_start', '')} to {st.get('window_end', '')} ({st.get('season_types', '')})", None),
        ("Leagues scored", ", ".join(data.active), None),
        ("Gates passed", st.get("gates_pass", ""), None),
        ("Gates warned", st.get("gates_warn", ""), None),
        ("Gates failed", st.get("gates_fail", ""), None),
        ("Data source", st.get("data_source", ""), None),
        ("Data licence", st.get("data_license", ""), None),
        ("nflverse address", NFLVERSE_URL, NFLVERSE_URL),
        ("Licence address", LICENSE_URL, LICENSE_URL),
        ("Latest file", RELEASE_URL, RELEASE_URL),
        ("How to change scoring",
         "This workbook holds values only; nothing here refreshes or recalculates. To change scoring, edit the files in "
         "NFL/02-config/ on GitHub. The next pipeline run rebuilds this workbook; download it again from the Latest file address.", None),
        ("Guide", AUTOMATION_URL, AUTOMATION_URL),
    ]
    for name, what in SHEETS:
        rows.append((f"Sheet {name}", what, None))
    return rows


def write_about(pkg: Package, sst: SharedStrings, data: Data, part: str) -> list[tuple[str, str]]:
    """Write the About sheet. Returns the external hyperlinks as (relationship id, URL)."""
    cols = [Col("Item", width=26), Col("Value", width=100)]
    out = SheetOut(pkg, part)
    out.put(sheet_head(cols, 0, 0, selected=True))

    def text_cell(ref: str, s: str, style: int) -> str:
        sst.count += 1
        st = f' s="{style}"' if style else ""
        return f'<c r="{ref}" t="s"{st}><v>{sst.add(s)}</v></c>'

    out.put(f'<row r="1">{text_cell("A1", "NFL-Analysis " + WORKBOOK_VERSION, S_TITLE)}</row>')
    out.put(f'<row r="2">{text_cell("A2", "Fantasy football from nflverse data. Values only: nothing to refresh.", S_NOTE)}</row>')
    out.put(f'<row r="4">{text_cell("A4", "Item", S_BOLD)}{text_cell("B4", "Value", S_BOLD)}</row>')
    links: list[tuple[str, str]] = []
    link_xml = []
    for i, (item, value, link) in enumerate(about_rows(data), start=5):
        if link:
            rid = f"rId{len(links) + 1}"
            links.append((rid, link))
            link_xml.append(f'<hyperlink ref="B{i}" r:id="{rid}"/>')
        style = S_LINK if link else S_WRAP
        if is_number(value) and not link and item.startswith("Gates"):
            cell_b = f'<c r="B{i}" s="{S_WRAP}"><v>{value}</v></c>'
        else:
            cell_b = text_cell(f"B{i}", value, style) if value != "" else ""
        out.put(f'<row r="{i}">{text_cell(f"A{i}", item, S_BOLD_TOP)}{cell_b}</row>')
    out.put(sheet_tail(f'<hyperlinks>{"".join(link_xml)}</hyperlinks>' if link_xml else ""))
    out.close()
    return links


def write_table_sheet(pkg: Package, sst: SharedStrings, part: str, cols: list[Col], rows, *, note: str | None,
                      freeze_cols: int = 0) -> int:
    """Write a sheet that is one table (optionally under a note row). Returns the data row count."""
    check_columns(cols, part)
    em = Emitter(sst, cols)
    out = SheetOut(pkg, part)
    first = 1
    out.put(sheet_head(cols, freeze_cols, 2 if note else 1, selected=False))
    if note:
        sst.count += 1
        out.put(f'<row r="1"><c r="A1" t="s" s="{S_NOTE}"><v>{sst.add(note)}</v></c></row>')
        first = 2
    out.put(em.header(first))
    rn = first
    for vals in rows:
        rn += 1
        if rn - first > MAX_DATA_ROWS:
            raise ExportError(f"{part}: more than {MAX_DATA_ROWS:,} data rows")
        out.put(em.row(rn, vals))
    n = rn - first
    if n == 0:                                   # Excel tables need at least one data row
        rn += 1
        out.put(f'<row r="{rn}"></row>')
    out.put(sheet_tail(table=True))
    out.close()
    pkg.last_table = (first, rn)                  # type: ignore[attr-defined]
    return n


def csv_cols(header: list[str]) -> list[Col]:
    return [Col(h, text=h.strip().lower() in CONFIG_TEXT) for h in header]


def player_games(pkg: Package, sst: SharedStrings, data: Data, part: str, totals: dict, total_rows: int) -> tuple[list[Col], int]:
    """Stream PlayerGames and, in the same pass, collect the SeasonTotals sums."""
    pts_style = S_POINTS
    header0 = None
    cols: list[Col] = []
    getters = None
    league_cols = ["FF_" + n for n in data.active]
    out = None
    em = None
    rn = 1
    for season, pw_path, sc_path in data.seasons:
        pw, sc = read_csv_rows(pw_path), read_csv_rows(sc_path)
        try:
            hdr = next(pw)
            shdr = next(sc)
        except StopIteration:
            raise ExportError(f"{pw_path.name} or {sc_path.name} is empty") from None
        if header0 is None:
            header0 = hdr
            if tuple(hdr[:len(IDENTITY)]) != IDENTITY:
                raise ExportError(f"{pw_path.name}: first columns are not {','.join(IDENTITY)}")
            for need in (*POINTS, *league_cols):
                if need not in (shdr if need in league_cols else hdr):
                    raise ExportError(f"{pw_path.name if need in POINTS else sc_path.name}: missing column '{need}'")
            metric_idx = [i for i, h in enumerate(hdr) if i >= len(IDENTITY) and h not in POINTS]
            names = list(IDENTITY) + league_cols + list(POINTS) + [hdr[i] for i in metric_idx]
            for nm in names:
                if nm in TEXT_IDENTITY:
                    cols.append(Col(nm, text=True, width={"player_id": 13, "player_display_name": 26, "season_type": 12,
                                                          "position_group": 15, "opponent_team": 14}.get(nm, 9)))
                elif nm in ("season", "week"):
                    cols.append(Col(nm, style=S_INT, width=8))
                elif nm in league_cols or nm in POINTS:
                    cols.append(Col(nm, style=pts_style, width=max(len(nm) + 4, 12)))
                else:
                    cols.append(Col(nm))
            check_columns(cols, "PlayerGames")
            id_get = itemgetter(*range(len(IDENTITY)))
            pts_get = itemgetter(*[hdr.index(c) for c in POINTS])
            met_get = (itemgetter(*metric_idx) if len(metric_idx) > 1 else
                       (lambda r, i=metric_idx[0]: (r[i],)) if metric_idx else (lambda r: ()))
            sc_idx = [shdr.index(c) for c in league_cols]
            getters = (id_get, sc_idx, pts_get, met_get)
            out = SheetOut(pkg, part)
            out.put(sheet_head(cols, 5, 1, selected=False))
            em = Emitter(sst, cols)
            out.put(em.header(1))
        elif hdr != header0:
            raise ExportError(f"{pw_path.name}: columns differ from {data.seasons[0][1].name}")
        id_get, sc_idx, pts_get, met_get = getters
        nlen, slen = len(hdr), len(shdr)
        for line, (row, srow) in enumerate(zip(pw, sc), start=2):
            if len(row) != nlen:
                raise ExportError(f"{pw_path.name} line {line}: {len(row)} values but {nlen} columns")
            if len(srow) != slen:
                raise ExportError(f"{sc_path.name} line {line}: {len(srow)} values but {slen} columns")
            if row[:2] != srow[:2] or row[2:4] != srow[2:4]:
                raise ExportError(f"{sc_path.name} line {line}: key differs from {pw_path.name} "
                                  f"({srow[:4]} vs {row[:4]})")
            ff = [srow[j] for j in sc_idx]
            rn += 1
            out.put(em.row(rn, (*id_get(row), *ff, *pts_get(row), *met_get(row))))
            # SeasonTotals sums (exact decimal arithmetic)
            key = (season, row[2], row[3])
            rec = totals.get(key)
            try:
                wk = float(row[1])
            except ValueError:
                wk = 0.0
            if rec is None:
                rec = totals[key] = [wk, row[4], row[5], row[7], 0, [Decimal(0)] * len(ff)]
            elif wk >= rec[0]:
                rec[0], rec[1], rec[2], rec[3] = wk, row[4], row[5], row[7]
            rec[4] += 1
            sums = rec[5]
            for j, v in enumerate(ff):
                if v != "":
                    try:
                        sums[j] += Decimal(v)
                    except InvalidOperation:
                        raise ExportError(f"{sc_path.name} line {line}: '{v}' is not a number in {league_cols[j]}") from None
        extra = next(pw, None)
        if extra is not None or next(sc, None) is not None:
            raise ExportError(f"{pw_path.name} and {sc_path.name} have different row counts")
    n = rn - 1
    if n != total_rows:
        raise ExportError(f"PlayerGames: read {n} rows but counted {total_rows}")
    if n == 0:
        rn += 1
        out.put(f'<row r="{rn}"></row>')
    out.put(sheet_tail(table=True))
    out.close()
    pkg.last_table = (1, rn)                      # type: ignore[attr-defined]
    return cols, n


def season_totals(data: Data, totals: dict) -> tuple[list[Col], list[list[str]]]:
    decimals = data.round_decimals
    cols = [Col("season", style=S_INT, width=8), Col("season_type", text=True, width=12),
            Col("player_id", text=True, width=13), Col("player_display_name", text=True, width=26),
            Col("position", text=True, width=9), Col("team", text=True, width=8), Col("games", style=S_INT, width=8)]
    for n in data.active:
        cols.append(Col(f"FF_{n}_total", style=S_POINTS, width=max(len(n) + 14, 14)))
        cols.append(Col(f"FF_{n}_avg", style=S_POINTS, width=max(len(n) + 12, 14)))
    rows = []
    with localcontext() as ctx:
        ctx.prec = 60
        for key in sorted(totals):
            season, stype, pid = key
            _, name, pos, team, games, sums = totals[key]
            row = [str(season), stype, pid, name, pos, team, str(games)]
            for s in sums:
                total = round_dec(s, decimals)
                row.append(dec_text(total))
                row.append(dec_text(round_dec(total / Decimal(games), decimals)))
            rows.append(row)
    return cols, rows


# ---------------------------------------------------------------------------------------------
# build

def build(data_dir: Path, out_path: Path) -> dict:
    data = Data(data_dir)
    counts = [count_rows(p) for _, p, _ in data.seasons]
    for (season, p, sc), n in zip(data.seasons, counts):
        m = count_rows(sc)
        if m != n:
            raise ExportError(f"{p.name} has {n} rows but {sc.name} has {m}: different row counts")
    total_rows = sum(counts)
    n_cols = len(IDENTITY) + len(data.active) + len(POINTS)
    with open(data.seasons[0][1], encoding="utf-8-sig", newline="") as handle:
        n_cols += max(len(next(csv.reader(handle))) - len(IDENTITY) - len(POINTS), 0)
    if total_rows > MAX_DATA_ROWS:
        raise ExportError(f"PlayerGames would have {total_rows:,} data rows; Excel allows {MAX_DATA_ROWS:,}")
    if n_cols > MAX_COLUMNS:
        raise ExportError(f"PlayerGames would have {n_cols:,} columns; Excel allows {MAX_COLUMNS:,}")

    # Small tables are read up front so a bad file fails before the big sheet is written.
    small = []
    note = "These are the rules this workbook's scores were made with. To change them, edit {} in NFL/02-config/ on GitHub."
    for sheet, rel, edit in (("Leagues", "config/leagues.csv", "leagues.csv"), ("Scoring", "config/scoring_weights.csv", "scoring_weights.csv"),
                             ("Bonus", "config/bonus_rules.csv", "bonus_rules.csv"), ("Checks", "checks/gates.csv", None),
                             ("Dictionary", "dictionary.csv", None)):
        header, rows = (data.leagues_header, data.leagues_rows) if sheet == "Leagues" else read_table(data_dir / rel)
        small.append((sheet, header, rows, note.format(edit) if edit else None))

    tmp = out_path.with_name(out_path.name + ".tmp")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sst = SharedStrings()
    tables: list[tuple[str, str, str]] = []           # (sheet part, table name, table xml)
    pkg = Package(tmp)
    try:
        part = lambda i: f"xl/worksheets/sheet{i}.xml"                      # noqa: E731
        created = data.status["generated_utc"]
        names = [s for s, _ in SHEETS]
        # Parts that do not depend on the data volume.
        pkg.add("[Content_Types].xml", content_types(len(SHEETS), 7))
        pkg.add("_rels/.rels", rels_xml([
            ("rId1", f"{REL_TYPE}/officeDocument", "xl/workbook.xml", False),
            ("rId2", "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties", "docProps/core.xml", False),
            ("rId3", f"{REL_TYPE}/extended-properties", "docProps/app.xml", False)]))
        pkg.add("docProps/core.xml", core_xml(created))
        pkg.add("docProps/app.xml", app_xml(names))
        pkg.add("xl/workbook.xml", workbook_xml(names))
        pkg.add("xl/_rels/workbook.xml.rels", rels_xml(
            [(f"rId{i}", f"{REL_TYPE}/worksheet", f"worksheets/sheet{i}.xml", False) for i in range(1, len(SHEETS) + 1)]
            + [(f"rId{len(SHEETS) + 1}", f"{REL_TYPE}/styles", "styles.xml", False),
               (f"rId{len(SHEETS) + 2}", f"{REL_TYPE}/sharedStrings", "sharedStrings.xml", False)]))
        pkg.add("xl/styles.xml", styles_xml(data.round_decimals))

        links = write_about(pkg, sst, data, part(1))
        if links:
            pkg.add("xl/worksheets/_rels/sheet1.xml.rels", rels_xml(
                [(rid, f"{REL_TYPE}/hyperlink", url, True) for rid, url in links]))

        totals: dict = {}
        pg_cols, pg_rows = player_games(pkg, sst, data, part(2), totals, total_rows)
        tables.append((2, "tblPlayerGames", table_xml(1, "tblPlayerGames", pg_cols, *pkg.last_table)))   # type: ignore[attr-defined]
        pkg.add("xl/worksheets/_rels/sheet2.xml.rels", table_rels(1))

        st_cols, st_rows = season_totals(data, totals)
        write_table_sheet(pkg, sst, part(3), st_cols, st_rows, note=None, freeze_cols=4)
        tables.append((3, "tblSeasonTotals", table_xml(2, "tblSeasonTotals", st_cols, *pkg.last_table)))   # type: ignore[attr-defined]
        pkg.add("xl/worksheets/_rels/sheet3.xml.rels", table_rels(2))
        n_totals = len(st_rows)
        del st_rows

        for k, (sheet, header, rows, nt) in enumerate(small):
            idx, tid = 4 + k, 3 + k
            cols = csv_cols(header)
            write_table_sheet(pkg, sst, part(idx), cols, rows, note=nt)
            tname = "tbl" + {"Checks": "Gates"}.get(sheet, sheet)
            tables.append((idx, tname, table_xml(tid, tname, cols, *pkg.last_table)))                  # type: ignore[attr-defined]
            pkg.add(f"xl/worksheets/_rels/sheet{idx}.xml.rels", table_rels(tid))

        for i, (idx, tname, xml) in enumerate(tables, start=1):
            pkg.add(f"xl/tables/table{i}.xml", xml)
        pkg.add("xl/sharedStrings.xml", sst.xml())
        pkg.close()
        os.replace(tmp, out_path)
    except BaseException:
        try:
            pkg.close()
        except Exception:
            pass
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    return {"player_rows": total_rows, "player_columns": len(pg_cols), "totals_rows": n_totals,
            "strings": len(sst.index), "bytes": out_path.stat().st_size}


def table_rels(tid: int) -> str:
    return rels_xml([("rId1", f"{REL_TYPE}/table", f"../tables/table{tid}.xml", False)])


def content_types(n_sheets: int, n_tables: int) -> str:
    ov = ['<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>']
    ov += [f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
           for i in range(1, n_sheets + 1)]
    ov += [f'<Override PartName="/xl/tables/table{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>'
           for i in range(1, n_tables + 1)]
    ov += ['<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
           '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>',
           '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
           '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>']
    return (f'{XML_DECL}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>' + "".join(ov) + "</Types>")


def core_xml(created: str) -> str:
    return (f'{XML_DECL}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>NFL-Analysis {WORKBOOK_VERSION}</dc:title><dc:creator>{AUTHOR}</dc:creator>"
            f"<cp:lastModifiedBy>{AUTHOR}</cp:lastModifiedBy>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{esc(created)}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{esc(created)}</dcterms:modified></cp:coreProperties>')


def app_xml(names: list[str]) -> str:
    return (f'{XML_DECL}<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            f"<Application>{AUTHOR}</Application></Properties>")


def workbook_xml(names: list[str]) -> str:
    sheets = "".join(f'<sheet name="{esc_attr(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, start=1))
    return (f'{XML_DECL}<workbook xmlns="{NS_MAIN}" xmlns:r="{NS_REL}"><workbookPr/>'
            '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="28800" windowHeight="15000" activeTab="0"/></bookViews>'
            f"<sheets>{sheets}</sheets></workbook>")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m nflpipe export",
                                     description="Build the values-only Excel workbook from the published 04-data.")
    parser.add_argument("--data-dir", type=Path, default=PROJECT / "04-data")
    parser.add_argument("--out", type=Path, default=PROJECT / ".work" / "workbook" / "NFL-Analysis.xlsx")
    args = parser.parse_args(argv)
    try:
        info = build(args.data_dir, args.out)
    except ExportError as exc:
        print(f"nflpipe export: error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:                                         # noqa: BLE001  never leave a traceback-only failure
        print(f"nflpipe export: error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {args.out} ({info['bytes'] / 1_048_576:.1f} MB): PlayerGames {info['player_rows']:,} rows x "
          f"{info['player_columns']} columns, SeasonTotals {info['totals_rows']:,} rows, {info['strings']:,} distinct strings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
