#!/usr/bin/env python3
"""Render PLAN.md from 01-plan/plan.json.

01-plan/plan.json is the single source of truth for the plan (CONTRACTS.md section 10, D-010).
Edit plan.json, then run from anywhere:  python3 01-plan/render_plan_md.py
Adapted from the 1.x renderer.
"""
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent  # the sport folder, e.g. NFL/


def esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def table(rows, cols):
    out = ["| " + " | ".join(h for h, _ in cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(esc(r[k]) for _, k in cols) + " |")
    return "\n".join(out)


def status_line(roadmap):
    def pick(status, last):
        rows = [x for x in roadmap if x["status"] == status]
        if not rows:
            return None
        r = rows[-1] if last else rows[0]
        return f"{r['version']} ({r['increment']})"

    bits = [f"{name}: {value}" for name, value in (
        ("Latest released", pick("Released", True)),
        ("In progress", pick("In progress", False)),
        ("Next planned", pick("Planned", False))) if value]
    return " · ".join(bits) + "."


def counts(items, key):
    c = {}
    for x in items:
        c[x[key]] = c.get(x[key], 0) + 1
    return ", ".join(f"{k} {v}" for k, v in c.items())


def render(plan):
    m = ["# NFL-Analysis Pipeline: Plan", "",
         status_line(plan["roadmap"]), "",
         "Generated from `01-plan/plan.json` by `01-plan/render_plan_md.py`. Edit the JSON, not this file.", "",
         "## What you are trying to do", ""]
    m += ["- " + b for b in plan["what_you_are_trying_to_do"]]
    m += ["", "## Objective", "", plan["objective"], "", "## Key findings", "",
          table(plan["key_findings"], [("Finding", "finding"), ("Source", "source")]), "",
          "## Architecture", "",
          "From nflverse to the workbook's PivotTables, in order. \"Where\" says where each step runs.", "",
          table(plan["architecture"], [("Step", "step"), ("Component", "component"),
                                       ("Description", "description"), ("Where", "where")]), "",
          "## Scope", "", "### In scope", ""]
    m += ["- " + s for s in plan["scope_in"]]
    m += ["", "### Out of scope", ""] + ["- " + s for s in plan["scope_out"]]
    m += ["", "## Roadmap", ""]
    for r in plan["roadmap"]:
        m += [f"### {r['version']} {r['increment']} ({r['status']})", "",
              f"- **Scope:** {r['scope']}", f"- **Deliverables:** {r['deliverables']}",
              f"- **Acceptance criteria:** {r['acceptance_criteria']}",
              f"- **Depends on:** {r['depends_on']}", ""]
    m += ["## Requirements", "",
          f"{len(plan['requirements'])} requirements. By status: {counts(plan['requirements'], 'status')}.", "",
          table(plan["requirements"], [("ID", "id"), ("Requirement", "requirement"), ("Type", "type"),
                                       ("Priority", "priority"), ("Source", "source"),
                                       ("Version", "target_version"),
                                       ("Acceptance criteria", "acceptance_criteria"),
                                       ("Status", "status")]), "",
          "## RAID log", "",
          f"{len(plan['raid'])} items. By status: {counts(plan['raid'], 'status')}.", "",
          table(plan["raid"], [("ID", "id"), ("Type", "type"), ("Title", "title"), ("Detail", "detail"),
                               ("Rating", "rating"), ("Response", "response"), ("Owner", "owner"),
                               ("Version", "target_version"), ("Status", "status")]), "",
          "## Controls", "",
          table(plan["controls"], [("ID", "id"), ("Control", "control"), ("Method", "method"),
                                   ("Expected result", "expected_result"),
                                   ("Version", "target_version"), ("Status", "status")]), "",
          "## Glossary", "",
          table(plan["glossary"], [("Term", "term"), ("Definition", "definition")]), ""]
    return "\n".join(m)


if __name__ == "__main__":
    plan = json.loads((PROJECT / "01-plan" / "plan.json").read_text(encoding="utf-8"))
    (PROJECT / "PLAN.md").write_text(render(plan), encoding="utf-8")
    print({k: len(v) for k, v in plan.items() if isinstance(v, list)})
