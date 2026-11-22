# Adversarial review, roadmap 3.005 (decisions D-054 and D-056)

Reviewer: Q1 QA Reviewer, adversarial committee. Branch `agents/pensive-noether-dxfoz6`, head `ea046a8`, compared with `origin/main`.
Nothing was committed, pushed or published. Working files are in `NFL/.work/a305/` (git ignores them).
No Excel was available. Everything about how Excel behaves is reasoning, marked as such.

## Verdict

**Safe to merge: yes.** There is no Critical finding.
- The first run after the merge ends with all four assets published.
- No path deletes a live asset before all four `.next` files are verified.
- Every failure I could force is loud: the run turns red and the alert issue opens.
- Security and privacy are clean.

Before the merge I recommend two cheap fixes: **M-1** (probable Excel repair cause) and **M-2** (headline link can stay dark). I also recommend demoting the refresh workbook on the visitor pages (section "Refresh workbook: publish or hold").

## Findings

### Critical
None.

### Major

**M-1. The refresh workbook has no hidden `ExternalData_N` defined names (probable Excel repair prompt).**
- Evidence: `NFL-Analysis-Refresh.xlsx` has no `<definedNames>` in `xl/workbook.xml`. Its two query tables are both named `ExternalData_1`.
- Evidence: every Excel-written workbook in this repository carries one hidden, sheet-scoped defined name per query table. `NFL/maintainer/archive-2.x/NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx` has them: `<definedName name="ExternalData_1" localSheetId="9" hidden="1">Checks!$A$5:$E$6</definedName>`, and so on. Its builder script even rewrites them (`archive-2.x/experimental/build_queries_installed.py` line 567).
- Reproduction: `unzip -p NFL/.work/a305/out/NFL-Analysis-Refresh.xlsx xl/workbook.xml | grep -c definedName` prints 0.
- Likelihood is moderate. I cannot confirm it without Excel. The archive's experimental workbook was never opened in Excel either, so it is not proof that Excel accepts the structure.
- Fix, in `refresh_workbook.py` `build_parts`, between `</sheets>` and `<calcPr>`:
  ```
  <definedNames><definedName name="ExternalData_1" localSheetId="1" hidden="1">PlayerGames!$A$1:$K$2</definedName><definedName name="ExternalData_1" localSheetId="2" hidden="1">SeasonTotals!$A$1:$G$2</definedName></definedNames>
  ```
  Build the range from the seed column count, not from literals. Add a test that the names exist, that `localSheetId` is the zero-based sheet index, and that the range equals the table `ref`.
- If the owner's test shows a repair message, this is the first thing to try.

**M-2. A lost reply on `DELETE` leaves the headline workbook link dark until the next run.**
- Reproduced in `NFL/.work/a305/test_a305.py::test_s2`.
- The server deletes the old `NFL-Analysis.xlsx`, but the reply is lost (a 502).
- `retry` repeats the delete and gets 404, so `drop_assets` returns 1.
- The workflow records "could not remove the old NFL-Analysis.xlsx; it was left in place" and `continue`s. That is false: the old file is gone and the new one is stranded as `NFL-Analysis.next.xlsx`.
- Result: `NFL-Analysis.xlsx` answers 404 (the stub's `served()` returns `None`).
- Duration: until the next run that builds. That is Tuesday to Thursday in season. From March to August it is the 1st of the month, because the 16th is heartbeat-only. So it is up to about 31 days.
- Mitigations already present: the run is red, the alert issue opens, and `workbook_only` repairs it. The next run does repair it, because the decide step sees the missing asset.
- The same pattern applies to `PATCH`: a lost reply followed by a retry that is refused.
- Fix, in the swap loop of both workflows. After a failed `drop_assets "$a"`, read the asset list again. If no asset named `$a` remains, treat the delete as done and go on to the rename:
  ```
  if ! drop_assets "$a"; then
    left="$(asset_ids "$a")" || left="?"
    if [[ -n "$left" ]]; then bad+="could not remove the old ${a}; ..."; continue; fi
  fi
  ```
  Make the rename loop accept success if `asset_ids "$a"` equals `${newid[$a]}`.
- Add a stub knob "delete applies, reply lost" to the `gh` stand-in in `test_workflows.py`.

### Minor

**m-1. A stray `.next` asset survives a SKIP.**
- Reproduced: `test_s3`. With the key current and a leftover `NFL-PlayerGames.next.csv` (38 MB), decide answers `build=false`.
- The comment "the next run removes it" and the warning text in the swap are true only for a run that builds.
- Fix: in "Decide whether to build the workbook", list all asset names. If any matches `*.next.*`, set `build=true` with reason "a temporary asset is left over". Alternatively delete it there.

**m-2. The link check can run longer than the step timeout, in the worst case.**
- `curl --max-time 60` is tried 5 times with 5 s to 25 s sleeps, for 4 assets.
- If the public address never answers, that is 20 × 60 s plus 300 s, which is about 25 minutes (measured: 300 s of sleeps and 20 calls in `test_s4`). The publish step has `timeout-minutes: 30`, after uploads.
- A timeout there is harmless: the swaps are done and the notes keep the old key, so the next run rebuilds.
- A range request `-r 0-0` does not download 38 MB, so a slow CDN costs little.
- Fix: `--max-time 20`.

**m-3. The CSV files carry formula-looking text verbatim.**
- Reproduced: with `player_display_name` set to `=HYPERLINK(...)`, `@SUM(1+1)`, `+1+1` and `-2+3` in a copy of `04-data` (`NFL/.work/a305/inj`), the exporter writes them unchanged into `NFL-PlayerGames.csv` line 9657 and the lines after it.
- The workbook stores them as strings, and Power Query types them as text, so both are safe.
- A visitor who double-clicks the CSV in Excel would get a formula.
- Today the real data has 0 such cells in text columns (checked on both files). The risk is a crafted upstream name.
- Fix:
  - Add to the visitor guide the second reason not to double-click: formulas, not only encoding.
  - Add an exporter check that rejects a text-column cell starting with one of `= + - @ tab CR`, with a test. Do not prefix with `'`, because that would show in Power Query.

**m-4. Power Query's default request timeout is 100 s.**
- This is from the Power Query documentation and is unverified here.
- `Web.Contents` has a 100 s default for a 38 MB file, so a slow connection (under about 3 Mbit/s) could time out.
- Fix: in `pq/PlayerGames.m` and `pq/SeasonTotals.m`, and in the README snippets, add the option `[Timeout = #duration(0, 0, 10, 0)]` to `Web.Contents`.
- The tests check that the README copies equal the `.m` files, so change all of them together.

**m-5. A fix to the refresh workbook will not republish by itself.**
- CONTRACTS 13.6 says it is rebuilt only when `TABLES_VERSION` changes.
- The owner's Excel test will probably lead to a change in `refresh_workbook.py` or `pq/*.m`. Merging that starts a weekly run, which SKIPs because the key is current, so the old file stays up.
- Fix: say in CONTRACTS and `AUTOMATION.md` that such a change needs `TABLES_VERSION` bumped, or a `workbook_only` run. Better: put a hash of `refresh_workbook.py` and `pq/*.m` into `TABLES_VERSION`'s test, so a change without a bump fails CI.

**m-6. The first run swaps an identical workbook.**
- The exporter's workbook is byte-identical to what is live (SHA-256 `be3ed041cae19f6b…`), so the first run opens an avoidable window of about 1 s on the headline link.
- It is bounded and by design, so this is a note rather than a defect. A "same size and hash, skip the swap" shortcut is possible, but I do not recommend adding code for it now.

**m-7. Documentation overstates three points.**
- `AUTOMATION.md` says "The finished workbook link keeps working throughout" for the first run. There is a short 404 window between `DELETE` and `PATCH` (calls are adjacent: 0 calls between them in the log of `test_s1`; the real gap is two API round trips).
- "If any step fails, the link keeps giving the old workbook" is not true for a half-done swap. The same paragraph then admits the exception.
- The refresh workbook is "about 20 KB" in the README, `AUTOMATION.md` and the CONTRACTS table; the real file is 14,282 bytes.
- The "visitors" pages gain no decision numbers or owner addresses (checked).

## 1. The first run after the merge (release has `NFL-Analysis.xlsx` and a three-field key)

Trace, driven through the workflow's own shell steps with the test stubs (`test_s1`):
1. The push to `main` gives decision `run`. `run` publishes if there is new upstream data, or SKIPs. The pipeline version is not bumped, so it does not rebuild all seasons.
2. Decide: the key has four fields, the notes have three, and three assets are missing. It sets `build=true` and the summary says `no finished NFL-PlayerGames.csv, NFL-SeasonTotals.csv, NFL-Analysis-Refresh.xlsx`.
3. Build (replayed with the real exporter on the real data): passes every size, line-count and zip check (see section 6).
4. Publish: the four `.next` uploads, then four verifications by id, state and size, then the swaps, the four link checks, and last the notes.
5. In the swap, only `NFL-Analysis.xlsx` has an old file. The three new assets have nothing to delete: each `drop_assets` finds nothing and goes straight to `PATCH`.
6. Does the workbook link stay up throughout? **Not strictly.** It answers 404 between the `DELETE` and the `PATCH` of that one asset: two adjacent API calls, about a second. The link is up for the whole upload phase (about a minute), which is the long part.

What if something fails:

| Case | Result |
|---|---|
| One of the three new uploads fails 3 times | `drop_all_next`, red run, "no asset already on the release was touched". The workbook link is never affected. The next run repeats everything. Covered by existing tests (`GH_UPLOAD_FAIL_NAME`). |
| A new upload leaves a zero-byte starter | The retry removes it first. Covered. |
| The rename of a new asset is refused | Five attempts, then the same file is uploaded under the stable name (`--clobber`: nothing there to overwrite), then the `.next` is dropped. If that fails too, the link answers 404 until the next run, which is reported. Covered. |
| CDN slow for a 38 MB file | The check is a one-byte range request, so slowness is not a risk. See m-2 for the timeout arithmetic. The upload itself has no `gh` timeout; the 30-minute step limit applies. |

## 2. The swap

- **Can a live asset be deleted before all four `.next` files are verified?** No. The only delete of a stable name is inside the swap loop, after the verification loop has set `newid` for all four. The `gh` stand-in in `test_workflows.py` records a violation if a live asset is deleted while any new file is missing, and none was recorded in any scenario I ran.
- **Is `--clobber` ever applied to a live asset?** Only in the rename fallback, after `drop_assets "$a"` succeeded, so nothing is left to overwrite (the stand-in flags a violation otherwise).
- **Inconsistent four?**
  - Normal path: the four swaps are adjacent pairs, so old and new files are mixed for a few seconds.
  - Failure path: a partial swap (for example a refused rename after the workbook swapped) leaves a mixed set until the next building run. The stop message names each affected asset, and the notes keep the old key so the next run rebuilds all four.
  - The window is reported (red run, alert issue). It is not announced to visitors, who see only the files. See M-2 for the worst case.
- **Does the next run repair a partial state?** Yes. It sees a missing asset or an old key. It does not remove a stray `.next` on a SKIP (m-1).
- **`workbook_only`:** on main it gives decision `workbook`, outcome `WORKBOOK`, `build=true`, and builds and swaps all four. Off main it ends red, with nothing done. It does not run the pipeline and does not commit.
- **Dry runs and the monthly heartbeat:** both stay non-publishing. The build and publish steps need `dry_run != 'true'` and `github.ref == 'refs/heads/main'`. The 16th gives outcome `HEARTBEAT`, which is not in the build condition. The heartbeat step only commits an empty tree.

## 3. Limits

- GitHub allows each release asset up to 2 GiB. The 38.6 MB CSV is far below. A release can hold up to 1,000 assets (we hold at most 8).
- `gh release upload` is one HTTP upload per file with no overall timeout. At 38 MB it takes seconds on an Actions runner.
- The artifact change, level 0 to 6: compressing all four files at level 6 took under 1 s and gave 13.8 MB (measured with Python's `zipfile`). Negligible runtime.
- Artifact storage per run is about 14 MB for 7 days. Actions minutes on a public repository are free anyway.
- Export time on the real data: 11 s.

## 4. Security

- **Permissions:** the top level is `contents: read`. Write permission is on the job only, as before.
- **Fork pull requests:** neither publishing workflow has a `pull_request` or `pull_request_target` trigger.
  - The only `pull_request_target` text in the repository is a comment in `nfl-pipeline-ci.yml`.
  - Publishing needs `github.ref == refs/heads/main`, and a dispatch needs write access.
  - A fork's own Actions would only act on the fork's own repository and token.
- **Inputs:** every dispatch input goes through `env:`. `seasons` is matched against `^(current|all|YYYY|YYYY-YYYY)$` before use, and is never echoed.
- **Pins:** the three actions are pinned to full SHAs, equal to `KNOWN_PINS` in `test_workflows.py`.
- **Secrets:** none. No `secrets.` reference in any workflow.
- **Formula injection:** see m-3. M types: text columns are `type text`. Every other column is `type number`, and I checked that every non-text value in all 98 and 17 columns parses as a number, so no type errors on today's data. A future text column that the M text lists do not name would show error cells, not formulas.

## 5. The refresh workbook in Excel (reasoning only)

| Likely failure | What the owner would see | Fallback |
|---|---|---|
| Missing `ExternalData_N` names (M-1) or other structure Excel dislikes | "We found a problem with some content ... recover?" then "Removed Feature: Table / Query table". The sheets open as plain empty tables with no refresh. | The visitor guide's Get Data, From Web steps. The finished workbook. |
| Empty permission bindings (zero-length block) | MS-QDEFF treats unverifiable bindings as absent, so Excel should ask its privacy and credential questions once. If it rejects the whole DataMashup it drops the queries (same as row 1). | Same. |
| Seed tables of 11 and 7 columns widened to 98 and 17 | Excel rewrites the layout on refresh. The sheets hold only the table, so nothing overlaps. Column widths and frozen panes from the seed may look narrow. The 2.x experiment used the same pattern but was never opened in Excel either. | None needed. |
| GitHub-to-objects redirect | Up to two "Access Web content" prompts and a privacy-level prompt. The Start sheet and README tell the user to choose Anonymous and Public. Each query reads one host, so no `Formula.Firewall` combination. | The README steps, with the "Ignore the Privacy Levels" option. |
| Slow connection or large load | A 100 s timeout error (m-4); 17 million cells, about 1 to 3 minutes; a 32-bit Excel may run out of memory. | The finished workbook. |
| Refresh during the 1 s swap window | `DataSource.Error ... 404`. | Refresh again. |

### Refresh workbook: publish or hold?

**Recommendation: publish at merge, demoted. Do not hold the asset.**
- Holding it needs a code and test change in the four-asset machinery, then a `TABLES_VERSION` bump and a second republish when the test passes.
- A broken file does no damage: it is a 14 KB file with no data, macros or secrets. It can only show a repair prompt, and the guide has a path that cannot fail.
- What does harm is promotion before proof. So before the merge:
  - Remove the refresh-workbook sentence from the front page `README.md`. Keep the two CSV links there.
  - In `NFL/05-excel/README.md`, label "The quick way" as "new, not yet confirmed in every Excel version".
  - Flip those texts after the owner's test passes.
- If the test fails, fix the generator (M-1 first) and bump `TABLES_VERSION` (m-5).

## 6. What I ran

- `git diff origin/main --stat`, `git log origin/main..HEAD`, and read both workflows in full, the exporter diff, `refresh_workbook.py`, `pq/*.m`, and the stubs in `test_workflows.py` and `NFL/.work/qr/`.
- Full tests, both venvs from `NFL/03-pipeline`: `NFL/.work/venv/bin/python -m pytest -q` (Python 3.13.18) and `NFL/.work/venv311/bin/python -m pytest -q` (Python 3.11.18). Result: **782 passed** on each, about 155 s. The 3.11 run printed one harmless temp-directory warning.
- `NFL/.work/c1/actionlint-dl/actionlint -shellcheck NFL/.work/c1/sc-dl/shellcheck-v0.11.0/shellcheck .github/workflows/*.yml`: actionlint 1.7.12, shellcheck 0.11.0, no findings. (Without `-shellcheck` actionlint does not check the shell.)
- `python3 NFL/maintainer/plan/validate_plan.py`: PASS, 0 errors.
- Exporter on the real data: `python -m nflpipe export --data-dir ../04-data --out ... --tables-dir ...`: 180,301 rows by 98 columns, 24,250 season rows, 11 s. `python -m nflpipe refresh-workbook`: 14,282 bytes. SHA-256: workbook `be3ed041cae19f6b…` (equal to live), PlayerGames `ddb95ecd8cb5d530…`, SeasonTotals `75c45dea7fd6085e…`, refresh `39bf9bcde6317c6c…`. Repeating the build gave the same hashes.
- Replayed the workflow's own "Build the workbook" `run:` block extracted from the YAML (`NFL/.work/a305/build_step.sh`), with the real thresholds and the real interpreter: exit 0, all checks passed (CSV lines 180,302 and 24,251, no BOM, header `season,`).
- Independent check that the CSV equals the workbook cell for cell (`NFL/.work/a305/cmp.py`, own XML reader): 180,302 and 24,251 rows, 0 mismatches.
- CSV scan (`NFL/.work/a305/csvcheck.py`): no ragged rows, no duplicate headers, no text cell starting `= + - @`, all non-listed columns numeric.
- Scenario tests on the workflow shell steps with the test stubs (`NFL/.work/a305/test_a305.py`, 10 selected tests passed): the first run after the merge, lost `DELETE` reply, stray `.next`, all link checks failing.
- Formula-injection probe: a copy of `04-data` with four hostile names (`NFL/.work/a305/inj`, output in `inj-out`).
- Level-6 compression timing with Python `zipfile`.
- Privacy: scanned the diff and the three commits (authors are `Claude <noreply@anthropic.com>`, no personal detail), the refresh workbook parts and the decoded DataMashup, the workbook parts, and both CSVs for local paths, email addresses, tokens, the archived project and private names. Result: nothing found. The league names in the headers (`FF_Standard`, `FF_Half_PPR`, `FF_PPR`, `FF_League_1`, `FF_ESPN_League`) are already in the published `04-data`. Workbook and refresh properties carry only `NFL-Analysis pipeline`.

## Not checked

- Nothing was run in Excel, so M-1 and every row of the Excel table are reasoning.
- No real GitHub API call was made. The stand-in models documented behaviour (422 on a duplicate name, 404 on a deleted id).
- GitHub's asset-size limit and the Power Query default timeout come from documentation I know, not from a call made here.
