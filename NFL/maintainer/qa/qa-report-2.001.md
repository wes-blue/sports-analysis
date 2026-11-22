# QA report: NFL-Analysis 2.001 (first release in `wes-blue/sports-analysis`)

Reviewer: Q1 QA Reviewer (independent of every builder). Date: 2026-11-20.
Scope: everything `git add -A` would commit from branch `agents/pensive-noether-dxfoz6` (177 files), the two workbook candidates in `NFL/.work/rc/`, the four workflows, the published data and every owner-facing document.
Method: re-derived, not re-read. My scripts are in `NFL/.work/q3/` (git-ignored). Personal-data findings are described by location and kind only.

## Verdicts

**Publish verdict: SAFE TO PUSH.** No personal data, local path, secret, token or private-repository content was found in any file that would be committed or inside either workbook (every zip part, the Power Query package, its metadata and the Data Model, in ASCII and UTF-16 at both byte alignments). Fix QA-M1 first anyway: it is one line, and without it the pull request's first CI run is red.

**Release verdict: NOT READY. It becomes READY once QA-M1 is fixed** and the orchestrator completes the placeholders in `RELEASES.md` and `MEMORY.md`.

| Gate | Verdict | Basis |
|---|---|---|
| G1 Source | PASS | Upstream paths resolve. The play-by-play columns the new metric uses exist in the 2026 file. The pipeline rebuilt all 10 seasons from the cache, and the workflow simulation re-downloaded with `--force` |
| G2 Code | **FAIL (QA-M1)** | 377/377 tests pass on Python 3.13, but 1 fails on 3.11, which the CI matrix runs. Every §6 gate is implemented. actionlint is clean. All 15 queries pass Microsoft's M parser and the lint |
| G3 Workbook | PASS | LibreOffice recalculation: paste-ready 262 formulas, 0 errors; experimental 267 formulas, 0 errors. Tables and defined names are valid. **Neither file has been opened in Excel** |
| G4 Release | PASS, pending the orchestrator | Version strings agree in each file (filename, Cover `WorkbookVersion`, Title, Version, Version_Log). The personal-data scan is clean. `RELEASES.md` 2.001 row and `MEMORY.md` status are still placeholders |
| G5 Data | PASS | `check` exit 0 (10 checks). `run --seasons all` on a copy gives SKIP with byte-identical output. Independent rescoring: 0 mismatches |

**Counts:** Critical 0, Major 1, Minor 12.

## Findings

### Major

**QA-M1: the CI test job fails on Python 3.11, so the pull request and the merge commit get a red cross**
- *Where:* `NFL/03-pipeline/tests/test_qa_1006.py::test_m02_float_sum_on_a_half_rounds_away_from_zero`, run by `.github/workflows/nfl-pipeline-ci.yml` (matrix `["3.11", "3.13"]`).
- *What I did:* ran the suite with the pinned `requirements-dev.txt` under Python 3.11.18, 3.12 and 3.13.
- *What happened:* 376 passed and 1 failed on 3.11. The test asserts `sum([13*0.1, 2*0.1, -2.0]) == -0.49999999999999994`. Python 3.12 changed how `sum()` adds floats, so 3.11 returns `-0.5` and 3.12/3.13 return `-0.49999999999999994`. The pipeline's output is not affected, because scores are rounded to 9 decimals first. Only this assertion depends on the Python version.
- *Consequence:* `nfl-pipeline-ci / pytest (3.11)` turns red when the pull request is opened and again on the merge commit. GitHub emails a failure. `AUTOMATION.md` §2 step 5 tells the owner "The nfl-pipeline-ci run should have a green tick". An owner who follows instructions literally will stop or report a failure on day one.
- *Should:* the CI job passes on every Python version in the matrix, which is the contract's minimum (3.11) and the newest.
- *Fix:* delete that one assertion line, or build the float with an explicit left-to-right addition (`functools.reduce(operator.add, …)`), which behaves the same on every version. Keep the two `score_row` assertions. Re-run the suite on 3.11 before pushing.

### Minor

**QA-m1: the contract names the wrong file for the ESPN D/ST stat fixture.** `NFL/CONTRACTS.md` §5.5 says `06-qa/fixtures/espn_dst_game_log.csv`, but the file and the code (`gates.py` `ESPN_DST_STATS`) use `06-qa/fixtures/espn_dst_stats.csv`. The fixture table in `NFL/06-qa/README.md` leaves that file out altogether. *Fix:* correct the name in §5.5 and add a row for it to the fixture table in `06-qa/README.md`.

**QA-m2: the contract's two-point rule is ambiguous for a blocked extra point returned by the defense.**
- *What I did:* rebuilt `dst_points_allowed_excl_def` from play-by-play.
- *What happened:* nflverse flags two plays in ten seasons as `defensive_two_point_conv = 1` even though they are `extra_point` (kick) plays: 2025 week 4 GB at DAL and 2026 week 7 TB at CAR, both blocked extra points returned for 2. Contract §3 says both "2 for a two-point try returned by the defense" and "Kick and punt plays never count". The code follows the second rule and does not subtract them, which is defensible. Both games sit in the same points-allowed band either way (37 vs 35, and 40 vs 38, both in 35–45), so no published score changes today.
- *Fix:* name this case in §3 and D-038 as an assumption, and include it in Q-019's list of open cases.

**QA-m3: assumptions are stated as facts in the metric description.** The `Description` of `dst_points_allowed_excl_def` in `NFL/02-config/scoring_weights.csv` says "special-teams TDs and the extra point after a defensive TD still count". That text flows into `04-data/dictionary.csv` and the paste-ready workbook's Data_Dictionary. The contract and D-038 correctly mark these cases as unproven, but the description does not. *Fix:* append "(assumption until Q-019 is answered)". Note that this edits a config file, so after the merge it starts a pipeline run.

**QA-m4: two documents claim the 1.006 QA records were copied here, but they were not.** `NFL/08-releases/RELEASES.md` says "The independent QA records of 1.006 were copied here and are in ../06-qa/". `00-Governance/MEMORY.md` says "Its QA records are in `NFL/06-qa/`". `NFL/06-qa/README.md` correctly says they stayed in the private repository, and no such file is in `06-qa/`. *Fix:* reword both to match `06-qa/README.md`.

**QA-m5: the owner is pointed at the wrong question for reporting the experimental test.** Q-011 is Answered, and Q-020 is now where the owner reports how the experimental workbook went. Three places still point at Q-011: `NFL/05-excel/README.md` ("how the experimental workbook went (Q-011)"), `NFL/05-excel/experimental/README.md` §7 ("in `BLOCKERS.csv` (Q-011)"), and `MEMORY.md`'s "Waiting on the owner" table. That table also omits Q-019, Q-020, Q-021 and Q-022. An owner who follows these pages writes the answer into an already-answered row. *Fix:* replace those Q-011 references with Q-020 and refresh the table.

**QA-m6: Q-020 overstates the fallback.** `BLOCKERS.csv` Q-020 `Default_Used_Meanwhile` calls the paste-ready workbook "the proven route and the fallback". No pipeline-fed workbook (1.006 or 2.001) has run in Excel, and `MEMORY.md` says so. *Fix:* "the paste-ready workbook (adds the same queries by hand) is the fallback".

**QA-m7: wrong section number in the paste-ready workbook.** The Checks sheet (row 3) says "Start_Here section 5 explains each check" and the Cover legend says "FAIL / MISSING: Red: act (Start_Here, section 5)". Checks are explained in section 6; section 5 is "Each week". *Fix:* change both to section 6 in `build_workbook.py`.

**QA-m8: misleading leftovers in the experimental workbook.**
- After recalculation, the Scoring sheet's `Metric_Check` shows `NOT IN DATASET` for `dst_points_allowed_excl_def`, because it looks the metric up in the 1.x nflverse-column snapshot (`tblDataDictionary`), where a derived metric can never appear.
- Version_Log jumps from 1.005 to 2.001-experimental with no 1.006 row.

*Fix:* make the check treat `dst_*` metrics as derived, or blank it for them, and add the 1.006 row. Alternatively, list both under "Known differences".

**QA-m9: the experimental build re-compresses the Data Model part.** `xl/model/item.data` is stored uncompressed in the Excel-saved base, as Excel writes it. The build writes it deflated. This contradicts the build script's own comment ("same part order and compression as the base"), and the README does not mention it. Excel's package reader should accept it (UNVERIFIED), but it is a needless change to the one part most likely to break. *Fix:* write `xl/model/item.data` with `ZIP_STORED`.

**QA-m10: residual candid or private material, low sensitivity (D-034).**
- `00-Governance/DECISIONS.md` D-011 makes a short critical remark about a named third-party project ("needs R … and maps an outdated column name").
- The experimental workbook's 1.x Plan snapshot repeats that remark.
- Its 1.x Plan, Requirements and RAID snapshots paraphrase the owner's private search transcript, with line references and quotations.

None of this identifies the owner. *Fix:* neutral wording in D-011, and blank or replace the snapshot text in the experimental build. Or ask the owner explicitly in Q-018.

**QA-m11: the workbook's attribution has no link to the licence.** The Cover (experimental) and Start_Here (paste-ready) say "licensed CC BY 4.0. Details … in DATA-LICENSE.md". CC BY 4.0 §3(a)(1)(C) asks for the licence's URI, and a refreshed workbook that is shared contains the data. *Fix:* add `https://creativecommons.org/licenses/by/4.0/` and the repository URL to that sentence in both build scripts.

**QA-m12: a session link would become permanent public history.** The orchestrator's commit and pull-request attribution would end with a `claude.ai/code/session_…` URL. Other people cannot open it, but it would stay in the public history of this repository for good. No file contains one today. *Fix:* the orchestrator and owner decide on purpose: keep it, or leave it out per the owner's instructions.

## Verified independently

**Personal data and safety**
- I derived 16 candidate strings from the private base workbook's author field and its saved-folder path: name variants, the Windows user name, the machine name found inside its Data Model, its 8.3 short form and the path's folder names.
- They were searched in all 177 files to be committed, and in every part of both workbooks: decoded DataMashup package, permissions, metadata and its inner zip, and `item.data` at both byte alignments.
- **Zero personal hits.** The remaining hits were common project words, or NFL players who share the first name.
- In the experimental Data Model, the 797 user-folder occurrences and the 1 machine-name occurrence were confirmed overwritten by same-length placeholders. 6,388 bytes differ from the base and the size is equal. `x15ac:absPath` was removed and `lastModifiedBy` is neutral.
- No emails apart from noreply and test addresses, no tokens, no internal hosts, no session links in files.
- Git identity is `Claude <noreply@anthropic.com>`. `origin/main` holds only `LICENSE` (MIT, "wes-blue").
- `.gitignore` excludes `**/.work/` (and so the workbook candidates and caches), `__pycache__`, `.pytest_cache` and Excel lock files. Running pytest left no stray file.
- `.gitattributes` marks `04-data`, the fixtures, the config CSVs and `BLOCKERS.csv` as `-text` (confirmed with `git check-attr`), so a Windows checkout keeps the hashed bytes.
- Largest file 4.0 MB; 48.9 MB in total.
- Licence text: nflverse-data `LICENSE.md` is "Attribution 4.0 International" (fetched). No third-party code without its notice was found.

**Data**
- *Rescoring:* my scorer, written from CONTRACTS §4 before I read `scoring.py`, recomputed **901,165 scores** (5 leagues × 180,233 rows, 2017–2026), with **0 mismatches**. Row keys and order of `scored` equal `player_week`.
- *New metric:* I rebuilt `dst_points_allowed_excl_def` from play-by-play for **all 10 seasons**, using a reading consistent with the contract (kick plays excluded; OAK→LV): **5,288 D/ST rows, 0 mismatches**. It differs from the full score on 640 rows.
- *Change since yesterday:* compared with yesterday's published data (private repository, last commit), 0 rows were added or removed. The only scored change is **FF_ESPN_League on 300 D/ST rows**. In `player_week` the only change is the new column. **Claim verified.**
- *Arizona evidence:* **70/70** ESPN stat cells match (TD, INT, FR, SCK, SFTY, BLK, PA). FPTS match exactly in **9/10** weeks; week 8 is 224 against ESPN's 225. Week 4 goes from 290 yesterday to 292 now (ESPN 292).
  - Week 4 refutes the full-score rule (36 vs ESPN 30).
  - Week 8 refutes the older `excl_def_st` approximation (24 vs ESPN 30).
  - The other 8 weeks cannot tell the rules apart.
  - The rule for interception and fumble return touchdowns is supported. The other cases are labelled assumptions in the contract and in D-038 (but see QA-m2 and QA-m3).
- *Pipeline runs on copies:* `run --seasons all` gave SKIP with output byte-identical to `04-data` and all 13 gates PASS. `check` gave PASS with 46 manifest hashes verified.

**Workflows**
- actionlint 1.7.12 found no problems.
- The pinned SHAs of checkout, setup-python and upload-artifact equal the `v7.0.1`, `v7.1.0` and `v7.0.2` tags (`git ls-remote`).
- The data address answers 404 today, as the documents predict, and raw.githubusercontent.com sends `cache-control: max-age=300`.
- My own simulation (`NFL/.work/q3/sim.py`, `sim2.py`, using G2's step executor only) started from a bare remote holding `LICENSE`, then added the squash-merge commit of exactly the files `git add -A` would commit. Results:
  - the weekly run on the merge push ended PUBLISH and committed as github-actions[bot];
  - a Tuesday scheduled run ended SKIP;
  - a valid web edit ended PUBLISH: all seasons rebuilt, G-GOLDEN WARN for the changed league only;
  - an invalid web edit ended HOLD: red run, alert opened, G-CONFIG text in the summary;
  - committing the fix ended PUBLISH and closed the alert;
  - the heartbeat with a 24-day-old commit pushed one empty commit with the same tree, then did nothing on the next fire;
  - the monthly run on the 1st ended SKIP;
  - the watchdog ended HEALTHY.
- Fork pull requests: `pull_request` only, read-only token, credentials not persisted, no secrets.

**Workbooks**
- The M text on the paste-ready M_Code sheet equals the `.pq` files (15/15).
- The experimental `Section1.m` is exactly `section Section1;` plus the 15 `.pq` files in manifest order, and parses as one document.
- The templates regenerate the `.pq` files byte-identically. Lint is clean (firewall OK).
- The experimental metadata has 15 items with the expected load settings.
- `tblLeagues`, `tblScoring`, `tblBonus`, `tblGolden` and `tblGoldenRules` equal `02-config` and the fixtures in both files. In the experimental file `Applies_To` is the fourth column; the queries read columns by name.
- `tblGoldenRules` hashes equal `status.csv` `contract_*` (ESPN_League updated).
- Check anchors do not overlap.
- Docs: `PLAN.md` equals a fresh render of `plan.json`. Every relative link and named path resolves, except QA-m1's file name and the historical private-repository paths in DECISIONS, which its header explains.

## Could not verify here (ranked by risk)

1. **The branch push itself.** Pushing files under `.github/workflows/` needs a token with GitHub's `workflow` permission. If the session's token lacks it, the push is refused.
2. **First runs on GitHub:**
   - the job-level `contents: write` and `issues: write` with the repository default set to read;
   - `gh issue list --label … --author app/github-actions`. gh's debug output here shows it takes the search route, where `author:app/github-actions` is valid, but GitHub's GraphQL is blocked from this session. If it failed, every PUBLISH would end red with "could not list issues", and the data would still be committed.
3. **Experimental workbook in Excel:**
   - whether it opens without a repair prompt despite stale permission bindings, a deflated `item.data` (QA-m9), Data Model bytes overwritten in place, a widened or moved query table and an added table;
   - whether the Data Model replaces the old `Stats_Scored` (README §5).

   What the owner would see on failure: a repair prompt (README §6 says click No), or a Data Model error. The fallback is the paste-ready file. My confidence it opens and refreshes cleanly: moderate-low. For the paste-ready file: high that it opens, moderate that all 15 pasted queries refresh first time.
4. **The first web refresh:**
   - the Anonymous credentials and Public privacy answers;
   - Formula.Firewall, since a workbook value flows into `Web.Contents`;
   - raw.githubusercontent.com limits on unauthenticated requests across about 40 file reads;
   - refresh time for about 45 MB;
   - the 5-minute cache mixing two publishes, which the docs mention.
5. **Whether GitHub counts the heartbeat's empty commit as activity** (documented as unverified).
6. **Which address GitHub sends failure emails for scheduled runs to.**
7. **The owner's BLOCKERS answers were not compared with the private copy** (outside this review's permitted private reads). Internally they are intact and consistent with the `Claude_Response` texts, apart from QA-m5 and QA-m6.
