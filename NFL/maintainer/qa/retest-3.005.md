# Independent re-test of roadmap 3.005 (Q1 QA Reviewer)

Branch `agents/pensive-noether-dxfoz6`, head `4498198`, compared with `origin/main` (`80190a8`). The head is the two fix commits (`9a84622`, `7acdbb7`) plus one records-only commit (Q-026, memory, plan). I did not build or fix any of 3.005. I re-derived every result below by running it, not from the earlier reports. Scratch work is in `NFL/.work/retest-3.005/` (git-ignored). Nothing was committed, pushed or published, and `NFL/04-data/` was not touched (`git status` is clean).

## Verdict

**Ready to merge**, with the refresh workbook held behind `PUBLISH_REFRESH_WORKBOOK: "false"` as D-057 says.

- No Critical and no Major finding.
- 14 of the 19 prior items are confirmed fixed. 2 are partly fixed, and 3 are unchanged by design (an Excel-only point, an item outside this change, and an accepted note). None of the five is a reason to hold the merge.
- There are 4 new Minor findings (N1 to N4), all wording or defence in depth. None affects data, gates, the workbook or the workflows.
- The refresh workbook is still unproven in Excel. Only the owner's test (Q-026) can settle that. It is not published while the switch is off, so the merge does not depend on it.

## Findings from the two earlier reports

| ID | Finding | State | Evidence |
|---|---|---|---|
| Review F1 / adversarial M-1 | Refresh workbook structure (missing `ExternalData_N` names, duplicate query-table names, table name differs from query name) | **Confirmed fixed** | Built with `python -m nflpipe refresh-workbook`: 14,375 bytes, SHA-256 `1e0a8a16...`. `xl/workbook.xml` has two hidden, sheet-scoped names: `ExternalData_1` (`localSheetId` 1) on `PlayerGames!$A$1:$K$2` and `ExternalData_2` (`localSheetId` 2) on `SeasonTotals!$A$1:$G$2`. Each equals its `queryTable` `name` and its table `ref`, and the sheet name in the range is the sheet that holds the table. Table name = displayName = query name = `FillTarget` = `RecoveryTargetSheet` = metadata path `Section1/<name>` (decoded by my own code from `customXml/item1.xml`). Unique: sheet ids 1 to 3, table ids 1 and 2, connection ids 1 and 2, query-table names, the two `QueryID` GUIDs, every `tableColumn` id. All 23 parts parse, the zip tests clean, the relationships resolve and every part has a content type. |
| Review F2 | Nothing held the refresh workbook back | **Confirmed fixed** | See "The switch" below. D-057 is recorded, and the plan and memory describe it. |
| Review F3 | Size said "about 20 KB" | **Confirmed fixed** | `CONTRACTS.md` 13.6 now says "about 14 KB (14,375 bytes at tables version 1)", matching my build. `AUTOMATION.md`, the table in section 13.1 and both workflow comments say 14 KB. The visitor page has no size for it. |
| Review F4 | "Rebuilt only when `TABLES_VERSION` changes" was false | **Confirmed fixed** | 13.6 now says it is rebuilt on every publish with identical bytes, and that a content change needs a version bump. A pin test enforces the bump (see "Minors"). |
| Review F5 | Guide stated estimates and untested claims as fact | **Confirmed fixed** | The guide now says "about a minute or two (an estimate; not yet measured)", "Excel for the web may not be able to refresh these queries (not tested)", and "written for desktop Excel on Windows ... not tested [on a Mac]". The "Enable Content" sentence is gone. |
| Review F6 | Redirect host named wrongly; Start sheet silent about the second prompt | **Partly** | The guide (step 3) now says "a second address that ends in `githubusercontent.com`". The refresh workbook's `Start` sheet still names only the first address and mentions no second prompt (N2). The file is held back. |
| Review F7 | Stale records | **Confirmed fixed** | `plan.json`: roadmap 3.005 In progress, FR-53 to FR-56 In progress, C-37 Passing, RAID-108 and RAID-109 Open. `MEMORY.md` 1b describes the built state and the switch. `validate_plan.py` passes. |
| Review F8 | Bare CR in a quoted CSV field vs "LF line ends" | **Confirmed fixed** | `CONTRACTS.md` 13.6 now says records end with LF only and a CR can appear only inside a quoted field (none does today). The built CSVs have 0 CR bytes. |
| Review F9 | M text could not be run here | **Unchanged (cannot be tested here)** | I read both `.m` files and the decoded `Section1.m`. They are balanced and match the generator. Only Excel can run them. Covered by Q-026. |
| Review observation | Archived 2.x file carries a user-bound permission block | **Unchanged, outside this change** | The 2.x file still has its 294-byte bindings block. The branch does not touch `archive-2.x/`. The new refresh workbook has an empty bindings block by design. |
| Adversarial M-2 | Lost reply on `DELETE` or `PATCH` strands the headline link | **Confirmed fixed** | See "Lost replies" below. |
| Adversarial m-1 | A stray `.next` asset survives a SKIP | **Confirmed fixed** | Decide now lists every asset name. A leftover `*.next.*` in any state (`uploaded` size 7, or `starter` size 0), for any of the four names, gives `build=true` with "a temporary asset is left over". The publish removes it before the first upload. My own run with the switch off and a leftover refresh `.next` removed it, and left a stray stable refresh asset untouched. |
| Adversarial m-2 | Link check could outlast the step | **Confirmed fixed** | `curl --max-time 20`, 5 tries, pauses 5, 10, 15 and 20 s. Per asset 5 x 20 + 50 = 150 s. Four assets 600 s (10 minutes); three assets 450 s. The step limit is 30 minutes, so it is a third. The test records 20 calls, 200 s of pauses, 600 s in all. The checks are one-byte ranged requests, so a slow CDN costs little. The time spent before the check (uploads and retries) is not part of this arithmetic. A timeout there is harmless: the notes still carry the old key, so the next run rebuilds. |
| Adversarial m-3 | CSV text can look like a formula | **Partly (accepted)** | The guide now gives the second reason not to double-click the file (a cell starting `=`, `+`, `-` or `@` is read as a formula). No exporter check was added. The real files have 0 such text cells today. Power Query types them as text. |
| Adversarial m-4 | Power Query default timeout 100 s | **Confirmed fixed** | `grep` finds `[Timeout = #duration(0, 0, 10, 0)]` once in each `.m` file, once in each guide block, and in the decoded `Section1.m` of my build for both queries. Both guide blocks equal the `.m` text once the leading `//` comment lines are removed; `test_guide_query_text_equals_the_m_file` passes for both. |
| Adversarial m-5 | A refresh-workbook fix would not republish | **Confirmed fixed** | See "Minors". |
| Adversarial m-6 | First run swaps a byte-identical workbook | **Unchanged (accepted)** | Still true: my build of the workbook is byte-identical to the live one. The cost is a window of about one second. The report called it a note, not a defect. |
| Adversarial m-7 | Documentation overstated | **Confirmed fixed** | `AUTOMATION.md` now says "Replacing the files rarely leaves a link empty, and then only briefly", and gives the size as 14 KB. |

## The switch (F2)

I read the whole of `nfl-pipeline-weekly.yml` (860 lines). I compared the build and publish steps of the monthly file with the weekly one: they differ only in the `if:` of the decide step (`steps.outcome.outputs.dry_run` against `steps.resolve.outputs.dry_run`, as before). Both files carry `PUBLISH_REFRESH_WORKBOOK: "false"` as a string at the top level, and a test requires them to be equal.

| Case | What I ran | Result |
|---|---|---|
| `"false"`, first run (release holds the workbook only, old three-field-style key) | Own scratch test using the repository's stand-ins | Decide: `build=true`, "no finished NFL-PlayerGames.csv, NFL-SeasonTotals.csv". Build writes three files and never calls `refresh-workbook`. Publish: 3 uploads, 1 delete, 3 renames, 1 notes edit. Release ends with exactly three assets. 0 violations. A second decide gives `build=false`. |
| `"false"`, stray refresh asset on the release | Existing test and my variant | The stray stable `NFL-Analysis-Refresh.xlsx` is neither deleted nor replaced, and its size is unchanged. The notes do not list it. |
| `"false"`, leftover `NFL-Analysis-Refresh.next.xlsx` | My variant | Removed in the cleanup before the uploads. Nothing else of the refresh workbook is touched. |
| `"true"`, release holds three assets and a current key | Existing test and my variant | Decide finds the refresh workbook missing and gives `build=true` with the key unchanged (no `TABLES_VERSION` bump). Build writes four files. Publish: 4 uploads, 3 delete-and-rename pairs, 1 rename, 1 edit. Release ends with four assets and the notes list the fourth. The next decide gives `build=false`. |
| `"true"` back to `"false"` | Existing test | Key current: `build=false`, no write. The published copy stays. |
| Any other value | Scratch run with `maybe` (existing test), `True`, `TRUE`, empty, `yes`, `1`, `false ` (trailing space) | Decide stops with exit 1 and "must be "true" or "false"" in every case. Publish also stops with exit 1 before any call, and the release is unchanged. See N1 for the build step. |

## Lost replies (M-2)

I read the delete and rename code. I added two knobs to a copy of the `gh` stand-in in scratch (a listing that fails once a delete was tried, and a listing that answers empty once a delete was tried).

- **A genuinely failed delete is never counted as done.**
  - After a failed `drop_assets`, the code lists the assets again. `left="$(asset_ids "$a")" || left="?"`: if the listing fails, `left` is `?`, which is not empty, so it is a failure. If the listing works and the old file is there, it is a failure. Only a successful listing that finds no asset with that name counts as done.
  - My scenario "delete refused 99 times and every later listing fails": exit 1, "could not remove the old NFL-Analysis.xlsx" in the alert details, the old workbook still served, no rename of the workbook, the notes still carry the old key, 0 violations.
  - The repository tests cover the other two cases: a lost reply (server deleted, reply 502; the swap completes, no `--clobber`) and a refused delete with the old file still there (red run, old file served, the new one left as `.next`).
- **A listing that succeeds but answers empty.**
  - The code would treat the old file as gone and try the rename. GitHub refuses the name (422), the five tries fail, and the fallback uploads the new file under the stable name with `--clobber`. That replaces the old file, so the end state is still the new file. Real GitHub does not answer that way, so this is an observation, not a finding.
- **A live asset is deleted only after every `.next` file is verified.** The only delete of a stable name is in the swap loop. The verification loop (`state == uploaded` and the exact size, one id per name) has set `newid` for every asset before it. The `.next` cleanups only ever name `.next` assets. The stand-in's invariant (a live asset may go only when every new file is on the release or already renamed) recorded no violation in any scenario I ran. `--clobber` is used only in the rename fallback, after a delete that succeeded or was confirmed gone.
- **Lost reply on a rename.** The re-list compares `asset_ids "$a"` with the new id. The test shows four renames for four assets and no `--clobber`.

## Minors

- **F4: the `TABLES_VERSION` pin.** I worked on a copy of the tree outside git.
  - I changed `10` to `11` minutes in `PlayerGames.m`: `test_refresh_workbook_changes_only_with_tables_version` failed with "has changed (parts digest a9a9a958...) but TABLES_VERSION is still '1'. Bump TABLES_VERSION ... and pin the new digest". Two more tests failed for the same edit (the release-asset test and the guide-equals-`.m` test), as expected.
  - I restored it, then changed `TableStyleMedium2` to `TableStyleMedium3` in `refresh_workbook.py`: the pin test failed again.
  - After restoring both, `sha256sum` equals the first run (`2011065...` for `PlayerGames.m`, `eac2bc2...` for `refresh_workbook.py`). The repository files have the same hashes, and `git status` is clean.
  - One run after the restore still failed because of a stale `__pycache__` (the restore landed in the same second as the edit and the file size is equal). It passed (27 of 27) after the cache was removed. That is a scratch artefact, not a repository fault.
- **m-1, m-2:** above. **F3, F8, F5, F6, m-3:** above.

## New findings

### Critical, Major
None.

### Minor

**N1. The build step does not check the switch value.** Decide and publish stop on a value other than `"true"` or `"false"`. The build step treats any other value as `false` and builds three files (I ran it with `True`, empty and `yes`: exit 0). In the workflow it cannot be reached: the value is one workflow-level setting, and a failed decide skips the build. Suggested fix: the same two-line guard at the top of the build step, for consistency.

**N2. The refresh workbook's `Start` sheet does not mention the second prompt** (the address ending in `githubusercontent.com`). Only the guide does. This matters only if the switch goes to `"true"`. Suggested fix: add the sentence to the `Start` sheet at the same time as the first Excel-driven fix, and bump `TABLES_VERSION` (the pin test will demand it).

**N3. Residual structural differences from an Excel-saved file** (not a finding against the merge, because the file is held back). My comparison with the 2.x workbook, whose query tables carry Excel-written stamps (`FillCount` 58, `FillLastUpdated`, `FillStatus` Complete):
- Same as 2.x: hidden sheet-scoped `ExternalData_N` names on the table range; `tableType="queryTable"`; `uniqueName` equal to the column position; `refreshedVersion="8"`; connection string and `Location`; the same metadata keys (ours has none that 2.x lacks); the same column-type codes; permission list of 317 bytes.
- Different, and a plausible reason for an Excel prompt: the never-loaded state (`FillCount` 0, `FilledCompleteResultToWorksheet` 0, no `FillLastUpdated` or `FillStatus`); the empty bindings block (2.x has 294 bytes, machine-bound, so it cannot be copied); no `xr:uid` attributes; a `<row r="2"></row>` element with no cells, where Excel writes no row; a `<workbookPr/>` with no `date1904` or other attributes; no `fullCalcOnLoad`.
- None of these is a known repair trigger on its own. The hidden names, which were the likeliest cause, are now present. Only Q-026 settles it.

**N4. The CSV files are not mentioned in `NFL/README.md` or `NFL/04-data/README.md`.** The front page and `NFL/05-excel/README.md` describe them. `NFL/README.md` still says "there is nothing to refresh", which is true of the finished workbook it names. A visitor who starts in the NFL guide would not learn of the files. Optional: one sentence and a link.

### Observations (no action)
- Until the first publish run ends after the merge, the CSV links on the front page answer "not found" (see "First run after the merge").
- The CSV and workbook bytes are as the earlier review recorded.

## First run after the merge

State at the merge: the live release `nfl-workbook` holds `NFL-Analysis.xlsx` only (SHA-256 `be3ed041...`), and its notes carry a three-field key. `status.csv` says `pipeline_version` 1.2.1 and run `20261122T020950Z-gh44974771246`. Switch `"false"`.

**What starts.** The merge changes `NFL/03-pipeline/nflpipe/**` and both workflow files, so `nfl-pipeline-weekly` starts on the push (the monthly workflow has no push trigger). `nfl-pipeline-ci` also starts (tests and a dry run, read-only, no secrets). Runs of the publishing workflows are serialised by the `nfl-pipeline-publish` concurrency group.

**Weekly steps, in order, with what each does here:**

1. Check out, set up Python. No write.
2. **Resolve:** no stray file in `02-config`; push event, so `decision=run`, no `--force`.
3. **Run pipeline** (`run --seasons current --trigger push-weekly`). The config and the pipeline version are unchanged, so it publishes only if nflverse has new data: exit 3 (SKIP) if not, exit 0 (PUBLISH) if so. Nothing here touches the release.
4. **Record outcome.** The gate-report artifact (30 days) and **Commit 04-data** run only on PUBLISH. The data commit is not a push that starts another run, and `04-data` is outside the push filter.
5. **Decide whether to build.** It re-reads `main`, forms the four-field key, and finds the release holds `NFL-Analysis.xlsx` only. Result: `build=true`, with the reason "the release has no finished NFL-PlayerGames.csv, NFL-SeasonTotals.csv" (on a PUBLISH: "new data was published"). The refresh workbook is not required while the switch is off.
6. **Build** (about 11 s on the real data): one `export --tables-dir` pass writes the workbook (8,432,214 bytes) and the two CSV files (38,572,060 and 1,782,782 bytes). The size, readability, header and line-count checks run. `refresh-workbook` is not called; the summary says "none (not published)".
7. **Publish** (my stand-in replay of this state):
   - It deletes any leftover `.next` for all four names (none exist).
   - It uploads `NFL-Analysis.next.xlsx`, `NFL-PlayerGames.next.csv` and `NFL-SeasonTotals.next.csv`, and checks each (uploaded, exact size).
   - Swaps: `DELETE` of the old `NFL-Analysis.xlsx` then `PATCH` of its new file to the stable name; `PATCH` of the two CSV files to their stable names (nothing old to delete).
   - Link check: three one-byte ranged requests to the public addresses.
   - Last, the release notes are replaced with the four-field key. The refresh workbook is not created or touched.
8. **Keep the workbook** artifact (7 days: the workbook and the two CSV files). **Update the alert issue:** a SKIP leaves any open issue as it is; a PUBLISH closes it. "Fail the run" does not run.

**Assets touched:** `NFL-Analysis.xlsx` (replaced by a file with the same bytes on a SKIP, new bytes on a PUBLISH), `NFL-PlayerGames.csv` and `NFL-SeasonTotals.csv` (created), three temporary `.next` assets (created and renamed), the release notes. `NFL-Analysis-Refresh.xlsx` is never created.

**How long each link is down:**

| Link | Down for |
|---|---|
| `NFL-Analysis.xlsx` | About one second, between the `DELETE` and the `PATCH` (two adjacent API calls, 0 calls between them in my replay). It is up during the whole upload phase. If a call fails, the retries add seconds, and a failure ends red with the old file or the `.next` file named in the alert. |
| `NFL-PlayerGames.csv`, `NFL-SeasonTotals.csv` | They have never answered. The front page and the guide link to them as soon as the merge lands, so they answer "not found" from the merge until their rename in this run. That is the length of the run: queue, pipeline step, 11 s build, about 47 MB of uploads. I could not measure it; I would expect a few minutes. |
| `NFL-Analysis-Refresh.xlsx` | Not published. No visitor page links to it. |

## What I ran, and the results

**1. Refresh workbook structure**
- `python -m nflpipe refresh-workbook --out NFL/.work/retest-3.005/rf/r.xlsx` (Python 3.13): 14,375 bytes. Inspected with `inspect_rf.py` and `chk_ids.py` (my own code): the names, ranges, ids and DataMashup results above. The DataMashup decodes as version 0, package 1,440 bytes (three parts), permission list 317, metadata 3,490, bindings 0, no trailing bytes.
- Compared with the 2.x workbook in `NFL/maintainer/archive-2.x/` part by part and by metadata key: N3.
- `NFL/.work/pq/out3/NFL-Analysis-Refresh.xlsx` is byte-identical to my build. The test copy `...-TEST3.xlsx` has the same structure (names, ids, DataMashup) and differs only in the `Start` text, the two query URLs (it reads the data files on `main`) and the seed-sheet strings.

**2. Timeout:** `grep`, and a script that strips comment lines from the two guide blocks and compares them with the `.m` files: equal.

**3 and 4. Workflows and lost replies:** `nfl-pipeline-weekly.yml` read in full; the weekly and monthly publish sections diffed (4 differing lines, one `if:`). Repository tests for the switch, lost replies and leftovers pass (part of the 828). My own scratch tests (`NFL/.work/retest-3.005/test_rt.py`, built on the repository's stand-ins with two extra knobs): a failed delete with failing listings, a failed delete with an empty listing, six other switch values, a stray refresh asset with a leftover refresh `.next`, the `false` to `true` flip, and the first-run replay. All behaved as above; the one surprise is N1.

**5. Minors:** the pin mutation on a copy of the tree (above), with `sha256sum` before and after.

**6. Nothing else broke**
- Full suite, from `NFL/03-pipeline`: `../.work/venv/bin/python -m pytest -q` (Python 3.13.18): **828 passed**, 215 s. `../.work/venv311/bin/python -m pytest -q` (Python 3.11.18): **828 passed**, 210 s.
- `NFL/.work/c1/actionlint-dl/actionlint -shellcheck NFL/.work/c1/sc-dl/shellcheck-v0.11.0/shellcheck .github/workflows/*.yml` (actionlint 1.7.12): exit 0, no findings.
- `python3 NFL/maintainer/plan/validate_plan.py`: PASS, 0 errors.
- `python -m nflpipe export --data-dir ../04-data --out ... --tables-dir ...`: 180,301 rows by 98 columns and 24,250 season rows, 10.8 s. Workbook SHA-256 **`be3ed041cae19f6bf8bff37dd8903205b1783b14038ce4b4f4dc5c80e802ff0b`** (8,432,214 bytes), as required. `NFL-PlayerGames.csv` `ddb95ecd8cb5d530...`, `NFL-SeasonTotals.csv` `75c45dea7fd6085e...`, equal to the earlier review's hashes.
- **Full cell-by-cell comparison** (`cmp.py`, my own streaming reader that does not need cell addresses): `PlayerGames` 180,302 rows including the header and 17,669,596 cells, **0 mismatches**; `SeasonTotals` 24,251 rows and 412,267 cells, **0 mismatches**. Numbers by value, text exactly, blank equals blank.
- CSV format: no BOM, 0 CR, 0 NUL, ends with LF, every row has the header's width (98 and 17 columns). Every column the M text types as a number holds only numbers; `season`, `week` and `games` hold whole numbers only.
- `BLOCKERS.csv`: the branch adds one CRLF record (Q-026). The file now has 26 records (25 on `main`), each ending in CRLF, and the same 2,269 bare LF inside fields. Every existing `Answer` is identical to `main`.

**7. Visitor pages (switch off)**
- `README.md` and `NFL/05-excel/README.md` have no link to, and no mention of, the refresh workbook file. The only mention is "Coming: a ready-made refresh workbook ... once it has been confirmed in Excel", with the working steps given instead. `grep` finds no decision number, question number, "RAID", "owner" or "roadmap" on either page (the only "decisions" is in the pre-existing folder table).
- Every relative link in both pages resolves to a real file. The release links name `NFL-Analysis.xlsx`, `NFL-PlayerGames.csv` and `NFL-SeasonTotals.csv`, which are the three assets the first run publishes (see the note on timing above). The CC BY 4.0 credit with the "modified" statement is present.
- The steps read correctly to a stranger for Windows desktop Excel. I could not run Excel.

**8. Privacy**
- `git diff origin/main...HEAD` (4,471 lines) and the commit messages of all 9 commits on the branch: no e-mail address (the only matches are pytest decorators), no local path other than the test's own list of forbidden strings, no token, no private repository name, no fantasy-team or manager name. Commit authors are `Claude <noreply@anthropic.com>`.
- Refresh workbook (all 23 parts, zip metadata, the decoded package and metadata, and the metadata's inner zip) and the TEST3 copy: no e-mail, path, user or machine name, token or similar. Author and last-modified-by are `NFL-Analysis pipeline`, time stamps are fixed. The only URLs are the three release addresses, the licence address and the TEST3 copy's repository data addresses. (My pattern for a GitHub user matched the Start sheet's text "https://github.com/ (the data is public", a false hit.)
- This report holds no personal data.
