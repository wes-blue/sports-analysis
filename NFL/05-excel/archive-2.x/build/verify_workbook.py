#!/usr/bin/env python3
"""Independent structural checks of a built NFL-Analysis workbook (quality gate G3).

Usage: python3 NFL/05-excel/archive-2.x/build/verify_workbook.py <workbook.xlsx> --version 2.001 --date 2026-11-20
Reads expectations from WORKBOOK-REQUIREMENTS.md, the seed CSVs, manifest.json and the .pq files,
NOT from build_workbook.py, so it checks the generator instead of repeating it. Writes the M text it
extracts from the workbook to NFL/.work/verify/mx/ (LF, as stored) and NFL/.work/verify/mx_clip/
(CRLF, as Excel's clipboard would deliver a copied range), for parsing with Microsoft's M parser.
Exit code 0 when every check passes.
"""
import csv
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string as cidx, get_column_letter, range_boundaries

HERE = Path(__file__).resolve().parent      # NFL/05-excel/archive-2.x/build
P = HERE.parents[2]                          # NFL
E1 = P / ".work" / "verify"                  # scratch output (git-ignored)
E1.mkdir(parents=True, exist_ok=True)
ROOT = P.parent
PQ = P / "05-excel" / "archive-2.x" / "powerquery"
REQ = (PQ / "WORKBOOK-REQUIREMENTS.md").read_text(encoding="utf-8")

args = sys.argv[1:]
path = Path(args[0]).resolve()
if "--version" not in args or "--date" not in args:
    sys.exit("usage: verify_workbook.py <workbook.xlsx> --version <v> --date <yyyy-mm-dd>")
version = args[args.index("--version") + 1]
rdate = args[args.index("--date") + 1]

fails, passes = [], []


def check(cond, what):
    (passes if cond else fails).append(what)
    return cond


def read_csv(p):
    with open(p, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.reader(f) if any(c.strip() for c in r)]
    return rows[0], rows[1:]


NUM = re.compile(r"^-?(\d+)(\.\d+)?$")


def expect(text, numeric):
    """Expected cell value for CSV text: None for blank; int/float if numeric column; else the text."""
    if text == "":
        return None
    if numeric:
        m = NUM.match(text.strip())
        assert m, "non-numeric seed %r" % text
        return float(text) if m.group(2) else int(text)
    return text


def same(a, b):
    if a is None or b is None:
        return a is b
    if isinstance(b, str):
        return isinstance(a, str) and a == b
    if isinstance(b, bool) or isinstance(a, bool):
        return False
    # Excel stores every number as a double (15.0 and 15 are the same cell), so int/float are one type here
    return isinstance(a, (int, float)) and a == b


wb = load_workbook(path)
tables = {}
for ws in wb.worksheets:
    for t in ws.tables.values():
        tables[t.displayName] = (ws, t)


def tvals(name):
    ws, t = tables[name]
    c1, r1, c2, r2 = range_boundaries(t.ref)
    hdr = [ws.cell(r1, c).value for c in range(c1, c2 + 1)]
    rows = [[ws.cell(r, c).value for c in range(c1, c2 + 1)] for r in range(r1 + 1, r2 + 1)]
    return hdr, rows


# ---------------------------------------------------------------- 1. requirements: input tables
sec3 = re.findall(r"### `(tbl\w+)`: sheet `(\w+)`, anchor `([A-Z]+\d+)`", REQ)
check(len(sec3) == 5, "requirements list 5 input tables (found %d)" % len(sec3))
for tname, sheet, anchor in sec3:
    ok = check(tname in tables, "%s exists" % tname)
    if not ok:
        continue
    ws, t = tables[tname]
    check(ws.title == sheet, "%s on sheet %s (is %s)" % (tname, sheet, ws.title))
    check(t.ref.split(":")[0] == anchor, "%s anchored at %s (ref %s)" % (tname, anchor, t.ref))
    hdr, _ = tvals(tname)
    names = [c.name for c in t.tableColumns]
    check(hdr == names, "%s header cells equal table column names" % tname)

# exact column lists
lg_h, lg_rows = read_csv(P / "02-config/leagues.csv")
sc_h, sc_rows = read_csv(P / "02-config/scoring_weights.csv")
bo_h, bo_rows = read_csv(P / "02-config/bonus_rules.csv")
cf_h, cf_rows = read_csv(P / "02-config/pipeline_config.csv")
go_h, go_rows = read_csv(P / "06-qa/fixtures/golden_sample.csv")
leagues = [r[0] for r in lg_rows]
h, _ = tvals("tblConfig"); check(h == ["Setting", "Value", "Allowed_Values", "Description"], "tblConfig columns")
h, _ = tvals("tblLeagues"); check(h[:5] == lg_h and h[5:] in ([], ["Column_Check"]), "tblLeagues columns %s" % h)
h, _ = tvals("tblScoring")
check(h[:len(sc_h)] == sc_h and h[len(sc_h):] in ([], ["Metric_Check"]), "tblScoring columns = file order (+Metric_Check)")
check(sc_h == ["Metric", "Category", "Description"] + leagues + ["Notes", "Applies_To"], "scoring league columns follow tblLeagues order")
check(len(sc_rows) == 82, "tblScoring seed has 82 rows (2.001 adds dst_points_allowed_excl_def)")
h, _ = tvals("tblBonus"); check(h == bo_h == ["League", "Metric", "Lower", "Upper", "Points", "Applies_To", "Notes"], "tblBonus columns")
check(len(bo_rows) == 24, "tblBonus seed has 24 rows")
h, _ = tvals("tblGolden"); check(h == go_h, "tblGolden columns exactly the golden_sample.csv header")
check(len(go_rows) == 25, "golden seed has 25 rows")
_, tl = tables["tblLeagues"]; check(get_column_letter(range_boundaries(tl.ref)[2]) in ("E", "F"), "tblLeagues occupies A:E or A:F")

# ---------------------------------------------------------------- 2. seeds cell for cell, with types
_, rows = tvals("tblConfig")
exp = [[expect(c, False) for c in r] for r in cf_rows]
dl_desc = re.search(r'Suggested Description for `DataLocation`: "([^"]+)"', REQ).group(1)
check(len(rows) == len(exp) + 1, "tblConfig = %d seed rows + DataLocation" % len(exp))
for i, (a, b) in enumerate(zip(rows, exp)):
    check(all(same(x, y) for x, y in zip(a, b)), "tblConfig row %d equals seed (types incl.): %s" % (i + 1, a[:2]))
dl = rows[-1]
dl_default = re.search(r"^\| `DataLocation` \| `([^`]+)` \|", REQ, re.M).group(1)
check(dl[0] == "DataLocation" and dl[1] == dl_default and dl[3] == dl_desc, "DataLocation row: %s (D-037), suggested description" % dl_default)
ws, t = tables["tblConfig"]
c1, r1, c2, r2 = range_boundaries(t.ref)
check(all(ws.cell(r, 2).number_format == "@" for r in range(r1 + 1, r2 + 1)), "tblConfig[Value] formatted as Text")
check(all(isinstance(r[1], str) or r[1] is None for r in rows), "tblConfig[Value] cells are text (Latest-9, 2, 0.005 kept as typed)")
settings = [r[0] for r in rows]
check(len(set(settings)) == len(settings), "setting names unique")
cfg_sec = REQ[REQ.index("### `tblConfig`"):REQ.index("### `tblLeagues`")]
defaults = re.findall(r"^\| `(\w+)` \| (`[^`]*`|\*\(blank\)\*) \|", cfg_sec, re.M)
check(len(defaults) == 7, "7 tblConfig settings in requirements")
for k, d in defaults:
    d = None if d.startswith("*") else d.strip("`")
    row = next((r for r in rows if r[0] == k), None)
    check(row is not None and row[1] == d, "tblConfig %s default %r (is %r)" % (k, d, row and row[1]))

_, rows = tvals("tblLeagues")
for i, (a, b) in enumerate(zip(rows, lg_rows)):
    check(all(same(x, expect(y, False)) for x, y in zip(a[:5], b)), "tblLeagues row %d equals seed" % (i + 1))
check(len(rows) == len(lg_rows), "tblLeagues row count")

_, rows = tvals("tblScoring")
nl = len(leagues)
bad = 0
for a, b in zip(rows, sc_rows):
    b = b + [""] * (len(sc_h) - len(b))
    for j, y in enumerate(b):
        if not same(a[j], expect(y, 3 <= j < 3 + nl)):
            bad += 1
check(bad == 0 and len(rows) == len(sc_rows), "tblScoring 81 rows equal seed cell for cell (%d mismatches)" % bad)

_, rows = tvals("tblBonus")
bad = sum(1 for a, b in zip(rows, bo_rows) for j, y in enumerate(b) if not same(a[j], expect(y, j in (2, 3, 4))))
check(bad == 0 and len(rows) == len(bo_rows), "tblBonus 24 rows equal seed cell for cell (%d mismatches)" % bad)

_, rows = tvals("tblGolden")
textcols = {"season_type", "player_id", "player_display_name", "position", "team"}
bad = sum(1 for a, b in zip(rows, go_rows) for j, y in enumerate(b) if not same(a[j], expect(y, go_h[j] not in textcols)))
check(bad == 0 and len(rows) == len(go_rows), "tblGolden 25 rows equal seed cell for cell (%d mismatches)" % bad)
check(all(isinstance(r[0], int) and isinstance(r[1], int) for r in rows), "tblGolden season/week stored as numbers")
check(all(isinstance(v, (int, float)) for r in rows for j, v in enumerate(r) if go_h[j].startswith("FF_")),
      "tblGolden FF_ values stored as numbers")

dd_h, dd_rows = read_csv(P / "04-data/dictionary.csv")
h, rows = tvals("tblDictionary")
check(h[:5] == dd_h and len(rows) == len(dd_rows) and
      all(same(a[j], expect(y, False)) for a, b in zip(rows, dd_rows) for j, y in enumerate(b)),
      "tblDictionary equals 04-data/dictionary.csv (%d rows)" % len(dd_rows))
bl_h, bl_rows = read_csv(ROOT / "BLOCKERS.csv")
bl_rows = [r for r in bl_rows if r[8].strip() in ("Open", "Still open", "")]   # Open_Questions lists the open ones
h, rows = tvals("tblOpenQuestions")
check(h == bl_h and len(rows) == len(bl_rows) and
      all(same(a[j], expect(y, False)) for a, b in zip(rows, bl_rows) for j, y in enumerate(b[:7])) and
      all(a[7].date().isoformat() == b[7] for a, b in zip(rows, bl_rows)),
      "tblOpenQuestions equals the open rows of BLOCKERS.csv (%d rows; Raised as dates)" % len(bl_rows))
plan = json.loads((P / "01-plan/plan.json").read_text(encoding="utf-8"))
for tn, key, n in (("tblRequirements", "requirements", 61), ("tblRAID", "raid", 62), ("tblControls", "controls", 25),
                   ("tblRoadmap", "roadmap", 12), ("tblArchitecture", "architecture", 15),
                   ("tblGlossary", "glossary", 49), ("tblKeyFindings", "key_findings", 28)):
    _, rows = tvals(tn)
    check(len(rows) == len(plan[key]), "%s has %d rows (plan.json %d)" % (tn, len(rows), len(plan[key])))
_, rows = tvals("tblRequirements")
check([r[0] for r in rows] == [x["id"] for x in plan["requirements"]] and
      all(r[1] == x["requirement"] and r[6] == x["acceptance_criteria"] for r, x in zip(rows, plan["requirements"])),
      "tblRequirements text equals plan.json")

# ---------------------------------------------------------------- 3. named cell, version
nm = wb.defined_names.get("WorkbookFolder")
row = re.search(r"\| `WorkbookFolder` \| `([^`]+)` \(label `([^`]+)` in `([^`]+)`\) \| Formula `([^`]+)`", REQ)
dest, label, lab_cell, formula = row.groups()
check(nm is not None and nm.attr_text == dest.replace("$", "$"), "WorkbookFolder -> %s (is %s)" % (dest, nm and nm.attr_text))
check(nm is not None and nm.localSheetId is None, "WorkbookFolder has workbook scope")
cfg = wb["Config"]
check(cfg[lab_cell.split("!")[1].replace("$", "")].value == label, "label %r in %s" % (label, lab_cell))
check(cfg["B2"].value == formula, "WorkbookFolder formula exactly as required")
check(cfg["B2"].data_type == "f", "WorkbookFolder cell is a formula")
check(not any(t for n, (ws_, t) in tables.items() if ws_.title == "Config" and range_boundaries(t.ref)[1] <= 2
              and range_boundaries(t.ref)[3] >= 2), "WorkbookFolder is not inside a table")
wv = wb.defined_names.get("WorkbookVersion")
check(wv is not None and wv.attr_text == "Cover!$B$4" and wb["Cover"]["B4"].value == version
      and isinstance(wb["Cover"]["B4"].value, str), "WorkbookVersion = Cover!$B$4 = '%s' (text)" % version)
check(path.name == "NFL-Analysis-%s.xlsx" % version, "file name carries %s" % version)
check(wb.properties.title == "NFL-Analysis-%s" % version and wb.properties.version == version, "properties Title/Version")
_, vl = tvals("tblVersionLog")
check(vl[-1][0] == version and vl[-1][1].date().isoformat() == rdate and vl[-1][2] == "Released",
      "Version_Log last row %s %s Released" % (version, rdate))
check([r[0] for r in vl] == ["1.001", "1.002", "1.003", "1.004", "1.005", "1.006", version], "Version_Log versions 1.001-1.006 + new")
check(vl[4][2].startswith("Withdrawn"), "1.005 shown as withdrawn")
check(wb["Cover"]["B5"].value.date().isoformat() == rdate and wb["Cover"]["B6"].value == "Released", "Cover date/status")
check(wb.properties.created.date().isoformat() == rdate and wb.properties.modified.date().isoformat() == rdate,
      "core created/modified = %s" % rdate)

# ---------------------------------------------------------------- 4. Checks sheet anchors
ck = wb["Checks"]
sec4 = re.findall(r"^\| `(\w+)` \| `Checks!([A-Z]+)5` \| `([^`]+)` \| ([A-Z]+)–([A-Z]+) \|", REQ, re.M)
check(len(sec4) == 8, "requirements list 8 loaded queries (found %d)" % len(sec4))
spans = []
for q, col, cols, a, b in sec4:
    ncol = len([c.strip() for c in cols.split(",")])
    check(cidx(b) - cidx(a) + 1 == ncol and a == col, "%s span %s-%s fits %d columns" % (q, a, b, ncol))
    check(ck["%s4" % col].value == q, "Checks!%s4 label = %s" % (col, q))
    spans.append((cidx(a), cidx(b), q))
spans.sort()
for (a1, b1, q1), (a2, b2, q2) in zip(spans, spans[1:]):
    check(a2 - b1 >= 2, "gap column between %s and %s" % (q1, q2))
gaps = re.search(r"Gap columns: ([A-Z, ]+)\.", REQ).group(1).replace(" ", "").split(",")
check(sorted(cidx(g) for g in gaps) == sorted(b + 1 for _, b, _ in spans[:-1]), "gap columns %s" % gaps)
nonempty = [(c.coordinate) for rw in ck.iter_rows(min_row=5) for c in rw if c.value is not None]
check(not nonempty, "Checks rows 5+ empty for the query tables (%d stray cells)" % len(nonempty))
check(not ck.tables, "no tables yet on Checks")
mf = json.loads((PQ / "manifest.json").read_text(encoding="utf-8"))["queries"]
for q, col, *_ in sec4:
    m = next(x for x in mf if x["name"] == q)
    check("=Checks!$%s$5" % col in m["load_as"], "manifest load_as for %s matches requirements" % q)

# ---------------------------------------------------------------- 5. collisions on every sheet
for ws in wb.worksheets:
    ts = [(t.displayName, range_boundaries(t.ref)) for t in ws.tables.values()]
    for i, (n1, (c1, r1, c2, r2)) in enumerate(ts):
        # nothing below the table in its columns (it grows downward), nothing in the gap column at its right
        stray = [c.coordinate for rw in ws.iter_rows(min_row=r2 + 1, min_col=c1, max_col=c2 + 1) for c in rw
                 if c.value is not None]
        check(not stray, "%s!%s: nothing below it or in the column to its right (%s)" % (ws.title, n1, stray[:3]))
        for n2, (d1, s1, d2, s2) in ts[i + 1:]:
            check(c2 < d1 - 1 or d2 < c1 - 1, "%s: %s and %s share no column and have a gap" % (ws.title, n1, n2))
    grow = [n for n, _ in ts if n == "tblScoring"]
    if grow:
        gc = dict(ts)["tblScoring"]
        check(all(b[2] < gc[0] for n, b in ts if n != "tblScoring"), "tblScoring is the rightmost table")
        right = [c.coordinate for rw in ws.iter_rows(min_col=gc[2] + 1) for c in rw if c.value is not None]
        check(not right, "nothing right of tblScoring (%s)" % right[:3])
    for n, (c1, r1, c2, r2) in ts:
        check(r1 >= 4, "%s!%s starts at row 4 or below" % (ws.title, n))
check(range_boundaries(tables["tblScoring"][1].ref)[0] == cidx("H"), "tblScoring at H")

# ---------------------------------------------------------------- 6. M text byte for byte
mf_names = [q["name"] for q in mf]
h, mrows = tvals("tblMCode")
check(h == ["Query", "Line", "Code"], "tblMCode columns")
ws_m, _ = tables["tblMCode"]
check(all(ws_m.cell(r, 3).data_type in ("s", "n") for r in range(5, 5 + len(mrows))), "Code cells stored as text, never formulas")
order = []
for r in mrows:
    if not order or order[-1] != r[0]:
        order.append(r[0])
check(order == mf_names, "tblMCode queries in manifest order, each contiguous")
(E1 / "mx").mkdir(exist_ok=True); (E1 / "mx_clip").mkdir(exist_ok=True)
for f in list((E1 / "mx").glob("*.pq")) + list((E1 / "mx_clip").glob("*.pq")):
    f.unlink()
qh, qrows = tvals("tblQueries")
for i, q in enumerate(mf):
    lines = [r for r in mrows if r[0] == q["name"]]
    check([r[1] for r in lines] == list(range(1, len(lines) + 1)), "%s line numbers 1..%d" % (q["name"], len(lines)))
    text = "\n".join(r[2] if r[2] is not None else "" for r in lines) + "\n"
    src = (PQ / q["file"]).read_bytes()
    check(text.encode("utf-8") == src, "%s: reassembled tblMCode text == %s byte for byte (%d bytes)" % (q["name"], q["file"], len(src)))
    # via the Name Box range
    dn = wb.defined_names.get("PQ_%02d_%s" % (i + 1, q["name"]))
    ok = check(dn is not None, "defined name PQ_%02d_%s" % (i + 1, q["name"]))
    if ok:
        sh, rng = dn.attr_text.split("!")
        c1, r1, c2, r2 = range_boundaries(rng.replace("$", ""))
        cells = [wb[sh].cell(r, c1).value for r in range(r1, r2 + 1)]
        t2 = "\n".join(v if v is not None else "" for v in cells) + "\n"
        check(c1 == c2 == 3 and t2.encode() == src, "%s: Name Box range %s == file byte for byte" % (q["name"], dn.attr_text))
        (E1 / "mx" / q["file"]).write_bytes(t2.encode("utf-8"))
        # what Excel's clipboard delivers for a copied range: each cell + CRLF
        (E1 / "mx_clip" / q["file"]).write_bytes("".join((v or "") + "\r\n" for v in cells).encode("utf-8"))
    qr = qrows[i]
    check(qr[1] == q["name"] and qr[0] == i + 1 and qr[3] == (", ".join(q["depends_on"]) or None) and qr[4] == len(lines),
          "tblQueries row %d = %s (deps, lines)" % (i + 1, q["name"]))
    lt = qr[2]
    if q["load_as"] == "Connection only":
        check(lt == "Only Create Connection", "%s load setting" % q["name"])
    elif q["load_as"].startswith("Connection only + Data Model"):
        check("Data Model" in lt and lt.startswith("Only Create Connection"), "%s load setting" % q["name"])
    else:
        check(re.search(r"=Checks!\$[A-Z]+\$5", lt).group(0) in q["load_as"], "%s load setting" % q["name"])
check(len(mrows) == sum(len((PQ / q["file"]).read_text().splitlines()) for q in mf), "tblMCode line total %d" % len(mrows))

# ---------------------------------------------------------------- 7. formulas, freeze, print, validation
formulas = [(ws.title, c.coordinate, c.value) for ws in wb.worksheets for rw in ws.iter_rows() for c in rw
            if c.data_type == "f"]
check(all("[@" not in f[2] for f in formulas), "no [@...] shorthand in formulas (%d formulas)" % len(formulas))
check(not any(re.search(r"\b(XLOOKUP|FILTER|LET|UNIQUE|TEXTJOIN|IFS)\(", f[2]) for f in formulas), "Excel-2010-safe functions only")
for ws in wb.worksheets:
    if ws.tables and ws.title != "Plan":
        check(ws.freeze_panes is not None, "%s has frozen panes" % ws.title)
    if ws.max_row > 40 and ws.title not in ("Plan", "Start_Here", "Cover", "Checks"):
        check(bool(ws.print_title_rows), "%s has print titles" % ws.title)
dvs = {ws.title: [(d.type, str(d.sqref)) for d in ws.data_validations.dataValidation] for ws in wb.worksheets}
srow = {cfg.cell(r, 1).value: r for r in range(5, cfg.max_row + 1)}
for k in ("StartSeason", "EndSeason", "SeasonTypes", "RoundDecimals", "ReconcileTolerance"):
    check(any(("B%d" % srow[k]) == s for _, s in dvs["Config"]), "validation on %s (Config!B%d)" % (k, srow[k]))
check(len(dvs["Scoring"]) >= 3 and len(dvs["Bonus"]) >= 5, "validation on Scoring and Bonus")
for ws in wb.worksheets:
    for rw in ws.iter_rows():
        for c in rw:
            if isinstance(c.value, str) and c.data_type == "s" and c.value.startswith("#"):
                fails.append("text cell looks like an error: %s!%s" % (ws.title, c.coordinate))

print(json.dumps({"file": str(path), "bytes": path.stat().st_size,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "sheets": wb.sheetnames,
                  "tables": {n: "%s!%s" % (ws.title, t.ref) for n, (ws, t) in tables.items()},
                  "defined_names": {k: v.attr_text for k, v in wb.defined_names.items()},
                  "formulas": len(formulas), "passed": len(passes), "failed": fails}, indent=1))
sys.exit(1 if fails else 0)
