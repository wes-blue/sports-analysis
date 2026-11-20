#!/usr/bin/env python3
"""Build NFL-Analysis-<version>.xlsx (paste-ready, pipeline-fed) from source files.

Source files are the single source of truth; the workbook is a build output.
Adapted from the 1.x generator (archived in the owner's private repository).
See README.md beside this file for usage. One command for the 2.001 candidate (from the repository root):
    python3 NFL/05-excel/build/build_workbook.py --version 2.001 --release-date 2026-11-20 --force
"""
import argparse
import csv
import datetime as dt
import glob
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.worksheet.table import Table, TableFormula, TableStyleInfo

HERE = Path(__file__).resolve().parent            # <repo>/NFL/05-excel/build
DEFAULT_ROOT = HERE.parents[2]                    # <repo> (holds BLOCKERS.csv and NFL/)
PROJ = "NFL"
sys.path.insert(0, str(HERE))
import pii_scan  # noqa: E402  (personal-data scan of the output; this repository is public)

DATA_URL = "https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/"
REPO_URL = "https://github.com/wes-blue/sports-analysis"
# Instructions the owner must never be given (D-037: no clone, pull, sync, branch switch or Python on the PC).
# Broad pattern for the sheets this script writes; narrower (instruction-like) pattern for text copied from plan.json
# and BLOCKERS.csv, which may describe the pipeline (written in Python) without telling the owner to run anything.
INSTRUCTION_LIKE = re.compile(r"(?i)\bgit pull\b|pull origin|fetch origin|github desktop|switch(?:ing)? (?:to )?(?:the )?branch|"
                              r"current branch|python -m|\bpy -m\b|\bclone (?:the|this|a|it)\b|install python|run python")
FORBIDDEN_INSTRUCTIONS = re.compile(r"(?i)\bclone\b|\bgit pull\b|pull origin|fetch origin|\bsync(?:ed|ing)?\b|"
                                    r"switch(?:ing)? (?:to )?(?:the )?branch|current branch|\bpython\b|github desktop|\bpy -m\b")
LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"
ATTRIBUTION = ("The data is derived from nflverse (github.com/nflverse/nflverse-data), licensed CC BY 4.0 (%s). "
               "Details, and what this project changes, in DATA-LICENSE.md at the root of the repository %s."
               % (LICENCE_URL, REPO_URL))
DEFAULT_SUMMARY = {
    "2.001": "First 2.x workbook (D-035): reads the pipeline's published CSV files from the web "
             "(raw.githubusercontent.com, D-037), with a local folder as fallback; Start_Here rewritten for "
             "download, open and refresh; the workbook's golden and reconciliation checks follow the pipeline's "
             "rule for deliberate changes (QA N-1).",
}

# ---------------------------------------------------------------- styles (as 1.x)
NAVY = "013369"
F_BASE = Font(name="Arial", size=10)
F_BOLD = Font(name="Arial", size=10, bold=True)
F_TITLE = Font(name="Arial", size=16, bold=True)
F_SECTION = Font(name="Arial", size=12, bold=True)
F_HDR = Font(name="Arial", size=10, bold=True, color="FFFFFF")
F_INPUT = Font(name="Arial", size=10, color="0000FF")
F_CODE = Font(name="Consolas", size=10)
F_LINK = Font(name="Arial", size=10, color="0563C1", underline="single")
F_NOTE = Font(name="Arial", size=10, italic=True, color="595959")
F_BIGLINK = Font(name="Arial", size=11, bold=True, color="0563C1", underline="single")
FILL_HDR = PatternFill("solid", start_color=NAVY, end_color=NAVY)
FILL_INPUT = PatternFill("solid", start_color="FFF2CC", end_color="FFF2CC")
FILL_RED = PatternFill("solid", start_color="FFC7CE", end_color="FFC7CE")
FILL_GREEN = PatternFill("solid", start_color="C6EFCE", end_color="C6EFCE")
FILL_AMBER = PatternFill("solid", start_color="FFEB9C", end_color="FFEB9C")
FILL_GREY = PatternFill("solid", start_color="EDEDED", end_color="EDEDED")
FILL_STEP = PatternFill("solid", start_color="DDEBF7", end_color="DDEBF7")
WRAP = Alignment(wrap_text=True, vertical="top")
TOP = Alignment(vertical="top")
LEFT = Alignment(horizontal="left", vertical="top")

SHEETS = [
    ("Cover", "Version, release scope, sheet index and live summary counts."),
    ("Start_Here", "Read first: get the workbook, answer Excel's first questions, add the queries, refresh each week, read the checks and change scoring."),
    ("Config", "Settings that Power Query reads by name (tblConfig), including where the data is read from (DataLocation)."),
    ("Scoring", "Leagues (tblLeagues) and points per statistic per league (tblScoring). Edit the yellow cells."),
    ("Bonus", "Band bonuses per league (tblBonus): points when a statistic falls between Lower and Upper."),
    ("M_Code", "The 15 Power Query queries as text, one line per row, with the paste order and load settings (tblQueries)."),
    ("Checks", "Where the eight check queries load their tables (row 5). Leave row 5 and below empty until you load them."),
    ("Validation", "Golden sample: hand-checked player-games with expected points per league (tblGolden), and the rules they were made with (tblGoldenRules)."),
    ("Data_Dictionary", "Every metric column the pipeline publishes in player_week (from 04-data/dictionary.csv)."),
    ("Open_Questions", "Questions and actions still waiting on you (open rows of BLOCKERS.csv at build time)."),
    ("Plan", "Objective, what you are trying to do, scope and key findings."),
    ("Architecture", "How data flows from nflverse through the pipeline to this workbook."),
    ("Roadmap", "One version per increment, with scope, deliverables and acceptance criteria."),
    ("Requirements", "Requirements register with acceptance criteria and status."),
    ("RAID", "Risks, assumptions, issues, decisions and questions."),
    ("Controls", "Controls (checks) with method, expected result and status."),
    ("Glossary", "Terms used in this workbook and the project."),
    ("Version_Log", "History of workbook versions."),
]
DESCR = dict(SHEETS)
RESERVED = ["Metric", "Category", "Description", "Notes", "Metric_Check", "Applies_To"]
RESERVED_OR = ",".join('UPPER(tblLeagues[[#This Row],[League]])="%s"' % x.upper() for x in RESERVED)

# WORKBOOK-REQUIREMENTS.md section 4: query -> (anchor column, columns)
CHECK_LAYOUT = [
    ("Pipeline_Status", "A", ["Section", "Item", "Value", "Result", "Detail"]),
    ("Check_Parity", "G", ["League", "Rows_Compared", "Rows_Equal", "Rows_Different", "Largest_Difference",
                           "Only_In_Workbook", "Only_In_Pipeline", "Status", "Example"]),
    ("Check_Rules_Drift", "Q", ["League", "Kind", "Item", "Workbook", "Pipeline", "Status"]),
    ("Check_Metrics", "X", ["Metric", "In_Stats_Raw", "Is_Numeric", "Used_By_Leagues", "Status"]),
    ("Check_Reconciliation", "AD", ["League", "Reconcile_To", "Rows_Compared", "Rows_Mismatched", "Match_Pct",
                                    "Status", "Worst_Examples"]),
    ("Check_RowCounts", "AL", ["season", "season_type", "Season_Status", "Max_Week", "Published_Player_Rows",
                               "Workbook_Player_Rows", "Published_DST_Rows", "Workbook_DST_Rows", "Status"]),
    ("Check_Golden", "AV", ["League", "Golden_Rows", "Matched", "Mismatched", "Status", "Worst_Examples"]),
    ("Check_Integrity", "BC", ["Check", "Expected", "Actual", "Status"]),
]
CHECK_STATUS_COL = {"Pipeline_Status": "Result"}  # others use "Status"
CONFIG_ORDER = ["StartSeason", "EndSeason", "SeasonTypes", "RoundDecimals", "ReconcileTolerance", "DataLocation"]
DATALOCATION_ROW = ["DataLocation", DATA_URL,
                    "a web address starting with http | a folder path | blank = automatic local search",
                    "Where the pipeline's CSV files are. As shipped: the published data on GitHub (read from the web). "
                    "Or the full path of a folder that contains status.csv. Blank = the 04-data folder next to the "
                    "workbook's folder."]
GOLDEN_RULES_HDR = ["League", "Rules_SHA256", "RoundDecimals"]
FIXED_DT = None  # set in build()
CONFIG_VALUE_RANGE = [None]  # set in build()

INT_RE = re.compile(r"^-?(0|[1-9]\d*)$")
FLT_RE = re.compile(r"^-?(0|[1-9]\d*)?\.\d+$")


def die(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(2)


def conv(s):
    """CSV text -> int/float/str/None (numbers only for plain decimal text)."""
    if s is None or s == "":
        return None
    t = s.strip()
    if INT_RE.match(t):
        return int(t)
    if FLT_RE.match(t):
        return float(t)
    return s


def txt(s):
    return None if s is None or s == "" else s


def read_csv(path):
    if not path.exists():
        die("missing input: %s" % path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        die("empty input: %s" % path)
    rows = [r for r in rows if any(c.strip() for c in r)]
    return rows[0], rows[1:]


def find_recalc(cli):
    """--recalc-script, then $XLSX_RECALC, then known skill paths."""
    for c in (cli, os.environ.get("XLSX_RECALC")):
        if c:
            if Path(c).is_file():
                return str(c)
            die("recalc.py not found: %s" % c)
    hits = sorted(glob.glob("/mnt/skills/public/xlsx/scripts/recalc.py")) + \
        sorted(glob.glob("/root/.claude/skills/**/xlsx/scripts/recalc.py", recursive=True))
    if hits:
        return hits[0]
    die("recalc.py not found. Pass --recalc-script <path>, set XLSX_RECALC, or use --no-recalc.")


# ---------------------------------------------------------------- cell helpers
def put(ws, ref, value, font=F_BASE, fill=None, align=None, fmt=None, text=False):
    c = ws[ref] if isinstance(ref, str) else ws.cell(row=ref[0], column=ref[1])
    c.value = value
    if text and isinstance(value, str):
        c.data_type = "s"  # never let openpyxl turn "=..." text into a formula
    c.font = font
    if fill:
        c.fill = fill
    if align:
        c.alignment = align
    if fmt:
        c.number_format = fmt
    return c


def sheet_head(ws, title, purpose):
    put(ws, "A1", title, F_TITLE)
    put(ws, "A2", purpose, F_NOTE)


def section(ws, row, text, col=1):
    put(ws, (row, col), text, F_SECTION)


def add_table(ws, name, r0, c0, headers, rows, *, wrap=(), inputs=(), fmts=None,
              formulas=(), code=(), calc=(), style="TableStyleMedium2"):
    """Write header + rows and define an Excel table. Column args are indexes into
    headers. Returns (first_data_row, last_row)."""
    fmts = fmts or {}
    assert len(set(headers)) == len(headers), "duplicate headers in %s" % name
    assert all(isinstance(h, str) and h for h in headers), name
    if not rows:
        rows = [[None] * len(headers)]
    for j, h in enumerate(headers):
        put(ws, (r0, c0 + j), h, F_HDR, FILL_HDR, Alignment(wrap_text=True, vertical="center"), text=True)
    for i, row in enumerate(rows):
        assert len(row) == len(headers), (name, i, len(row), len(headers))
        for j, v in enumerate(row):
            r, c = r0 + 1 + i, c0 + j
            if j in code:
                put(ws, (r, c), v, F_CODE, align=TOP, text=True)
                continue
            font = F_INPUT if j in inputs else F_BASE
            fill = FILL_INPUT if j in inputs else None
            al = WRAP if j in wrap else TOP
            put(ws, (r, c), v, font, fill, al, fmts.get(j), text=j not in formulas)
    last = r0 + len(rows)
    ref = "%s%d:%s%d" % (get_column_letter(c0), r0, get_column_letter(c0 + len(headers) - 1), last)
    t = Table(displayName=name, ref=ref)
    t.tableStyleInfo = TableStyleInfo(name=style, showRowStripes=True, showFirstColumn=False,
                                      showLastColumn=False, showColumnStripes=False)
    if calc:  # real calculated columns: Excel fills them when a row is added
        t._initialise_columns()
        for j, col in enumerate(t.tableColumns):
            col.name = headers[j]
        for j in calc:
            f = rows[0][j]
            assert isinstance(f, str) and f.startswith("="), (name, j)
            t.tableColumns[j].calculatedColumnFormula = TableFormula(attr_text=f[1:])
    ws.add_table(t)
    return r0 + 1, last


def widths(ws, ws_widths):
    for k, w in ws_widths.items():
        ws.column_dimensions[k].width = w


def est_height(text, chars_per_line, line_h=13.0):
    lines = 0
    for part in str(text).split("\n"):
        lines += max(1, math.ceil(len(part) / max(chars_per_line, 1)))
    return lines * line_h + 3


def para(ws, row, text, c1, c2, cpl, font=F_BASE, fill=None):
    """Merged, wrapped paragraph row with an estimated height."""
    if c2 > c1:
        ws.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)
    put(ws, (row, c1), text, font, fill, align=WRAP, text=True)
    ws.row_dimensions[row].height = est_height(text, cpl)


def add_dv(ws, kind, formula, rng, allow_blank=True, **kw):
    dv = DataValidation(type=kind, formula1=formula, allow_blank=allow_blank, **kw)
    dv.showErrorMessage = True
    ws.add_data_validation(dv)
    dv.add(rng)
    return dv


def col_rng(col, first, last):
    L = get_column_letter(col)
    return "%s%d:%s%d" % (L, first, L, last)


def list_dv(ws, options, first, last, col, allow_blank=True, **kw):
    f = '"%s"' % ",".join(options)
    assert len(f) <= 255
    return add_dv(ws, "list", f, col_rng(col, first, last), allow_blank=allow_blank, **kw)


def season_dv(c):
    """Custom DV for a text-formatted season cell: a year 1999-2100, Latest, or Latest-N (N 0-30).
    Works whether the cell holds text or a number; no branch can raise an error."""
    m = "MID(%s,8,3)" % c
    f = ('OR(IFERROR(AND(--{c}>=1999,--{c}<=2100,INT(--{c})=--{c}),FALSE),UPPER({c})="LATEST",'
         'IFERROR(AND(UPPER(LEFT({c},7))="LATEST-",--{m}>=0,--{m}<=30,INT(--{m})=--{m}),FALSE))').format(c=c, m=m)
    assert len(f) <= 255, len(f)
    return f


def load_to_text(load_as):
    """manifest load_as -> the exact choice in Excel's Close & Load To dialog."""
    if load_as.startswith("Connection only + Data Model"):
        return "Only Create Connection + tick Add this data to the Data Model"
    if load_as == "Connection only":
        return "Only Create Connection"
    m = re.search(r"=Checks!\$([A-Z]+)\$5", load_as)
    if m:
        return "Table > Existing worksheet > =Checks!$%s$5" % m.group(1)
    die("unrecognised load_as in manifest.json: %s" % load_as)


# ---------------------------------------------------------------- main build
def build(args):
    global FIXED_DT
    root = Path(args.input_root).resolve()
    P = root / PROJ
    pq_dir = P / "05-excel" / "powerquery"

    plan_p = P / "01-plan" / "plan.json"
    if not plan_p.exists():
        die("missing input: %s" % plan_p)
    plan = json.loads(plan_p.read_text(encoding="utf-8"))
    cfg_h, cfg_rows = read_csv(P / "02-config" / "pipeline_config.csv")
    lg_h, lg_rows = read_csv(P / "02-config" / "leagues.csv")
    sc_h, sc_rows = read_csv(P / "02-config" / "scoring_weights.csv")
    bo_h, bo_rows = read_csv(P / "02-config" / "bonus_rules.csv")
    go_h, go_rows = read_csv(P / "06-qa" / "fixtures" / "golden_sample.csv")
    dd_h, dd_rows = read_csv(P / "04-data" / "dictionary.csv")
    bl_h, bl_rows = read_csv(root / "BLOCKERS.csv")
    gr_h, gr_rows = read_csv(P / "06-qa" / "fixtures" / "fixture_contracts.csv")
    if gr_h != ["league", "rules_sha256", "round_decimals"]:
        die("fixture_contracts.csv header %s" % gr_h)
    man_p = pq_dir / "manifest.json"
    if not man_p.exists():
        die("missing input: %s" % man_p)
    manifest = json.loads(man_p.read_text(encoding="utf-8"))["queries"]

    version = args.version
    rel_date = dt.date.fromisoformat(args.release_date)
    FIXED_DT = dt.datetime.combine(rel_date, dt.time(0, 0))
    status = args.status

    # ---- input contracts (CONTRACTS.md section 1, WORKBOOK-REQUIREMENTS.md)
    if cfg_h != ["Setting", "Value", "Allowed_Values", "Description"]:
        die("pipeline_config.csv header %s" % cfg_h)
    if lg_h != ["League", "Description", "Active", "Reconcile_To", "Notes"]:
        die("leagues.csv header %s" % lg_h)
    leagues = [r[0] for r in lg_rows]
    exp_sc = ["Metric", "Category", "Description"] + leagues + ["Notes", "Applies_To"]
    if sc_h != exp_sc:
        die("scoring_weights.csv header %s != %s" % (sc_h, exp_sc))
    bad = [l for l in leagues if l in RESERVED or not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", l)]
    if bad:
        die("invalid league names: %s" % bad)
    if bo_h != ["League", "Metric", "Lower", "Upper", "Points", "Applies_To", "Notes"]:
        die("bonus_rules.csv header %s" % bo_h)
    if dd_h[:5] != ["metric", "category", "description", "source", "applies_to"]:
        die("dictionary.csv header %s" % dd_h)
    names = [q["name"] for q in manifest]
    if names[7:] != [n for n, _, _ in CHECK_LAYOUT]:
        die("manifest order of loaded queries differs from WORKBOOK-REQUIREMENTS.md: %s" % names)
    for q in manifest:
        lt = load_to_text(q["load_as"])
        lay = next((x for x in CHECK_LAYOUT if x[0] == q["name"]), None)
        if lay and "=Checks!$%s$5" % lay[1] not in lt:
            die("manifest anchor for %s (%s) != requirements (%s5)" % (q["name"], q["load_as"], lay[1]))
        if not lay and not lt.startswith("Only Create Connection"):
            die("query %s should be connection only" % q["name"])

    wb = Workbook()
    wb._named_styles["Normal"].font = F_BASE
    wb.remove(wb.active)
    wss = {n: wb.create_sheet(n) for n, _ in SHEETS}
    for n, p in SHEETS:
        sheet_head(wss[n], "NFL-Analysis" if n == "Cover" else n.replace("_", " "), p)
    print_rows = {}

    # ================= Config: WorkbookFolder (B2) + tblConfig (A4)
    ws = wss["Config"]
    put(ws, "A2", "Workbook folder", F_BOLD)
    put(ws, "B2", '=LEFT(CELL("filename",$A$1),FIND("[",CELL("filename",$A$1))-1)', align=LEFT)
    wb.defined_names["WorkbookFolder"] = DefinedName("WorkbookFolder", attr_text="Config!$B$2")
    put(ws, "C2", "Formula: this workbook's folder (shows once the file is saved). Power Query uses it only when "
                  "DataLocation is blank, to look for a 04-data folder on this PC.", F_NOTE)
    put(ws, "A3", "Edit only the yellow Value cells; keep the Setting names unchanged. The Value column is Text, "
                  "so 2017, Latest-9 and paths stay exactly as typed.", F_NOTE)
    cfg_map = {r[0]: r for r in cfg_rows}
    if "DataLocation" in cfg_map:
        die("pipeline_config.csv already has DataLocation")
    for k in CONFIG_ORDER[:5]:
        if k not in cfg_map:
            die("pipeline_config.csv lacks setting %s" % k)
    cf = [[txt(c) for c in row] for row in cfg_rows] + [list(DATALOCATION_ROW)]
    a, z = add_table(ws, "tblConfig", 4, 1, cfg_h, cf, wrap={2, 3}, inputs={1}, fmts={1: "@"})
    srow = {row[0]: a + i for i, row in enumerate(cf)}
    CONFIG_VALUE_RANGE[0] = "B%d:B%d" % (a, z + 200)  # room for settings added later
    for rr in range(a, z + 1):
        ws.cell(row=rr, column=2).alignment = Alignment(horizontal="left", vertical="top", indent=1)
    for k in ("StartSeason", "EndSeason"):
        cell = "B%d" % srow[k]
        add_dv(ws, "custom", season_dv(cell), cell, allow_blank=False, errorTitle=k,
               error="Enter a season year 1999 or later (for example 2017), the word Latest, "
                     "or Latest-N with N from 0 to 30 (for example Latest-9).")
    add_dv(ws, "list", '"REG,POST,REG+POST"', "B%d" % srow["SeasonTypes"], allow_blank=False,
           errorTitle="SeasonTypes", error="Choose REG, POST or REG+POST.")
    c = "B%d" % srow["RoundDecimals"]
    add_dv(ws, "custom", "IFERROR(AND(--%s>=0,--%s<=6,INT(--%s)=--%s),FALSE)" % (c, c, c, c), c,
           allow_blank=False, errorTitle="RoundDecimals", error="Enter a whole number from 0 to 6.")
    c = "B%d" % srow["ReconcileTolerance"]
    add_dv(ws, "custom", 'OR(LEN(TRIM(%s))=0,IFERROR(--%s>=0,FALSE))' % (c, c), c,
           errorTitle="ReconcileTolerance", error="Enter 0 or a small positive number such as 0.005 (blank = 0.005).")
    # side notes (fixed text, right of the fixed-width table; never below it)
    put(ws, "F4", "Notes", F_SECTION)
    notes = [
        "DataLocation: as shipped, the web address of the published data on GitHub (" + DATA_URL + "). Leave it. "
        "To read a downloaded copy of the 04-data folder instead, type that folder's full path; blank = a 04-data "
        "folder next to the workbook's folder.",
        "PublishExtraColumns is read only by the pipeline (02-config/pipeline_config.csv). The workbook ignores it; "
        "it is kept for reference.",
        "The pipeline has its own copy of these settings. Check_Rules_Drift (Checks sheet) reports a RoundDecimals "
        "that differs from the pipeline's.",
        "Setting names must be unique; rows with a blank Setting are ignored.",
    ]
    for i, n in enumerate(notes):
        put(ws, (5 + i, 6), n, align=WRAP, text=True)
    widths(ws, {"A": 22, "B": 30, "C": 42, "D": 70, "E": 3, "F": 60})
    ws.freeze_panes = "A5"
    print_rows["Config"] = 4

    # ================= Scoring: tblLeagues (A4) + tblScoring (H4, rightmost)
    ws = wss["Scoring"]
    put(ws, "A3", "Yellow cells are inputs. To add a league: a row in tblLeagues and a column in tblScoring "
                  "(before Notes) with the identical name; Column_Check then shows OK. See Start_Here, section 7.",
        F_NOTE)
    lg = [[txt(c) for c in row] for row in lg_rows]
    lg_f = [row + ['=IF(OR(%s),"RESERVED name",'
                   'IF(ISNUMBER(MATCH(tblLeagues[[#This Row],[League]],tblScoring[#Headers],0)),'
                   '"OK","MISSING in tblScoring"))' % RESERVED_OR] for row in lg]
    a, z = add_table(ws, "tblLeagues", 4, 1, lg_h + ["Column_Check"], lg_f, wrap={1, 4},
                     inputs={0, 2, 3}, formulas={5}, calc={5})
    list_dv(ws, ["Yes", "No"], a, z, 3, allow_blank=False, errorTitle="Active", error="Choose Yes or No.")
    list_dv(ws, ["fantasy_points", "fantasy_points_ppr"], a, z, 4, errorTitle="Reconcile_To",
            error="Leave blank, or choose fantasy_points or fantasy_points_ppr.")
    nl = len(leagues)
    sc = []
    for row in sc_rows:
        row = list(row) + [""] * (len(sc_h) - len(row))
        vals = [txt(c) for c in row[:3]] + [conv(c) for c in row[3:3 + nl]] + [txt(c) for c in row[3 + nl:]]
        for v in vals[3:3 + nl]:
            if v is not None and not isinstance(v, (int, float)):
                die("non-numeric weight %r for %s" % (v, row[0]))
        vals.append('=IF(COUNTIF(tblDictionary[metric],tblScoring[[#This Row],[Metric]])>0,'
                    '"OK","not in published data (see Check_Metrics)")')
        sc.append(vals)
    sc_out_h = sc_h + ["Metric_Check"]
    wcols = set(range(3, 3 + nl))
    a, z = add_table(ws, "tblScoring", 4, 8, sc_out_h, sc, wrap={2, 3 + nl},
                     inputs=wcols | {4 + nl}, fmts={j: "0.00##" for j in wcols},
                     formulas={5 + nl}, calc={5 + nl})
    add_dv(ws, "decimal", "-1000", "%s%d:%s%d" % (get_column_letter(8 + 3), a, get_column_letter(8 + 2 + nl), z),
           formula2="1000", operator="between", errorTitle="Weight",
           error="Enter a number (points per unit), or leave blank for 0.")
    w = {"A": 16, "B": 40, "C": 8, "D": 17, "E": 34, "F": 18, "G": 3, "H": 26, "I": 18, "J": 36}
    for j in range(nl):
        w[get_column_letter(11 + j)] = 13
    w.update({get_column_letter(11 + nl): 48, get_column_letter(12 + nl): 12, get_column_letter(13 + nl): 22})
    widths(ws, w)
    ws.freeze_panes = "A5"
    print_rows["Scoring"] = 4

    # ================= Bonus: tblBonus (A4)
    ws = wss["Bonus"]
    put(ws, "A3", "A row adds Points when Lower <= value <= Upper (blank bound = no limit). Overlapping bands stack; "
                  "disjoint bands do not. Applies_To blank = all players, otherwise positions such as DST or K.", F_NOTE)
    bo = [[txt(r[0]), txt(r[1]), conv(r[2]), conv(r[3]), conv(r[4]), txt(r[5]), txt(r[6])] for r in bo_rows]
    a, z = add_table(ws, "tblBonus", 4, 1, bo_h, bo, wrap={6}, inputs={0, 1, 2, 3, 4, 5})
    add_dv(ws, "list", 'INDIRECT("tblLeagues[League]")', col_rng(1, a, z), allow_blank=False,
           errorTitle="League", error="Choose a League from tblLeagues (Scoring sheet).")
    add_dv(ws, "list", 'INDIRECT("tblScoring[Metric]")', col_rng(2, a, z), allow_blank=False,
           errorStyle="warning", errorTitle="Metric",
           error="This metric is not in tblScoring. Continue only if the pipeline publishes it (Data_Dictionary).")
    for j, nm in ((3, "Lower"), (4, "Upper"), (5, "Points")):
        add_dv(ws, "decimal", "-100000", col_rng(j, a, z), formula2="100000", operator="between",
               allow_blank=(nm != "Points"), errorTitle=nm,
               error="Enter a number." + (" Blank = no limit on this side." if nm != "Points" else ""))
    widths(ws, {"A": 16, "B": 22, "C": 9, "D": 9, "E": 9, "F": 12, "G": 90})
    ws.freeze_panes = "A5"
    print_rows["Bonus"] = 4

    # ================= M_Code: tblMCode (A4, Code is column C) + tblQueries (E4)
    ws = wss["M_Code"]
    put(ws, "A3", "To copy one query: click the Name Box (left of the formula bar), choose its PQ_ name "
                  "(listed in paste order), press Ctrl+C, then paste into Power Query's Advanced Editor. "
                  "One line per row is deliberate: copying a multi-line cell would add quotes.", F_NOTE)
    mc, qinfo = [], []
    r_first = 5
    for i, q in enumerate(manifest, 1):
        fp = pq_dir / q["file"]
        if not fp.exists():
            die("missing M file: %s" % fp)
        raw = fp.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            die("%s is not UTF-8" % fp)
        if "\r" in text or "\t" in text or text.startswith("﻿"):
            die("%s contains CR, TAB or a BOM; the paste-by-rows layout needs LF-only text" % fp)
        if not text.endswith("\n") or text.endswith("\n\n"):
            die("%s must end with exactly one newline" % fp)
        lines = text[:-1].split("\n")
        if any(len(ln) > 32767 for ln in lines):
            die("%s has a line longer than an Excel cell" % fp)
        start = r_first + len(mc)
        for k, ln in enumerate(lines, 1):
            mc.append([q["name"], k, ln if ln != "" else None])
        end = r_first + len(mc) - 1
        nm = "PQ_%02d_%s" % (i, q["name"])
        wb.defined_names[nm] = DefinedName(nm, attr_text="M_Code!$C$%d:$C$%d" % (start, end))
        qinfo.append([i, q["name"], load_to_text(q["load_as"]), ", ".join(q.get("depends_on") or []) or None,
                      len(lines), nm, "C%d:C%d" % (start, end), q.get("purpose"),
                      ", ".join((q.get("reads_tables") or []) + (q.get("reads_names") or [])) or None,
                      q.get("status")])
    add_table(ws, "tblMCode", 4, 1, ["Query", "Line", "Code"], mc, code={2})
    qh = ["No", "Query", "Close & Load To", "Depends On", "Lines", "Name Box", "Code Cells", "Purpose",
          "Reads", "Status"]
    add_table(ws, "tblQueries", 4, 5, qh, qinfo)
    widths(ws, {"A": 20, "B": 6, "C": 125, "D": 3, "E": 5, "F": 21, "G": 52, "H": 38, "I": 7, "J": 26,
                "K": 13, "L": 70, "M": 40, "N": 70})
    ws.freeze_panes = "A5"
    print_rows["M_Code"] = 4

    # ================= Checks: labels in row 4, anchors at row 5 left empty
    ws = wss["Checks"]
    put(ws, "A3", "Row 4 names the query that loads at the cell below it (Close & Load To > Table > Existing "
                  "worksheet). Status colours: green = good, amber = read it, red = act. Start_Here section 6 explains "
                  "each check.", F_NOTE)
    from openpyxl.utils import column_index_from_string as cidx
    cw = {}
    for qn, colL, cols in CHECK_LAYOUT:
        c0 = cidx(colL)
        put(ws, (4, c0), qn, F_BOLD, text=True)
        stc = CHECK_STATUS_COL.get(qn, "Status")
        sL = get_column_letter(c0 + cols.index(stc))
        rng = "%s6:%s5000" % (sL, sL)
        x = "%s6" % sL
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=['OR(%s="PASS",%s="OK",%s="matches pipeline",%s="same")' % (x, x, x, x)],
            fill=FILL_GREEN, stopIfTrue=True))
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=['AND(OR(LEFT(%s,4)="FAIL",LEFT(%s,7)="MISSING",%s="UNSUPPORTED",%s="NOT NUMERIC"),'
                     'LEFT(%s,9)<>"MISSING ("' % (x, x, x, x, x) + ')'],
            fill=FILL_RED, stopIfTrue=True))
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=['AND(LEN(%s)>0,%s<>"INFO",%s<>"%s")' % (x, x, x, stc)], fill=FILL_AMBER, stopIfTrue=True))
        for j, cn in enumerate(cols):
            L = get_column_letter(c0 + j)
            wide = cn in ("Detail", "Example", "Worst_Examples", "Item")
            cw[L] = 40 if wide else max(11, min(22, len(cn) + 3))
            if cn == "Match_Pct":
                for rr in range(6, 506):
                    ws["%s%d" % (L, rr)].number_format = "0.0%"
            if cn == "Largest_Difference":
                for rr in range(6, 506):
                    ws["%s%d" % (L, rr)].number_format = "0.00"
        cw[get_column_letter(c0 + len(cols))] = 3
    cw["A"] = 16
    widths(ws, cw)
    ws.freeze_panes = "A6"

    # ================= Validation: tblGolden (A4)
    ws = wss["Validation"]
    put(ws, "A3", "Expected FF_ values were made with the rules in tblGoldenRules (right). Check_Golden compares "
                  "your scores with them; a league whose rules were changed on purpose shows NOT APPLICABLE there, as "
                  "the pipeline's G-GOLDEN gate does. Do not edit these tables.", F_NOTE)
    text_cols = {"season_type", "player_id", "player_display_name", "position", "team"}
    gd = [[txt(c) if go_h[j] in text_cols else conv(c) for j, c in enumerate(row)] for row in go_rows]
    for row in gd:
        for j, v in enumerate(row):
            if go_h[j] not in text_cols and v is not None and not isinstance(v, (int, float)):
                die("golden_sample.csv: non-numeric %s=%r" % (go_h[j], v))
    add_table(ws, "tblGolden", 4, 1, go_h, gd)
    gr = []
    for row in gr_rows:
        if not re.fullmatch(r"[0-9a-f]{64}", row[1]) or not INT_RE.match(row[2]):
            die("fixture_contracts.csv: bad row %s" % row)
        gr.append([row[0], row[1], int(row[2])])
    gr_col = len(go_h) + 2  # one empty column right of tblGolden (WORKBOOK-REQUIREMENTS.md)
    add_table(ws, "tblGoldenRules", 4, gr_col, GOLDEN_RULES_HDR, gr)
    gw = {get_column_letter(j + 1): 12 for j in range(len(go_h))}
    gw.update({get_column_letter(gr_col - 1): 3, get_column_letter(gr_col): 14, get_column_letter(gr_col + 1): 68,
               get_column_letter(gr_col + 2): 14})
    gw.update({"A": 8, "B": 7, "C": 11, "D": 12, "E": 22, "F": 9, "G": 7})
    widths(ws, gw)
    ws.freeze_panes = "F5"
    print_rows["Validation"] = 4

    # ================= Data_Dictionary: tblDictionary (A4)
    ws = wss["Data_Dictionary"]
    put(ws, "A3", "Snapshot of 04-data/dictionary.csv at build time: the metric columns of player_week, in column "
                  "order. tblScoring Metric_Check looks metrics up here.", F_NOTE)
    dd = [[txt(c) for c in row] + [
        '=IF(COUNTIF(tblScoring[Metric],tblDictionary[[#This Row],[metric]])>0,"Yes","")',
        '=IF(COUNTIF(tblBonus[Metric],tblDictionary[[#This Row],[metric]])>0,"Yes","")'] for row in dd_rows]
    nd = len(dd_h)
    add_table(ws, "tblDictionary", 4, 1, dd_h + ["In_Scoring", "In_Bonus"], dd, wrap={2},
              formulas={nd, nd + 1}, calc={nd, nd + 1})
    widths(ws, {"A": 30, "B": 26, "C": 70, "D": 18, "E": 12, "F": 11, "G": 10})
    ws.freeze_panes = "B5"
    print_rows["Data_Dictionary"] = 4

    # ================= Open_Questions: tblOpenQuestions (A4)
    ws = wss["Open_Questions"]
    put(ws, "A3", "Answer in BLOCKERS.csv at the top of the repository on GitHub (the Answer column; on the file's page "
                  "click the pencil to edit), or tell Claude in chat. This sheet lists the questions still open when the "
                  "workbook was built; BLOCKERS.csv also holds the answered ones. Work continues on the default meanwhile.",
        F_NOTE)
    exp_bl = ["Question_ID", "Question", "Answer", "Type", "Default_Used_Meanwhile", "Options",
              "What_It_Blocks", "Raised", "Status", "Claude_Response"]
    if bl_h != exp_bl:
        die("BLOCKERS.csv header %s (expected %s, CONTRACTS.md section 11)" % (bl_h, exp_bl))

    def raised(v):
        for f in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return dt.datetime.strptime(v.strip(), f).date()
            except ValueError:
                pass
        return txt(v)
    open_rows = [r + [""] * (10 - len(r)) for r in bl_rows]
    open_rows = [r for r in open_rows if r[8].strip() in ("Open", "Still open", "")]
    bl = [[txt(c) for c in row[:7]] + [raised(row[7]) if row[7] else None, txt(row[8]), txt(row[9])]
          for row in open_rows]
    a, z = add_table(ws, "tblOpenQuestions", 4, 1, exp_bl, bl, wrap={1, 2, 4, 5, 6, 9}, fmts={7: "yyyy-mm-dd"})
    list_dv(ws, ["Answer needed", "Action needed"], a, z, 4)
    widths(ws, {"A": 10, "B": 60, "C": 24, "D": 14, "E": 45, "F": 50, "G": 45, "H": 11, "I": 11, "J": 60})
    ws.freeze_panes = "B5"
    print_rows["Open_Questions"] = 4

    # ================= Plan (prose, then tblKeyFindings as the last block)
    ws = wss["Plan"]
    ws.sheet_view.showGridLines = False
    widths(ws, {"A": 4, "B": 95, "C": 60})
    r = 4

    def plist(key):
        v = plan.get(key)
        if v is None:
            print("WARN: plan.json has no %r; the sheet shows it empty" % key)
            return []
        return v if isinstance(v, list) else [v]

    def ptext(v):
        if v is None:
            return None
        if isinstance(v, (list, tuple)):
            return "; ".join(str(x) for x in v)
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        return v
    section(ws, r, "Objective"); r += 1
    para(ws, r, ptext(plan.get("objective")) or "", 2, 3, 150); r += 2
    section(ws, r, "What you are trying to do"); r += 1
    for b in plist("what_you_are_trying_to_do"):
        para(ws, r, "•  " + b, 2, 3, 150); r += 1
    r += 1
    section(ws, r, "In scope"); r += 1
    for b in plist("scope_in"):
        para(ws, r, "•  " + b, 2, 3, 150); r += 1
    r += 1
    section(ws, r, "Out of scope"); r += 1
    for b in plist("scope_out"):
        para(ws, r, "•  " + b, 2, 3, 150); r += 1
    r += 1
    section(ws, r, "Key findings (tblKeyFindings)"); r += 1
    kf = [[ptext(k.get("finding")), ptext(k.get("source"))] for k in plist("key_findings")]
    add_table(ws, "tblKeyFindings", r, 2, ["Finding", "Source"], kf, wrap={0, 1})
    ws.freeze_panes = "A3"

    # ================= plan tables, one per sheet at A4
    def plan_sheet(sheet, tname, headers, keys, src, wrapcols, w, dvs=()):
        wsx = wss[sheet]
        rows = [[ptext(x.get(k)) for k in keys] for x in src]
        a_, z_ = add_table(wsx, tname, 4, 1, headers, rows, wrap=wrapcols)
        for col, opts in dvs:
            list_dv(wsx, opts, a_, z_, col)
        widths(wsx, w)
        wsx.freeze_panes = "B5" if sheet != "Architecture" else "A5"
        print_rows[sheet] = 4
        return a_, z_

    def opts(src, key, base):
        seen = list(base)
        for x in src:
            v = ptext(x.get(key))
            if v is not None and v not in seen:
                seen.append(v)
        # a list validation holds at most 255 characters; drop the rule's extra options rather than fail the build
        while len('"%s"' % ",".join(seen)) > 255:
            seen.pop()
        return seen

    arch = sorted(plist("architecture"), key=lambda x: (str(x.get("step", "")).zfill(6)))
    plan_sheet("Architecture", "tblArchitecture", ["Step", "Component", "Where", "Description"],
               ["step", "component", "where", "description"], arch, {1, 2, 3},
               {"A": 6, "B": 32, "C": 22, "D": 110})
    plan_sheet("Roadmap", "tblRoadmap",
               ["Version", "Increment", "Scope", "Deliverables", "Acceptance Criteria", "Depends On", "Status"],
               ["version", "increment", "scope", "deliverables", "acceptance_criteria", "depends_on", "status"],
               plist("roadmap"), {1, 2, 3, 4, 5},
               {"A": 9, "B": 24, "C": 60, "D": 45, "E": 60, "F": 30, "G": 12},
               dvs=[(7, opts(plist("roadmap"), "status", ["Planned", "In progress", "Released", "Withdrawn"]))])
    for rr in range(5, 5 + len(plist("roadmap"))):
        wss["Roadmap"].cell(row=rr, column=1).number_format = "@"
    plan_sheet("Requirements", "tblRequirements",
               ["ID", "Requirement", "Type", "Priority", "Source", "Target Version", "Acceptance Criteria", "Status"],
               ["id", "requirement", "type", "priority", "source", "target_version", "acceptance_criteria", "status"],
               plist("requirements"), {1, 4, 6},
               {"A": 9, "B": 60, "C": 15, "D": 10, "E": 26, "F": 10, "G": 60, "H": 12},
               dvs=[(3, opts(plist("requirements"), "type", ["Functional", "Non-functional", "Constraint"])),
                    (4, opts(plist("requirements"), "priority", ["Must", "Should", "Could"])),
                    (8, opts(plist("requirements"), "status", ["Planned", "In progress", "Done"]))])
    a, z = plan_sheet("RAID", "tblRAID",
                      ["ID", "Type", "Title", "Detail", "Rating", "Response", "Owner", "Target Version", "Status"],
                      ["id", "type", "title", "detail", "rating", "response", "owner", "target_version", "status"],
                      plist("raid"), {2, 3, 5, 6},
                      {"A": 9, "B": 12, "C": 32, "D": 60, "E": 9, "F": 50, "G": 18, "H": 10, "I": 10},
                      dvs=[(2, opts(plist("raid"), "type", ["Risk", "Assumption", "Issue", "Decision", "Question"])),
                           (5, opts(plist("raid"), "rating", ["High", "Medium", "Low"])),
                           (9, opts(plist("raid"), "status", ["Open", "Closed", "Accepted", "Answered"]))])
    wss["RAID"].conditional_formatting.add("E%d:E%d" % (a, z),
                                           CellIsRule(operator="equal", formula=['"High"'], fill=FILL_RED))
    plan_sheet("Controls", "tblControls",
               ["ID", "Control", "Method", "Expected Result", "Target Version", "Status"],
               ["id", "control", "method", "expected_result", "target_version", "status"],
               plist("controls"), {1, 2, 3},
               {"A": 8, "B": 34, "C": 70, "D": 60, "E": 10, "F": 12},
               dvs=[(6, opts(plist("controls"), "status", ["Designed", "Implemented", "Passing"]))])
    plan_sheet("Glossary", "tblGlossary", ["Term", "Definition"], ["term", "definition"],
               sorted(plist("glossary"), key=lambda g: str(g.get("term", "")).lower()), {1}, {"A": 28, "B": 120})
    for sh in ("Requirements", "RAID", "Controls"):
        tv = {"Requirements": 6, "RAID": 8, "Controls": 5}[sh]
        for rr in range(5, wss[sh].max_row + 1):
            wss[sh].cell(row=rr, column=tv).number_format = "@"

    # ================= Version_Log
    ws = wss["Version_Log"]
    rm_row = next((x for x in plist("roadmap") if str(x.get("version")) == version), None)
    summary = args.summary or ("%s: %s" % (ptext(rm_row.get("increment")), ptext(rm_row.get("scope"))) if rm_row else None) \
        or DEFAULT_SUMMARY.get(version)
    if not summary:
        die("no roadmap entry for %s in plan.json; pass --summary" % version)
    if not rm_row:
        print("WARN: plan.json has no roadmap entry for %s; Cover and Version_Log use the built-in summary" % version)
    vh_p = HERE / "version_history.csv"
    vh_h, vh_rows = read_csv(vh_p)
    if vh_h != ["Version", "Date", "Status", "Summary", "Gates_Passed", "Built_By"]:
        die("version_history.csv header mismatch: %s" % vh_h)
    vl = []
    for row in vh_rows:
        if row[0] == version:
            die("version_history.csv already contains %s" % version)
        vl.append([row[0], dt.date.fromisoformat(row[1]), row[2], txt(row[3]), txt(row[4]), txt(row[5])])
    vl.append([version, rel_date, status, summary, args.gates, args.built_by])
    add_table(ws, "tblVersionLog", 4, 1, ["Version", "Date", "Status", "Summary", "Gates Passed", "Built By"], vl,
              wrap={2, 3, 5}, fmts={1: "yyyy-mm-dd", 0: "@"})
    for rr in range(5, 5 + len(vl)):
        ws.cell(row=rr, column=2).alignment = Alignment(horizontal="left", vertical="top")
    widths(ws, {"A": 10, "B": 12, "C": 24, "D": 90, "E": 18, "F": 40})
    ws.freeze_panes = "A5"
    print_rows["Version_Log"] = 4

    # ================= Start_Here
    build_start_here(wss["Start_Here"], manifest, len(bl), version)

    # ================= Cover
    ws = wss["Cover"]
    ws.sheet_view.showGridLines = False
    widths(ws, {"A": 30, "B": 70, "C": 14})
    c = put(ws, "A3", "First time here? Read Start_Here  ›", F_BIGLINK)
    c.hyperlink = Hyperlink(ref="A3", location="'Start_Here'!A1", display="Start_Here")
    put(ws, "A4", "Version", F_BOLD)
    put(ws, "B4", version, F_BOLD, align=Alignment(horizontal="left"), fmt="@", text=True)
    wb.defined_names["WorkbookVersion"] = DefinedName("WorkbookVersion", attr_text="Cover!$B$4")
    put(ws, "A5", "Release date", F_BOLD)
    put(ws, "B5", rel_date, align=Alignment(horizontal="left"), fmt="yyyy-mm-dd")
    put(ws, "A6", "Status", F_BOLD)
    put(ws, "B6", status)
    put(ws, "A7", "Release scope", F_BOLD, align=TOP)
    para(ws, 7, "%s — %s" % (ptext(rm_row.get("increment")), ptext(rm_row.get("scope"))) if rm_row else summary, 2, 3, 100)
    put(ws, "A8", "Purpose", F_BOLD, align=TOP)
    para(ws, 8, ptext(plan.get("objective")) or "", 2, 3, 100)
    put(ws, "A9", "Power Query", F_BOLD, align=TOP)
    para(ws, 9, "Paste-ready: the %d queries are on the M_Code sheet and are added once in Excel "
                "(Start_Here, section 4). Until then the Checks sheet is empty. A copy with the queries already "
                "installed (experimental) is on the same GitHub page (Start_Here, section 2)." % len(manifest), 2, 3, 100)
    r = 11
    section(ws, r, "Sheet index"); r += 1
    for n, p in SHEETS:
        if n == "Cover":
            continue
        c = put(ws, (r, 1), n, F_LINK, align=TOP)
        c.hyperlink = Hyperlink(ref=c.coordinate, location="'%s'!A1" % n, display=n)
        put(ws, (r, 2), DESCR[n], align=WRAP, text=True)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
        ws.row_dimensions[r].height = est_height(DESCR[n], 100)
        r += 1
    r += 1
    section(ws, r, "Legend"); r += 1
    put(ws, (r, 1), "Input cell", F_INPUT, FILL_INPUT)
    put(ws, (r, 2), "Blue text on yellow = you may edit it. Black = formula or fixed text."); r += 1
    put(ws, (r, 1), "Code cells", F_CODE)
    put(ws, (r, 2), "M_Code cells use Consolas (monospace)."); r += 1
    for lab, fill, t in (("PASS / OK / same", FILL_GREEN, "Green on the Checks sheet: good."),
                         ("changed / differs / WARN", FILL_AMBER, "Amber: read it; often expected after you edit rules."),
                         ("FAIL / MISSING", FILL_RED, "Red: act (Start_Here, section 6).")):
        put(ws, (r, 1), lab, fill=fill)
        put(ws, (r, 2), t); r += 1
    r += 1
    section(ws, r, "Live summary"); r += 1
    live = [
        ("Questions waiting on you", "=ROWS(tblOpenQuestions[Question_ID])"),
        ("Active leagues", '=COUNTIF(tblLeagues[Active],"Yes")'),
        ("Scoring metrics", "=ROWS(tblScoring[Metric])"),
        ("Bonus bands", "=ROWS(tblBonus[League])"),
        ("Power Query queries", "=ROWS(tblQueries[Query])"),
        ("M code lines", "=ROWS(tblMCode[Line])"),
        ("Requirements (total)", "=ROWS(tblRequirements[ID])"),
        ("Requirements (Must)", '=COUNTIF(tblRequirements[Priority],"Must")'),
        ("Open RAID items", '=COUNTIF(tblRAID[Status],"Open")'),
        ("Controls", "=ROWS(tblControls[ID])"),
    ]
    for lab, f in live:
        put(ws, (r, 1), lab); put(ws, (r, 2), f, align=Alignment(horizontal="left")); r += 1
    r += 1
    section(ws, r, "Data source"); r += 1
    for lab, t in (("Reads", "The CSV files the pipeline publishes in NFL/04-data (player_week, scored, seasons, status, "
                             "checks, config), from the web address in DataLocation (Config sheet): " + DATA_URL),
                   ("Published by", "The nflpipe pipeline in NFL/03-pipeline of " + REPO_URL + ", run by GitHub "
                                    "Actions from public nflverse data (CC BY 4.0)."),
                   ("Upstream", "https://github.com/nflverse/nflverse-data/releases"),
                   ("Data licence", ATTRIBUTION)):
        put(ws, (r, 1), lab, align=TOP)
        para(ws, r, t, 2, 3, 100)
        r += 1

    # ---- workbook-level
    wb.properties.title = "NFL-Analysis-%s" % version
    wb.properties.version = version
    wb.properties.subject = "NFL weekly player stats + custom fantasy scoring (pipeline CSV + Power Query)"
    wb.properties.creator = "NFL-Analysis Committee (Claude)"
    wb.properties.lastModifiedBy = "NFL-Analysis build_workbook.py"
    wb.properties.keywords = "nflverse; Power Query; fantasy football; pipeline"
    wb.properties.description = "Paste-ready workbook %s (%s), generated from source in %s." % (version, status, REPO_URL)
    wb.properties.created = FIXED_DT
    wb.properties.modified = FIXED_DT
    wb.calculation.fullCalcOnLoad = True
    for n, w_ in wss.items():
        w_.page_setup.orientation = "landscape"
        w_.page_setup.fitToWidth = 1
        w_.page_setup.fitToHeight = 0
        w_.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        w_.page_margins.left = w_.page_margins.right = 0.5
        w_.page_margins.top = w_.page_margins.bottom = 0.6
        w_.page_margins.header = w_.page_margins.footer = 0.3
        if n in print_rows:
            w_.print_title_rows = "%d:%d" % (print_rows[n], print_rows[n])
    wss["M_Code"].print_area = "A1:C%d" % (4 + len(mc))
    wb.active = 0
    return wb


STATUS_LEGEND = ("Green = good: PASS, OK, same, matches pipeline. Amber = read the row; often expected after you "
                 "change a rule: NOT APPLICABLE, RULES CHANGED, DECIMALS CHANGED, NO TEST VALUES, WARN, CHECK, changed, "
                 "differs, only in workbook, only in pipeline, not in pipeline, not scored in workbook, NOT PUBLISHED, "
                 "NO ROWS, MISSING (zero weight everywhere). Red = act: FAIL, MISSING, MISSING COLUMN, NOT NUMERIC, "
                 "UNSUPPORTED. INFO = information only.")
EXPERIMENTAL_NAME = "NFL-Analysis-%s-queries-installed-EXPERIMENTAL.xlsx"


def build_start_here(ws, manifest, n_open, version):
    ws.sheet_view.showGridLines = False
    widths(ws, {"A": 4, "B": 24, "C": 16, "D": 44, "E": 34, "F": 52})
    CPL = 195
    st = {"r": 4}
    nq = len(manifest)
    exp_name = EXPERIMENTAL_NAME % version

    def nxt(k=1):
        st["r"] += k

    def h(text):
        nxt()
        section(ws, st["r"], text)
        nxt()

    def p(text, font=F_BASE, fill=None):
        para(ws, st["r"], text, 2, 6, CPL, font, fill)
        nxt()

    def step(n, text):
        put(ws, (st["r"], 1), n, F_BOLD, FILL_STEP, Alignment(horizontal="center", vertical="top"))
        para(ws, st["r"], text, 2, 6, CPL)
        nxt()

    def grid(headers, rows, spans=((2, 2), (3, 3), (4, 4), (5, 5), (6, 6))):
        wid = {2: 24, 3: 16, 4: 44, 5: 34, 6: 52}
        for j, hd in enumerate(headers):
            c1, c2 = spans[j]
            put(ws, (st["r"], c1), hd, F_HDR, FILL_HDR, WRAP, text=True)
            if c2 > c1:
                ws.merge_cells(start_row=st["r"], start_column=c1, end_row=st["r"], end_column=c2)
        nxt()
        for row in rows:
            hmax = 16
            for j, v in enumerate(row):
                c1, c2 = spans[j]
                put(ws, (st["r"], c1), v, F_BOLD if j == 0 else F_BASE, FILL_GREY if j == 0 else None,
                    WRAP, text=True)
                if c2 > c1:
                    ws.merge_cells(start_row=st["r"], start_column=c1, end_row=st["r"], end_column=c2)
                hmax = max(hmax, est_height(v, sum(wid[c] for c in range(c1, c2 + 1)) * 1.05))
            ws.row_dimensions[st["r"]].height = hmax
            nxt()

    put(ws, "A3", "Download, open, refresh. Nothing to install and nothing to keep in step on your PC: the data comes "
                  "from GitHub over the web. After the first refresh, one click a week.", F_NOTE)

    h("1. What this workbook is")
    p("NFL-Analysis %s gives you every NFL player's game-by-game stats for a rolling 10 seasons, one team defense and "
      "special teams (D/ST) row per team-game, and fantasy points for each of your leagues." % version)
    p("Where the numbers come from: a pipeline that runs on GitHub (in the repository %s) downloads the public "
      "nflverse data each week in season, works out long-touchdown bonuses and team D/ST rows, scores every league "
      "and publishes plain CSV files. This workbook reads those files from the web, at the address in DataLocation "
      "on the Config sheet. Your laptop does not need to be on for the pipeline to run, and it needs no copy of the "
      "repository and no other software than Excel. " % REPO_URL + ATTRIBUTION)
    p("You still set the points per league here: the Scoring and Bonus sheets drive the workbook's own scoring, so a "
      "change there shows in your scores at the next refresh. The Checks sheet compares your scores with the "
      "pipeline's and lists every rule that differs, so you always know why two numbers differ.")
    p("Version %s is the first of the 2.x line: 2.x workbooks read the published data from the web; the 1.x "
      "workbooks computed everything inside Excel." % version, F_NOTE)
    if n_open:
        p("%d question(s) on the Open_Questions sheet are still waiting on you. None stops you from starting: each has "
          "a default that is used meanwhile." % n_open, F_NOTE)

    h("2. Get the workbook (you may have done this already)")
    step(1, "In your browser, open %s and click the folders NFL, then 05-excel. Two workbooks are there:\n"
            "a. %s: the same workbook with the %d queries already installed, so there is nothing to paste. Try it "
            "first. It has not yet been opened in Excel, so it is labelled experimental; the page "
            "NFL/05-excel/experimental/README.md on GitHub says exactly what to do and what to report.\n"
            "b. NFL-Analysis-%s.xlsx (this file): paste-ready. Every table and check location is in place; you add "
            "the %d queries once, which takes about 30 minutes (section 4). Use it if the experimental file does "
            "not work." % (REPO_URL, exp_name, nq, version, nq))
    step(2, "To download one: click its name, then the Download raw file button (the arrow pointing down, at the top "
            "right of the file view). Save it anywhere, for example in Documents. Use Windows desktop Excel for "
            "Microsoft 365 (the Data Model is needed; not Excel for Mac or Excel for the web).")
    step(3, "The data must be on GitHub's main branch. Until the pull request that brings this project there is "
            "merged (Open_Questions Q-015), the first refresh stops with \"HTTP 404 ... Nothing is published at that "
            "address\": merge it, then refresh again.")

    h("3. Open it, and answer Excel's questions once")
    step(1, "Excel opens a downloaded file in Protected View: click Enable Editing. If a yellow bar says that "
            "external data connections have been disabled, click Enable Content.")
    step(2, "At the first refresh Excel asks how to connect to the web site (dialog Access Web content; inside the "
            "Power Query window it is a yellow bar: Edit Credentials). Choose Anonymous on the left, choose "
            "https://raw.githubusercontent.com/ in the drop-down Select which level to apply these settings to, "
            "then click Connect. Do not choose Windows, Basic or Organizational account: the data is public.")
    step(3, "Then Excel asks about privacy levels (\"Information is required about data privacy\"; inside the Power "
            "Query window click Continue). Set Current Workbook to Public and https://raw.githubusercontent.com/ to "
            "Public, then click Save. Only file names and season years go to the web; the data itself is public. "
            "Only if a privacy or Formula.Firewall message keeps coming back: Data > Get Data > Query Options > "
            "Current Workbook > Privacy > Ignore the Privacy Levels and potentially improve performance > OK, then "
            "Data > Refresh All.")
    p("Excel remembers these answers on this PC. To change them later: Data > Get Data > Data Source Settings.", F_NOTE)

    h("4. One-time setup in this paste-ready file: add the %d queries" % nq)
    p("Skip this section in the experimental file: its queries are installed already.", F_NOTE)
    step(1, "Optional, saves time: Data > Queries & Connections; while you add the queries, right-click each one > "
            "Properties > untick Enable background refresh.")
    step(2, "Add the queries in the order of the tblQueries table on the M_Code sheet. For each one:\n"
            "a. On M_Code, click the Name Box (left of the formula bar) and choose its name, PQ_01_Stats_Raw first. "
            "That selects exactly its code lines. Press Ctrl+C.\n"
            "b. Data > Get Data > From Other Sources > Blank Query. In Power Query: Home > Advanced Editor, select "
            "all, Ctrl+V, Done. (The first query may show the questions of section 3: answer them.)\n"
            "c. Rename the query to exactly the name in the Query column (Query Settings > Name).\n"
            "d. Home > Close & Load To..., and choose what the Close & Load To column says: Only Create Connection "
            "(queries 1-6); Only Create Connection plus Add this data to the Data Model (7, Stats_Scored); Table > "
            "Existing worksheet > the Checks cell shown (8-15).")
    step(3, "Data > Refresh All. The first refresh downloads about 45 MB and scores about 180,000 rows for every "
            "league; how long it takes in Excel has not been measured yet, so allow several minutes. Then read the "
            "Checks sheet (section 6).")
    step(4, "Save the file. Tell Claude how it went: the saved, query-filled file can become the next version.")
    p("Do not edit the M inside Excel; if a query must change, paste the new text again. Every step, every message "
      "and what to do about it: NFL/05-excel/powerquery/README.md on GitHub (the runbook).", F_NOTE)

    h("5. Each week")
    step(1, "Open the workbook and click Data > Refresh All. That is all: GitHub runs the pipeline and publishes new "
            "data Tuesday to Thursday in season, and the workbook reads it at every refresh.")
    step(2, "Checks sheet: Pipeline_Status shows how far the data goes (Data through). Everything should be green; "
            "amber rows after a rule you changed on purpose are expected (section 7).")
    step(3, "If new data was published only minutes ago and a check is amber or red, wait 5 minutes and refresh again: "
            "GitHub keeps copies of the files for up to 5 minutes.")
    p("How the scheduled runs work, what an alert means and how to start a run by hand: NFL/03-pipeline/AUTOMATION.md "
      "on GitHub.", F_NOTE)

    h("6. What each check tells you")
    p("Each check loads as a table on the Checks sheet, side by side from column A. " + STATUS_LEGEND)
    grid(["Check (cell)", "Green means", "What it tells you", "Amber", "Red, and what to do"], [
        ["Pipeline_Status (A5)", "OK, PASS",
         "Where the data was read from, when the pipeline made it, data through which season and week, pipeline and "
         "data contract versions, run outcome, one row per pipeline gate, and one row per league saying whether the "
         "pipeline still uses the rules the test values were made with.",
         "RULES CHANGED or DECIMALS CHANGED on a league row, or WARN on a gate with \"not applicable: rules for "
         "<League> changed\": expected after a scoring change on GitHub (section 7). NO TEST VALUES: a new league. "
         "CHECK: read Detail.",
         "UNSUPPORTED: the data uses a contract version other than 1; ask for matching queries. MISSING: status.csv "
         "lacks an item. FAIL on a gate: the publish is suspect; tell Claude."],
        ["Check_Parity (G5)", "matches pipeline",
         "Your workbook's scores against the pipeline's scores, per league, on every row.",
         "differs: workbook rules changed? = your rules differ from the pipeline's (see Check_Rules_Drift). not in "
         "pipeline / not scored in workbook = a league added, renamed or switched off. blank scores on one side or "
         "row sets differ = refresh again in 5 minutes.",
         "No red state."],
        ["Check_Rules_Drift (Q5)", "same (one row)",
         "Every weight, position gate, bonus band, active flag or RoundDecimals where your tables differ from the "
         "rules the pipeline used.",
         "changed, only in workbook, only in pipeline: one row per difference. Fine if intended.",
         "No red state. The Pipeline column shows the pipeline's value."],
        ["Check_Metrics (X5)", "OK",
         "Every statistic in tblScoring and tblBonus exists as a numeric column in the data.",
         "MISSING (zero weight everywhere): a row no league gives points for; harmless.",
         "MISSING COLUMN: a league gives points for a statistic the data lacks, so its scores are too low; add it "
         "on GitHub (section 7). NOT NUMERIC: tell Claude."],
        ["Check_Reconciliation (AD5)", "PASS (100%)",
         "The control leagues (Standard, PPR) reproduce nflverse's own fantasy points within ReconcileTolerance "
         "(widened to 0.5 or 0.05 when RoundDecimals is 0 or 1, as in the pipeline). D/ST rows are left out.",
         "NOT APPLICABLE: that control league's rules were changed on purpose, here or on GitHub; Worst_Examples "
         "says which. The pipeline says the same.",
         "FAIL: with unchanged rules the scores no longer match nflverse; tell Claude."],
        ["Check_RowCounts (AL5)", "PASS",
         "Rows per season and season type in the workbook against the pipeline's seasons.csv.",
         "NOT PUBLISHED: your season window asks for a season the pipeline has not published; narrow the window.",
         "FAIL: files from two publishes were read; refresh again in 5 minutes."],
        ["Check_Golden (AV5)", "PASS (25 of 25)",
         "Hand-checked player-games per league (Validation sheet) against your scores.",
         "NOT APPLICABLE: the league's rules or RoundDecimals were changed on purpose, here or on GitHub, so its "
         "expected values no longer apply; Worst_Examples says which. The pipeline says the same.",
         "FAIL: with unchanged rules a score differs; tell Claude."],
        ["Check_Integrity (BC5)", "PASS",
         "Scoring kept every row, and each player-game appears once. The last row counts D/ST rows (INFO).",
         "",
         "FAIL: tell Claude; do not trust the scores until fixed."],
    ])

    h("7. Change scoring")
    p("Two places, which can be used together.")
    p("A. In this workbook (yours alone, at once): edit a yellow cell in tblScoring (Scoring sheet) or tblBonus "
      "(Bonus sheet), then Data > Refresh All. Your scores use the new number; the published data does not change. "
      "On the Checks sheet you will then see, as expected:\n"
      "•  Check_Parity for that league: differs: workbook rules changed? (see Check_Rules_Drift), with the number "
      "of rows that differ, the largest difference and an example player-game.\n"
      "•  Check_Rules_Drift: one row per change, for example  ESPN_League | Weight | receptions | 0.5 | 1 | changed.\n"
      "•  Check_Golden for that league: NOT APPLICABLE (its expected values were made with other rules); for "
      "Standard or PPR also Check_Reconciliation: NOT APPLICABLE.")
    p("B. On GitHub (changes the published scores): in your browser open NFL/02-config in the repository, edit "
      "scoring_weights.csv or bonus_rules.csv (RoundDecimals is in pipeline_config.csv) and save the change there. "
      "Saving starts the pipeline, which publishes new data a few minutes later. How to edit and what happens next "
      "are in NFL/03-pipeline/AUTOMATION.md; NFL/02-config/README.md explains the files. At your next refresh:\n"
      "•  Pipeline_Status: that league's row says RULES CHANGED, and the gate G-GOLDEN (also G-ESPN for "
      "ESPN_League, G-RECON for Standard or PPR) says WARN, not applicable. Nothing is wrong: the stored test values "
      "were made with the old rules.\n"
      "•  Check_Golden (and Check_Reconciliation for Standard or PPR): NOT APPLICABLE for that league, the same "
      "verdict as the pipeline.\n"
      "•  If you did not make the same change here, Check_Parity says differs and Check_Rules_Drift lists the new "
      "rules: copy the Pipeline values into tblScoring or tblBonus and refresh.\n"
      "A mistake in the file (for example a misspelt statistic) stops the publish (G-CONFIG FAIL); the workbook then "
      "keeps reading the previous data.")
    p("RoundDecimals touches every league: with 0 or 1 decimals Check_Golden shows NOT APPLICABLE for all leagues "
      "(the expected values have 2 decimals) and Check_Reconciliation widens its tolerance, as the pipeline does, so "
      "it stays PASS. A position gate (Applies_To) changed here counts as a change to every league.")
    p("Add a league:")
    step(1, "tblLeagues (Scoring sheet): add a row. League = letters, digits and underscores, starting with a letter "
            "(for example My_League); Active = Yes; Reconcile_To blank.")
    step(2, "tblScoring: insert a column just before Notes with exactly the same header, and fill a weight for each "
            "statistic (blank = 0). Column_Check in tblLeagues turns OK.")
    step(3, "Optional: tblBonus rows with that League name. Then Data > Refresh All: the scores get FF_My_League by "
            "themselves, with no change to the M.")
    p("The checks then show  My_League | not in pipeline: league added or renamed in the workbook?  in "
      "Check_Parity, and in Check_Rules_Drift a row  My_League | League | Active | active | (absent)  followed by "
      "one only in workbook row per non-zero weight and band: expected until the league is added on GitHub too. "
      "Switching a league off (Active = No) shows not scored in workbook in Check_Parity and inactive against "
      "active in Check_Rules_Drift.")
    p("Score a new statistic: add a row to tblScoring with the exact column name from Data_Dictionary. If the data "
      "does not have it, Metric_Check says not in published data and Check_Metrics says MISSING COLUMN: add the "
      "metric to NFL/02-config/scoring_weights.csv on GitHub so the pipeline publishes it.")

    h("8. Where the data comes from")
    p("Config sheet, setting DataLocation. As shipped it is %s, the published data on GitHub's main branch. "
      "Leave it. It also accepts the full path of a folder on your PC that holds a copy of the 04-data folder "
      "(for example to work offline), and blank means a 04-data folder next to the workbook's folder. If a "
      "message says HTTP 404, the data is not at that address: see section 2, step 3." % DATA_URL)
    p("Help: NFL/05-excel/README.md on GitHub is the starting page; NFL/05-excel/powerquery/README.md is the "
      "runbook with every message and its fix.", F_NOTE)
    ws.freeze_panes = "A4"


EXPECTED_TABLES = {
    "Config": ["tblConfig"], "Scoring": ["tblLeagues", "tblScoring"], "Bonus": ["tblBonus"],
    "M_Code": ["tblMCode", "tblQueries"], "Validation": ["tblGolden", "tblGoldenRules"], "Data_Dictionary": ["tblDictionary"],
    "Open_Questions": ["tblOpenQuestions"], "Plan": ["tblKeyFindings"], "Architecture": ["tblArchitecture"],
    "Roadmap": ["tblRoadmap"], "Requirements": ["tblRequirements"], "RAID": ["tblRAID"],
    "Controls": ["tblControls"], "Glossary": ["tblGlossary"], "Version_Log": ["tblVersionLog"],
}


def sheet_part(items, sheet):
    """Zip part name of a worksheet, found through workbook.xml and its relationships."""
    d = dict(items)
    m = re.search(rb'<sheet [^>]*name="%s"[^>]*r:id="(rId\d+)"' % sheet.encode(), d["xl/workbook.xml"])
    rid = m.group(1)
    t = re.search(rb'<Relationship [^>]*Id="%s"[^>]*Target="([^"]+)"' % rid, d["xl/_rels/workbook.xml.rels"]) or \
        re.search(rb'<Relationship [^>]*Target="([^"]+)"[^>]*Id="%s"' % rid, d["xl/_rels/workbook.xml.rels"])
    target = t.group(1).decode().lstrip("/")
    return target if target.startswith("xl/") else "xl/" + target


def normalize_zip(path, fixed, ignore_text_numbers=None):
    """Rewrite the .xlsx with fixed entry timestamps and a fixed core.xml modified date,
    keeping entry order, so identical inputs give identical bytes. Optionally add
    <ignoredErrors numberStoredAsText> to one sheet (openpyxl cannot write it), so Excel shows
    no green triangles on the deliberately text-formatted tblConfig[Value] cells."""
    stamp = fixed.strftime("%Y-%m-%dT%H:%M:%SZ")
    with zipfile.ZipFile(path) as zin:
        items = [(i.filename, zin.read(i.filename)) for i in zin.infolist()]
    if ignore_text_numbers:
        sheet, sqref = ignore_text_numbers
        part = sheet_part(items, sheet)
        ie = ('<ignoredErrors><ignoredError sqref="%s" numberStoredAsText="1"/></ignoredErrors>' % sqref).encode()
        out = []
        for name, data in items:
            if name == part:
                assert b"<ignoredErrors" not in data and data.count(b"<tableParts") == 1, part
                assert not re.search(rb"<(smartTags|drawing|legacyDrawing|picture|oleObjects|controls)\b", data)
                data = data.replace(b"<tableParts", ie + b"<tableParts")
            out.append((name, data))
        items = out
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w") as zout:
        for name, data in items:
            if name == "docProps/core.xml":
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                              lambda m: m.group(1) + stamp.encode() + m.group(2), data)
                data = re.sub(rb"(<dcterms:created[^>]*>)[^<]*(</dcterms:created>)",
                              lambda m: m.group(1) + stamp.encode() + m.group(2), data)
            zi = zipfile.ZipInfo(name, date_time=fixed.timetuple()[:6])
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 0
            zi.external_attr = 0
            zout.writestr(zi, data, compresslevel=6)
    os.replace(tmp, path)


def inventory(path, version):
    wb = load_workbook(path)
    assert wb.sheetnames == [n for n, _ in SHEETS], wb.sheetnames
    for sh, tabs in EXPECTED_TABLES.items():
        got = sorted(wb[sh].tables.keys())
        assert got == sorted(tabs), (sh, got)
    assert wb.defined_names["WorkbookVersion"].attr_text == "Cover!$B$4"
    assert wb.defined_names["WorkbookFolder"].attr_text == "Config!$B$2"
    assert wb["Cover"]["B4"].value == version
    assert wb.properties.title == "NFL-Analysis-%s" % version and wb.properties.version == version
    vlws = wb["Version_Log"]
    assert vlws.cell(row=vlws.max_row, column=1).value == version
    return {
        "sheets": wb.sheetnames,
        "tables": {ws.title: {k: v for k, v in ws.tables.items()} for ws in wb.worksheets if ws.tables},
        "defined_names": sorted(wb.defined_names.keys()),
        "data_validations": {ws.title: len(ws.data_validations.dataValidation)
                             for ws in wb.worksheets if ws.data_validations.dataValidation},
    }


OWN_SHEETS = {"Cover", "Start_Here", "Config", "Scoring", "Bonus", "M_Code", "Checks", "Validation", "Data_Dictionary"}


PLAN_CELLS = {("Cover", "B7"), ("Cover", "B8")}  # text copied from plan.json


def instruction_hits(path):
    """Cells that would tell the owner to clone, pull, sync, switch branch or run Python: (sheet, cell, match, text).
    Sheets this script writes are held to FORBIDDEN_INSTRUCTIONS; copied plan and BLOCKERS text to INSTRUCTION_LIKE."""
    wb = load_workbook(path)
    out = []
    for ws in wb.worksheets:
        if ws.title == "M_Code":
            continue  # M code text, not instructions
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str):
                    own = ws.title in OWN_SHEETS and (ws.title, c.coordinate) not in PLAN_CELLS
                    m = (FORBIDDEN_INSTRUCTIONS if own else INSTRUCTION_LIKE).search(c.value)
                    if m:
                        out.append((ws.title if own else ws.title + " (copied text)", c.coordinate, m.group(0), c.value))
    return out


def run_recalc(out, script, work):
    """Recalculate a COPY with LibreOffice (the candidate itself is never rewritten)."""
    work.mkdir(parents=True, exist_ok=True)
    (work / "tmp").mkdir(exist_ok=True)
    copy = work / ("recalc-" + out.name)
    shutil.copyfile(out, copy)
    env = dict(os.environ, TMPDIR=str(work / "tmp"))
    p = subprocess.run([sys.executable, script, str(copy), "120"], capture_output=True, text=True, env=env)
    try:
        res = json.loads(p.stdout[p.stdout.index("{"):])
    except Exception:
        res = {"error": "unparseable recalc output", "stdout": p.stdout[-2000:], "stderr": p.stderr[-2000:]}
    try:
        res["WorkbookFolder_evaluated"] = load_workbook(copy, data_only=True)["Config"]["B2"].value
    except Exception as e:  # pragma: no cover
        res["WorkbookFolder_evaluated"] = "unreadable: %s" % e
    res["recalculated_copy"] = str(copy)
    return res


def main():
    ap = argparse.ArgumentParser(description="Build NFL-Analysis-<version>.xlsx (paste-ready)")
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", help="default: NFL/.work/rc/NFL-Analysis-<version>.xlsx")
    ap.add_argument("--force", action="store_true", help="overwrite an existing output (never a released file)")
    ap.add_argument("--no-recalc", action="store_true")
    ap.add_argument("--recalc-script")
    ap.add_argument("--recalc-dir", help="where the recalculated copy goes (default NFL/.work/build-recalc)")
    ap.add_argument("--input-root", default=str(DEFAULT_ROOT), help="the repository root (holds BLOCKERS.csv and NFL/)")
    ap.add_argument("--forbid-file", help="extra words the personal-data scan must not find (keep the file out of git)")
    ap.add_argument("--release-date", default=dt.date.today().isoformat())
    ap.add_argument("--status", default="Released")
    ap.add_argument("--summary")
    ap.add_argument("--gates", default="G1–G5")
    ap.add_argument("--built-by", default="Orchestrator + Opus 5.5 committee (generated by build_workbook.py)")
    args = ap.parse_args()
    if not re.match(r"^\d+\.\d{3}$", args.version):
        die("--version must match ^\\d+\\.\\d{3}$ (e.g. 2.001)")
    dt.date.fromisoformat(args.release_date)
    proj = Path(args.input_root).resolve() / PROJ
    out = Path(args.out) if args.out else proj / ".work" / "rc" / ("NFL-Analysis-%s.xlsx" % args.version)
    out = out.resolve()
    if out.name != "NFL-Analysis-%s.xlsx" % args.version:
        die("output file name must be NFL-Analysis-%s.xlsx (version must match the file name)" % args.version)
    if out.exists() and not args.force:
        die("%s already exists; released files are immutable. Use --force to overwrite a non-released build."
            % out)
    recalc_script = None if args.no_recalc else find_recalc(args.recalc_script)

    wb = build(args)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    normalize_zip(out, FIXED_DT, ignore_text_numbers=("Config", CONFIG_VALUE_RANGE[0]))

    recalc = None
    if recalc_script:
        rdir = Path(args.recalc_dir).resolve() if args.recalc_dir else proj / ".work" / "build-recalc"
        recalc = run_recalc(out, recalc_script, rdir)
        print("RECALC: " + json.dumps(recalc))
        if "error" in recalc or recalc.get("status") != "success" or recalc.get("total_errors", 1) != 0:
            die("recalc did not report success with 0 errors")
    inv = inventory(out, args.version)
    words = pii_scan.load_forbidden(None, args.forbid_file)
    findings, pinv = pii_scan.scan(str(out), words)
    for f in findings:
        print("PERSONAL DATA: %(part)s | %(rule)s | %(detail)s" % f)
    if findings:
        out.unlink()
        die("personal-data scan found %d item(s); the output was deleted" % len(findings))
    print("PERSONAL-DATA SCAN: clean (%d parts, %d texts, %d extra words)" % (pinv["parts"], pinv["texts_scanned"], len(words)))
    hits = instruction_hits(out)
    for sheet, ref, word, text in hits:
        print("%s: %s!%s says %r: %s" % ("STOP" if sheet in OWN_SHEETS else "WARN", sheet, ref, word, text[:120]))
    if any(h[0] in OWN_SHEETS for h in hits):
        out.unlink()
        die("the workbook would tell the owner to clone, pull, sync, switch branch or run Python; output deleted")
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    print("SHA256: %s  %s" % (sha, out))
    print(json.dumps({"version": args.version, "output": str(out), "bytes": out.stat().st_size, "sha256": sha,
                      "recalc": recalc, "inventory": inv}, indent=1))


if __name__ == "__main__":
    main()
