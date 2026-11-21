# Interface Contracts: <Sport>

List every file format and command behaviour that one part of the project hands to another: path, owner, consumer, columns or keys, allowed values. Changing a contract needs the orchestrator's approval. `NFL/CONTRACTS.md` is the model; keep its section numbers so that briefs and plans can cite them the same way:

0. Architecture in one picture
1. Config files (`02-config/`)
2. Upstream sources, with their licences
3. Derived metrics
4. Scoring semantics
5. Published data (`04-data/`), including the public address and the data contract version
6. Gates
7. Command line (`03-pipeline/`)
8. GitHub Actions (`/.github/workflows/<sport>-pipeline-*.yml`)
9. (NFL only: the retired Power Query workbook. A new sport skips this section.)
10. Plan content (`01-plan/plan.json`)
11. Blockers for the owner (`/BLOCKERS.csv`)
12. Releases (`08-releases/`)
13. The generated workbook (the `export` command, sheets, cell rules, publication as a release asset)
