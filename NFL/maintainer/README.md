Visitors can ignore this folder: it holds how the project is run.

# NFL/maintainer

Everything here is for the people who run the project. The published data, the workbook and the scoring rules are elsewhere in this repository.

## What is here

| Path | Purpose |
|---|---|
| [`BLOCKERS.csv`](BLOCKERS.csv) | Questions and actions waiting on the owner. The owner fills in the `Answer` column. |
| [`governance/`](governance/CHARTER.md) | Charter, versioning policy, decision log, memory and the committee role cards |
| [`governance/DECISIONS.md`](governance/DECISIONS.md) | The decision log |
| [`governance/MEMORY.md`](governance/MEMORY.md) | Where things stand and what a new session must know |
| [`governance/VERSIONING.md`](governance/VERSIONING.md) | How workbook versions are numbered and released |
| [`governance/committee/ROLE-CARDS.md`](governance/committee/ROLE-CARDS.md) | Rules and role cards for the committee members |
| [`plan/`](plan/README.md) | `plan.json` (the single source of the plan, requirements, RAID and roadmap), `validate_plan.py`, `render_plan_md.py` and the rendered `PLAN.md` |
| [`qa/`](qa/README.md) | QA reports and dispositions, one set per version |
| [`research/`](research/README.md) | Design notes |
| [`releases/`](releases/RELEASES.md) | The release register and the released 2.001 workbook (released files are immutable) |
| [`archive-2.x/`](archive-2.x/README.md) | The retired Power Query route (not maintained) |
| [`sport-template/`](sport-template/README.md) | Skeleton and checklist for adding a sport |

## Older paths

Older records (the decision log, the QA reports, some release notes) use the repository layout of their time. To read them, map the old path to the new one:

| Old path | New path |
|---|---|
| `00-Governance/` | `NFL/maintainer/governance/` |
| `BLOCKERS.csv` (repository root) | `NFL/maintainer/BLOCKERS.csv` |
| `CLAUDE.md` (repository root) | `.claude/CLAUDE.md` |
| `NFL/01-plan/` | `NFL/maintainer/plan/` |
| `NFL/PLAN.md` | `NFL/maintainer/plan/PLAN.md` |
| `NFL/06-qa/<report>.md` (reviews, dispositions, reports) | `NFL/maintainer/qa/<report>.md` |
| `NFL/06-qa/fixtures/`, `NFL/06-qa/evidence/`, `NFL/06-qa/README.md` | unchanged |
| `NFL/07-research/` | `NFL/maintainer/research/` |
| `NFL/08-releases/` | `NFL/maintainer/releases/` |
| `NFL/05-excel/archive-2.x/` | `NFL/maintainer/archive-2.x/` |
| `_Sport-Template/` | `NFL/maintainer/sport-template/` |

Nothing else moved: `NFL/02-config/`, `NFL/03-pipeline/`, `NFL/04-data/` and `NFL/05-excel/README.md` keep their addresses.

The session instructions are in [`/.claude/CLAUDE.md`](../../.claude/CLAUDE.md).
