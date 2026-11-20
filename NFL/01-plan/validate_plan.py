#!/usr/bin/env python3
"""Validate NFL/01-plan/plan.json (control C-26).

Checks: shape (CONTRACTS.md §10), allowed values, ID formats, unique IDs, IDs stable against a baseline copy of the
plan (none removed, new numbers above the baseline's highest, so none reused), target versions, sources, cited
decisions, BLOCKERS.csv coverage by Status, cross-references, and a public-safety scan of the plan text.

The baseline is the last committed plan (`git show HEAD:NFL/01-plan/plan.json`) unless --baseline names a file.
When neither is available (for example before the first commit) the stability check compares the plan with itself.

Run from anywhere:  python3 NFL/01-plan/validate_plan.py [--baseline PATH]
"""
import argparse, csv, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NFL = HERE.parent              # <repo>/NFL
ROOT = NFL.parent              # repository root
ap = argparse.ArgumentParser()
ap.add_argument("--baseline", default=None)
args = ap.parse_args()

plan = json.loads((NFL / "01-plan/plan.json").read_text(encoding="utf-8"))
if args.baseline:
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
else:
    shown = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:NFL/01-plan/plan.json"], capture_output=True)
    base = json.loads(shown.stdout.decode("utf-8")) if shown.returncode == 0 else plan
with open(ROOT / "BLOCKERS.csv", encoding="utf-8-sig", newline="") as f:
    blockers = {r["Question_ID"]: r for r in csv.DictReader(f)}
decisions = set(re.findall(r"\| (D-\d{3}) \|", (ROOT / "00-Governance/DECISIONS.md").read_text(encoding="utf-8")))

errors = []
def err(msg): errors.append(msg)

KEYS = ["objective", "what_you_are_trying_to_do", "key_findings", "architecture", "scope_in", "scope_out",
        "roadmap", "requirements", "raid", "controls", "glossary"]
if list(plan) != KEYS:
    err(f"top-level keys {list(plan)} != {KEYS}")

FIELDS = {
    "key_findings": ["finding", "source"],
    "architecture": ["step", "component", "description", "where"],
    "roadmap": ["version", "increment", "scope", "deliverables", "acceptance_criteria", "depends_on", "status"],
    "requirements": ["id", "requirement", "type", "priority", "source", "target_version", "acceptance_criteria", "status"],
    "raid": ["id", "type", "title", "detail", "rating", "response", "owner", "target_version", "status"],
    "controls": ["id", "control", "method", "expected_result", "target_version", "status"],
    "glossary": ["term", "definition"],
}
for sec, flds in FIELDS.items():
    for i, x in enumerate(plan[sec]):
        if list(x) != flds:
            err(f"{sec}[{i}] keys {list(x)} != {flds}")
        for k in flds:
            v = x.get(k)
            if v is None or (isinstance(v, str) and not v.strip()):
                err(f"{sec}[{i}].{k} empty")
for sec in ("what_you_are_trying_to_do", "scope_in", "scope_out"):
    if not plan[sec] or not all(isinstance(s, str) and s.strip() for s in plan[sec]):
        err(f"{sec} must be a non-empty list of strings")

ALLOWED = {
    ("architecture", "where"): {"nflverse (GitHub Releases)", "Power Query", "Excel sheet", "Data Model", "PivotTable",
                                "Python pipeline", "GitHub Actions", "Published CSV"},
    ("roadmap", "status"): {"In progress", "Planned", "Released", "Withdrawn"},
    ("requirements", "type"): {"Functional", "Non-functional", "Constraint"},
    ("requirements", "priority"): {"Must", "Should", "Could", "Won't (this release)"},
    ("requirements", "status"): {"Planned", "In progress", "Done", "Retired"},
    ("raid", "type"): {"Risk", "Assumption", "Issue", "Decision", "Question"},
    ("raid", "rating"): {"High", "Medium", "Low"},
    ("raid", "status"): {"Open", "Closed", "Accepted"},
    ("raid", "owner"): {"Orchestrator", "User", "A1 Plan and Requirements Analyst", "B1 Pipeline Engineer",
                        "B2 Gates and Test Engineer", "C1 Actions Engineer", "D1 Power Query Engineer",
                        "E1 Workbook Builder", "E2 Mashup Engineer", "Q1 QA Reviewer"},
    ("controls", "status"): {"Designed", "Implemented", "Passing"},
}
for (sec, k), allowed in ALLOWED.items():
    for x in plan[sec]:
        if x[k] not in allowed:
            err(f"{sec} {x.get('id', x.get('step', x.get('version')))}: {k}={x[k]!r} not allowed")

# Formats and uniqueness
steps = [a["step"] for a in plan["architecture"]]
if steps != list(range(1, len(steps) + 1)) or not all(isinstance(s, int) for s in steps):
    err(f"architecture steps not 1..n integers: {steps}")
versions = [r["version"] for r in plan["roadmap"]]
for v in versions:
    if not re.fullmatch(r"\d\.\d{3}", v):
        err(f"roadmap version format {v}")
if versions != sorted(versions, key=lambda v: tuple(map(int, v.split(".")))):
    err("roadmap not in version order")
idre = {"Functional": r"FR-\d{2}", "Non-functional": r"NFR-\d{2}", "Constraint": r"CON-\d{2}"}
for r in plan["requirements"]:
    if not re.fullmatch(idre[r["type"]], r["id"]):
        err(f"requirement id {r['id']} does not match type {r['type']}")
for sec, pat in (("raid", r"RAID-\d{2}"), ("controls", r"C-\d{2}")):
    for x in plan[sec]:
        if not re.fullmatch(pat, x["id"]):
            err(f"{sec} id format {x['id']}")
for sec, key in (("requirements", "id"), ("raid", "id"), ("controls", "id"), ("roadmap", "version"),
                 ("glossary", "term")):
    vals = [x[key] for x in plan[sec]]
    dup = {v for v in vals if vals.count(v) > 1}
    if dup:
        err(f"{sec} duplicate {key}: {sorted(dup)}")

# IDs stable against the baseline: nothing removed; new IDs numbered above the baseline's highest of their prefix
def prefix_num(i):
    m = re.fullmatch(r"([A-Z]+)-(\d+)", i)
    return m.group(1), int(m.group(2))
for sec, key in (("requirements", "id"), ("raid", "id"), ("controls", "id"), ("roadmap", "version")):
    old = [x[key] for x in base[sec]]
    new = [x[key] for x in plan[sec]]
    for i in old:
        if i not in new:
            err(f"{sec}: baseline ID {i} was removed")
    if key == "id":
        top = {}
        for i in old:
            p, n = prefix_num(i)
            top[p] = max(top.get(p, 0), n)
        for i in new:
            if i not in old:
                p, n = prefix_num(i)
                if n <= top.get(p, 0):
                    err(f"{sec}: new ID {i} is not above the baseline's highest {p}-{top.get(p, 0):02d} (possible reuse)")
for x in plan["requirements"]:
    if x["status"] == "Retired" and not x["acceptance_criteria"].startswith("Retired "):
        err(f"{x['id']}: a Retired requirement must say when and why ('Retired YYYY-MM-DD: ...')")

# At most one In progress roadmap item, and it comes after the latest Released one
inprog = [r["version"] for r in plan["roadmap"] if r["status"] == "In progress"]
if len(inprog) > 1:
    err(f"more than one In progress version: {inprog}")
released = [r["version"] for r in plan["roadmap"] if r["status"] == "Released"]
if inprog and released and inprog[0] <= released[-1]:
    err(f"In progress version {inprog[0]} is not after the latest Released version {released[-1]}")

# Target versions exist; open items do not target a released or withdrawn version
vstat = {r["version"]: r["status"] for r in plan["roadmap"]}
DONE = {"Done", "Retired", "Closed", "Accepted"}
for sec in ("requirements", "raid", "controls"):
    for x in plan[sec]:
        tv = x["target_version"]
        if tv not in vstat:
            err(f"{sec} {x['id']}: target_version {tv} not in roadmap")
        elif x["status"] not in DONE | {"Passing", "Implemented"} and vstat[tv] in ("Released", "Withdrawn"):
            err(f"{sec} {x['id']}: status {x['status']} but targets {vstat[tv]} version {tv}")
        elif sec == "controls" and x["status"] == "Designed" and vstat[tv] in ("Released", "Withdrawn"):
            err(f"controls {x['id']}: Designed but targets {vstat[tv]} version {tv}")

# Sources trace to something recognisable
SRC = [r"Transcript L\d+(-\d+)?(, L\d+(-\d+)?)*( \(.*\))?", r"Verified live \d{4}-\d{2}-\d{2}( \([A-Z]\d\))?",
       r"Orchestrator review", r"User instruction( \d{4}-\d{2}-\d{2})?", r"D-\d{3}",
       r"CONTRACTS\.md §\d+(\.\d+)?(, §\d+(\.\d+)?)*( \(.*\))?", r"BLOCKERS\.csv Q-\d{3}",
       r"(00-Governance|01-plan|02-config|03-pipeline|04-data|05-excel|06-qa|07-research|08-releases)/\S+.*",
       r"CLAUDE\.md §.*", r"Prior-art review rounds? \d(-\d)? \(private, D-034\)( .*)?",
       r".+ \(private, D-034\)"]
def check_source(where, s):
    for part in s.split("; "):
        if not any(re.fullmatch(p, part) for p in SRC):
            err(f"{where}: unrecognised source part {part!r}")
for i, k in enumerate(plan["key_findings"]):
    check_source(f"key_findings[{i}]", k["source"])
for r in plan["requirements"]:
    check_source(r["id"], r["source"])

# Decision IDs cited anywhere must exist
text = json.dumps(plan, ensure_ascii=False)
cited_d = set(re.findall(r"D-\d{3}", text))
for d in sorted(cited_d - decisions):
    err(f"cited decision {d} not in DECISIONS.md")

# Every Q-ID cited anywhere exists in BLOCKERS.csv
cited_q = set(re.findall(r"Q-\d{3}", text))
for q in sorted(cited_q - set(blockers)):
    err(f"cited {q} not in BLOCKERS.csv")

# BLOCKERS.csv coverage by Status. A RAID Question item covers the Q-IDs named in its title.
OPEN_STATUSES = {"Open", "Still open"}
for q, row in blockers.items():
    if row["Status"] not in OPEN_STATUSES | {"Answered"}:
        err(f"BLOCKERS {q}: unknown Status {row['Status']!r}")
questions = [x for x in plan["raid"] if x["type"] == "Question"]
for x in questions:
    if x["status"] not in ("Open", "Closed"):
        err(f"{x['id']}: a Question is Open or Closed, not {x['status']}")
    if x["status"] == "Closed" and not x["response"].startswith(("Outcome:", "Closed")):
        err(f"{x['id']}: a closed Question must state its outcome ('Outcome: ...')")
covers = {x["id"]: set(re.findall(r"Q-\d{3}", x["title"])) for x in questions}
for q, row in blockers.items():
    items = [x for x in questions if q in covers[x["id"]]]
    if not items:
        err(f"BLOCKERS {q} ({row['Status']}): no RAID Question names it in its title")
        continue
    if row["Status"] in OPEN_STATUSES and not any(x["status"] == "Open" for x in items):
        err(f"BLOCKERS {q} is {row['Status']} but its RAID item(s) {[x['id'] for x in items]} are not Open")
    if row["Status"] == "Answered":
        if not any(x["status"] == "Closed" for x in items):
            err(f"BLOCKERS {q} is Answered but no RAID item naming it is Closed")
        if any(x["status"] == "Open" for x in items):
            err(f"BLOCKERS {q} is Answered but RAID item(s) naming it are still Open")
for x in questions:
    if x["status"] == "Open" and not covers[x["id"]]:
        # Questions asked before BLOCKERS.csv existed are all closed; an open one must name its Q-ID
        err(f"{x['id']}: open Question names no BLOCKERS Question_ID in its title")

# Cross-references (RAID-nn, C-nn, FR-nn, NFR-nn, CON-nn) resolve
ids = {x["id"] for s in ("requirements", "raid", "controls") for x in plan[s]}
for ref in sorted(set(re.findall(r"\b(?:RAID|FR|NFR|CON)-\d{2}\b|\bC-\d{2}\b", text))):
    if ref not in ids:
        err(f"cross-reference {ref} does not exist")

# Public safety: no private-repository paths, local paths, emails or personal descriptions in the plan
FORBIDDEN = [r"Personal/", r"20-Projects", r"30-Deliverables", r"90-Archive", r"10-Assets", r"\bresearch/",
             r"[A-Za-z]:\\\\", r"\\\\Users\\\\", r"/home/", r"OneDrive -", r"[\w.+-]+@[\w-]+\.[\w.]+",
             r"wes-blue/(?!sports-analysis)[\w.-]+", r"pull request #\d+", r"(?i)\bemployer\b", r"(?i)\bjob title\b"]
for pat in FORBIDDEN:
    for m in re.finditer(pat, text):
        err(f"public-safety: {pat!r} matches {text[max(0, m.start()-40):m.end()+40]!r}")

print("Counts:")
for k in KEYS[1:]:
    print(f"  {k}: {len(plan[k])}")
def tally(sec, key):
    c = {}
    for x in plan[sec]:
        c[x[key]] = c.get(x[key], 0) + 1
    return c
print("  requirements by type:", tally("requirements", "type"))
print("  requirements by status:", tally("requirements", "status"))
print("  raid by type:", tally("raid", "type"))
print("  raid by status:", tally("raid", "status"))
print("  controls by status:", tally("controls", "status"))
print("  roadmap by status:", tally("roadmap", "status"))
print(f"  baseline: {len(base['requirements'])} requirements, {len(base['raid'])} RAID, {len(base['controls'])} controls, "
      f"{len(base['roadmap'])} roadmap versions")
print(f"  Q-IDs cited: {len(cited_q)} of {len(blockers)} in BLOCKERS.csv; decisions cited: {len(cited_d)}")
if errors:
    print(f"\nFAIL: {len(errors)} error(s)")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("\nPASS: 0 errors")
