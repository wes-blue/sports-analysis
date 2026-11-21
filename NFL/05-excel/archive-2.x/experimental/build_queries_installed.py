"""Build NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx (E2, experimental).

Takes the owner's Excel-authored 1.004/1.005 workbook (a private file that is never copied into this public
repository and is never modified), installs the fifteen 2.001 Power Query queries into its DataMashup, rewires the
Checks sheet, applies the 2.001 data steps and removes the personal data that Excel stored in the file, all by
direct OOXML editing (D-020 technique; openpyxl never saves this file). Output is byte-reproducible.

One command (from the repository root; the base is the owner's private file, passed by argument):
    python3 NFL/05-excel/archive-2.x/experimental/build_queries_installed.py --base <path to the owner's 1.005 workbook>

Options:
    --base PATH   the owner's private base workbook (or set NFL_EXPERIMENTAL_BASE). Checked by SHA-256.
    --out PATH    default NFL/.work/rc/NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx (the orchestrator
                  promotes the verified file into 05-excel/).
    --forbid-file PATH   extra words the personal-data scan must not find (keep that file out of git).

Inputs from this repository: ../powerquery/manifest.json and *.pq (Section1.m = the 15 .pq files, byte-identical),
../../02-config/{pipeline_config,leagues,scoring_weights,bonus_rules}.csv, ../../06-qa/fixtures/golden_sample.csv and
fixture_contracts.csv.

What changes inside the package is listed in README.md (technical note). Summary:
  * customXml/item1.xml (DataMashup): new Formulas/Section1.m; metadata items for the 15 queries (step-level items
    dropped, 7 connection-only items added, Check_RowCounts columns and Check_Golden recovery column updated);
    Config/Package.xml, [Content_Types].xml, permissions, permission bindings and the metadata content zip are kept
    byte-identical.
  * xl/connections.xml: 7 connection-only connections added (same form as Excel's own for Golden_Keys).
  * Checks sheet: cached 1.004 results cleared; Check_RowCounts widened to its 9 new columns (table + queryTable);
    Check_Golden moved from W5 to AB5; labelled empty anchors for the 4 new loaded checks.
  * Data: tblConfig (ReconcileTolerance, DataLocation = the published data's web address), WorkbookFolder named cell,
    tblLeagues, tblScoring and tblBonus rewritten from 02-config (rows added or removed as needed), tblGolden
    (fixture header and rows), a new table tblGoldenRules (fixture_contracts.csv) beside it, notes, nflverse
    attribution, version strings 2.001-experimental, a "Known differences" box on the Cover.
  * Personal data removed: docProps/core.xml lastModifiedBy; xl/workbook.xml x15ac:absPath (the folder the owner last
    saved in); in the Data Model (xl/model/item.data) the Windows user folder name and the machine name that Excel
    wrote into the backup log, each overwritten in place by a neutral placeholder of the same length, so no offset
    or size in the Data Model changes; the CRC-32 trailers of the two edited inner files are recomputed.
  * 1.x Plan, Requirements and RAID snapshot text: private-transcript citations, quoted chat answers and a critical
    remark about a third-party project reworded neutrally (shared-string text only).
Every part keeps the base entry's storage (compression method, date, attributes): item.data stays STORED.
One part is added (the tblGoldenRules table) with its relationship and content type; none is removed. The Power Pivot
customXml items 2-17, styles and theme are untouched.
"""
import base64
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import struct
import sys
import uuid
import zipfile
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
P = HERE.parents[2]                                   # NFL (the sport folder)
sys.path.insert(0, str(P / "05-excel" / "archive-2.x" / "build"))
import pii_scan  # noqa: E402
BASE_SHA256 = "ac302c95c9bed31552bd4d6b0aaa6b51faba6b0a5af32b93302ed41392b60877"
PQ_DIR = P / "05-excel/archive-2.x/powerquery"
CFG = P / "02-config"
GOLDEN = P / "06-qa/fixtures/golden_sample.csv"
GOLDEN_RULES = P / "06-qa/fixtures/fixture_contracts.csv"
OUT_DEFAULT = P / ".work/rc/NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx"
DATA_URL = "https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/"
REPO_URL = "https://github.com/wes-blue/sports-analysis"
LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"
ATTRIBUTION = ("The data is derived from nflverse (github.com/nflverse/nflverse-data), licensed CC BY 4.0 (%s). "
               "Details, and what this project changes, in DATA-LICENSE.md at the root of the repository %s."
               % (LICENCE_URL, REPO_URL))

VERSION = "2.001-experimental"   # one version is one file; the release 2.001 is the paste-ready workbook
KNOWN_DIFFERENCES = (
    "Experimental, not a release. Compared with the paste-ready NFL-Analysis-2.001.xlsx:\n"
    "1. Plan, Requirements, RAID, Data_Dictionary and M_Code are 1.x snapshots, for reference only.\n"
    "2. tblScoring sits just below tblLeagues: insert sheet rows above row 17 before adding more than one new league.\n"
    "3. There is no Start_Here sheet: follow NFL/05-excel/archive-2.x/experimental/README.md on GitHub.\n"
    "4. Metric_Check on the Scoring sheet (1.x) looks each metric up in the 1.x Data_Dictionary snapshot, so it says "
    "NOT IN DATASET for dst_points_allowed_excl_def, which the pipeline derives. Check_Metrics on the Checks sheet is "
    "the check that counts.")
BUILD_DATE = dt.date(2026, 11, 20)
SERIAL = (BUILD_DATE - dt.date(1899, 12, 30)).days
NEUTRAL_AUTHOR = "NFL-Analysis build_queries_installed.py"
GUID_NS = uuid.UUID("6f1d3c52-6a0e-4a51-9a59-0e2f4d1a1006")   # fixed: deterministic GUIDs, reproducible build

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
X14AC = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"
XR = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
XR3 = "http://schemas.microsoft.com/office/spreadsheetml/2016/revision3"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def q(tag):
    return "{%s}%s" % (NS, tag)


def guid(label):
    return "{%s}" % str(uuid.uuid5(GUID_NS, label)).upper()


def col_letter(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def col_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def fail(msg):
    sys.exit("BUILD STOPPED: " + msg)


def check(cond, msg):
    if not cond:
        fail(msg)


# ====================================================================================== inputs
def arg(name):
    if name in sys.argv:
        i = sys.argv.index(name)
        check(i + 1 < len(sys.argv), "%s needs a value" % name)
        return sys.argv[i + 1]
    return None


out_path = Path(arg("--out")).resolve() if arg("--out") else OUT_DEFAULT
base_arg = arg("--base") or os.environ.get("NFL_EXPERIMENTAL_BASE")
if not base_arg:
    fail("no base workbook given. This build needs the owner's private Excel-authored 1.005 workbook, which is never "
         "stored in this public repository. Pass it with --base <path> (or set NFL_EXPERIMENTAL_BASE). A session "
         "without access to that private file cannot rebuild the experimental workbook; the paste-ready workbook "
         "(05-excel/archive-2.x/build/build_workbook.py) needs no private input.")
BASE = Path(base_arg).expanduser()
if not BASE.is_file():
    fail("the base workbook was not found at the path given with --base (%s). It is the owner's private file; a session "
         "without access to it cannot rebuild the experimental workbook." % BASE)
try:
    base_bytes = BASE.read_bytes()
except OSError as e:
    fail("cannot read the base workbook given with --base: %s" % e.strerror)
check(hashlib.sha256(base_bytes).hexdigest() == BASE_SHA256,
      "the file given with --base is not the expected base workbook (SHA-256 differs; expected %s)" % BASE_SHA256)
check(BASE.resolve() != out_path, "--out must not be the base workbook")

manifest = json.loads((PQ_DIR / "manifest.json").read_text(encoding="utf-8"))["queries"]
QUERIES = [(m["name"], (PQ_DIR / m["file"]).read_bytes(), m) for m in manifest]
check(len(QUERIES) == 15, "manifest must list 15 queries, found %d" % len(QUERIES))
for name, body, _ in QUERIES:
    check(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is not None, "query name needs quoting: " + name)
    body.decode("ascii")  # the .pq files are ASCII; Section1.m is UTF-8 so they embed unchanged
    check(b"\r" not in body, name + ".pq contains CR")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


cfg_rows = read_csv(CFG / "pipeline_config.csv")
league_rows = read_csv(CFG / "leagues.csv")
weight_rows = read_csv(CFG / "scoring_weights.csv")
bonus_rows = read_csv(CFG / "bonus_rules.csv")
with open(GOLDEN, encoding="utf-8-sig", newline="") as f:
    g = list(csv.reader(f))
GOLDEN_HDR, GOLDEN_BODY = g[0], g[1:]
check(len(GOLDEN_BODY) >= 1, "golden sample has no rows")
golden_rules = read_csv(GOLDEN_RULES)
check(golden_rules and list(golden_rules[0]) == ["league", "rules_sha256", "round_decimals"], "fixture_contracts.csv header")

zin = zipfile.ZipFile(io.BytesIO(base_bytes))
infos = zin.infolist()
data = {i.filename: zin.read(i.filename) for i in infos}
changed = []


def parse(name):
    return etree.fromstring(data[name])


def put(name, root):
    data[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    changed.append(name)


def put_text(name, text):
    data[name] = text.encode("utf-8")
    changed.append(name)


# ====================================================================================== 1. DataMashup
MASHUP_PART = "customXml/item1.xml"
raw = data[MASHUP_PART]
check(raw[:2] == b"\xff\xfe", "DataMashup item is not UTF-16LE with BOM")
mtxt = raw[2:].decode("utf-16-le")
m = re.fullmatch(r'(<\?xml version="1.0" encoding="utf-16"\?><DataMashup [^>]*xmlns="http://schemas.microsoft.com/DataMashup">)'
                 r'([A-Za-z0-9+/=]+)(</DataMashup>)', mtxt)
check(m is not None, "unexpected DataMashup framing")
blob = base64.b64decode(m.group(2))


def sections(b):
    """MS-QDEFF top level: Version, then four length-prefixed blocks."""
    p = 0
    ver = b[0:4]
    p = 4
    blocks = []
    for _ in range(4):
        n = struct.unpack("<I", b[p:p + 4])[0]
        blocks.append(b[p + 4:p + 4 + n])
        p += 4 + n
    check(p == len(b), "trailing bytes after permission bindings")
    return ver, blocks


ver, (pkg, perm, meta, bindings) = sections(blob)
check(ver == b"\x00\x00\x00\x00", "DataMashup version is not 0")

# ---- 1a. package parts: replace Formulas/Section1.m only
pz = zipfile.ZipFile(io.BytesIO(pkg))
pinfos = pz.infolist()
check([i.filename for i in pinfos] == ["Config/Package.xml", "[Content_Types].xml", "Formulas/Section1.m"],
      "unexpected package parts: %s" % [i.filename for i in pinfos])
old_m = pz.read("Formulas/Section1.m").decode("utf-8")
OLD_QUERIES = re.findall(r"^shared (\w+) = ", old_m, re.M)
check(OLD_QUERIES == ["Stats_Raw", "Scoring_Weights", "Stats_Scored", "Check_Metrics", "Check_Reconciliation",
                      "Check_RowCounts", "Golden_Keys", "Check_Golden"], "unexpected queries in base: %s" % OLD_QUERIES)
NEW_NAMES = [n for n, _, _ in QUERIES]
check(set(OLD_QUERIES) <= set(NEW_NAMES), "a query loaded by the base workbook is missing from the manifest")
# Excel's own layout ("section Section1;" CRLF CRLF "shared X = <text>;" ...), each .pq embedded byte-for-byte.
section1 = b"section Section1;\r\n" + b"".join(b"\r\nshared " + n.encode() + b" = " + body + b";\r\n"
                                              for n, body, _ in QUERIES)
section1 = section1[:-2]  # Excel ends the section with ';' and no newline
pbuf = io.BytesIO()
with zipfile.ZipFile(pbuf, "w") as pzo:
    for i in pinfos:
        zi = zipfile.ZipInfo(i.filename, i.date_time)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.create_system = i.create_system
        pzo.writestr(zi, section1 if i.filename == "Formulas/Section1.m" else pz.read(i.filename))
new_pkg = pbuf.getvalue()

# ---- 1b. metadata: query-level items only, in manifest order
mver = meta[:4]
mlen = struct.unpack("<I", meta[4:8])[0]
mxml = meta[8:8 + mlen].decode("utf-8")
mrest = meta[8 + mlen:]                      # content-length + empty content zip, kept as is
check(mxml.startswith("﻿<?xml"), "metadata XML without BOM")
head_end = mxml.index("<Items>") + len("<Items>")
tail_start = mxml.index("</Items>")
items = re.findall(r"<Item>.*?</Item>", mxml[head_end:tail_start], re.S)
check("".join(items) == mxml[head_end:tail_start], "metadata items do not tile the Items element")


def item_path(it):
    mm = re.search(r"<ItemPath>(.*?)</ItemPath>", it)
    return mm.group(1) if mm else ""


all_formulas = [it for it in items if "<ItemType>AllFormulas</ItemType>" in it]
check(len(all_formulas) == 1, "AllFormulas item")
by_query = {}
step_items = 0
for it in items:
    pth = item_path(it)
    if pth.count("/") == 1 and pth.startswith("Section1/"):
        by_query[pth.split("/")[1]] = it
    elif pth.count("/") >= 2:
        step_items += 1
check(sorted(by_query) == sorted(OLD_QUERIES), "metadata query items differ from Section1.m")


def set_entry(it, typ, value):
    new, n = re.subn(r'<Entry Type="%s" Value="[^"]*" />' % typ, '<Entry Type="%s" Value="%s" />' % (typ, value), it)
    check(n == 1, "metadata entry %s not found exactly once" % typ)
    return new


# Check_RowCounts: new 9 columns (types from the query's final type table: 3 = Int64, 6 = text)
ROWCOUNTS_COLS = ["season", "season_type", "Season_Status", "Max_Week", "Published_Player_Rows",
                  "Workbook_Player_Rows", "Published_DST_Rows", "Workbook_DST_Rows", "Status"]
ROWCOUNTS_TYPES = bytes([3, 6, 6, 3, 3, 3, 3, 3, 6])
it = by_query["Check_RowCounts"]
it = set_entry(it, "FillColumnNames", "s[" + ",".join("&quot;%s&quot;" % c for c in ROWCOUNTS_COLS) + "]")
it = set_entry(it, "FillColumnTypes", "s" + base64.b64encode(ROWCOUNTS_TYPES).decode())
by_query["Check_RowCounts"] = it
GOLDEN_NEW_COL = col_index("AB")
by_query["Check_Golden"] = set_entry(by_query["Check_Golden"], "RecoveryTargetColumn", "l%d" % GOLDEN_NEW_COL)

# new queries: connection only, cloned from Excel's own connection-only item (Golden_Keys)
template = by_query["Golden_Keys"]
check("sConnectionOnly" in template and '"FillEnabled" Value="l0"' in template, "Golden_Keys is not connection only")
NEW_QUERIES = [n for n in NEW_NAMES if n not in OLD_QUERIES]
check(NEW_QUERIES == ["Bonus_Rules", "Pipeline_Scored", "Published_Seasons", "Pipeline_Status", "Check_Parity",
                      "Check_Rules_Drift", "Check_Integrity"], "unexpected new queries %s" % NEW_QUERIES)
for n in NEW_QUERIES:
    it = template.replace("<ItemPath>Section1/Golden_Keys</ItemPath>", "<ItemPath>Section1/%s</ItemPath>" % n)
    it = set_entry(it, "QueryID", "s" + guid("query:" + n)[1:-1].lower())
    by_query[n] = it
new_mxml = mxml[:head_end] + all_formulas[0] + "".join(by_query[n] for n in NEW_NAMES) + mxml[tail_start:]
etree.fromstring(new_mxml.encode("utf-8"))   # well-formed
mx = new_mxml.encode("utf-8")
new_meta = mver + struct.pack("<I", len(mx)) + mx + mrest


def block(b):
    return struct.pack("<I", len(b)) + b


new_blob = ver + block(new_pkg) + block(perm) + block(new_meta) + block(bindings)
new_txt = m.group(1) + base64.b64encode(new_blob).decode("ascii") + m.group(3)
data[MASHUP_PART] = b"\xff\xfe" + new_txt.encode("utf-16-le")
changed.append(MASHUP_PART)

# ====================================================================================== 2. connections
conn = data["xl/connections.xml"].decode("utf-8")
gk = re.search(r'<connection id="\d+" [^>]*name="Query - Golden_Keys".*?</connection>', conn).group(0)
check('refreshedVersion="0"' in gk and "saveData" not in gk, "Golden_Keys connection is not connection-only")
ids = [int(x) for x in re.findall(r'<connection id="(\d+)"', conn)]
check(ids == list(range(1, 10)), "unexpected connection ids %s" % ids)
for k, n in enumerate(NEW_QUERIES):
    c = gk.replace('id="5"', 'id="%d"' % (10 + k), 1)
    c = re.sub(r'xr16:uid="\{[^}]+\}"', 'xr16:uid="%s"' % guid("connection:" + n), c, count=1)
    c = c.replace("Golden_Keys", n)
    check(c.count(n) == 4, "connection clone for " + n)
    conn = conn.replace("</connections>", c + "</connections>")
put_text("xl/connections.xml", conn)
QT_CONN = {"Check_Metrics": 2, "Check_RowCounts": 4, "Check_Reconciliation": 3, "Check_Golden": 1}

# ====================================================================================== shared strings and cell helpers
sst = parse("xl/sharedStrings.xml")
sis = sst.findall(q("si"))
lookup = {}
for i, si in enumerate(sis):
    kids = list(si)
    if len(kids) == 1 and kids[0].tag == q("t"):
        lookup.setdefault(kids[0].text or "", i)
n_unique = [len(sis)]


def S(text):
    if text in lookup:
        return lookup[text]
    si = etree.SubElement(sst, q("si"))
    t = etree.SubElement(si, q("t"))
    t.text = text
    if text != text.strip() or "\n" in text:
        t.set(XML_SPACE, "preserve")
    lookup[text] = n_unique[0]
    n_unique[0] += 1
    return lookup[text]


def sst_text(c):
    return "".join(sst.findall(q("si"))[int(c.find(q("v")).text)].itertext())


def numtxt(v):
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return repr(v)


def setv(c, v):
    for k in list(c):
        c.remove(k)
    c.attrib.pop("t", None)
    if v is None or v == "":
        return
    if isinstance(v, str):
        c.set("t", "s")
        etree.SubElement(c, q("v")).text = str(S(v))
    else:
        etree.SubElement(c, q("v")).text = numtxt(v)


def mk(ref, style, v=None, formula=None):
    c = etree.Element(q("c"))
    c.set("r", ref)
    if style is not None:
        c.set("s", str(style))
    if formula is not None:
        etree.SubElement(c, q("f")).text = formula
    else:
        setv(c, v)
    return c


def rowmap(root):
    return {int(r.get("r")): r for r in root.find(q("sheetData")).findall(q("row"))}


def cells(row):
    return {re.match(r"[A-Z]+", c.get("r")).group(0): c for c in row.findall(q("c"))}


def newrow(rn, spans, ht=None):
    r = etree.Element(q("row"))
    r.set("r", str(rn))
    r.set("spans", spans)
    if ht:
        r.set("ht", ht)
        r.set("customHeight", "1")
    r.set("{%s}dyDescent" % X14AC, "0.25")
    return r


def insert_row(sheet_data, row):
    rn = int(row.get("r"))
    for r in sheet_data.findall(q("row")):
        if int(r.get("r")) > rn:
            r.addprevious(row)
            return
    sheet_data.append(row)


def typed(v):
    """CSV text to a cell value: whole numbers and decimals as numbers, everything else as text."""
    if v == "":
        return None
    if re.fullmatch(r"-?\d+", v) and not (len(v) > 1 and v.startswith("0")):
        return int(v)
    if re.fullmatch(r"-?\d*\.\d+", v):
        return float(v)
    return v


def set_table_ref(table_part, ref):
    t = parse(table_part)
    t.set("ref", ref)
    t.find(q("autoFilter")).set("ref", ref)
    return t


# ====================================================================================== 3. Checks sheet (sheet10)
CHECKS = "xl/worksheets/sheet10.xml"
sh = parse(CHECKS)
sd = sh.find(q("sheetData"))
rows = rowmap(sh)
label_style = cells(rows[4])["A"].get("s")
title_row, note_row = rows[1], rows[2]
for r in list(sd):
    sd.remove(r)
sd.append(title_row)
setv(cells(note_row)["A"], "Power Query outputs (2.001). Refresh All fills the four wired tables. The four tables "
     "labelled 'Load To' are installed as connection-only queries: load each once to the cell shown (README).")
sd.append(note_row)

# (query, anchor column, columns, wired?)  Wired = an existing Excel-made query table, kept or moved.
LAYOUT = [
    ("Check_Metrics", "A", ["Metric", "In_Stats_Raw", "Is_Numeric", "Used_By_Leagues", "Status"], True),
    ("Check_Reconciliation", "H", ["League", "Reconcile_To", "Rows_Compared", "Rows_Mismatched", "Match_Pct",
                                   "Status", "Worst_Examples"], True),
    ("Check_RowCounts", "R", ROWCOUNTS_COLS, True),
    ("Check_Golden", "AB", ["League", "Golden_Rows", "Matched", "Mismatched", "Status", "Worst_Examples"], True),
    ("Pipeline_Status", "AI", ["Section", "Item", "Value", "Result", "Detail"], False),
    ("Check_Parity", "AO", ["League", "Rows_Compared", "Rows_Equal", "Rows_Different", "Largest_Difference",
                            "Only_In_Workbook", "Only_In_Pipeline", "Status", "Example"], False),
    ("Check_Rules_Drift", "AY", ["League", "Kind", "Item", "Workbook", "Pipeline", "Status"], False),
    ("Check_Integrity", "BF", ["Check", "Expected", "Actual", "Status"], False),
]
spans = []
r4, r5 = newrow(4, ""), newrow(5, "")
occupied = []
for name, a, cols, wired in LAYOUT:
    c0 = col_index(a)
    c1 = c0 + len(cols) - 1
    for lo, hi in occupied:
        check(c0 > hi + 1 or c1 < lo - 1, "Checks tables overlap or touch: " + name)
    occupied.append((c0, c1))
    label = name if wired else "%s  (Load To: Existing worksheet =Checks!$%s$5)" % (name, a)
    r4.append(mk("%s4" % a, label_style, label))
    if wired:
        for k, h in enumerate(cols):
            r5.append(mk("%s5" % col_letter(c0 + k), None, h))
last_col = max(hi for _, hi in occupied)
r4.set("spans", "1:%d" % last_col)
r5.set("spans", "1:%d" % last_col)
sd.append(r4)
sd.append(r5)
sh.find(q("dimension")).set("ref", "A1:%s6" % col_letter(last_col))
# column widths: data columns 16, gap columns 2.7
colsel = sh.find(q("cols"))
for c in list(colsel):
    colsel.remove(c)
data_cols = {c for lo, hi in occupied for c in range(lo, hi + 1)}
for cidx in range(1, last_col + 1):
    c = etree.SubElement(colsel, q("col"))
    c.set("min", str(cidx))
    c.set("max", str(cidx))
    c.set("width", "16.7109375" if cidx in data_cols else "2.7109375")
    c.set("customWidth", "1")
sv = sh.find(q("sheetViews")).find(q("sheetView")).find(q("selection"))
sv.set("activeCell", "A5")
sv.set("sqref", "A5")
put(CHECKS, sh)

# the four Excel-made query tables
rels10 = data["xl/worksheets/_rels/sheet10.xml.rels"].decode()
table_of = {}
for tp in re.findall(r'Target="\.\./tables/(table\d+\.xml)"', rels10):
    tname = re.search(r' name="([^"]+)"', data["xl/tables/" + tp].decode()).group(1)
    table_of[tname] = "xl/tables/" + tp
check(sorted(table_of) == sorted(QT_CONN), "Checks tables %s" % sorted(table_of))
qt_of = {}
for tname, tpart in table_of.items():
    r = data["xl/tables/_rels/" + tpart.split("/")[-1] + ".rels"].decode()
    qt_of[tname] = "xl/queryTables/" + re.search(r'Target="\.\./queryTables/(queryTable\d+\.xml)"', r).group(1)
    qtx = data[qt_of[tname]].decode()
    check('connectionId="%d"' % QT_CONN[tname] in qtx, "queryTable/connection mismatch for " + tname)

wb = data["xl/workbook.xml"].decode("utf-8")
for name, a, cols, wired in LAYOUT:
    if not wired:
        continue
    c0 = col_index(a)
    ref = "%s5:%s6" % (a, col_letter(c0 + len(cols) - 1))
    t = set_table_ref(table_of[name], ref)
    tcols = t.find(q("tableColumns"))
    existing = [c.get("name") for c in tcols.findall(q("tableColumn"))]
    if existing != cols:
        check(name == "Check_RowCounts", "unexpected column change for " + name)
        # keep season and season_type (ids 1, 2); drop Rows (id 3); new ids from the queryTable's nextId (4)
        for c in tcols.findall(q("tableColumn")):
            if c.get("name") not in cols:
                tcols.remove(c)
        kept = [c.get("name") for c in tcols.findall(q("tableColumn"))]
        check(kept == ["season", "season_type"], "Check_RowCounts kept columns %s" % kept)
        qt = etree.fromstring(data[qt_of[name]])
        qtr = qt.find(q("queryTableRefresh"))
        next_id = int(qtr.get("nextId"))
        check(next_id == 4, "Check_RowCounts nextId")
        fields = qtr.find(q("queryTableFields"))
        for fld in fields.findall(q("queryTableField")):
            if fld.get("name") not in cols:
                fields.remove(fld)
        for h in cols[2:]:
            tc = etree.SubElement(tcols, q("tableColumn"))
            tc.set("id", str(next_id))
            tc.set("{%s}uid" % XR3, guid("Check_RowCounts:col:" + h))
            tc.set("uniqueName", str(next_id))
            tc.set("name", h)
            tc.set("queryTableFieldId", str(next_id))
            fld = etree.SubElement(fields, q("queryTableField"))
            fld.set("id", str(next_id))
            fld.set("name", h)
            fld.set("tableColumnId", str(next_id))
            next_id += 1
        tcols.set("count", str(len(cols)))
        fields.set("count", str(len(cols)))
        qtr.set("nextId", str(next_id))
        put(qt_of[name], qt)
        check([c.get("name") for c in tcols.findall(q("tableColumn"))] == cols, "Check_RowCounts columns")
    put(table_of[name], t)
    qtname = re.search(r' name="(ExternalData_\d+)"', data[qt_of[name]].decode()).group(1)
    dn = r'(<definedName name="%s" localSheetId="9" hidden="1">)Checks!\$[A-Z]+\$\d+:\$[A-Z]+\$\d+(</definedName>)' % qtname
    absref = "Checks!$%s$5:$%s$6" % (a, col_letter(c0 + len(cols) - 1))
    wb, n = re.subn(dn, lambda mm: mm.group(1) + absref + mm.group(2), wb)
    check(n == 1, "defined name " + qtname)

# ====================================================================================== 4. Config sheet (sheet5)
CONFIG = "xl/worksheets/sheet5.xml"
sh = parse(CONFIG)
sd = sh.find(q("sheetData"))
rows = rowmap(sh)
check(sst_text(cells(rows[4])["A"]) == "Setting" and sst_text(cells(rows[8])["A"]) == "RoundDecimals", "Config layout")
desc_style = cells(rows[2])["A"].get("s")
desc_text = sst_text(cells(rows[2])["A"])
label_s = cells(rows[11])["A"].get("s")
formula_s = cells(rows[11])["B"].get("s")
note_s = cells(rows[20])["A"].get("s")
note_text = sst_text(cells(rows[20])["A"])
row8 = cells(rows[8])
styles8 = {k: row8[k].get("s") for k in "ABCD"}
for rn in range(9, 21):
    if rn in rows:
        sd.remove(rows[rn])
# row 2: WorkbookFolder; row 3: the sheet description that row 2 held
r2 = rows[2]
for c in list(r2):
    r2.remove(c)
r2.set("spans", "1:4")
r2.append(mk("A2", label_s, "Workbook folder"))
r2.append(mk("B2", formula_s, formula='LEFT(CELL("filename",$A$1),FIND("[",CELL("filename",$A$1))-1)'))
r3 = newrow(3, "1:4")
r3.append(mk("A3", desc_style, desc_text + " DataLocation (row 10) is the web address the queries read the data "
             "from; leave it. Workbook folder (B2, named WorkbookFolder) is used only when DataLocation is blank."))
insert_row(sd, r3)
cfg = {r["Setting"]: r for r in cfg_rows}
check(list(cfg) == ["StartSeason", "EndSeason", "SeasonTypes", "RoundDecimals", "PublishExtraColumns",
                    "ReconcileTolerance"], "pipeline_config.csv settings %s" % list(cfg))
SETTINGS = [cfg["StartSeason"], cfg["EndSeason"], cfg["SeasonTypes"], cfg["RoundDecimals"], cfg["ReconcileTolerance"],
            {"Setting": "DataLocation", "Value": DATA_URL,
             "Allowed_Values": "a web address starting with http | a folder path | blank = automatic local search",
             "Description": "Where the pipeline's CSV files are. As shipped: the published data on GitHub (read from "
                            "the web). Or the full path of a folder that contains status.csv. Blank = the 04-data "
                            "folder next to the workbook's folder."}]
for k, s in enumerate(SETTINGS):
    rn = 5 + k
    if rn in rows and rn <= 8:
        cd = cells(rows[rn])
        for col, key in zip("ABCD", ("Setting", "Value", "Allowed_Values", "Description")):
            setv(cd[col], s[key])          # Value stays text (the Value cells are formatted as Text)
    else:
        r = newrow(rn, "1:4")
        for col, key in zip("ABCD", ("Setting", "Value", "Allowed_Values", "Description")):
            r.append(mk("%s%d" % (col, rn), styles8[col], s[key]))
        insert_row(sd, r)
r12 = newrow(12, "1:4")
r12.append(mk("A12", note_s, note_text))
insert_row(sd, r12)
mc = sh.find(q("mergeCells"))
mcell = mc.find(q("mergeCell"))
check(mcell.get("ref") == "A20:D20", "Config merge")
mcell.set("ref", "A12:D12")
sh.find(q("dimension")).set("ref", "A1:D12")
put(CONFIG, sh)
put("xl/tables/table6.xml", set_table_ref("xl/tables/table6.xml", "A4:D10"))
check("WorkbookFolder" not in wb, "WorkbookFolder already defined")
wb = wb.replace('<definedName name="WorkbookVersion">',
                '<definedName name="WorkbookFolder">Config!$B$2</definedName><definedName name="WorkbookVersion">')

# ====================================================================================== 5. Scoring: tblLeagues, tblScoring
SCORING = "xl/worksheets/sheet6.xml"
sh = parse(SCORING)
rows = rowmap(sh)


def table_part_named(sheet_part, tname):
    relp = "xl/worksheets/_rels/" + sheet_part.split("/")[-1] + ".rels"
    for tp in re.findall(r'Target="\.\./tables/(table\d+\.xml)"', data[relp].decode()):
        if re.search(r' name="%s"' % tname, data["xl/tables/" + tp].decode()):
            return "xl/tables/" + tp
    fail("table %s not found on %s" % (tname, sheet_part))


def set_cell(row, ref, style, v):
    """Set (or create, in column order) one cell of a row element."""
    col = col_index(re.match(r"[A-Z]+", ref).group(0))
    for c in row.findall(q("c")):
        cc = col_index(re.match(r"[A-Z]+", c.get("r")).group(0))
        if cc == col:
            setv(c, v)
            return 0
        if cc > col:
            c.addprevious(mk(ref, style, v))
            return 1
    row.append(mk(ref, style, v))
    return 1


def sync_rows(sh, sheet_part, tname, hdr_row, csv_rows):
    """Rewrite a table's CSV columns from csv_rows, in CSV order; rows are added (copied from the last row, so styles
    and calculated-column formulas carry over) or removed at the end, and the table ref follows.
    Returns (cells changed, rows added, rows removed)."""
    sd = sh.find(q("sheetData"))
    rows = rowmap(sh)
    tpart = table_part_named(sheet_part, tname)
    t = parse(tpart)
    c0, r0, c1, r1 = ref_box(t.get("ref"))
    check(r0 == hdr_row, "%s header row %d (table ref %s)" % (tname, hdr_row, t.get("ref")))
    if len(csv_rows) != r1 - r0:
        check(not [r for r in rows if r > r1], "%s: rows can be added or removed only when nothing sits below it" % tname)
    hdr = {sst_text(c): k for k, c in cells(rows[hdr_row]).items()}
    old_n, new_n = r1 - r0, len(csv_rows)
    for i in range(old_n, new_n):                         # add rows: deep copy of the last data row
        src = rows[r0 + old_n]
        nr = etree.fromstring(etree.tostring(src))
        rn = r0 + 1 + i
        nr.set("r", str(rn))
        for c in nr.findall(q("c")):
            c.set("r", re.match(r"[A-Z]+", c.get("r")).group(0) + str(rn))
        sd.append(nr)
        rows[rn] = nr
    for i in range(new_n, old_n):                         # remove rows
        sd.remove(rows[r0 + 1 + i])
        del rows[r0 + 1 + i]
    n = 0
    for i, rec in enumerate(csv_rows):
        row = rows[r0 + 1 + i]
        cd = cells(row)
        for key, v in rec.items():
            check(key in hdr, "%s has no column %s" % (tname, key))
            colL = hdr[key]
            want = typed(v)
            c = cd.get(colL)
            if c is None:
                if want is not None:
                    style = cells(rows[r0 + 1])[colL].get("s") if colL in cells(rows[r0 + 1]) else None
                    n += set_cell(row, "%s%d" % (colL, r0 + 1 + i), style, want)
                continue
            have = None if c.find(q("v")) is None else (sst_text(c) if c.get("t") == "s" else c.find(q("v")).text)
            if have is None or str(have) != (numtxt(want) if not isinstance(want, str) and want is not None else want):
                if c.find(q("f")) is None:
                    setv(c, want)
                    n += 1
    ref = "%s%d:%s%d" % (col_letter(c0), r0, col_letter(c1), r0 + new_n)
    if ref != t.get("ref"):
        t.set("ref", ref)
        if t.find(q("autoFilter")) is not None:
            t.find(q("autoFilter")).set("ref", ref)
        put(tpart, t)
    dim = sh.find(q("dimension"))
    m = re.fullmatch(r"([A-Z]+\d+):([A-Z]+)(\d+)", dim.get("ref"))
    dim.set("ref", "%s:%s%d" % (m.group(1), m.group(2), max(rows)))
    return n, max(0, new_n - old_n), max(0, old_n - new_n)


def ref_box(ref):
    m = re.fullmatch(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", ref)
    return col_index(m.group(1)), int(m.group(2)), col_index(m.group(3)), int(m.group(4))


check(sh.find(q("dimension")).get("ref") == "A1:K99", "Scoring layout")
n_leagues = sync_rows(sh, SCORING, "tblLeagues", 10, league_rows)
check(n_leagues[1] == 0 and n_leagues[2] == 0, "tblLeagues must keep its 5 rows (tblScoring sits below it)")
n_weights = sync_rows(sh, SCORING, "tblScoring", 18, weight_rows)
put(SCORING, sh)

BONUS = "xl/worksheets/sheet12.xml"
sh = parse(BONUS)
rows = rowmap(sh)
n_bonus = sync_rows(sh, BONUS, "tblBonus", 4, bonus_rows)
put(BONUS, sh)

# ====================================================================================== 6. Validation: tblGolden and notes
VAL = "xl/worksheets/sheet9.xml"
sh = parse(VAL)
sd = sh.find(q("sheetData"))
rows = rowmap(sh)
check(max(rows) == 88 and sst_text(cells(rows[48])["A"]) == "season", "Validation layout")
hdr_style = cells(rows[48])["A"].get("s")
body_style = cells(rows[49])["A"].get("s")
hdr_ht = rows[48].get("ht")
setv(cells(rows[16])["A"], "1.x row-count baseline (tblBaseline), kept for reference only: the 2.001 queries do not "
     "read it. Check_RowCounts now compares the workbook's rows with the pipeline's published seasons.csv.")
setv(cells(rows[47])["A"], "Golden sample (tblGolden) = 06-qa/fixtures/golden_sample.csv: hand-verified "
     "player-games. Golden_Keys reads it; Check_Golden compares it with Stats_Scored. tblGoldenRules (right) = the rules "
     "the expected values were made with (06-qa/fixtures/fixture_contracts.csv); Pipeline_Status reads it. Do not edit.")
for rn in list(range(40, 45)) + list(range(48, 89)):
    if rn in rows:
        sd.remove(rows[rn])
ncol = len(GOLDEN_HDR)
lastc = col_letter(ncol)
r = newrow(48, "1:%d" % ncol)
r.set("ht", hdr_ht)
r.set("customHeight", "1")
for k, h in enumerate(GOLDEN_HDR):
    r.append(mk("%s48" % col_letter(k + 1), hdr_style, h))
sd.append(r)
for i, rec in enumerate(GOLDEN_BODY):
    rn = 49 + i
    r = newrow(rn, "1:%d" % ncol)
    for k, v in enumerate(rec):
        r.append(mk("%s%d" % (col_letter(k + 1), rn), body_style, typed(v)))
    sd.append(r)
golden_ref = "A48:%s%d" % (lastc, 48 + len(GOLDEN_BODY))
# tblGoldenRules: one empty column right of tblGolden, header in row 48 (WORKBOOK-REQUIREMENTS.md)
GR_HDR = ["League", "Rules_SHA256", "RoundDecimals"]
gr0 = ncol + 2
grows = rowmap(sh)
for k, h in enumerate(GR_HDR):
    set_cell(grows[48], "%s48" % col_letter(gr0 + k), hdr_style, h)
for i, rec in enumerate(golden_rules):
    rn = 49 + i
    if rn not in grows:
        nr = newrow(rn, "1:%d" % (gr0 + 2))
        sd.append(nr)
        grows[rn] = nr
    vals = [rec["league"], rec["rules_sha256"], int(rec["round_decimals"])]
    check(re.fullmatch(r"[0-9a-f]{64}", vals[1]) is not None, "fixture_contracts.csv hash")
    for k, v in enumerate(vals):
        set_cell(grows[rn], "%s%d" % (col_letter(gr0 + k), rn), body_style, v)
for rn, r in grows.items():
    if r.get("spans") and int(r.get("spans").split(":")[1]) < gr0 + 2 and rn >= 48:
        r.set("spans", "1:%d" % (gr0 + 2))
gr_last = 48 + len(golden_rules)
gr_ref = "%s48:%s%d" % (col_letter(gr0), col_letter(gr0 + 2), gr_last)
sh.find(q("dimension")).set("ref", "A1:%s%d" % (col_letter(gr0 + 2), max(48 + len(GOLDEN_BODY), gr_last)))
tps = sh.find(q("tableParts"))
etree.SubElement(tps, q("tablePart")).set("{%s}id" % "http://schemas.openxmlformats.org/officeDocument/2006/relationships", "rIdGR1")
tps.set("count", str(len(tps)))
put(VAL, sh)
GR_PART = "xl/tables/table%d.xml" % (max(int(x) for x in re.findall(r"xl/tables/table(\d+)\.xml", " ".join(data))) + 1)
gr_id = max(int(re.search(rb'<table [^>]*\bid="(\d+)"', data[n]).group(1)) for n in data if re.fullmatch(r"xl/tables/table\d+\.xml", n)) + 1
gr_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
          '<table xmlns="%s" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="xr xr3" '
          'xmlns:xr="%s" xmlns:xr3="%s" id="%d" xr:uid="%s" name="tblGoldenRules" displayName="tblGoldenRules" ref="%s">'
          '<autoFilter ref="%s" xr:uid="%s"/><tableColumns count="3">%s</tableColumns>'
          '<tableStyleInfo name="TableStyleMedium2" showFirstColumn="0" showLastColumn="0" showRowStripes="1" showColumnStripes="0"/></table>'
          % (NS, XR, XR3, gr_id, guid("tblGoldenRules"), gr_ref, gr_ref, guid("tblGoldenRules:filter"),
             "".join('<tableColumn id="%d" xr3:uid="%s" name="%s"/>' % (k + 1, guid("tblGoldenRules:col:" + h), h)
                     for k, h in enumerate(GR_HDR))))
data[GR_PART] = gr_xml.encode("utf-8")
etree.fromstring(data[GR_PART])
changed.append(GR_PART)
VREL = "xl/worksheets/_rels/sheet9.xml.rels"
vr = data[VREL].decode()
check('Id="rIdGR1"' not in vr, "relationship id free")
vr = vr.replace("</Relationships>", '<Relationship Id="rIdGR1" Type="http://schemas.openxmlformats.org/officeDocument/'
                "2006/relationships/table\" Target=\"../tables/%s\"/></Relationships>" % GR_PART.split("/")[-1])
put_text(VREL, vr)
ctx = data["[Content_Types].xml"].decode()
ctx = ctx.replace("</Types>", '<Override PartName="/%s" ContentType="application/vnd.openxmlformats-officedocument.'
                  'spreadsheetml.table+xml"/></Types>' % GR_PART)
put_text("[Content_Types].xml", ctx)
t = set_table_ref("xl/tables/table14.xml", golden_ref)
check(t.get("name") == "tblGolden", "table14 is not tblGolden")
tcols = t.find(q("tableColumns"))
for c in list(tcols):
    tcols.remove(c)
for k, h in enumerate(GOLDEN_HDR, 1):
    c = etree.SubElement(tcols, q("tableColumn"))
    c.set("id", str(k))
    c.set("{%s}uid" % XR3, guid("tblGolden:col:" + h))
    c.set("name", h)
tcols.set("count", str(ncol))
put("xl/tables/table14.xml", t)

# ====================================================================================== 7. version strings and notes
sh = parse("xl/worksheets/sheet1.xml")
rows = rowmap(sh)
check(sst_text(cells(rows[4])["B"]) == "1.005", "Cover version")
setv(cells(rows[4])["B"], VERSION)
setv(cells(rows[5])["B"], SERIAL)
setv(cells(rows[6])["B"], "Experimental (not a release): queries installed by Claude, not yet opened in Excel")
setv(cells(rows[8])["B"], "NFL weekly player stats and fantasy points for your leagues. The pipeline on GitHub "
     "(wes-blue/sports-analysis) publishes the data; this workbook reads it from the web, re-scores every league with "
     "your Scoring and Bonus tables and checks itself against the pipeline.")
# Known differences box in the empty row 3 (QA m-12): label, wrapped text merged over B:C, taller row
row3 = rows[3]
check(len(row3) == 0, "Cover row 3 empty")
row3.set("ht", "165")
row3.append(mk("A3", cells(rows[7])["A"].get("s"), "Known differences"))
row3.append(mk("B3", cells(rows[7])["B"].get("s"), KNOWN_DIFFERENCES))
row3.append(mk("C3", cells(rows[7])["C"].get("s")))
cmc = sh.find(q("mergeCells"))
etree.SubElement(cmc, q("mergeCell")).set("ref", "B3:C3")
cmc.set("count", str(len(cmc)))
setv(cells(rows[7])["B"], "2.001: Power Query reads the pipeline's published CSV files from the web (DataLocation), "
     "re-scores every league with the Scoring and Bonus tables, and checks itself against the pipeline (parity, rules "
     "drift, golden sample, reconciliation)")
setv(cells(rows[14])["B"], "Settings that Power Query reads (tblConfig), including DataLocation, the web address of the data.")
setv(cells(rows[19])["B"], "Power Query check outputs (row 5). Refresh All fills them; leave the anchor areas empty.")
setv(cells(rows[34])["A"], "Data source")
setv(cells(rows[35])["A"], "Data location")
setv(cells(rows[35])["B"], "The pipeline's published CSV files, read from the web address in Config > tblConfig > "
     "DataLocation: " + DATA_URL)
r36 = newrow(36, "1:3")
r36.append(mk("A36", cells(rows[35])["A"].get("s"), "Data licence"))
r36.append(mk("B36", cells(rows[35])["B"].get("s"), ATTRIBUTION))
insert_row(sh.find(q("sheetData")), r36)
sh.find(q("dimension")).set("ref", "A1:C36")
put("xl/worksheets/sheet1.xml", sh)

sh = parse("xl/worksheets/sheet11.xml")
sd = sh.find(q("sheetData"))
rows = rowmap(sh)
check(max(rows) == 9 and sst_text(cells(rows[9])["A"]) == "1.005", "Version_Log layout")
check(sst_text(cells(rows[8])["A"]) == "1.004", "Version_Log 1.004 row")
setv(cells(rows[8])["C"], "Superseded by 1.006")
setv(cells(rows[9])["C"], "Withdrawn (never released; D-028)")
tm = cells(rows[9])
# QA-m8: the 1.006 row (the last 1.x release) from build/version_history.csv, then the experimental row
vh = {r_["Version"]: r_ for r_ in read_csv(P / "05-excel/archive-2.x/build/version_history.csv")}
check("1.006" in vh, "version_history.csv has no 1.006 row")
v6 = vh["1.006"]
r = newrow(10, "1:6")
for col, v in zip("ABCDEF", ("1.006", (dt.date.fromisoformat(v6["Date"]) - dt.date(1899, 12, 30)).days, v6["Status"],
                             v6["Summary"], v6["Gates_Passed"], v6["Built_By"])):
    r.append(mk("%s10" % col, tm[col].get("s"), v))
sd.append(r)
r = newrow(11, "1:6")
for col, v in zip("ABCDEF", (VERSION, SERIAL, "Experimental (not a release; untested in Excel)",
                             "Pipeline-fed workbook reading the published data from the web, with the fifteen 2.001 "
                             "queries installed directly in the file (experimental E2 build from the owner's "
                             "1.004/1.005 workbook).",
                             "Structural checks only; Excel pending", "Claude (E2 Mashup Engineer, experimental)")):
    r.append(mk("%s11" % col, tm[col].get("s"), v))
sd.append(r)
sh.find(q("dimension")).set("ref", "A1:F11")
put("xl/worksheets/sheet11.xml", sh)
put("xl/tables/table19.xml", set_table_ref("xl/tables/table19.xml", "A4:F11"))

sh = parse("xl/worksheets/sheet8.xml")
rows = rowmap(sh)
setv(cells(rows[2])["A"], "1.x snapshot of the M code, for reference only. The 2.001 queries are installed in this "
     "workbook (Data > Queries & Connections); their source is 05-excel/archive-2.x/powerquery/*.pq. Do not paste from this sheet.")
put("xl/worksheets/sheet8.xml", sh)
sh = parse("xl/worksheets/sheet13.xml")
rows = rowmap(sh)
setv(cells(rows[2])["A"], "1.x reference only: static long-touchdown counts (tblLongTD). The 2.001 queries do not read "
     "this sheet; the pipeline derives long touchdowns from play-by-play (D-029).")
put("xl/worksheets/sheet13.xml", sh)

# ====================================================================================== 8. workbook, properties, shared strings
# personal data 1: x15ac:absPath = the folder the owner last saved the file in (Excel rewrites it at the next save)
wb, n_abs = re.subn(r'<mc:AlternateContent xmlns:mc="[^"]+"><mc:Choice Requires="x15"><x15ac:absPath [^>]*/></mc:Choice>'
                    r'</mc:AlternateContent>', "", wb)
check(n_abs == 1 and "absPath" not in wb, "x15ac:absPath removed")
put_text("xl/workbook.xml", wb)
app = data["docProps/app.xml"].decode("utf-8")
check("<vt:lpstr>Named Ranges</vt:lpstr></vt:variant><vt:variant><vt:i4>9</vt:i4>" in app, "app.xml named ranges")
app = app.replace("<vt:lpstr>Named Ranges</vt:lpstr></vt:variant><vt:variant><vt:i4>9</vt:i4>",
                  "<vt:lpstr>Named Ranges</vt:lpstr></vt:variant><vt:variant><vt:i4>10</vt:i4>")
app = app.replace('<TitlesOfParts><vt:vector size="22"', '<TitlesOfParts><vt:vector size="23"')
app = app.replace("<vt:lpstr>WorkbookVersion</vt:lpstr>", "<vt:lpstr>WorkbookFolder</vt:lpstr><vt:lpstr>WorkbookVersion</vt:lpstr>")
put_text("docProps/app.xml", app)
core = data["docProps/core.xml"].decode("utf-8")
core, n1 = re.subn(r"<dc:title>[^<]*</dc:title>", "<dc:title>NFL-Analysis-%s</dc:title>" % VERSION, core)
core, n2 = re.subn(r"<cp:version>[^<]*</cp:version>", "<cp:version>%s</cp:version>" % VERSION, core)
core, n4 = re.subn(r"<cp:lastModifiedBy>[^<]*</cp:lastModifiedBy>", "<cp:lastModifiedBy>%s</cp:lastModifiedBy>" % NEUTRAL_AUTHOR, core)
check(n4 == 1, "core.xml lastModifiedBy")   # personal data 2: the owner's name
core, n3 = re.subn(r"<dcterms:modified xsi:type=\"dcterms:W3CDTF\">[^<]*</dcterms:modified>",
                   '<dcterms:modified xsi:type="dcterms:W3CDTF">%sT00:00:00Z</dcterms:modified>' % BUILD_DATE, core)
check(n1 == n2 == n3 == 1, "core.xml")
put_text("docProps/core.xml", core)
# personal data 3: the Data Model backup log names the Windows user folder (also in 8.3 short form) and the machine.
# Each name is overwritten in place by a neutral placeholder of the same length (UTF-16LE and ASCII), so no size or
# offset in the ABF backup changes; the paths stay consistent with each other (Excel restores the model into a new
# temporary folder of its own at every load).
MODEL = "xl/model/item.data"
mb = data[MODEL]
u16 = mb.decode("latin-1")   # byte-transparent view for regex over UTF-16LE text
users = set(re.findall(r"\\\x00U\x00s\x00e\x00r\x00s\x00\\\x00((?:[^\\\x00]\x00){1,64}?)\\\x00", u16))
machines = set(re.findall(r"<\x00O\x00b\x00j\x00e\x00c\x00t\x00P\x00a\x00t\x00h\x00>\x00((?:[^\\\x00<]\x00){1,64}?)\\\x00L\x00o\x00c\x00a\x00l\x00C\x00u\x00b\x00e", u16))
users_a = set(re.findall(r"\\Users\\([^\\\x00]{1,64}?)\\", u16))
machines_a = set(re.findall(r"<ObjectPath>([^\\<\x00]{1,64}?)\\LocalCube", u16))
names = {}
for u in users:
    names[u.encode("latin-1").decode("utf-16-le")] = "user"
for m_ in machines:
    names[m_.encode("latin-1").decode("utf-16-le")] = "machine"
for u in users_a:
    names[u] = "user"
for m_ in machines_a:
    names[m_] = "machine"
model_replacements = []
for nm, kind in sorted(names.items()):
    neutral = (("U" if kind == "user" else "PC") + "0" * 64)[:len(nm)]
    if nm == neutral:
        continue
    cnt = 0
    for enc in ("utf-16-le", "ascii"):
        try:
            a_, b_ = nm.encode(enc), neutral.encode(enc)
        except UnicodeEncodeError:
            continue
        cnt += mb.count(a_)
        mb = mb.replace(a_, b_)
    model_replacements.append((kind, len(nm), cnt))
check(len(mb) == len(data[MODEL]), "Data Model size unchanged")
# The Data Model stores a CRC-32/BZIP2 trailer (4 bytes, little-endian) after every inner file, including the two plain
# UTF-16 files edited above (LOG, the backup log, and PARTITIONS). Every changed byte must lie inside an inner file's
# content (never in a trailer, the header or the VirtualDirectory), and the trailer of each edited file is recomputed,
# so every inner file's checksum is valid again, as in the base (790 of 790).
model_files = pii_scan.abf_files(data[MODEL])
check(len(model_files) > 2 and all(pii_scan.crc32_bzip2(data[MODEL][o:o + n - 4]) == struct.unpack("<I", data[MODEL][o + n - 4:o + n])[0]
                                   for _, o, n in model_files), "Data Model: base inner-file checksums not as expected")
mbuf = bytearray(mb)
crc_fixed = []
diff_at = [i for i in range(len(mb)) if mb[i] != data[MODEL][i]] if mb != data[MODEL] else []
for fname, o, n in model_files:
    inside = [i for i in diff_at if o <= i < o + n]
    if inside:
        check(max(inside) < o + n - 4, "Data Model: a placeholder overlaps the checksum of " + fname)
        mbuf[o + n - 4:o + n] = struct.pack("<I", pii_scan.crc32_bzip2(bytes(mbuf[o:o + n - 4])))
        crc_fixed.append(fname)
check(sum(1 for i in diff_at if any(o <= i < o + n - 4 for _, o, n in model_files)) == len(diff_at),
      "Data Model: a changed byte lies outside the inner files")
mb = bytes(mbuf)
check(all(pii_scan.crc32_bzip2(mb[o:o + n - 4]) == struct.unpack("<I", mb[o + n - 4:o + n])[0] for _, o, n in model_files),
      "Data Model: inner-file checksums after the edit")
if mb != data[MODEL]:
    data[MODEL] = mb
    changed.append(MODEL)

# private-repository folder names in the 1.x snapshot text (Requirements, M_Code): neutral wording instead
PRIVATE_TEXT = [(re.compile(r"\b[A-Z][a-z]+/NFL-Analysis\b(?!-)"), "the 1.x project folder"),
                (re.compile(r"\b\d\d-[A-Za-z]+/NFL-Analysis-Workbook/src/powerquery/"), "the 1.x Power Query source folder"),
                (re.compile(r"\b\d\d-[A-Z][a-z]+/[^\s;,]*[A-Za-z0-9]"), "a file in the private 1.x project")]
LEFTOVER = re.compile(r"\b\d\d-[A-Z][a-z]+/|\b[A-Z][a-z]+/NFL-Analysis\b(?!-)")
n_private = 0
for t_ in sst.iter(q("t")):
    if t_.text:
        for rx_, b_ in PRIVATE_TEXT:
            t_.text, k_ = rx_.subn(b_, t_.text)
            n_private += k_
check(not LEFTOVER.search("".join(t_.text or "" for t_ in sst.iter(q("t")))), "private folder names left in shared strings")

# QA-m10: the 1.x Plan, Requirements and RAID snapshots cited the owner's private 1.x source transcript by line, quoted
# the owner's chat answers and repeated a critical remark about a third-party project. Neutral wording instead. Only
# the text of shared strings changes (no worksheet XML), and only strings that no other sheet uses.
SNAPSHOT_SHEETS = ("Plan", "Requirements", "RAID")
SNAPSHOT_EDITS = [
    # RAID detail texts (before the shorter source edits below, which would otherwise cut into them)
    ("Old column names in transcript formula and code", "Old column names in older formulas and code"),
    ("The Half-PPR formula (Transcript L59) and the PRISM code use", "Older Half-PPR formulas and code samples use"),
    ("Record.FieldOrDefault(_, metric, 0) (Transcript L301) hides missing metrics: no error, but wrong totals. Source: "
     "Transcript L301, L314; Orchestrator review.",
     "Record.FieldOrDefault(_, metric, 0) hides missing metrics: no error, but wrong totals. Source: Orchestrator review."),
    ("The transcript's 'schema drift protection' (L252-253, L314) is a feature and a hazard: drift becomes invisible. "
     "Source: Transcript L252-253; Orchestrator review.",
     "Silent defaults for missing columns ('schema drift protection') are a feature and a hazard: drift becomes "
     "invisible. Source: Orchestrator review."),
    (" Not in the transcript.", ""),
    ("The code uses {2014..2023} (Transcript L291), contradicting 'last 10 years' (L3) and earlier 2016-2026 ranges "
     "(L9, L15). Source: Transcript L3, L291.",
     "A hardcoded season window such as {2014..2023} goes out of date. Source: Orchestrator review."),
    ("DraftKings bonuses (Transcript L51) and D/ST or kicker tiers cannot be modelled as stat x multiplier. Source: "
     "Transcript L51, L52; Orchestrator review.",
     "DraftKings bonuses and D/ST or kicker tiers cannot be modelled as stat x multiplier. Source: Orchestrator review."),
    ("; the transcript asked for the Excel version (L254) and got no answer. Source: Orchestrator review; Transcript L254.",
     "; the Excel version was not yet confirmed. Source: Orchestrator review."),
    ("Transcript Blind Spots 1 and 2 (L245-250): avoid", "Avoid"),
    ("Replaces the transcript's single Metric/Multiplier table (L238) with", "Replaces a single Metric/Multiplier table with"),
    (" Transcript L254 asked the same and was not answered.", ""),
    ("ESPN, Sleeper, Yahoo, DraftKings or FanDuel (Transcript L51)?", "ESPN, Sleeper, Yahoo, DraftKings or FanDuel?"),
    ("The combined file named at Transcript L76 returns HTTP 404; only per-season files exist. Source: Transcript L76; ",
     "The combined file returns HTTP 404; only per-season files exist. Source: "),
    (' (user, 2026-11-14: "I\'ll paste").', " (user, 2026-11-14)."),
    ('Accepted by the user, 2026-11-14 ("yes"):', "Accepted by the user, 2026-11-14:"),
    # Plan: what you are trying to do, and key findings
    (" (Transcript L3, L224).", "."),
    (" (Transcript L212, L259).", "."),
    (" (Transcript L224).", "."),
    (" (Transcript L178, L248-250).", "."),
    (" names in the first answer are superseded by the unified stats_player release; the transcript says so itself.",
     " names are superseded by the unified stats_player release."),
    ("The transcript's Half-PPR formula and the PRISM M code use old column names",
     "Older Half-PPR formulas and M code samples use old column names"),
    (" The transcript presents this as 'schema drift protection'.", ""),
    (" The transcript does not mention this.", ""),
    ("The window is hardcoded as {2014..2023}, which contradicts 'last 10 years' and the 2016-2026 ranges quoted "
     "earlier (11 seasons). It must be parameterised.",
     "A hardcoded season window such as {2014..2023} goes out of date. It must be parameterised."),
    (" The transcript asked for the Excel version (L254) but it was never answered.", ""),
    ("Transcript Blind Spot 1: Excel", "Excel"),
    ("Transcript Blind Spot 2: load", "Load"),
    (" mentioned in the transcript returns", " returns"),
    (" but needs R and maps an outdated column name (interceptions).", "."),
    (" ffscrapr needs R and a supported league platform and maps an outdated column name.", ""),
    # Requirements
    (" Confirmed by the user (D-007: B, 'I'll paste').", " Confirmed by the user (D-007: option B)."),
    # Source columns (Plan C, Requirements E)
    ("Orchestrator review (formula at Transcript L59; code at L301)", "Orchestrator review"),
    ("Transcript L245-250 (D-003)", "1.x brief (D-003)"),
    ("; Transcript L254", ""),
]
SOURCE_ONLY = re.compile(r"Transcript L\d+(?:-\d+)?(?:, L\d+(?:-\d+)?)*")    # a whole cell that only cites lines
SOURCE_PREFIX = re.compile(r"^Transcript L\d+(?:-\d+)?(?:, L\d+(?:-\d+)?)*; ")  # "Transcript L.., L..; <other source>"
CANDID_LEFT = re.compile(r"(?i)\btranscript\b|outdated column name|\bneeds R and\b|\bPRISM\b|I'll paste|\(\"yes\"\)")
_wrels = {r_.get("Id"): r_.get("Target") for r_ in etree.fromstring(data["xl/_rels/workbook.xml.rels"])}
_sheet_part = {s_.get("name"): "xl/" + _wrels[s_.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")]
               for s_ in etree.fromstring(data["xl/workbook.xml"]).find(q("sheets"))}


def sst_refs(part):
    return [int(v) for v in re.findall(rb'<c [^>]*t="s"[^>]*>(?:<f>[^<]*</f>)?<v>(\d+)</v>', data[part])]


snap_refs = {nm: sst_refs(_sheet_part[nm]) for nm in SNAPSHOT_SHEETS}
other_refs = set()
for nm, part in _sheet_part.items():
    if nm not in SNAPSHOT_SHEETS:
        other_refs.update(sst_refs(part))
sis = sst.findall(q("si"))
used_edits = set()
snap_changed = set()
for idx in sorted(set().union(*snap_refs.values())):
    si = sis[idx]
    old_t = "".join(si.itertext())
    new_t = old_t
    for k_, (a_, b_) in enumerate(SNAPSHOT_EDITS):
        if a_ in new_t:
            new_t = new_t.replace(a_, b_)
            used_edits.add(k_)
    new_t = SOURCE_PREFIX.sub("", new_t)
    if SOURCE_ONLY.fullmatch(new_t):
        new_t = "1.x brief"
    if new_t != old_t:
        check(idx not in other_refs, "snapshot string %d is also used outside the snapshot sheets" % idx)
        check(len(si) == 1 and si[0].tag == q("t"), "snapshot string %d is rich text" % idx)
        si[0].text = new_t
        snap_changed.add(idx)
check(len(used_edits) == len(SNAPSHOT_EDITS), "snapshot edits not found: %s" % [SNAPSHOT_EDITS[k_][0] for k_ in
                                                                              range(len(SNAPSHOT_EDITS)) if k_ not in used_edits])
left = [t_ for t_ in ("".join(si.itertext()) for si in sis) if CANDID_LEFT.search(t_)]
check(not left, "private-source or candid text left in shared strings: %d string(s)" % len(left))
snap_cells = {nm: sum(1 for i_ in refs if i_ in snap_changed) for nm, refs in snap_refs.items()}

# exact reference count over every sheet
refs = sum(len(re.findall(rb'<c [^>]*t="s"', data[n])) for n in data if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
sst.set("count", str(refs))
sst.set("uniqueCount", str(n_unique[0]))
put("xl/sharedStrings.xml", sst)

# ====================================================================================== write (same part order and storage as the base)
# Each part keeps the base entry's compression method (xl/model/item.data is STORED, as Excel wrote it; every other
# part is deflated), date and attributes; the added table part copies those of the base's tblGolden part.
out_path.parent.mkdir(parents=True, exist_ok=True)
names_out = [i.filename for i in infos] + [GR_PART]
base_info = {i.filename: i for i in infos}
base_info[GR_PART] = base_info["xl/tables/table14.xml"]
with zipfile.ZipFile(out_path, "w") as zo:
    for n_ in names_out:
        bi = base_info[n_]
        zi = zipfile.ZipInfo(n_, bi.date_time)
        zi.compress_type = bi.compress_type
        zi.create_system = bi.create_system
        zi.external_attr = bi.external_attr
        zo.writestr(zi, data[n_])
with zipfile.ZipFile(out_path) as zc:
    check([(i.filename, i.compress_type) for i in zc.infolist()] == [(n_, base_info[n_].compress_type) for n_ in names_out],
          "output compression differs from the base")
findings, pinv = pii_scan.scan(str(out_path), pii_scan.load_forbidden(None, arg("--forbid-file")), candid=True)
for f in findings:
    print("PERSONAL DATA: %(part)s | %(rule)s | %(detail)s" % f)
if findings:
    out_path.unlink()
    fail("personal-data scan found %d item(s); the output was deleted" % len(findings))
print("personal data removed: core.xml lastModifiedBy; workbook.xml absPath; Data Model names (kind, length, "
      "occurrences): %s, checksums recomputed for inner files %s; private folder names in 1.x snapshot text: %d"
      % (model_replacements, crc_fixed, n_private))
print("1.x snapshot text neutralised (QA-m10): %d shared strings, cells per sheet %s" % (len(snap_changed), snap_cells))
print("PERSONAL-DATA SCAN: clean (%d parts, %d texts)" % (pinv["parts"], pinv["texts_scanned"]))

print("wrote", out_path)
print("sha256", hashlib.sha256(out_path.read_bytes()).hexdigest())
print("Section1.m: %d queries, %d bytes; metadata items: %d query + 1 AllFormulas (dropped %d step items)"
      % (len(QUERIES), len(section1), len(NEW_NAMES), step_items))
print("cells changed / rows added / rows removed: tblLeagues %s; tblScoring %s; tblBonus %s" % (n_leagues, n_weights, n_bonus))
print("changed parts (%d):" % len(set(changed)))
for c in sorted(set(changed)):
    print("   ", c)
