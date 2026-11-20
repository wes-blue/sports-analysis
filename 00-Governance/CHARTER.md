# Committee Charter

## Purpose

`wes-blue/sports-analysis` is a public repository of fantasy-sports analysis, one top-level folder per sport, delivered in small, verified increments (`CLAUDE.md` §1). Each sport has the same three parts:

1. A **pipeline** that downloads public statistics, derives what the scoring needs, scores every league in the sport's config files, checks the result with gates, and publishes plain CSV files to `<Sport>/04-data/` only when every blocking gate passes.
2. **GitHub Actions workflows** (`.github/workflows/<sport>-pipeline-*.yml`) that run the pipeline on GitHub on a schedule and when the config changes. GitHub is the only runtime: nothing routine depends on the owner's computer being on.
3. An **Excel workbook with Power Query** that reads the published CSV files from their public web address and lets the owner customize fantasy points per league.

**NFL** (`NFL/`) is the only sport so far. Its 1.x workbooks were built in the owner's private repository; the project moved here on 2026-11-20 and continues as the 2.x line (decisions D-033 and D-035). A new sport starts from `_Sport-Template/`.

Every increment is planned, verified against live sources and traceable to a requirement in the sport's `01-plan/plan.json`.

## Roles

| Role | Runs on | Accountable for |
|---|---|---|
| Orchestrator | The session model (`CLAUDE.md` §3) | Plan direction, contracts, briefs, integration, decisions, release, memory, `BLOCKERS.csv` |
| A1 Plan and Requirements Analyst | One tier below the orchestrator, like every member | `<Sport>/01-plan/plan.json` and `PLAN.md`: requirements, roadmap, RAID, controls |
| B1 Pipeline Engineer | Member tier | Pipeline core: ingest, derived metrics, scoring, publishing |
| B2 Gates and Test Engineer | Member tier | Gates, check files, tests, fixtures, evidence, the full data run |
| C1 Actions Engineer | Member tier | Scheduling logic, workflow files and the owner's automation guide |
| D1 Power Query Engineer | Member tier | Power Query modules and the Excel runbook |
| E1 Workbook Builder | Member tier | Workbook generator and build |
| E2 Mashup Engineer | Member tier | Experimental workbook with the queries installed |
| Q1 QA Reviewer | Member tier | Independent review against requirements, contracts and quality gates |
| Product Owner | `wes-blue` | Priorities, approvals, decisions marked "User", merging to `main`, actions in Excel and on GitHub, answers in `BLOCKERS.csv` |

Role cards: `committee/ROLE-CARDS.md`. The committee is shared by all sports; a brief names the sport and the paths a member may write.

## RACI

R = does the work, A = accountable, C = consulted, I = informed.

| Activity | Orch | A1 | B1 | B2 | C1 | D1 | E1 | E2 | Q1 | Owner |
|---|---|---|---|---|---|---|---|---|---|---|
| Plan, requirements, roadmap | A | R | C | C | C | C | I | I | C | C |
| Interface contracts | R/A | C | C | C | C | C | C | C | C | I |
| Pipeline code | A | I | R | C | C | I | I | I | C | I |
| Gates, tests, data run | A | I | C | R | I | I | I | I | C | I |
| Workflows and automation guide | A | I | C | I | R | I | I | I | C | C (merges to `main`) |
| Power Query | A | I | I | I | I | R | C | C | C | C (tests in Excel) |
| Workbook build | A | C | I | I | I | C | R | C | C | I |
| Experimental workbook | A | I | I | I | I | C | C | R | C | C (opens it in Excel) |
| QA review | A | I | I | I | I | I | I | I | R | I |
| Public-safety check before publishing | R/A | C | I | I | I | I | C | C | R | I |
| Release, versioning, blockers | R/A | I | I | C | I | I | C | I | C | C |
| Decisions | R | C | C | C | C | C | C | C | C | A (when flagged "User") |

## Operating rules

1. The scope and privacy rules in `CLAUDE.md` §2 apply to every member. Everything committed here is public.
2. Members write only to the paths named in their brief and follow the sport's `CONTRACTS.md`.
3. No fabricated facts. Every number traces to a source or is labelled `ASSUMPTION` or `UNVERIFIED`. Anything not yet run on GitHub or in Excel is labelled as such.
4. Members do not commit, push, publish or release. The orchestrator commits and pushes to a branch with a pull request; the owner merges to `main` (`CLAUDE.md` §6).
5. **Blockers never stop the work.** A member takes the best default, continues, and reports the blocker. The orchestrator records it in `BLOCKERS.csv` for the owner.
6. When members disagree, the orchestrator decides and logs it in `DECISIONS.md`. Anything that changes scope or owner-facing behaviour goes to the owner.
7. One fact lives in one place. Where two documents would say the same thing, one says it and the other points to it.

## Quality gates (a release must pass all five)

| Gate | Check | Owner |
|---|---|---|
| G1 Source | Data addresses and column names verified against the live upstream files | B1, then Q1 |
| G2 Code | Pipeline tests pass; every data gate in the sport's `CONTRACTS.md` §6 is implemented; workflow files pass their tests; Power Query parses cleanly (Microsoft `@microsoft/powerquery-parser`). Anything not yet run in Excel or on GitHub is labelled. | B2, C1 and D1, then Q1 |
| G3 Workbook | File opens; `recalc.py` reports zero formula errors; tables and defined names are valid | E1, then Q1 |
| G4 Release | Version matches across filename, Cover, file properties, Version_Log and `RELEASES.md`; `MEMORY.md` updated; nothing to be published contains personal details, local paths or secrets (`CLAUDE.md` §2), including workbook file properties | Orchestrator, with Q1's scan |
| G5 Data | The published data passes the sport's read-only check (for NFL: `python -m nflpipe check`); no blocking gate fails | B2, then Q1 |
