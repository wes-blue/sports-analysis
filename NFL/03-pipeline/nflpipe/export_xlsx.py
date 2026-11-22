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
* **Validated before it is written.** Column names are checked against Excel's rules (unique after
  case and white space are normalised, at most 255 characters, the same text in the header cell and
  in the table definition); every number must be finite and storable; ``generated_utc`` must be an ISO
  8601 UTC time stamp; scored values are matched to ``player_week`` rows by key and column name.
* **Deterministic.** Time stamps come from ``status.csv``; zip entries have a fixed date, fixed
  attributes and a fixed order; dictionaries keep insertion order.
* **All or nothing.** The file is written beside ``--out`` under a temporary name and renamed into
  place only when complete; on any error the temporary file is removed.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import os
import re
import sys
import zipfile
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation, localcontext
from operator import itemgetter
from pathlib import Path

WORKBOOK_VERSION = "3.002"
TABLES_VERSION = "1"
DATA_CONTRACT_VERSION = "1"          # the data contract (CONTRACTS.md section 5) this exporter understands
AUTHOR = "NFL-Analysis pipeline"
MAX_DATA_ROWS = 1_048_575
MAX_COLUMNS = 16_384
MAX_CELL_CHARS = 32_767              # Excel's limit, counted in UTF-16 code units
MAX_NAME_CHARS = 255                 # Excel's limit for a table column name / header text
MAX_COL_WIDTH = 255
RELEASE_URL = "https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx"
AUTOMATION_URL = "https://github.com/wes-blue/sports-analysis/blob/main/NFL/03-pipeline/AUTOMATION.md"
NFLVERSE_URL = "https://github.com/nflverse/nflverse-data"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

PROJECT = Path(__file__).resolve().parent.parent.parent
IDENTITY = ("season", "week", "season_type", "player_id", "player_display_name", "position",
            "position_group", "team", "opponent_team")      # the first columns of every player_week file (CONTRACTS.md section 5)
TEXT_IDENTITY = frozenset(IDENTITY) - {"season", "week"}
POINTS = ("fantasy_points", "fantasy_points_ppr")
# PlayerGames layout (section 13.2): FRONT, the league columns, then BACK, then the metric columns.
FRONT = ("season", "week", "season_type", "player_display_name", "position", "team", "opponent_team")
BACK = ("player_id", "position_group", *POINTS)
FREEZE_PLAYER_GAMES = 4              # season, week, season_type, player_display_name
FREEZE_SEASON_TOTALS = 3             # season, season_type, player_display_name
SEASON_TYPE_ORDER = {"REG": 0, "POST": 1}
SCORED_KEY = ("season", "week", "season_type", "player_id")

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
REL_TYPE = NS_REL
XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

# Cell styles (indexes into cellXfs in styles.xml).
S_GENERAL, S_INT, S_POINTS, S_BOLD, S_TITLE, S_WRAP, S_NOTE, S_LINK, S_BOLD_TOP = range(9)

_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
_NONFINITE = re.compile(r"[+-]?(?:nan|inf|infinity)\Z", re.IGNORECASE)
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_WEEK = re.compile(r"[0-9]{1,3}\Z")
_BAD_XML = re.compile("[^\u0009\u000a\u000d -퟿-�\U00010000-\U0010ffff]")
_X_ESCAPE = re.compile(r"_(?=x[0-9A-Fa-f]{4}_)")      # an underscore that would start Excel's _xHHHH_ escape


class ExportError(Exception):
    """A problem the owner can understand; becomes the one-line error message (exit 1)."""


class BadValue(ExportError):
    """One value that cannot go into the workbook. ``column`` (an output column index) is filled in by the
    emitter; the code that knows the file and line turns this into a message that names them."""

    def __init__(self, reason: str, value: str = "", column: int | None = None):
        self.reason, self.value, self.column = reason, value, column
        super().__init__(f"the value {value[:40]!r} {reason}")


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


def protect_x(s: str) -> str:
    """Excel reads ``_xHHHH_`` as an escaped character, in shared strings and in table column names alike.
    Write the underscore that starts such a sequence as ``_x005F_`` so the text reads back unchanged."""
    return _X_ESCAPE.sub("_x005F_", s)


def esc(s: str) -> str:
    """Escape text for an XML text node (also protects Excel's ``_xHHHH_`` escape syntax)."""
    return protect_x(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\r", "&#13;")


def esc_attr(s: str) -> str:
    """Escape text for an XML attribute that Excel decodes like a cell string (a table column name)."""
    return (protect_x(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            .replace("\r", "&#13;").replace("\n", "&#10;").replace("\t", "&#9;"))


def utf16_len(s: str) -> int:
    """Length in UTF-16 code units, which is how Excel counts characters."""
    return len(s) if len(s) <= MAX_CELL_CHARS // 2 else len(s.encode("utf-16-le", "surrogatepass")) // 2


def number_problem(v: str) -> str | None:
    """None for text and for a number Excel can store; otherwise why this value cannot be a cell."""
    if _NUMBER.match(v):
        try:
            d = Decimal(v)
            if not d.is_zero() and not -300 <= d.adjusted() <= 300:
                return "is outside the range Excel can store (about 1e-300 to 1e300)"
        except ArithmeticError:
            return "is not a number Excel can store"
        return None
    if _NONFINITE.match(v):
        return "is not a finite number"
    return None


def is_number(v: str) -> bool:
    """True when the CSV text is a plain finite number (leading zeros or '+' make it text)."""
    return bool(_NUMBER.match(v)) and number_problem(v) is None


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


def iter_csv(path: Path):
    """Yield ``(line number, row)`` of a published CSV (UTF-8, RFC 4180). Blank lines are skipped everywhere."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                if row:
                    yield reader.line_num, row
    except FileNotFoundError:
        raise ExportError(f"missing file {path}") from None
    except UnicodeDecodeError as exc:
        raise ExportError(f"{path.name}: not valid UTF-8 ({exc})") from None
    except csv.Error as exc:
        raise ExportError(f"{path.name}: {exc}") from None
    except OSError as exc:
        raise ExportError(f"cannot read {path}: {exc.strerror or exc}") from None


def read_csv_rows(path: Path):
    for _, row in iter_csv(path):
        yield row


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
        units = utf16_len(text)
        if units > MAX_CELL_CHARS:
            raise BadValue(f"is {units:,} characters long (counted as Excel counts them); Excel allows {MAX_CELL_CHARS:,}", text)
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
    """One column: header text, whether values are forced to text, cell style and width.

    ``strict`` columns (the league points) must hold a number or nothing; anything else is an error."""

    def __init__(self, name: str, text: bool = False, style: int = S_GENERAL, width: float | None = None,
                 strict: bool = False):
        self.name, self.text, self.style, self.strict = name, text, style, strict
        self.width = min(width if width is not None else min(max(len(name) + 4, 9), 28), MAX_COL_WIDTH)


class Emitter:
    """Turns rows of CSV text into ``<row>`` XML, caching the cell text of repeated values."""

    def __init__(self, sst: SharedStrings, cols: list[Col], compact: bool = False):
        # compact: leave out ``r`` on a data cell that directly follows the previous written cell (D-047)
        self.sst, self.cols, self.compact = sst, cols, compact
        self.prefix = ['<c r="' + col_letter(i + 1) for i in range(len(cols))]
        self.caches: list[dict[str, str]] = [{} for _ in cols]

    def _make(self, k: int, v: str) -> str:
        col = self.cols[k]
        st = f' s="{col.style}"' if col.style else ""
        try:
            if not col.text:
                problem = number_problem(v)
                if problem:
                    raise BadValue(problem, v)
                if _NUMBER.match(v):
                    if col.strict and Decimal(v).adjusted() >= 15:
                        raise BadValue("is too large for a fantasy-points value (more than 15 digits)", v)
                    return f'{st}><v>{v}</v></c>'
                if col.strict:
                    raise BadValue("is not a number", v)
            return f' t="s"{st}><v>{self.sst.add(v)}</v></c>'
        except BadValue as exc:
            exc.column = k
            raise

    def row(self, rn: int, vals) -> str:
        rs = str(rn)
        parts = [f'<row r="{rs}">']
        sst = self.sst
        prev = -2                       # index of the previous written cell; -2 = none yet in this row
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
            if self.compact and k == prev + 1:
                parts.append("<c")      # directly after the previous written cell: no r (D-047)
            else:
                parts.append(self.prefix[k])
                parts.append(rs)
                parts.append('"')
            parts.append(frag)
            prev = k
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
    """Make every column name a legal, unique Excel table column name, before anything is written.

    The cleaned name is stored back in ``Col.name`` and is the one text used for both the header cell and the
    table definition, so the two cannot differ. Excel compares names case-insensitively with white space
    collapsed, allows at most 255 characters, and decodes ``_xHHHH_`` in both places (handled by ``esc``)."""
    if len(cols) > MAX_COLUMNS:
        raise ExportError(f"{sheet}: {len(cols):,} columns; Excel allows {MAX_COLUMNS:,}")
    seen: dict[str, str] = {}
    for c in cols:
        name = re.sub(r"[\t\r\n]+", " ", clean_text(c.name))
        if not name.strip():
            raise ExportError(f"{sheet}: a column has no name")
        if utf16_len(name) > MAX_NAME_CHARS:
            raise ExportError(f"{sheet}: the column name '{name[:40]}...' is {utf16_len(name)} characters; "
                              f"Excel allows {MAX_NAME_CHARS} in a table header")
        key = " ".join(name.split()).casefold()
        if key in seen:
            same = "" if seen[key] == name else f" ('{seen[key]}' and '{name}' are the same to Excel)"
            raise ExportError(f"{sheet}: duplicate column name '{name}'{same}")
        seen[key] = name
        c.name = name


# ---------------------------------------------------------------------------------------------
# package parts

class Package:
    """The zip file: deterministic entry dates, attributes and order."""

    def __init__(self, path: Path):
        self.zf = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED)
        self.open_streams: list = []

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
        w = self.zf.open(self._info(name), "w")
        self.open_streams.append(w)
        return w

    def close(self) -> None:
        self.zf.close()

    def abort(self) -> None:
        """Close everything after a failure (an open stream first, or the zip cannot close; Windows cannot
        delete a file that is still open)."""
        for w in self.open_streams:
            try:
                w.close()
            except Exception:                                   # noqa: BLE001
                pass
        try:
            self.zf.close()
        except Exception:                                       # noqa: BLE001
            pass


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
            shown = "missing" if found is None else repr(found)
            raise ExportError(f"status.csv data_contract_version is {shown}; this exporter understands "
                              f"version {DATA_CONTRACT_VERSION!r}")
        for key in ("generated_utc", "latest_season", "latest_week", "latest_season_type", "run_id"):
            if not self.status.get(key):
                raise ExportError(f"status.csv has no value for '{key}'")
        self._check_generated_utc(self.status["generated_utc"])
        self.round_decimals = self._round_decimals()
        self.leagues_header, self.leagues_rows = read_table(data_dir / "config" / "leagues.csv")
        for need in ("League", "Active"):
            if need not in self.leagues_header:
                raise ExportError(f"config/leagues.csv has no '{need}' column")
        li, ai = self.leagues_header.index("League"), self.leagues_header.index("Active")
        self.league_desc_idx = self.leagues_header.index("Description") if "Description" in self.leagues_header else None
        self.active = [r[li] for r in self.leagues_rows if r[ai].strip().lower() == "yes"]
        if not self.active:
            raise ExportError("config/leagues.csv: no league is Active")
        self.league_desc = {r[li]: (r[self.league_desc_idx] if self.league_desc_idx is not None else "")
                            for r in self.leagues_rows}
        self.seasons = self._season_files()
        self.in_progress = self._latest_in_progress()

    @staticmethod
    def _check_generated_utc(value: str) -> None:
        try:
            if not _UTC.match(value):
                raise ValueError
            stamp = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
            if stamp.year < 1900:
                raise ValueError
        except ValueError:
            raise ExportError(f"status.csv generated_utc is {clean_text(value)[:40]!r}; expected an ISO 8601 UTC "
                              "time stamp such as 2026-01-02T03:04:05Z") from None

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

    def _latest_in_progress(self) -> bool:
        """True when ``seasons.csv`` says the latest season is still being played."""
        header, rows = read_table(self.dir / "seasons.csv")
        for need in ("season", "season_status"):
            if need not in header:
                raise ExportError(f"seasons.csv has no '{need}' column")
        si, ti = header.index("season"), header.index("season_status")
        latest = self.status["latest_season"]
        return any(r[si] == latest and r[ti].strip().lower() == "in_progress" for r in rows)

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
    for _ in iter_csv(path):
        n += 1
    return max(n, 0)


def first_row(path: Path) -> list[str]:
    for _, row in iter_csv(path):
        return row
    raise ExportError(f"{path.name} is empty")


# ---------------------------------------------------------------------------------------------
# PlayerGames layout

class Layout:
    """The PlayerGames columns, planned from the ``player_week`` header before anything is written."""

    def __init__(self, data: Data):
        _, self.header_path, _ = data.seasons[-1]
        hdr = self.header0 = first_row(self.header_path)
        if tuple(hdr[:len(IDENTITY)]) != IDENTITY:
            raise ExportError(f"{self.header_path.name}: first columns are not {','.join(IDENTITY)}")
        for need in POINTS:
            if need not in hdr:
                raise ExportError(f"{self.header_path.name}: missing column '{need}'")
        self.league_cols = ["FF_" + n for n in data.active]
        self.metrics = [h for i, h in enumerate(hdr) if i >= len(IDENTITY) and h not in POINTS]
        self.front_get = itemgetter(*[hdr.index(n) for n in FRONT])
        self.rest_get = itemgetter(*[hdr.index(n) for n in (*BACK, *self.metrics)])
        self.names = [*FRONT, *self.league_cols, *BACK, *self.metrics]
        self.cols: list[Col] = []
        wide = {"player_id": 13, "player_display_name": 26, "season_type": 12, "position_group": 15, "opponent_team": 14}
        for nm in self.names:
            if nm in TEXT_IDENTITY:
                self.cols.append(Col(nm, text=True, width=wide.get(nm, 9)))
            elif nm in ("season", "week"):
                self.cols.append(Col(nm, style=S_INT, width=8))
            elif nm in self.league_cols:
                self.cols.append(Col(nm, style=S_POINTS, width=max(len(nm) + 4, 12), strict=True))
            elif nm in POINTS:
                self.cols.append(Col(nm, style=S_POINTS, width=max(len(nm) + 4, 12)))
            else:
                self.cols.append(Col(nm))
        check_columns(self.cols, "PlayerGames")


def scored_columns(sc_path: Path, header: list[str], league_cols: list[str]) -> tuple[list[int], list[int]]:
    """Positions (by column name) of the key columns and of the league columns in one scored file."""
    where: dict[str, int] = {}
    for i, h in enumerate(header):
        if h in SCORED_KEY or h in league_cols:
            if h in where:
                raise ExportError(f"{sc_path.name}: column '{h}' appears twice")
            where[h] = i
    for need in (*SCORED_KEY, *league_cols):
        if need not in where:
            raise ExportError(f"{sc_path.name}: missing column '{need}' (the leagues in config/leagues.csv and "
                              f"the scored file do not match)")
    return [where[n] for n in SCORED_KEY], [where[n] for n in league_cols]


def check_headers(data: Data, layout: Layout) -> None:
    """Cheap pass over every season's two headers, so a mismatch fails before any sheet is written."""
    for season, pw_path, sc_path in data.seasons:
        hdr = first_row(pw_path)
        if hdr != layout.header0:
            raise ExportError(f"{pw_path.name}: columns differ from {layout.header_path.name}")
        scored_columns(sc_path, first_row(sc_path), layout.league_cols)


def load_scored(sc_path: Path, league_cols: list[str]) -> dict[tuple, list[tuple[int, tuple]]]:
    """Read one scored file into ``{key: [(line, league values), ...]}``, found by column name, never by position.

    A key is unique in published data (gate G-GRAIN); if one does repeat, its rows are matched to the repeated
    ``player_week`` rows in published order, and any row left over is an error."""
    rows = iter_csv(sc_path)
    try:
        _, header = next(rows)
    except StopIteration:
        raise ExportError(f"{sc_path.name} is empty") from None
    key_idx, lg_idx = scored_columns(sc_path, header, league_cols)
    kget = itemgetter(*key_idx)
    lget = itemgetter(*lg_idx) if len(lg_idx) > 1 else (lambda r, i=lg_idx[0]: (r[i],))
    n = len(header)
    out: dict[tuple, list[tuple[int, tuple]]] = {}
    for line, row in rows:
        if len(row) != n:
            raise ExportError(f"{sc_path.name} line {line}: {len(row)} values but {n} columns")
        out.setdefault(kget(row), []).append((line, lget(row)))
    return out


# ---------------------------------------------------------------------------------------------
# sheets

SHEETS = [
    ("About", "Title, version, data date, licence and a guide to the sheets"),
    ("PlayerGames", "One row per player-game and team defense game, newest first: identity, your leagues' fantasy points (the FF_ columns), "
                    "nflverse points and every stat"),
    ("SeasonTotals", "Per player, season and season type, newest first: games, and each league's total and average fantasy points"),
    ("Leagues", "The leagues these scores were made for (copy of NFL/02-config/leagues.csv)"),
    ("Scoring", "The scoring weights per league (copy of NFL/02-config/scoring_weights.csv)"),
    ("Bonus", "The bonus bands per league (copy of NFL/02-config/bonus_rules.csv)"),
    ("Checks", "The quality gates of the latest run (pass, warn, fail)"),
    ("Dictionary", "What every column in PlayerGames means"),
]
CONFIG_TEXT = frozenset({"league", "metric", "category", "description", "notes", "applies_to", "reconcile_to", "active",
                         "gate_id", "gate", "severity", "result", "detail", "checked_utc", "source"})

IDENTITY_TEXT = {
    "season": "The season (the year it starts in).",
    "week": "Week of the season. Playoff weeks continue the numbering after the regular season, so they sort above it.",
    "season_type": "REG = regular season, POST = playoffs.",
    "player_display_name": "Player name; for a team defense row, the team code followed by D/ST.",
    "position": "Position as nflverse lists it; DST for a team defense row.",
    "team": "The player's team in that game.",
    "opponent_team": "The opposing team in that game.",
    "player_id": "nflverse player id (a GSIS id); for a team defense row, DST_ followed by the team code. Use it, not the name, to follow a player.",
    "position_group": "nflverse position group (QB, RB, WR, TE, K, DL, LB, DB, ...; DST for a team defense row).",
    "fantasy_points": "nflverse's own fantasy points, standard scoring (no points for receptions). Not your league.",
    "fantasy_points_ppr": "nflverse's own fantasy points with one point per reception. Not your league.",
}


def dictionary_table(data: Data, layout: Layout) -> tuple[list[str], list[list[str]]]:
    """One row per PlayerGames column: the identity, league and points columns (written here), then dictionary.csv."""
    header, rows = read_table(data.dir / "dictionary.csv")
    lower = [h.strip().lower() for h in header]
    for need in ("metric", "category", "description", "source"):
        if need not in lower:
            raise ExportError(f"dictionary.csv has no '{need}' column")

    def make(metric: str, category: str, description: str, source: str) -> list[str]:
        row = [""] * len(header)
        for name, value in (("metric", metric), ("category", category), ("description", description), ("source", source)):
            row[lower.index(name)] = value
        return row

    out = []
    for nm in layout.names[:len(FRONT)]:
        out.append(make(nm, "Identity", IDENTITY_TEXT[nm], "nflverse"))
    for league in data.active:
        text = data.league_desc.get(league, "")
        out.append(make("FF_" + league, "Your league", f"Fantasy points under the scoring of the league '{league}'"
                        + (f": {text}" if text else "."), "scored"))
    for nm in BACK[:2]:
        out.append(make(nm, "Identity", IDENTITY_TEXT[nm], "nflverse"))
    for nm in POINTS:
        out.append(make(nm, "nflverse points", IDENTITY_TEXT[nm], "nflverse"))
    return header, out + rows


def about_rows(data: Data) -> list[tuple[str, str, str | None]]:
    """(item, value, link) rows for the About sheet."""
    st = data.status
    through = f"{st['latest_season']} week {st['latest_week']} ({st['latest_season_type']})"
    leagues = ", ".join(data.active)
    rows: list[tuple[str, str, str | None]] = [
        ("Workbook version", WORKBOOK_VERSION, None),
        ("Leagues scored", f"{leagues}. Each league has one column in PlayerGames (FF_ followed by the league name) "
                           "and a total and an average in SeasonTotals.", None),
    ]
    for n in data.active:
        text = data.league_desc.get(n, "")
        rows.append((f"Column FF_{n}", f"Fantasy points under the scoring of the league '{n}'" + (f": {text}" if text else "."), None))
    rows.append(("Data through", through, None))
    if data.in_progress:
        rows.append(("Latest week", f"Season {st['latest_season']} is still being played, so the latest week "
                                    f"(week {st['latest_week']}) may be incomplete, and so may the {st['latest_season']} totals.", None))
    rows += [
        ("Opening this file", "This is a large file (hundreds of thousands of rows). Excel may take a minute or more to open it; "
                              "let it finish.", None),
        ("Generated (UTC)", st["generated_utc"], None),
        ("Data run id", st["run_id"], None),
        ("Pipeline version", st.get("pipeline_version", ""), None),
        ("Data contract version", st.get("data_contract_version", ""), None),
        ("Seasons", f"{st.get('window_start', '')} to {st.get('window_end', '')} ({st.get('season_types', '')})", None),
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


def write_table_sheet(pkg: Package, sst: SharedStrings, part: str, sheet: str, cols: list[Col], rows, *, note: str | None,
                      freeze_cols: int = 0, compact: bool = False) -> int:
    """Write a sheet that is one table (optionally under a note row). Returns the data row count.
    The column names were checked by ``check_columns`` before the file was started."""
    em = Emitter(sst, cols, compact)
    out = SheetOut(pkg, part)
    first = 1
    out.put(sheet_head(cols, freeze_cols, 2 if note else 1, selected=False))
    if note:
        sst.count += 1
        out.put(f'<row r="1"><c r="A1" t="s" s="{S_NOTE}"><v>{sst.add(note)}</v></c></row>')
        first = 2
    out.put(em.header(first))
    rn = first
    limit = MAX_DATA_ROWS - (first - 1)           # the sheet ends at Excel's last row, note row included
    for vals in rows:
        rn += 1
        if rn - first > limit:
            raise ExportError(f"{sheet}: more than {limit:,} data rows")
        try:
            out.put(em.row(rn, vals))
        except BadValue as exc:
            raise ExportError(f"{sheet} row {rn}, column '{cols[exc.column].name}': {exc}") from None
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


def iter_player_rows(data: Data, layout: Layout, totals: dict, total_rows: int):
    """The one row generator behind PlayerGames: yields ``(values, pw_name, line, sc_name, scored_line)`` per row,
    newest season first, week descending, then published order. The workbook and the published CSV
    (``--tables-dir``) both consume it, so they cannot differ. It also fills ``totals`` (the SeasonTotals
    sums, exact decimal arithmetic) and refuses a source that does not match.

    Scored values are looked up by key (season, week, season_type, player_id) and column name, so the order of
    rows or columns in a scored file cannot put a value under the wrong player or league."""
    nleague = len(layout.league_cols)
    i_week, i_name, i_pos, i_team = (layout.header0.index(n) for n in ("week", "player_display_name", "position", "team"))
    ctx = Context(prec=60)
    n = 0
    for season, pw_path, sc_path in reversed(data.seasons):            # newest season first
        pw = iter_csv(pw_path)
        try:
            _, hdr = next(pw)
        except StopIteration:
            raise ExportError(f"{pw_path.name} is empty") from None
        if hdr != layout.header0:
            raise ExportError(f"{pw_path.name}: columns differ from {layout.header_path.name}")
        scored = load_scored(sc_path, layout.league_cols)
        nlen = len(hdr)
        rows = []
        for line, row in pw:
            if len(row) != nlen:
                raise ExportError(f"{pw_path.name} line {line}: {len(row)} values but {nlen} columns")
            if row[0] != str(season):
                raise ExportError(f"{pw_path.name} line {line}: season is '{row[0]}' but the file is for {season}")
            if not _WEEK.match(row[i_week]):
                raise ExportError(f"{pw_path.name} line {line}: week '{row[i_week][:20]}' is not a whole number")
            rows.append((-int(row[i_week]), line, row))
        rows.sort(key=itemgetter(0, 1))                                # week descending, then published order
        for negweek, line, row in rows:
            key = (row[0], row[1], row[2], row[3])
            waiting = scored.get(key)
            if not waiting:
                raise ExportError(f"{pw_path.name} line {line}: {sc_path.name} has no row for season {key[0]}, week {key[1]}, "
                                  f"{key[2]}, player {key[3]}")
            sline, ff = waiting.pop(0)
            if not waiting:
                del scored[key]
            n += 1
            yield (*layout.front_get(row), *ff, *layout.rest_get(row)), pw_path.name, line, sc_path.name, sline
            # SeasonTotals sums (exact decimal arithmetic)
            tkey = (season, row[2], row[3])
            rank = (-negweek, line)                                    # the last game: highest week, later published row
            rec = totals.get(tkey)
            if rec is None:
                rec = totals[tkey] = [rank, row[i_name], row[i_pos], row[i_team], 0, [Decimal(0)] * nleague]
            elif rank > rec[0]:
                rec[0], rec[1], rec[2], rec[3] = rank, row[i_name], row[i_pos], row[i_team]
            rec[4] += 1
            sums = rec[5]
            for j, v in enumerate(ff):
                if v != "":
                    sums[j] = ctx.add(sums[j], Decimal(v))
        if scored:
            line = min(w[0][0] for w in scored.values())
            left = sum(len(w) for w in scored.values())
            raise ExportError(f"{sc_path.name} line {line}: no matching row in {pw_path.name} "
                              f"({left} scored rows have no player_week row)")
    if n != total_rows:
        raise ExportError(f"PlayerGames: read {n} rows but counted {total_rows}")


class TableCsv:
    """One published table (``--tables-dir``): UTF-8 without BOM, LF, RFC 4180 quoting only where needed.
    Written under a temporary name; ``commit`` renames it into place, ``abort`` removes it."""

    def __init__(self, path: Path, header: list[str]):
        self.path = path
        self.tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            self.fh = open(self.tmp, "w", encoding="utf-8", newline="")
        except OSError as exc:
            raise ExportError(f"cannot write {path}: {exc.strerror or exc}") from None
        self.w = csv.writer(self.fh, lineterminator="\n")
        self.rows = 0
        self.w.writerow([clean_text(h) for h in header])

    def row(self, vals) -> None:
        self.w.writerow([clean_text(v) if v else v for v in vals])
        self.rows += 1

    def close(self) -> None:
        if not self.fh.closed:
            self.fh.close()

    def commit(self) -> None:
        self.close()
        os.replace(self.tmp, self.path)

    def abort(self) -> None:
        try:
            self.close()
        except Exception:                                       # noqa: BLE001
            pass
        try:
            self.tmp.unlink()
        except OSError:
            pass


def player_games(pkg: Package, sst: SharedStrings, data: Data, part: str, layout: Layout, totals: dict,
                 total_rows: int, tee: TableCsv | None = None) -> int:
    """Stream PlayerGames into the sheet from ``iter_player_rows`` (and, with ``tee``, into the CSV) and, in the
    same pass, collect the SeasonTotals sums."""
    cols, nfront, nleague = layout.cols, len(FRONT), len(layout.league_cols)
    out = SheetOut(pkg, part)
    out.put(sheet_head(cols, FREEZE_PLAYER_GAMES, 1, selected=False))
    em = Emitter(sst, cols, compact=True)
    out.put(em.header(1))
    rn = 1
    for vals, pw_name, line, sc_name, sline in iter_player_rows(data, layout, totals, total_rows):
        rn += 1
        try:
            out.put(em.row(rn, vals))
        except BadValue as exc:
            if nfront <= exc.column < nfront + nleague:
                src, ln, name = sc_name, sline, layout.league_cols[exc.column - nfront]
            else:
                src, ln, name = pw_name, line, cols[exc.column].name
            raise ExportError(f"{src} line {ln}, column '{name}': {exc}") from None
        if tee is not None:
            tee.row(vals)
    n = rn - 1
    if n == 0:
        rn += 1
        out.put(f'<row r="{rn}"></row>')
    out.put(sheet_tail(table=True))
    out.close()
    pkg.last_table = (1, rn)                      # type: ignore[attr-defined]
    return n


def season_total_cols(data: Data) -> list[Col]:
    cols = [Col("season", style=S_INT, width=8), Col("season_type", text=True, width=12),
            Col("player_display_name", text=True, width=26), Col("position", text=True, width=9),
            Col("team", text=True, width=8), Col("games", style=S_INT, width=8)]
    for n in data.active:
        cols.append(Col(f"FF_{n}_total", style=S_POINTS, width=max(len(n) + 14, 14)))
        cols.append(Col(f"FF_{n}_avg", style=S_POINTS, width=max(len(n) + 12, 14)))
    cols.append(Col("player_id", text=True, width=13))
    return cols


def season_totals(data: Data, totals: dict) -> list[list[str]]:
    """Rows in the section 13.2 order: newest season first, REG before POST, first league's total (highest first), player_id."""
    decimals = data.round_decimals
    items = []
    with localcontext() as ctx:
        ctx.prec = 60
        for (season, stype, pid), (_, name, pos, team, games, sums) in totals.items():
            try:
                totals_r = [round_dec(s, decimals) for s in sums]
                row = [str(season), stype, name, pos, team, str(games)]
                for total in totals_r:
                    row.append(dec_text(total))
                    row.append(dec_text(round_dec(total / Decimal(games), decimals)))
            except InvalidOperation:
                raise ExportError(f"SeasonTotals: cannot add up the points of player {pid} in {season} {stype}") from None
            row.append(pid)
            items.append((-season, SEASON_TYPE_ORDER.get(stype, 2), stype, -totals_r[0], pid, row))
    items.sort(key=itemgetter(0, 1, 2, 3, 4))
    return [it[5] for it in items]


# ---------------------------------------------------------------------------------------------
# build

PLAYER_GAMES_CSV = "NFL-PlayerGames.csv"
SEASON_TOTALS_CSV = "NFL-SeasonTotals.csv"


def build(data_dir: Path, out_path: Path, tables_dir: Path | None = None) -> dict:
    data = Data(data_dir)
    layout = Layout(data)
    check_headers(data, layout)
    counts = [count_rows(p) for _, p, _ in data.seasons]
    for (season, p, sc), n in zip(data.seasons, counts):
        m = count_rows(sc)
        if m != n:
            raise ExportError(f"{p.name} has {n} rows but {sc.name} has {m}: different row counts")
    total_rows = sum(counts)
    if total_rows > MAX_DATA_ROWS:
        raise ExportError(f"PlayerGames would have {total_rows:,} data rows; Excel allows {MAX_DATA_ROWS:,}")

    # Everything that can be checked is checked before the file is started.
    st_cols = season_total_cols(data)
    check_columns(st_cols, "SeasonTotals")
    small = []
    note = "These are the rules this workbook's scores were made with. To change them, edit {} in NFL/02-config/ on GitHub."
    for sheet, rel, edit in (("Leagues", "config/leagues.csv", "leagues.csv"), ("Scoring", "config/scoring_weights.csv", "scoring_weights.csv"),
                             ("Bonus", "config/bonus_rules.csv", "bonus_rules.csv"), ("Checks", "checks/gates.csv", None),
                             ("Dictionary", "dictionary.csv", None)):
        if sheet == "Leagues":
            header, rows = data.leagues_header, data.leagues_rows
        elif sheet == "Dictionary":
            header, rows = dictionary_table(data, layout)
        else:
            header, rows = read_table(data_dir / rel)
        cols = csv_cols(header)
        check_columns(cols, sheet)
        small.append((sheet, cols, rows, note.format(edit) if edit else None))
    created = data.status["generated_utc"]

    tmp = out_path.with_name(f"{out_path.name}.{os.getpid()}.tmp")
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportError(f"cannot create the folder {out_path.parent}: {exc.strerror or exc}") from None
    csvs: list[TableCsv] = []
    if tables_dir is not None:
        try:
            tables_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ExportError(f"cannot create the folder {tables_dir}: {exc.strerror or exc}") from None
    sst = SharedStrings()
    tables: list[tuple[int, str, str]] = []           # (sheet number, table name, table xml)
    try:
        pkg = Package(tmp)
    except OSError as exc:
        raise ExportError(f"cannot write {out_path}: {exc.strerror or exc}") from None
    try:
        if tables_dir is not None:
            csvs.append(TableCsv(tables_dir / PLAYER_GAMES_CSV, layout.names))
            csvs.append(TableCsv(tables_dir / SEASON_TOTALS_CSV, [c.name for c in st_cols]))
        part = lambda i: f"xl/worksheets/sheet{i}.xml"                      # noqa: E731
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
        n_games = player_games(pkg, sst, data, part(2), layout, totals, total_rows, csvs[0] if csvs else None)
        tables.append((2, "tblPlayerGames", table_xml(1, "tblPlayerGames", layout.cols, *pkg.last_table)))   # type: ignore[attr-defined]
        pkg.add("xl/worksheets/_rels/sheet2.xml.rels", table_rels(1))

        st_rows = season_totals(data, totals)
        write_table_sheet(pkg, sst, part(3), "SeasonTotals", st_cols, st_rows, note=None, freeze_cols=FREEZE_SEASON_TOTALS, compact=True)
        tables.append((3, "tblSeasonTotals", table_xml(2, "tblSeasonTotals", st_cols, *pkg.last_table)))   # type: ignore[attr-defined]
        pkg.add("xl/worksheets/_rels/sheet3.xml.rels", table_rels(2))
        n_totals = len(st_rows)
        if csvs:
            for r in st_rows:
                csvs[1].row(r)
        del st_rows

        for k, (sheet, cols, rows, nt) in enumerate(small):
            idx, tid = 4 + k, 3 + k
            write_table_sheet(pkg, sst, part(idx), sheet, cols, rows, note=nt)
            tname = "tbl" + {"Checks": "Gates"}.get(sheet, sheet)
            tables.append((idx, tname, table_xml(tid, tname, cols, *pkg.last_table)))                  # type: ignore[attr-defined]
            pkg.add(f"xl/worksheets/_rels/sheet{idx}.xml.rels", table_rels(tid))

        for i, (idx, tname, xml) in enumerate(tables, start=1):
            pkg.add(f"xl/tables/table{i}.xml", xml)
        pkg.add("xl/sharedStrings.xml", sst.xml())
        pkg.close()
        for t in csvs:
            t.close()
        os.replace(tmp, out_path)
        for t in csvs:
            t.commit()
    except BaseException as exc:
        pkg.abort()
        for t in csvs:
            t.abort()
        try:
            tmp.unlink()
        except OSError:
            pass
        if isinstance(exc, OSError):
            raise ExportError(f"cannot write {out_path}: {exc.strerror or exc}") from None
        raise
    return {"player_rows": total_rows, "player_columns": len(layout.cols), "totals_rows": n_totals,
            "strings": len(sst.index), "bytes": out_path.stat().st_size,
            "tables": [(t.path, t.path.stat().st_size, t.rows) for t in csvs]}


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
    """File properties. The time stamp is the validated ``generated_utc``; everything is cleaned and escaped."""
    stamp = esc(clean_text(created))
    return (f'{XML_DECL}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>NFL-Analysis {WORKBOOK_VERSION}</dc:title><dc:creator>{AUTHOR}</dc:creator>"
            f"<cp:lastModifiedBy>{AUTHOR}</cp:lastModifiedBy>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{stamp}</dcterms:modified></cp:coreProperties>')


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
    parser.add_argument("--tables-dir", type=Path, default=None,
                        help="also write NFL-PlayerGames.csv and NFL-SeasonTotals.csv (the sheets' values) into this folder")
    args = parser.parse_args(argv)
    try:
        info = build(args.data_dir, args.out, args.tables_dir)
    except ExportError as exc:
        print(f"nflpipe export: error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        where = f" ({exc.filename})" if exc.filename else ""
        print(f"nflpipe export: error: a file could not be read or written{where}: {exc.strerror or exc}", file=sys.stderr)
        return 1
    except Exception as exc:                                         # noqa: BLE001  never leave a traceback-only failure
        print(f"nflpipe export: error: unexpected {type(exc).__name__}: {exc}. Nothing was written; this is a bug in "
              "the exporter, please report it.", file=sys.stderr)
        return 1
    print(f"wrote {args.out} ({info['bytes'] / 1_048_576:.1f} MB): PlayerGames {info['player_rows']:,} rows x "
          f"{info['player_columns']} columns, SeasonTotals {info['totals_rows']:,} rows, {info['strings']:,} distinct strings")
    for path, size, rows in info["tables"]:
        print(f"wrote {path} ({size / 1_048_576:.1f} MB): {rows:,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
