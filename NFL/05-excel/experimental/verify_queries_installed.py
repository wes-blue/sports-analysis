"""Structural, data, personal-data and recalculation checks for the experimental workbook (E2 proof).

Usage: python3 verify_queries_installed.py [<workbook.xlsx>] [--base <owner's private base workbook>] [--forbid-file PATH]
Default workbook: NFL/.work/rc/NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx. The base (or NFL_EXPERIMENTAL_BASE)
is optional: without it the comparison with the base (section 2) is skipped and said so. Checks the Open XML package,
the query-table wiring, the data tables against the config CSVs, scans every part for personal data (section 6; it
fails if the owner's name, a user folder, a machine name or the last-saved folder reappears), and recalculates a copy
with LibreOffice headless (in NFL/.work/e2/lo/). Exit code 1 on any FAIL.
The independent DataMashup reader is verify_mashup.js (Node)."""
import csv
import hashlib
import io
import os
import posixpath
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import openpyxl
from lxml import etree

HERE = Path(__file__).resolve().parent
P = HERE.parents[1]                                   # NFL
sys.path.insert(0, str(P / "05-excel" / "build"))
import pii_scan  # noqa: E402


def arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else None


positional = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] not in ("--base", "--forbid-file")]
OUT = Path(positional[0]) if positional else P / ".work/rc/NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx"
_b = arg("--base") or os.environ.get("NFL_EXPERIMENTAL_BASE")
BASE = Path(_b) if _b and Path(_b).is_file() else None
if not OUT.is_file():
    sys.exit("verify: workbook not found: %s (build it with build_queries_installed.py --base <private base>)" % OUT)
URL = "https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/"
WORK = P / ".work/e2/lo"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
      "ct": "http://schemas.openxmlformats.org/package/2006/content-types"}
fails = []


def ok(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        fails.append(msg)


def load(path):
    z = zipfile.ZipFile(path)
    names = [i.filename for i in z.infolist()]
    return z, names, {n: z.read(n) for n in names}


oz, onames, odata = load(OUT)
if BASE is not None:
    bz, bnames, bdata = load(BASE)
print("output sha256", hashlib.sha256(OUT.read_bytes()).hexdigest(), OUT.stat().st_size, "bytes")

# ------------------------------------------------------------------ 1. Open XML package
print("\n== 1. Open XML package")
ok(len(onames) == len(set(onames)), "no duplicate zip entries (%d parts)" % len(onames))
ok(oz.testzip() is None, "zip CRCs valid")
bad = []
for n, b in odata.items():
    if n.endswith(".xml") or n.endswith(".rels"):
        try:
            etree.fromstring(b)
        except etree.XMLSyntaxError as e:
            bad.append("%s: %s" % (n, e))
ok(not bad, "every XML part well formed (%d parts)%s" % (sum(n.endswith((".xml", ".rels")) for n in odata), bad))
ct = etree.fromstring(odata["[Content_Types].xml"])
defaults = {d.get("Extension").lower(): d.get("ContentType") for d in ct.findall("ct:Default", NS)}
overrides = {o.get("PartName"): o.get("ContentType") for o in ct.findall("ct:Override", NS)}
untyped = [n for n in onames if n != "[Content_Types].xml" and "/" + n not in overrides
           and n.rsplit(".", 1)[-1].lower() not in defaults]
ok(not untyped, "every part has a content type%s" % (": %s" % untyped if untyped else ""))
dangling = [p for p in overrides if p.lstrip("/") not in odata]
ok(not dangling, "every Override names an existing part%s" % (": %s" % dangling if dangling else ""))
broken = []
nrels = 0
for n in onames:
    if not n.endswith(".rels"):
        continue
    src_dir = posixpath.dirname(posixpath.dirname(n))
    for rel in etree.fromstring(odata[n]).findall("pr:Relationship", NS):
        nrels += 1
        if rel.get("TargetMode") == "External":
            continue
        t = rel.get("Target")
        tgt = t.lstrip("/") if t.startswith("/") else posixpath.normpath(posixpath.join(src_dir, t))
        if tgt not in odata:
            broken.append("%s -> %s" % (n, t))
ok(not broken, "every relationship resolves (%d internal relationships)%s" % (nrels, broken))

# ------------------------------------------------------------------ 2. difference from the base
print("\n== 2. Parts compared with the base")
if BASE is None:
    print("SKIP  no base workbook given (--base or NFL_EXPERIMENTAL_BASE): the base is the owner's private file")
else:
    added = [n for n in onames if n not in bdata]
    ok([n for n in onames if n in bdata] == bnames and len(added) == 1 and re.fullmatch(r"xl/tables/table\d+\.xml", added[0]),
       "the base's %d parts in the same order, plus one added table part (%s); none removed" % (len(bnames), added))
    same = [n for n in bnames if odata[n] == bdata[n]]
    diff = [n for n in bnames if odata[n] != bdata[n]]
    EXPECTED = {"[Content_Types].xml", "customXml/item1.xml", "docProps/app.xml", "docProps/core.xml", "xl/connections.xml",
                "xl/model/item.data", "xl/queryTables/queryTable2.xml", "xl/sharedStrings.xml", "xl/workbook.xml",
                "xl/tables/table6.xml", "xl/tables/table8.xml", "xl/tables/table14.xml", "xl/tables/table15.xml",
                "xl/tables/table16.xml", "xl/tables/table17.xml", "xl/tables/table18.xml", "xl/tables/table19.xml",
                "xl/tables/table20.xml", "xl/worksheets/_rels/sheet9.xml.rels",
                "xl/worksheets/sheet1.xml", "xl/worksheets/sheet5.xml", "xl/worksheets/sheet6.xml",
                "xl/worksheets/sheet8.xml", "xl/worksheets/sheet9.xml", "xl/worksheets/sheet10.xml",
                "xl/worksheets/sheet11.xml", "xl/worksheets/sheet12.xml", "xl/worksheets/sheet13.xml"}
    OPTIONAL = {"xl/tables/table8.xml", "xl/tables/table20.xml", "xl/worksheets/sheet12.xml"}  # only when row counts change
    ok(EXPECTED - OPTIONAL <= set(diff) <= EXPECTED, "changed parts are the intended ones%s" % (
        "" if EXPECTED - OPTIONAL <= set(diff) <= EXPECTED else ": unexpected %s, missing %s" % (set(diff) - EXPECTED, EXPECTED - OPTIONAL - set(diff))))
    for n in diff:
        print("      %-36s %9d -> %9d bytes" % (n, len(bdata[n]), len(odata[n])))
    must_keep = [n for n in bnames if re.match(r"customXml/item(\d+)\.xml$", n) and n != "customXml/item1.xml"] + \
        [n for n in bnames if n.startswith("customXml/") and ("itemProps" in n or "_rels" in n)] + \
        ["xl/queryTables/queryTable1.xml", "xl/queryTables/queryTable3.xml",
         "xl/queryTables/queryTable4.xml", "xl/styles.xml", "xl/theme/theme1.xml",
         "xl/_rels/workbook.xml.rels", "xl/worksheets/_rels/sheet10.xml.rels"]
    ok(all(n in same for n in must_keep), "Power Pivot items 2-17, customXml props/rels, untouched queryTables, styles, "
       "theme and workbook rels byte-identical (%d parts)" % len(must_keep))
    # storage: every part is stored the way the base stores it (QA-m9: item.data STORED, as Excel wrote it)
    binfo = {i.filename: i for i in bz.infolist()}
    oinfo = {i.filename: i for i in oz.infolist()}
    cdiff = [n for n in bnames if oinfo[n].compress_type != binfo[n].compress_type]
    ok(not cdiff and oinfo[added[0]].compress_type == zipfile.ZIP_DEFLATED,
       "compression method of every part equals the base's (%d parts; stored: %s; the added part deflated)%s" % (
           len(bnames), [n for n in bnames if binfo[n].compress_type == zipfile.ZIP_STORED], cdiff or ""))
    import base64

    def pkg_infos(d):
        t = d["customXml/item1.xml"][2:].decode("utf-16-le")
        blob = base64.b64decode(re.search(r">([A-Za-z0-9+/=]+)</DataMashup>", t).group(1))
        n = struct.unpack("<I", blob[4:8])[0]
        return [(i.filename, i.compress_type) for i in zipfile.ZipFile(io.BytesIO(blob[8:8 + n])).infolist()]
    ok(pkg_infos(odata) == pkg_infos(bdata), "Power Query package: same inner parts, order and compression as the base %s"
       % pkg_infos(odata))
    # Data Model: same size; every changed byte belongs to a neutral placeholder (U000..., PC000...), UTF-16LE or ASCII,
    # or to the CRC trailer of an edited inner file
    bm, om = bdata["xl/model/item.data"], odata["xl/model/item.data"]
    runs, i = [], 0
    while i < len(bm):
        if bm[i] != om[i]:
            j = i
            while j < len(bm) and (bm[j] != om[j] or (j + 1 < len(bm) and bm[j + 1] != om[j + 1])):
                j += 1
            runs.append((i, j))
            i = j
        i += 1
    mfiles = pii_scan.abf_files(bm)
    ok(mfiles == pii_scan.abf_files(om), "Data Model: same header and VirtualDirectory (%d inner files, same offsets "
       "and sizes)" % len(mfiles))
    trailers = {(o + n - 4, o + n): f for f, o, n in mfiles}
    in_trailer = lambda r: any(a <= r[0] and r[1] <= b for a, b in trailers)
    bad_runs = [r for r in runs if not set(om[r[0]:r[1]]) <= set(b"UPC0\x00") and not in_trailer(r)]
    edited = sorted({f for f, o, n in mfiles for r in runs if o <= r[0] < o + n})
    ok(len(bm) == len(om) and runs and not bad_runs,
       "Data Model: same size (%d bytes); %d changed runs, all neutral placeholders (U000.../PC000...) or the "
       "checksum trailer of an edited inner file%s" % (len(om), len(runs), " BAD %s" % bad_runs[:3] if bad_runs else ""))
    crc_bad = lambda d: [f for f, o, n in mfiles if pii_scan.crc32_bzip2(d[o:o + n - 4]) != struct.unpack("<I", d[o + n - 4:o + n])[0]]
    ok(not crc_bad(bm) and not crc_bad(om) and edited == ["LOG", "PARTITIONS"],
       "Data Model: every inner file's CRC-32/BZIP2 trailer valid in the base and the output (%d of %d); edited inner "
       "files %s (both plain UTF-16 XML, same length)" % (len(mfiles) - len(crc_bad(om)), len(mfiles), edited))
    logf = [x for x in mfiles if x[0] == "LOG"][0]
    log = om[logf[1]:logf[1] + logf[2] - 4].decode("utf-16-le")
    root = re.search(r"<ServerRoot>([^<]*)</ServerRoot>", log).group(1)
    paths = re.findall(r"<(?:Path|PersistLocationPath)>([^<]*)</(?:Path|PersistLocationPath)>", log)
    ok(paths and all(p_.startswith(root) for p_ in paths),
       "Data Model backup log: all %d file paths still start with its ServerRoot (placeholders applied consistently)" % len(paths))
    sizes = dict((sp, int(sz)) for sp, sz in re.findall(r"<StoragePath>([^<]*)</StoragePath><LastWriteTime>\d+</LastWriteTime><Size>(\d+)</Size>", log))
    ok(len(sizes) == len(mfiles) - 2 and all(len(pii_scan.abf_inner(om, o, n)) == sizes[f] for f, o, n in mfiles if f in sizes),
       "Data Model: all %d data files decompress to the size the backup log records (their contents scanned in section 6)" % len(sizes))
    print("      byte-identical parts: %d of %d" % (len(same), len(bnames)))

# ------------------------------------------------------------------ 3. workbook wiring
print("\n== 3. Tables, query tables, connections, names")
wbx = etree.fromstring(odata["xl/workbook.xml"])
sst = [("".join(si.itertext())) for si in etree.fromstring(odata["xl/sharedStrings.xml"]).findall("m:si", NS)]
wrels = {r.get("Id"): r.get("Target") for r in etree.fromstring(odata["xl/_rels/workbook.xml.rels"]).findall("pr:Relationship", NS)}
sheets = [(s.get("name"), "xl/" + wrels[s.get("{%s}id" % NS["r"])]) for s in wbx.find("m:sheets", NS)]


def ref_box(ref):
    m = re.fullmatch(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", ref)
    ci = lambda s: sum((ord(c) - 64) * 26 ** i for i, c in enumerate(reversed(s)))
    return ci(m.group(1)), int(m.group(2)), ci(m.group(3)), int(m.group(4))


def cell_values(sheet_part):
    root = etree.fromstring(odata[sheet_part])
    vals = {}
    for c in root.iter("{%s}c" % NS["m"]):
        v = c.find("m:v", NS)
        if c.get("t") == "s" and v is not None:
            vals[c.get("r")] = sst[int(v.text)]
        elif c.get("t") == "inlineStr":
            vals[c.get("r")] = "".join(c.itertext())
        elif v is not None:
            vals[c.get("r")] = v.text
        elif c.find("m:f", NS) is not None:
            vals[c.get("r")] = "=" + c.find("m:f", NS).text
    return vals


tables = {}
ids, tnames = [], []
for sname, spart in sheets:
    relp = posixpath.join(posixpath.dirname(spart), "_rels", posixpath.basename(spart) + ".rels")
    if relp not in odata:
        continue
    vals = cell_values(spart)
    boxes = []
    for rel in etree.fromstring(odata[relp]).findall("pr:Relationship", NS):
        if not rel.get("Type").endswith("/table"):
            continue
        tpart = posixpath.normpath(posixpath.join(posixpath.dirname(spart), rel.get("Target")))
        t = etree.fromstring(odata[tpart])
        name, ref = t.get("name"), t.get("ref")
        ids.append(t.get("id"))
        tnames.append(name.lower())
        cols = [c.get("name") for c in t.find("m:tableColumns", NS)]
        c0, r0, c1, r1 = ref_box(ref)
        hdr_ok = all(vals.get("%s%d" % (openpyxl.utils.get_column_letter(c0 + k), r0)) == h for k, h in enumerate(cols))
        probs = []
        if t.find("m:autoFilter", NS) is not None and t.find("m:autoFilter", NS).get("ref") != ref:
            probs.append("autoFilter ref")
        if c1 - c0 + 1 != len(cols) or int(t.find("m:tableColumns", NS).get("count")) != len(cols):
            probs.append("column count")
        if not hdr_ok:
            probs.append("header cells differ from column names")
        if r1 <= r0:
            probs.append("no data row")
        if len({c.get("id") for c in t.find("m:tableColumns", NS)}) != len(cols):
            probs.append("duplicate column ids")
        for (bn, bx) in boxes:
            if not (c1 < bx[0] or c0 > bx[2] or r1 < bx[1] or r0 > bx[3]):
                probs.append("overlaps " + bn)
        boxes.append((name, (c0, r0, c1, r1)))
        tables[name] = {"sheet": sname, "part": tpart, "ref": ref, "cols": cols, "xml": t, "type": t.get("tableType")}
        ok(not probs, "%-22s %-12s %-10s %2d cols %s" % (name, sname, ref, len(cols), probs or ""))
ok(len(set(ids)) == len(ids), "table ids unique (%d tables)" % len(ids))
ok(len(set(tnames)) == len(tnames), "table names unique (case-insensitive)")

conns = {c.get("id"): c for c in etree.fromstring(odata["xl/connections.xml"]).findall("m:connection", NS)}
cnames = {c.get("name"): c for c in conns.values()}
ok(len(cnames) == len(conns) and sorted(int(i) for i in conns) == list(range(1, len(conns) + 1)),
   "connection ids 1..%d and names unique" % len(conns))
dn = {(d.get("name"), d.get("localSheetId")): d.text for d in wbx.find("m:definedNames", NS)}
for name, t in tables.items():
    if t["type"] != "queryTable":
        continue
    tp = t["part"]
    rp = posixpath.join(posixpath.dirname(tp), "_rels", posixpath.basename(tp) + ".rels")
    qtp = posixpath.normpath(posixpath.join(posixpath.dirname(tp), etree.fromstring(odata[rp]).find("pr:Relationship", NS).get("Target")))
    qt = etree.fromstring(odata[qtp])
    fields = qt.find("m:queryTableRefresh/m:queryTableFields", NS)
    fl = [(f.get("id"), f.get("name"), f.get("tableColumnId")) for f in fields]
    tc = {c.get("id"): (c.get("name"), c.get("queryTableFieldId")) for c in t["xml"].find("m:tableColumns", NS)}
    probs = []
    if int(fields.get("count")) != len(fl):
        probs.append("field count")
    for fid, fname, tcid in fl:
        if tcid not in tc or tc[tcid][0] != fname or tc[tcid][1] != fid:
            probs.append("field %s/%s not matched by its table column" % (fid, fname))
    if [f[1] for f in fl] != t["cols"]:
        probs.append("field order")
    nxt = int(qt.find("m:queryTableRefresh", NS).get("nextId"))
    if nxt <= max(int(f[0]) for f in fl):
        probs.append("nextId")
    c = conns.get(qt.get("connectionId"))
    if c is None or c.get("name") != "Query - " + name or "Location=%s;" % name not in c.find("m:dbPr", NS).get("connection"):
        probs.append("connection")
    sheet_index = [s[0] for s in sheets].index(t["sheet"])
    c0, r0, c1, r1 = ref_box(t["ref"])
    want = "%s!$%s$%d:$%s$%d" % (t["sheet"], openpyxl.utils.get_column_letter(c0), r0, openpyxl.utils.get_column_letter(c1), r1)
    if dn.get((qt.get("name"), str(sheet_index))) != want:
        probs.append("defined name %s = %s, want %s" % (qt.get("name"), dn.get((qt.get("name"), str(sheet_index))), want))
    ok(not probs, "query table %-22s <- %s, connection %s '%s', %s %s" % (name, qtp.split("/")[-1], qt.get("connectionId"),
                                                                       c.get("name") if c is not None else None, qt.get("name"), probs or ""))
extern = [k for k in dn if k[0].startswith("ExternalData_")]
ok(len(extern) == 4, "4 ExternalData names, one per query table")
ok("tblGoldenRules" in tables and tables["tblGoldenRules"]["sheet"] == "Validation", "tblGoldenRules on Validation")
manifest_names = re.findall(r'"name": "([^"]+)"', (P / "05-excel/powerquery/manifest.json").read_text())
missing = [n for n in manifest_names if "Query - " + n not in cnames]
ok(not missing, "a 'Query - <name>' connection for each of the 15 queries%s" % (missing or ""))
ok(cnames["Query - Stats_Scored"].get("type") == "100" and b'connection="Query - Stats_Scored"' in odata["xl/workbook.xml"],
   "Stats_Scored model connection (type 100) and x15:modelTable unchanged")
for n in manifest_names:
    c = cnames.get("Query - " + n)
    if c is not None and c.get("type") == "5":
        dbpr = c.find("m:dbPr", NS)
        if dbpr.get("command") != "SELECT * FROM [%s]" % n:
            ok(False, "command of connection " + n)
ok(dn.get(("WorkbookFolder", None)) == "Config!$B$2", "defined name WorkbookFolder = Config!$B$2 (workbook scope)")
# Checks sheet: anchors of the four connection-only checks are empty from row 5 down
checks_vals = cell_values(dict(sheets)["Checks"])
for name, a, ncols in [("Pipeline_Status", "AI", 5), ("Check_Parity", "AO", 9), ("Check_Rules_Drift", "AY", 6), ("Check_Integrity", "BF", 4)]:
    c0 = openpyxl.utils.column_index_from_string(a)
    used = [k for k in checks_vals if openpyxl.utils.column_index_from_string(re.match(r"[A-Z]+", k).group(0)) in
            range(c0, c0 + ncols + 1) and int(re.search(r"\d+", k).group(0)) >= 5]
    ok(not used and checks_vals.get("%s4" % a, "").startswith(name),
       "Checks!%s5 free for %s (%d cols + gap), label in %s4" % (a, name, ncols, a))

# ------------------------------------------------------------------ 4. data (openpyxl, read only)
print("\n== 4. Data tables against 02-config and the golden fixture (openpyxl)")
wb = openpyxl.load_workbook(OUT)


def table_rows(name):
    for ws in wb:
        if name in ws.tables:
            rows = [[c.value for c in r] for r in ws[ws.tables[name].ref]]
            return ws, rows[0], rows[1:]
    raise KeyError(name)


def read_csv(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def same(cell, text):
    if text == "":
        return cell is None or cell == ""
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        try:
            return abs(float(text) - float(cell)) < 1e-12
        except ValueError:
            return False
    return str(cell) == text


def compare(name, csv_rows, keycols=None):
    ws, hdr, body = table_rows(name)
    keycols = keycols or list(csv_rows[0].keys())
    bad = []
    if len(body) != len(csv_rows):
        bad.append("rows %d vs %d" % (len(body), len(csv_rows)))
    for i, (r, c) in enumerate(zip(body, csv_rows)):
        d = dict(zip(hdr, r))
        for k in keycols:
            if k not in d:
                bad.append("no column " + k)
                break
            if not same(d[k], c[k]):
                bad.append("row %d %s: %r vs %r" % (i + 1, k, d[k], c[k]))
    ok(not bad, "%-11s %s!%s: %d rows x %d CSV columns equal the source%s" % (
        name, ws.title, ws.tables[name].ref, len(body), len(keycols), (" " + str(bad[:5])) if bad else ""))
    return hdr, body


compare("tblLeagues", read_csv(P / "02-config/leagues.csv"))
compare("tblScoring", read_csv(P / "02-config/scoring_weights.csv"))
compare("tblBonus", read_csv(P / "02-config/bonus_rules.csv"))
with open(P / "06-qa/fixtures/golden_sample.csv", encoding="utf-8-sig", newline="") as f:
    g = list(csv.reader(f))
ghdr, gbody = compare("tblGolden", [dict(zip(g[0], r)) for r in g[1:]])
ok(ghdr == g[0], "tblGolden header = golden_sample.csv header exactly (%d columns)" % len(g[0]))
ok(all(isinstance(r[ghdr.index(k)], (int, float)) for r in gbody for k in ghdr if k in ("season", "week") or k.startswith("FF_")),
   "tblGolden season, week and FF_ values stored as numbers")
_, chdr, cbody = table_rows("tblConfig")
cfg = {r[0]: r for r in cbody}
pc = {r["Setting"]: r for r in read_csv(P / "02-config/pipeline_config.csv")}
ok(chdr == ["Setting", "Value", "Allowed_Values", "Description"], "tblConfig columns")
ok(list(cfg) == ["StartSeason", "EndSeason", "SeasonTypes", "RoundDecimals", "ReconcileTolerance", "DataLocation"],
   "tblConfig settings: %s (PublishExtraColumns left out: pipeline-only)" % list(cfg))
ok(all(cfg[k][1] == pc[k]["Value"] and isinstance(cfg[k][1], str) for k in cfg if k in pc),
   "tblConfig values = pipeline_config.csv, stored as text: %s" % {k: cfg[k][1] for k in cfg})
ok(cfg["DataLocation"][1] == URL, "DataLocation = the published data's web address (D-037)")
_, rhdr, rbody = table_rows("tblGoldenRules")
fx = read_csv(P / "06-qa/fixtures/fixture_contracts.csv")
ok(rhdr == ["League", "Rules_SHA256", "RoundDecimals"] and len(rbody) == len(fx)
   and all(r[0] == f["league"] and r[1] == f["rules_sha256"] and r[2] == int(f["round_decimals"]) for r, f in zip(rbody, fx)),
   "tblGoldenRules = fixture_contracts.csv (%d rows), %s" % (len(fx), tables.get("tblGoldenRules", {}).get("ref")))
cws = wb["Config"]
ok(cws["A2"].value == "Workbook folder" and cws["B2"].value == '=LEFT(CELL("filename",$A$1),FIND("[",CELL("filename",$A$1))-1)',
   "Config!A2 label and B2 formula as WORKBOOK-REQUIREMENTS.md")
ver = {"Cover!B4 (WorkbookVersion)": wb["Cover"]["B4"].value,
       "Version_Log last row": wb["Version_Log"]["A11"].value,
       "core title": wb.properties.title, "core version": wb.properties.version}
EXP = "2.001-experimental"   # the experimental file never claims the release number 2.001
ok(ver["Cover!B4 (WorkbookVersion)"] == EXP and ver["Version_Log last row"] == EXP
   and ver["core title"] == "NFL-Analysis-" + EXP and ver["core version"] == EXP, "version strings %s: %s" % (EXP, ver))
ok(str(wb["Cover"]["B6"].value).startswith("Experimental (not a release)")
   and wb["Version_Log"]["C11"].value.startswith("Experimental (not a release")
   and str(wb["Cover"]["B3"].value).startswith("Experimental, not a release."),
   "Cover status, Version_Log status and Known differences box say experimental, not a release")
ok("nflverse" in str(wb["Cover"]["B36"].value) and "CC BY 4.0" in str(wb["Cover"]["B36"].value)
   and "https://creativecommons.org/licenses/by/4.0/" in str(wb["Cover"]["B36"].value)
   and "https://github.com/wes-blue/sports-analysis" in str(wb["Cover"]["B36"].value),
   "Cover!B36 nflverse attribution (CC BY 4.0, licence address and repository address)")
vl = [[c.value for c in r] for r in wb["Version_Log"]["A5:C11"]]
ok([r[0] for r in vl] == ["1.001", "1.002", "1.003", "1.004", "1.005", "1.006", EXP] and vl[3][2] == "Superseded by 1.006",
   "Version_Log lists 1.001 to 1.006, then %s; 1.004 superseded by 1.006 (QA-m8)" % EXP)
ok("Metric_Check" in str(wb["Cover"]["B3"].value) and "dst_points_allowed_excl_def" in str(wb["Cover"]["B3"].value),
   "Known differences box names the 1.x Metric_Check leftover (QA-m8)")
anchors = {"tblConfig": "Config!A4", "tblLeagues": "Scoring!A10", "tblScoring": "Scoring!A18", "tblBonus": "Bonus!A4", "tblGolden": "Validation!A48"}
print("      table anchors:", ", ".join("%s %s" % kv for kv in anchors.items()))

# ------------------------------------------------------------------ 6 (run before 5). personal data
print("\n== 6. Personal data (every part, inside the Power Query package and the Data Model's readable strings)")
words = pii_scan.load_forbidden(None, arg("--forbid-file"))
findings, pinv = pii_scan.scan(str(OUT), words, candid=True)
for f in findings:
    print("      FOUND %(part)s | %(rule)s | %(detail)s" % f)
ok(not findings, "no personal data and no private-source or candid text found (%d parts and %d Data Model inner "
   "files read, %d non-empty texts scanned, %d extra forbidden words): core.xml %s" % (pinv["parts"], pinv["model_inner_files"], pinv["texts_scanned"],
   len(words), {k: pinv["core"].get(k) for k in ("dc:creator", "cp:lastModifiedBy")}))
ok("absPath" not in odata["xl/workbook.xml"].decode("utf-8"), "workbook.xml has no x15ac:absPath (last-saved folder)")

# ------------------------------------------------------------------ 5. LibreOffice recalculation
print("\n== 5. LibreOffice headless recalculation (ignores Power Query)")
if WORK.exists():
    shutil.rmtree(WORK)
(WORK / "in").mkdir(parents=True)
shutil.copy(OUT, WORK / "in" / "wb.xlsx")
res = subprocess.run(["soffice", "--headless", "--norestore", "-env:UserInstallation=file://%s" % (WORK / "profile"),
                      "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(WORK / "out"), str(WORK / "in" / "wb.xlsx")],
                     capture_output=True, text=True, timeout=600)
recalc = WORK / "out" / "wb.xlsx"
ok(recalc.exists(), "LibreOffice opened and recalculated the workbook")
if recalc.exists():
    rv = openpyxl.load_workbook(recalc, data_only=True)
    rf = openpyxl.load_workbook(OUT)
    errs, nform = [], 0
    for ws in rf:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    nform += 1
                    v = rv[ws.title][c.coordinate].value
                    if isinstance(v, str) and v.startswith("#"):
                        errs.append("%s!%s=%s" % (ws.title, c.coordinate, v))
    other = errs
    ok(not other, "%d formulas recalculated; formula errors: %s" % (nform, other or "none"))
    print("      Config!B2 (WorkbookFolder) =", rv["Config"]["B2"].value)
    print("      Cover!B32 active leagues =", rv["Cover"]["B32"].value, "; Scoring!F15 =", rv["Scoring"]["F15"].value,
          "; last Metric_Check =", rv["Scoring"]["K%d" % rv["Scoring"].max_row].value)

print("\n%s" % ("ALL PASS" if not fails else "%d FAILED" % len(fails)))
sys.exit(1 if fails else 0)
