"""``python -m nflpipe refresh-workbook``: write ``NFL-Analysis-Refresh.xlsx`` (CONTRACTS.md section 13.6).

A small workbook that carries **no data and no scoring**: a Start sheet and two empty, query-backed tables
(``tblPlayerGames`` on ``PlayerGames``, ``tblSeasonTotals`` on ``SeasonTotals``). Each table is bound to a Power Query
query (``pq/PlayerGames.m``, ``pq/SeasonTotals.m``) that downloads one of the two published CSV files and types its
columns. In Excel the user clicks Data > Refresh All and the tables fill.

Standard library only. The Power Query part is a DataMashup package (MS-QDEFF) written here: the framing, the
package zip, the permission list, the metadata items and ``Formulas/Section1.m``. The package skeleton (Package.xml,
content types, permission list) is embedded below as constants; the permission *bindings* block is left empty
(Excel then asks its privacy question once and writes its own). The structure follows what Excel itself wrote
for the retired 2.x experiment; only desktop Excel can confirm that this file opens and refreshes.

Deterministic: fixed time stamps, fixed zip dates and order, ids derived from names. Author ``NFL-Analysis pipeline``.
No path, user or machine name appears in any part.
"""

from __future__ import annotations

import argparse
import base64
import os
import struct
import sys
import uuid
import zipfile
import io
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from .export_xlsx import (AUTHOR, FRONT, BACK, LICENSE_URL, NS_MAIN, NS_PKG_REL, NS_REL, TABLES_VERSION, XML_DECL,
                          ExportError, col_letter)

HERE = Path(__file__).resolve().parent
RELEASE_BASE = "https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/"
WORKBOOK_URL = RELEASE_BASE + "NFL-Analysis.xlsx"
PLAYER_URL = RELEASE_BASE + "NFL-PlayerGames.csv"
TOTALS_URL = RELEASE_BASE + "NFL-SeasonTotals.csv"
STAMP = "2026-01-01T00:00:00Z"
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
INT, TEXT, NUM = 3, 6, 5                    # Excel's FillColumnTypes codes: whole number, text, decimal

# Seed columns: what the empty tables show before the first refresh. Excel re-lays the table to the query's real
# columns on refresh, so these never go stale when leagues or metrics change.
PLAYER_SEED = [*FRONT, *BACK]
TOTALS_SEED = ["season", "season_type", "player_display_name", "position", "team", "games", "player_id"]

# (sheet and table name, source file, seed columns, whole-number columns, text columns)
QUERIES = [
    ("PlayerGames", "PlayerGames.m", PLAYER_SEED, {"season", "week"},
     {"season_type", "player_display_name", "position", "team", "opponent_team", "player_id", "position_group"}),
    ("SeasonTotals", "SeasonTotals.m", TOTALS_SEED, {"season", "games"},
     {"season_type", "player_display_name", "position", "team", "player_id"}),
]

# The package skeleton, as Excel wrote it for the retired 2.x workbook (public format constants; no personal data).
PACKAGE_XML = ('﻿<?xml version="1.0" encoding="utf-8"?><Package xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
               'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><Version>2.159.229.0</Version>'
               '<MinVersion>2.21.0.0</MinVersion><Culture>en-US</Culture></Package>').encode("utf-8")
PACKAGE_CONTENT_TYPES = ('﻿<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
                         'content-types"><Default Extension="xml" ContentType="text/xml" /><Default Extension="m" '
                         'ContentType="application/x-ms-m" /></Types>').encode("utf-8")
PERMISSION_LIST = ('﻿<?xml version="1.0" encoding="utf-8"?><PermissionList xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
                   'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><CanEvaluateFuturePackages>false</CanEvaluateFuturePackages>'
                   '<FirewallEnabled>true</FirewallEnabled><WorkbookGroupType>Public</WorkbookGroupType></PermissionList>').encode("utf-8")
PERMISSION_BINDINGS = b""                   # an Excel-written one is machine- and user-bound (encrypted); none is shipped


def gid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "nfl-pq/" + label))


def kind(name: str, whole: set, text: set) -> int:
    return INT if name in whole else TEXT if name in text else NUM


def read_m(name: str) -> str:
    try:
        raw = (HERE / "pq" / name).read_bytes().decode("utf-8")
    except OSError as exc:
        raise ExportError(f"cannot read the Power Query text pq/{name}: {exc.strerror or exc}") from None
    return raw.replace("\r\n", "\n")


def section_text(queries) -> str:
    """The text of Formulas/Section1.m: one ``shared`` member per query, CRLF line ends."""
    body = "section Section1;\r\n" + "".join(f"\r\nshared {n} = {m.strip()};\r\n" for n, m, _, _ in queries)
    return body.replace("\r\n", "\n").replace("\n", "\r\n")


def mashup(queries) -> bytes:
    """customXml/item1.xml: UTF-16LE with BOM, the DataMashup element holding the MS-QDEFF stream in base64."""
    pkg = io.BytesIO()
    with zipfile.ZipFile(pkg, "w") as po:
        for name, data in (("Config/Package.xml", PACKAGE_XML), ("[Content_Types].xml", PACKAGE_CONTENT_TYPES),
                           ("Formulas/Section1.m", section_text(queries).encode("utf-8"))):
            zi = zipfile.ZipInfo(name, ZIP_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            po.writestr(zi, data)
    items = ['<Item><ItemLocation><ItemType>AllFormulas</ItemType><ItemPath /></ItemLocation><StableEntries>'
             '<Entry Type="Relationships" Value="sAAAAAA==" /></StableEntries></Item>']
    for name, _, names, types in queries:
        names_json = "[" + ",".join('"' + n + '"' for n in names) + "]"
        rel = ('{"columnCount":1,"keyColumnNames":[],"queryRelationships":[],"columnIdentities":["Section1/%s/AutoRemovedColumns1.{Result,0}"],'
               '"ColumnCount":1,"KeyColumnNames":[],"ColumnIdentities":["Section1/%s/AutoRemovedColumns1.{Result,0}"],"RelationshipInfo":[]}') % (name, name)
        entries = [("IsPrivate", "l0"), ("QueryID", "s" + gid("query/" + name)), ("FillEnabled", "l1"), ("FillCount", "l0"),
                   ("FillErrorCode", "sUnknown"), ("NavigationStepName", "sNavigation"), ("NameUpdatedAfterFill", "l0"),
                   ("ResultType", "sTable"), ("BufferNextRefresh", "l1"), ("FilledCompleteResultToWorksheet", "l0"),
                   ("FillTarget", "s" + name), ("FillColumnTypes", "s" + base64.b64encode(bytes(types)).decode()),
                   ("FillColumnNames", "s" + names_json), ("RecoveryTargetRow", "l1"), ("RecoveryTargetColumn", "l1"),
                   ("RecoveryTargetSheet", "s" + name), ("FillToDataModelEnabled", "l0"), ("FillObjectType", "sTable"),
                   ("FillErrorCount", "l0"), ("AddedToDataModel", "l0"), ("RelationshipInfoContainer", "s" + rel)]
        es = "".join(f'<Entry Type="{k}" Value={quoteattr(v)} />' for k, v in entries)
        items.append(f"<Item><ItemLocation><ItemType>Formula</ItemType><ItemPath>Section1/{name}</ItemPath></ItemLocation>"
                     f"<StableEntries>{es}</StableEntries></Item>")
    mxml = ('﻿<?xml version="1.0" encoding="utf-8"?><LocalPackageMetadataFile xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><Items>' + "".join(items) + "</Items></LocalPackageMetadataFile>").encode("utf-8")
    empty_zip = b"PK\x05\x06" + b"\x00" * 18
    meta = struct.pack("<I", 0) + struct.pack("<I", len(mxml)) + mxml + struct.pack("<I", len(empty_zip)) + empty_zip
    body = struct.pack("<I", 0)
    for b in (pkg.getvalue(), PERMISSION_LIST, meta, PERMISSION_BINDINGS):
        body += struct.pack("<I", len(b)) + b
    doc = ('<?xml version="1.0" encoding="utf-16"?><DataMashup sqmid="%s" xmlns="http://schemas.microsoft.com/DataMashup">%s</DataMashup>'
           % (gid("sqm"), base64.b64encode(body).decode()))
    return b"\xff\xfe" + doc.encode("utf-16-le")


# ---------------------------------------------------------------- sheets and parts
class Strings:
    def __init__(self) -> None:
        self.idx: dict[str, int] = {}
        self.count = 0

    def add(self, s: str) -> int:
        self.count += 1
        return self.idx.setdefault(s, len(self.idx))

    def xml(self) -> str:
        si = "".join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in self.idx)
        return f'{XML_DECL}<sst xmlns="{NS_MAIN}" count="{self.count}" uniqueCount="{len(self.idx)}">{si}</sst>'


def table_sheet(sst: Strings, headers, widths, freeze_cols) -> str:
    cells = "".join(f'<c r="{col_letter(i + 1)}1" t="s"><v>{sst.add(h)}</v></c>' for i, h in enumerate(headers))
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths))
    pane = (f'<sheetViews><sheetView workbookViewId="0"><pane xSplit="{freeze_cols}" ySplit="1" topLeftCell="{col_letter(freeze_cols + 1)}2" '
            f'activePane="bottomRight" state="frozen"/></sheetView></sheetViews>')
    return (f'{XML_DECL}<worksheet xmlns="{NS_MAIN}" xmlns:r="{NS_REL}">{pane}<sheetFormatPr defaultRowHeight="15"/><cols>{cols}</cols>'
            f'<sheetData><row r="1">{cells}</row><row r="2"></row></sheetData><tableParts count="1"><tablePart r:id="rId1"/></tableParts></worksheet>')


def table_xml(tid: int, name: str, headers) -> str:
    n = len(headers)
    ref = f"A1:{col_letter(n)}2"
    tc = "".join(f'<tableColumn id="{i + 1}" uniqueName="{i + 1}" name={quoteattr(h)} queryTableFieldId="{i + 1}"/>' for i, h in enumerate(headers))
    return (f'{XML_DECL}<table xmlns="{NS_MAIN}" id="{tid}" name="{name}" displayName="{name}" ref="{ref}" tableType="queryTable" totalsRowShown="0">'
            f'<autoFilter ref="{ref}"/><tableColumns count="{n}">{tc}</tableColumns>'
            f'<tableStyleInfo name="TableStyleMedium2" showFirstColumn="0" showLastColumn="0" showRowStripes="1" showColumnStripes="0"/></table>')


def query_table_xml(cid: int, headers) -> str:
    f = "".join(f'<queryTableField id="{i + 1}" name={quoteattr(h)} tableColumnId="{i + 1}"/>' for i, h in enumerate(headers))
    return (f'{XML_DECL}<queryTable xmlns="{NS_MAIN}" name="ExternalData_1" connectionId="{cid}" autoFormatId="16" applyNumberFormats="0" '
            f'applyBorderFormats="0" applyFontFormats="0" applyPatternFormats="0" applyAlignmentFormats="0" applyWidthHeightFormats="0">'
            f'<queryTableRefresh nextId="{len(headers) + 1}"><queryTableFields count="{len(headers)}">{f}</queryTableFields></queryTableRefresh></queryTable>')


def rels(items) -> str:
    r = "".join(f'<Relationship Id="{i}" Type="{t}" Target="{g}"/>' for i, t, g in items)
    return f'{XML_DECL}<Relationships xmlns="{NS_PKG_REL}">{r}</Relationships>'


START_LINES = [
    ("NFL fantasy football: refreshable workbook", True),
    ("", False),
    ("Click Data > Refresh All. Excel downloads two finished tables from this project's GitHub release and fills the sheets PlayerGames and SeasonTotals.", False),
    ("Nothing is scored in Excel: the points columns (FF_...) are calculated by the project and are already in the files.", False),
    ("The first time, Excel asks how to connect: choose Anonymous, level https://github.com/ (the data is public; no sign-in).", False),
    ("If a privacy question appears, choose Public.", False),
    ("", False),
    (f"Data these queries read: {PLAYER_URL} and {TOTALS_URL}", False),
    (f"Data: nflverse, CC BY 4.0 ({LICENSE_URL}), modified. See DATA-LICENSE.md in the repository.", False),
    (f"Prefer a finished workbook with no refresh? Download NFL-Analysis.xlsx from the same release: {WORKBOOK_URL}", False),
    (f"Tables version {TABLES_VERSION}.", False),
]


def build_parts(seeds: dict[str, list[str]] | None = None) -> dict[str, bytes | str]:
    spec = []
    for name, mfile, headers, whole, text in QUERIES:
        headers = (seeds or {}).get(name, headers)
        spec.append((name, read_m(mfile), headers, [kind(c, whole, text) for c in headers]))
    sst = Strings()
    bold = ' s="1"'
    start_rows = "".join(f'<row r="{i + 1}"><c r="A{i + 1}" t="s"{bold if b else ""}><v>{sst.add(t)}</v></c></row>'
                         for i, (t, b) in enumerate(START_LINES) if t)
    start = (f'{XML_DECL}<worksheet xmlns="{NS_MAIN}"><sheetViews><sheetView showGridLines="0" tabSelected="1" workbookViewId="0"/></sheetViews>'
             f'<sheetFormatPr defaultRowHeight="15"/><cols><col min="1" max="1" width="130" customWidth="1"/></cols><sheetData>{start_rows}</sheetData></worksheet>')
    parts: dict[str, bytes | str] = {"xl/worksheets/sheet1.xml": start}
    ws_ct = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
    ct_over = [("/xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
               ("/xl/worksheets/sheet1.xml", ws_ct),
               ("/xl/styles.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"),
               ("/xl/sharedStrings.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"),
               ("/xl/connections.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.connections+xml"),
               ("/customXml/itemProps1.xml", "application/vnd.openxmlformats-officedocument.customXmlProperties+xml"),
               ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
               ("/docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml")]
    conns = []
    for k, (name, _, headers, _types) in enumerate(spec, start=1):
        sheet = k + 1
        widths = [{"player_display_name": 26, "player_id": 13}.get(h, 12 if k == 1 else 14) for h in headers]
        parts[f"xl/worksheets/sheet{sheet}.xml"] = table_sheet(sst, headers, widths, 4 if k == 1 else 3)
        parts[f"xl/worksheets/_rels/sheet{sheet}.xml.rels"] = rels([("rId1", NS_REL + "/table", f"../tables/table{k}.xml")])
        parts[f"xl/tables/table{k}.xml"] = table_xml(k, "tbl" + name, headers)
        parts[f"xl/tables/_rels/table{k}.xml.rels"] = rels([("rId1", NS_REL + "/queryTable", f"../queryTables/queryTable{k}.xml")])
        parts[f"xl/queryTables/queryTable{k}.xml"] = query_table_xml(k, headers)
        conns.append(f'<connection id="{k}" keepAlive="1" name="Query - {name}" description="Connection to the \'{name}\' query in the workbook." '
                     f'type="5" refreshedVersion="8" background="1" saveData="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;Data Source=$Workbook$;'
                     f'Location={name};Extended Properties=&quot;&quot;" command="SELECT * FROM [{name}]"/></connection>')
        ct_over += [(f"/xl/worksheets/sheet{sheet}.xml", ws_ct),
                    (f"/xl/tables/table{k}.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"),
                    (f"/xl/queryTables/queryTable{k}.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.queryTable+xml")]
    parts["xl/connections.xml"] = f'{XML_DECL}<connections xmlns="{NS_MAIN}">{"".join(conns)}</connections>'
    parts["xl/sharedStrings.xml"] = sst.xml()
    parts["xl/styles.xml"] = (f'{XML_DECL}<styleSheet xmlns="{NS_MAIN}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
        '<font><b/><sz val="14"/><name val="Calibri"/><family val="2"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles><dxfs count="0"/><tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/></styleSheet>')
    names = ["Start", "PlayerGames", "SeasonTotals"]
    parts["xl/workbook.xml"] = (f'{XML_DECL}<workbook xmlns="{NS_MAIN}" xmlns:r="{NS_REL}"><workbookPr/><bookViews><workbookView activeTab="0"/></bookViews><sheets>'
        + "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, start=1)) + '</sheets><calcPr calcId="191029"/></workbook>')
    parts["xl/_rels/workbook.xml.rels"] = rels([(f"rId{i}", NS_REL + "/worksheet", f"worksheets/sheet{i}.xml") for i in (1, 2, 3)]
        + [("rId4", NS_REL + "/styles", "styles.xml"), ("rId5", NS_REL + "/sharedStrings", "sharedStrings.xml"),
           ("rId6", NS_REL + "/connections", "connections.xml"), ("rId7", NS_REL + "/customXml", "../customXml/item1.xml")])
    parts["customXml/item1.xml"] = mashup(spec)
    parts["customXml/itemProps1.xml"] = (f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n<ds:datastoreItem ds:itemID="{{{gid("item").upper()}}}" '
        'xmlns:ds="http://schemas.openxmlformats.org/officeDocument/2006/customXml"><ds:schemaRefs><ds:schemaRef ds:uri="http://schemas.microsoft.com/DataMashup"/></ds:schemaRefs></ds:datastoreItem>')
    parts["customXml/_rels/item1.xml.rels"] = rels([("rId1", NS_REL + "/customXmlProps", "itemProps1.xml")])
    parts["docProps/core.xml"] = (f'{XML_DECL}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        f'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>NFL-Analysis Refresh</dc:title><dc:creator>{AUTHOR}</dc:creator>'
        f'<cp:lastModifiedBy>{AUTHOR}</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{STAMP}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{STAMP}</dcterms:modified></cp:coreProperties>')
    parts["docProps/app.xml"] = (f'{XML_DECL}<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>{AUTHOR}</Application></Properties>')
    parts["_rels/.rels"] = rels([("rId1", NS_REL + "/officeDocument", "xl/workbook.xml"),
        ("rId2", "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties", "docProps/core.xml"), ("rId3", NS_REL + "/extended-properties", "docProps/app.xml")])
    parts["[Content_Types].xml"] = (f'{XML_DECL}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>' + "".join(f'<Override PartName="{p}" ContentType="{c}"/>' for p, c in ct_over) + "</Types>")
    return parts


def build(out_path: Path, seeds: dict[str, list[str]] | None = None) -> int:
    parts = build_parts(seeds)
    order = ["[Content_Types].xml", "_rels/.rels"] + sorted(k for k in parts if k not in ("[Content_Types].xml", "_rels/.rels"))
    tmp = out_path.with_name(f"{out_path.name}.{os.getpid()}.tmp")
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp, "w") as z:
            for name in order:
                zi = zipfile.ZipInfo(name, ZIP_DATE)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.create_system = 0
                zi.external_attr = 0
                d = parts[name]
                z.writestr(zi, d if isinstance(d, bytes) else d.encode("utf-8"))
        os.replace(tmp, out_path)
    except BaseException as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        if isinstance(exc, OSError):
            raise ExportError(f"cannot write {out_path}: {exc.strerror or exc}") from None
        raise
    return out_path.stat().st_size


def main(argv: list[str]) -> int:
    from .export_xlsx import PROJECT
    parser = argparse.ArgumentParser(prog="python -m nflpipe refresh-workbook",
                                     description="Write NFL-Analysis-Refresh.xlsx: two Power Query tables that load the published CSV files. No data inside.")
    parser.add_argument("--out", type=Path, default=PROJECT / ".work" / "workbook" / "NFL-Analysis-Refresh.xlsx")
    args = parser.parse_args(argv)
    try:
        size = build(args.out)
    except ExportError as exc:
        print(f"nflpipe refresh-workbook: error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:                                         # noqa: BLE001
        print(f"nflpipe refresh-workbook: error: unexpected {type(exc).__name__}: {exc}. Nothing was written; this is a bug, "
              "please report it.", file=sys.stderr)
        return 1
    print(f"wrote {args.out} ({size:,} bytes): Start, PlayerGames and SeasonTotals, two Power Query queries, no data")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
