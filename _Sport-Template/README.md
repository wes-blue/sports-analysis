# Sport Template

The empty skeleton for adding a sport to `wes-blue/sports-analysis`, and the checklist for wiring it up. Every step below is drawn from what `NFL/` has; open the NFL file named in each step and follow it.

Below, `<Sport>` is the new folder's name (for example `NBA`) and `<sport>` the same in lower case (`nba`).

## Before you start

- Adding a sport changes the repository's scope, so the owner must have asked for it. Record the decision in `00-Governance/DECISIONS.md`.
- Check the data source's licence first and read it from the source, not from memory. The published data is public, so the licence must allow redistribution and you must be able to meet its attribution terms.
- Everything committed here is public (`CLAUDE.md` §2).

## Steps

1. **Copy the skeleton.** Copy this folder to `<Sport>/` at the repository root. Keep the numbered folder names: `CLAUDE.md` §5, the root `.gitattributes` and the shared documents assume them.

2. **Write the contract first.** Fill in `<Sport>/CONTRACTS.md` before any build work: config files, upstream sources and their licence, derived metrics, scoring, published files and their public address, gates, command line, workflows, Power Query, plan, blockers, releases. Use the section numbers of `NFL/CONTRACTS.md`.

3. **Write the plan.** Create `<Sport>/01-plan/plan.json` (shape: `NFL/CONTRACTS.md` §10), copy `NFL/01-plan/render_plan_md.py`, change its title line, and render `<Sport>/PLAN.md`.

4. **Create the config files** in `<Sport>/02-config/`, with a README written for an owner who edits them on GitHub (model: `NFL/02-config/README.md`).

5. **Build the pipeline** in `<Sport>/03-pipeline/` with its tests and `AUTOMATION.md`, the owner's guide to the workflows (model: `NFL/03-pipeline/`). It writes only to `<Sport>/04-data/` and publishes only when every blocking gate passes.

6. **Add the workflows** at the repository root, in `.github/workflows/`, named **`<sport>-pipeline-*.yml`**. Start from the four NFL files and change every NFL-specific value:

   | NFL file | New file |
   |---|---|
   | `nfl-pipeline-weekly.yml` | `<sport>-pipeline-weekly.yml` |
   | `nfl-pipeline-monthly.yml` | `<sport>-pipeline-monthly.yml` |
   | `nfl-pipeline-watchdog.yml` | `<sport>-pipeline-watchdog.yml` |
   | `nfl-pipeline-ci.yml` | `<sport>-pipeline-ci.yml` |

   Inside each: the workflow `name`; the working directory (`<Sport>/03-pipeline`); every path filter and the committed data path (`<Sport>/02-config/**`, `<Sport>/04-data`, `<Sport>/06-qa/fixtures/**`); the alert labels (`<sport>-pipeline-alert-weekly`, `-monthly`, `-watchdog`); the concurrency group (`<sport>-pipeline-publish`, so that two sports never block each other); the link to the guide; the schedule (cron lines and months) for that sport's season. Keep the security rules of `NFL/CONTRACTS.md` §8: `pull_request` only, least privilege, actions pinned by commit SHA, inputs through `env:`, no secrets. GitHub runs scheduled workflows only from `main`.

7. **Check `.gitattributes`** at the repository root. Its patterns (`*/04-data/** -text`, `*/06-qa/fixtures/** -text`, `*/02-config/*.csv -text`) already cover any sport folder that keeps the numbered folder names; add a pattern only if the sport publishes or hashes files elsewhere. Without them, a Windows clone changes line endings and every published file's SHA-256 check fails.

8. **Build the workbook** in `<Sport>/05-excel/`, named `<SPORT>-Analysis-<version>.xlsx`, reading `<Sport>/04-data/` from `https://raw.githubusercontent.com/wes-blue/sports-analysis/main/<Sport>/04-data/` by default. Versioning for a new sport (its own name, its own version line from 1.001): `00-Governance/VERSIONING.md`.

9. **Write the sport's READMEs**: `<Sport>/README.md` (model: `NFL/README.md`), `<Sport>/04-data/README.md` with the address pattern and the data attribution (model: `NFL/04-data/README.md`), and `<Sport>/08-releases/RELEASES.md` in place of the placeholder README there.

10. **Wire it into the shared files** (the orchestrator does this):
    - the root `README.md`: add a row to the **Sports** table with the same five columns as the NFL row: the sport, a link to `<Sport>/README.md`, what it covers, the workbook name (`<SPORT>-Analysis-<major>.xxx`) and its status with a link to its `RELEASES.md`;
    - `DATA-LICENSE.md`: add a section with the new source's attribution and what this repository changes;
    - `CLAUDE.md` §5 folder map, if anything differs from NFL;
    - `00-Governance/MEMORY.md`: the sport's status and next step;
    - `BLOCKERS.csv`: questions for the owner, with a `Question_ID` that continues the existing numbering.

## Folders

| Folder | Holds | Rule |
|---|---|---|
| `01-plan/` | `plan.json`: objective, scope, roadmap, requirements, RAID, controls, glossary | The single source of the plan. `PLAN.md` is rendered from it. |
| `02-config/` | Inputs the owner edits (CSV) | One fact lives in one file. A change on `main` starts the pipeline. |
| `03-pipeline/` | Code, tests and `AUTOMATION.md` | Runs from source; no hand-edited outputs. |
| `04-data/` | Outputs the pipeline publishes | Never edited by hand. Public. |
| `05-excel/` | The workbook, its Power Query and its generator | The working copy the owner opens. |
| `06-qa/` | QA reports, dispositions, evidence, test fixtures | Every finding gets a disposition. |
| `07-research/` | Design notes and investigations | Evidence, with sources. |
| `08-releases/` | `RELEASES.md` and released workbooks | Released files are immutable. |
| `.work/` | Scratch space | Ignored by git. Create it when needed. |

## Files at the top of a sport folder

| File | Purpose |
|---|---|
| `README.md` | What the sport's project is, how its parts connect, where to start |
| `PLAN.md` | The plan, rendered from `01-plan/plan.json` |
| `CONTRACTS.md` | The file formats and command behaviours that the parts hand to each other |

Questions and actions for the owner go in the shared `BLOCKERS.csv` at the repository root, not in the sport folder.
