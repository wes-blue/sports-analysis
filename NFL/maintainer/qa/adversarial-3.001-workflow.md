# Adversarial review A2: the workbook publishing steps (3.001)

Reviewer: A2 of the adversarial committee (Q1 QA Reviewer card). Target: `.github/workflows/nfl-pipeline-weekly.yml` and `nfl-pipeline-monthly.yml` at branch `agents/pensive-noether-dxfoz6`, commit `dd05adb`, plus `NFL/CONTRACTS.md` sections 8 and 13.5. Date of review: 2026-11-21. Nothing in the repository was changed except this report; scratch work is in `NFL/.work/a2x/` (git-ignored).

## Summary

| Grade | Count | IDs |
|---|---|---|
| Critical | 1 | A2-01 |
| Major | 2 | A2-02, A2-03 |
| Minor | 10 | A2-04 to A2-13 |

Verdict: the release logic is well guarded against the failures it was written for (unknown is never treated as missing, nothing from `status.csv` runs as code, no fork or branch can reach the release steps, no loops). The two things that go wrong in practice are on the owner's path: the link is dead from the merge until the next scheduled run, and the chosen upload command removes the live workbook before the new one exists, which the guide and the tests both claim it does not.

How the findings were produced: `actionlint` 1.7.12 (clean), `pytest tests/test_workflows.py` (157 passed), the three workbook steps and the alert step executed from the YAML against a stand-in `gh` (`NFL/.work/a2x/gh`, modelled on `cli/cli` v2.89.0 source fetched from `raw.githubusercontent.com`), 40 mutations of scratch copies of the workflow files run against the test file, and the real exporter run on the real published data (37.9 MB, 12 s, byte-identical on a second run). The real GitHub API was never called.

---

## Critical

### A2-01 The download link is dead from the merge until Tue 2026-11-24 15:17 UTC (certain)

**Reproduction.** List what the merge changes: `git diff --name-only origin/main...HEAD`. Under `NFL/02-config/` only `README.md` changes. The weekly push filter is `NFL/02-config/**` then `!NFL/02-config/**/*.md`; GitHub's own filter table lists `docs/**/*.md` as matching `docs/README.md`, so the README is excluded and the weekly workflow does not start. The CI workflow starts (push touches `NFL/03-pipeline/**`) but only runs pytest and has no release step. The weekly schedule is Tue, Wed, Thu only (cron `... 2`, `3`, `4`), the monthly is the 1st and 16th, the watchdog does not build. Today is a Saturday, so the first scheduled chance is Tue 2026-11-24 15:17 UTC. Until then `https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx` answers 404, while `NFL/README.md`, `NFL/05-excel/README.md` and `AUTOMATION.md` section 0 already print it as the place to download.

**Evidence.** Merge diff above; trigger blocks of the four workflows; `AUTOMATION.md` step 7 and `NFL/05-excel/README.md` "Status (2026-11-21)" both admit the first workbook does not exist yet. So it is known and documented, but it is a certain dead link for about 3.5 days if nobody acts, and the very first run (Tuesday) will then happen unwatched.

**Confidence.** High.

**Fix (no code).** Immediately after the merge, dispatch the workflow once on `main`: Actions, `nfl-pipeline-weekly`, Run workflow, tick `workbook_only` (or `gh workflow run nfl-pipeline-weekly.yml --ref main -f workbook_only=true`). Then check the link answers: `curl -sL -r 0-0 -o /dev/null -w '%{http_code}\n' https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx` should print `206` or `200`. Put this in the orchestrator's merge checklist, so the first creation of the release is watched, not left to Tuesday.

**Not recommended as a code fix:** making the weekly `push` trigger also match `NFL/03-pipeline/**`. `Resolve` treats every push as a config change and forces a full publish, so every pipeline merge would republish data.

---

## Major

### A2-02 `--clobber` deletes the live workbook before the new one is uploaded; a failed upload leaves no workbook at all (high confidence in the mechanism)

**Reproduction (stand-in, `NFL/.work/a2x/s1.py`, log `s1.log`).** Release holds a good `NFL-Analysis.xlsx`. Make the three upload attempts fail. Result: the step turns red as designed, but `assets after: []`. The old asset is gone, the old notes still point at it.

**Evidence.**
- `gh` source (`pkg/cmd/release/shared/upload.go`, v2.89.0): `uploadWithDelete` calls `deleteAsset` on the existing asset first and only then POSTs the new file (retrying 3 times at 200 ms on 5xx or network errors). `release upload --clobber` is "delete, then upload", not an atomic replace.
- GitHub REST docs, "Upload a release asset": "When an upstream failure occurs, you will receive a `502 Bad Gateway` status. This may leave an empty asset with a state of `starter`." So a failed upload can also leave a broken asset under the real name.
- `AUTOMATION.md` ("When the workbook fails but the data was published") promises "the download link still gives the previous workbook". That is false after a failed upload. The test `test_upload_failure_is_red_keeps_the_old_notes_and_points_at_the_artifact` passes because its stand-in `gh` (`GH_RELEASE_STUB` in `tests/test_workflows.py`) fails before it touches any asset, which is the opposite of what `gh` does.
- Even on success, the 404 window is the whole upload of a 37.9 MB file, not "a few seconds" (guide) and not a fixed "about a minute" (contract): it is however long the POST takes.

**Impact.** One transient 502 on the uploads host leaves the owner with no workbook (and a red run) until the next scheduled run repairs it, up to days, longer in the off-season. The stable address is the product; a 404 on it is the worst outcome of this design.

**Fix: upload under a temporary name, then swap.** Replace the `uploaded=false; for attempt ...; [[ uploaded ]] || stop` block of "Publish the workbook" in both workflows with the block below. The live asset is deleted only after the new file is on the release, so a failed upload cannot hurt the old workbook, and the dark window shrinks from the length of the upload to one DELETE plus one PATCH (about a second). I ran the same sequence (`NFL/.work/a2x/swap.sh`, `s7.py`, log `s7.log`) against the stand-in for: normal replace, first run, leftover temporary asset from a dead run, upload failure (old asset survives), failed DELETE (old survives), failed rename (worst case: no live asset, new file present under the temporary name, next run repairs it).

```bash
          next="${WORKBOOK_ASSET%.xlsx}.next.xlsx"      # must differ from the live name; GitHub rejects a duplicate name
          stage="$(mktemp -d)"; cp "$WORKBOOK_FILE" "$stage/$next"
          api="repos/${GH_REPO}/releases"
          ids() { gh api "${api}/tags/${WORKBOOK_TAG}" --jq ".assets[] | select(.name==\"$1\") | .id"; }
          upload_next() {
            local id
            for id in $(ids "$next"); do gh api -X DELETE "${api}/assets/${id}" >/dev/null || return 1; done  # leftover of a dead run
            gh release upload "$WORKBOOK_TAG" "$stage/$next"                                               # live asset untouched
          }
          uploaded=false
          for attempt in 1 2 3; do
            if upload_next; then uploaded=true; break; fi
            echo "::warning::upload failed (attempt $attempt)"
            sleep $((attempt * 10))
          done
          [[ "$uploaded" == "true" ]] || stop "could not upload ${WORKBOOK_ASSET} after 3 attempts; the workbook already on the release was not touched; the built file is in this run's workbook-${GITHUB_RUN_ID} artifact for 7 days"
          new="$(ids "$next")"; [[ -n "$new" ]] || stop "the upload finished but the new asset cannot be found; the workbook already on the release was not touched"
          for id in $(ids "$WORKBOOK_ASSET"); do      # the dark window opens here
            gh api -X DELETE "${api}/assets/${id}" >/dev/null || stop "could not remove the old ${WORKBOOK_ASSET}; the new file is on the release as ${next}"
          done
          renamed=false
          for attempt in 1 2 3 4 5; do
            if gh api -X PATCH "${api}/assets/${new}" -f name="$WORKBOOK_ASSET" >/dev/null; then renamed=true; break; fi   # and closes here
            sleep 2
          done
          [[ "$renamed" == "true" ]] || stop "the new workbook is on the release as ${next} but could not be renamed to ${WORKBOOK_ASSET}; the next run repairs it"
```

The existing check in "Decide" already treats a missing `NFL-Analysis.xlsx` as "build again", and the leftover `.next.xlsx` is removed by the first line of `upload_next` on the next run. Also harden "Decide" so a half-finished asset (state `starter`, zero bytes) does not count as present: change the asset query to `--jq '.assets[] | select(.state=="uploaded" and .size>0) | .name'` (`state` and `size` are fields of `gh release view --json assets`; checked in `shared/fetch.go`).

**Untestable here, to confirm on the first real run (watch it, see A2-01):** that `PATCH /releases/assets/{id}` with `name` renames an asset on a pre-release (the OpenAPI description lists `name` as editable, "users with push access"), that a duplicate name is refused rather than overwritten (not documented), and the real length of the dark window. If PATCH should misbehave, the fallback is to keep `--clobber` and accept the window, but then fix the guide text and the test stub to say so.

**Confidence.** High on the mechanism (source plus REST documentation), medium on how often it bites.

### A2-03 A re-run of a failed run fails again after a successful publish: artifact name conflict (medium-high confidence, not executed on GitHub)

**Reproduction.** A run builds the workbook, the publish step fails (for example A2-02). The step "Keep the workbook" still runs (`!cancelled()` and `wbbuild` succeeded) and stores artifact `workbook-<run_id>`. The owner presses "Re-run failed jobs" (the obvious button). Attempt 2 has the same `run_id`; resolve now says SKIP, "Decide" sees a stale or missing asset and rebuilds, the publish succeeds, and then "Keep the workbook" tries to create `workbook-<run_id>` again.

**Evidence.** `actions/upload-artifact` at the pinned SHA `cf430e03...`, `action.yml`: `overwrite` default `'false'`: "If false, the action will fail if an artifact for the given name already exists." Its README: "Artifact names must be unique ... or else you will encounter conflict errors". Artifacts belong to the run, not to the attempt. The same applies to the existing `gate-report-<run_id>` after a PUBLISH.

**Impact.** The release is good, the run is red again, a comment is added to the alert issue, and the owner concludes the fix did not work.

**Fix.** In both workflows give both artifacts the attempt number, and make the convenience copy unable to turn a good run red:

```yaml
      - name: Keep the workbook (run artifact, 7 days)
        if: ${{ !cancelled() && steps.wbbuild.outcome == 'success' }}
        continue-on-error: true
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: workbook-${{ github.run_id }}-${{ github.run_attempt }}
```
and `name: gate-report-${{ github.run_id }}-${{ github.run_attempt }}` for the gate report (`test_workflows.py` currently pins the shorter names and needs the matching change). The guide sentence "the run page also holds the finished file under Artifacts as workbook-..." stays true.

---

## Minor

### A2-04 The alert issue is not closed by the run that repairs the workbook, and its heading is misleading (high confidence; documented behaviour, but worth fixing)

Reproduction `NFL/.work/a2x/s9.py`: a SKIP run whose upload failed produces the issue text `**nfl-pipeline-weekly** ended **SKIP** (job status: failure)` with a details block `workbook: could not upload ...`. The repair then goes green as SKIP (issue stays open), as WORKBOOK (stays open), and only a PUBLISH closes it. In the off-season (March to August) a weekly PUBLISH may not come for months, and the monthly workflow's repair of a weekly failure can never close the weekly issue (different label). Section 8 of the contract ("closed only by a run that proves the problem is gone") is followed to the letter, but for a workbook failure a successful upload does prove it.

**Fix.** Give the workbook its own alert: label `nfl-pipeline-alert-workbook`, opened or commented by a run where `wbcheck`, `wbbuild` or `wbpublish` failed, closed by any run where `wbpublish` succeeded or `wbcheck` found `build=false`. Keep the data alert as is. Heading text: say "workbook step failed" instead of "ended SKIP". Until then, the sentence in the guide ("close the issue yourself") is the safety net.

### A2-05 Release-not-found detection is a match on gh's English error text (verified safe direction, fragile)

`grep -qi "release not found" "$err"`. Source check (`shared/fetch.go`, v2.89.0): `FetchRelease` runs a REST lookup and a GraphQL draft lookup; both map HTTP 404 to `ErrReleaseNotFound`, whose text is exactly `release not found`; any other status becomes a different error. Stand-in runs `s3` (502, 403 rate limit, timeout, reworded message) all end in `stop` ("could not look at the release") and never reach `gh release create`: unknown is not treated as missing, a duplicate release cannot be created. Two weaknesses: (1) the string is not a documented interface and `ubuntu-latest` moves its `gh` version; a reworded message would make the first run a permanent red (no release is ever created, safe but stuck); (2) there is no retry, so one transient 502 on a PUBLISH run (data already committed) turns the run red and raises an alert (the next run repairs it).

**Fix.** Do not parse an error message: list releases and read a field.

```bash
          if ! rel="$(gh release list --limit 100 --json tagName,isDraft \
                      --jq ".[] | select(.tagName==\"$WORKBOOK_TAG\") | .isDraft" 2>"$err")"; then
            stop "could not list the releases: $(head -c 300 "$err")"      # network, 5xx, rate limit: never "missing"
          fi
          case "$rel" in
            "")    echo "no release $WORKBOOK_TAG yet" ;;                  # listed fine, tag not among them
            false) have_release=true ;;
            true)  stop "release $WORKBOOK_TAG is a draft; delete or publish it" ;;
          esac
```
(the jq expression was checked on sample JSON). Wrap the two reads in a three-try loop with `sleep`. The same applies to `gh release edit` (below, A2-08).

### A2-06 A draft release holding the current key counts as published; nothing checks that the public link works (medium confidence)

`FetchRelease` also finds draft releases (GraphQL path), so a hand-made draft named `nfl-workbook` with a current key passes "Decide" (`s4`: `build=false`) while `releases/download/...` is dead for a draft. After publishing, the workflow never fetches the public address. Add at the end of "Publish the workbook", after the notes edit:

```bash
          for attempt in 1 2 3; do
            code="$(curl -sL -r 0-0 -o /dev/null -w '%{http_code}' "$url")"
            [[ "$code" == "200" || "$code" == "206" ]] && break
            sleep $((attempt * 5))
          done
          [[ "$code" == "200" || "$code" == "206" ]] || stop "the workbook was uploaded but ${url} answers ${code}"
```
A GET with a one-byte range is used because the download redirect is a signed GET URL (a HEAD may be refused; UNVERIFIED). This single check also catches any of: draft, wrong asset name, immutable-release refusal (A2-11), a renamed asset.

### A2-07 The freshness key ignores the exporter: an exporter fix does not ship on a SKIP (high confidence, by design)

Key = `run_id|pipeline_version`. The 3.001 merge changes `nflpipe/export_xlsx.py` and not `pipeline_version` (still `1.2.1`). Any later fix or design change to the workbook is invisible to SKIP runs, which in the off-season means "not until the next publish"; the only way out is a manual `workbook_only`. **Fix:** add a short hash of the exporter to the key, in "Decide": `exp="$(sha256sum nflpipe/export_xlsx.py | cut -c1-10)"` and `key="${run_id}|${version}|${exp}"`, and change the contract text accordingly. (A weaker alternative: bump `pipeline_version` whenever the exporter changes, so `resolve` already says run.) Related stale-docs note: `NFL/05-excel/README.md` still says the file is "about 20 MB"; measured 39,760,580 bytes (37.9 MB), as `CONTRACTS.md` 13.5 says.

### A2-08 No retry on `gh release edit`; a failed notes update costs one extra rebuild (verified self-repair)

`s2`: upload succeeds, `gh release edit` fails: the run is red, the asset is the new one but the notes still carry the old (or placeholder) key. The next SKIP rebuilds and republishes once, and from then on the key is right; it is not "forever" and not a loop, unless the edit keeps failing. A three-try loop with `sleep` removes the extra 38 MB rebuild and the red run in the common transient case. In the first-run case the placeholder text "The workbook is being uploaded" would otherwise stay on the public release page until then.

### A2-09 A queued run reads the data of the commit that existed when it was triggered (medium confidence, rare)

`github.sha` for `schedule` and `push` is fixed when the event fires. A run that waits in the `nfl-pipeline-publish` group behind another publish checks out older `NFL/04-data`. If its resolve still says SKIP (or the run is a `workbook_only` dispatch), "Decide" compares the newer key on the release with the older `status.csv`, rebuilds from the old data and replaces a newer workbook with an older one. The next SKIP run sees the key mismatch and repairs it, so the damage is a few days of stale data, not a dead link. **Fix:** at the start of "Decide", `git fetch --depth=1 origin main && git checkout -q FETCH_HEAD -- NFL/04-data` (anonymous fetch works on a public repository), or check out with `ref: main`. Related, same cause: GitHub keeps only one pending run per concurrency group, so a third queued run silently cancels the second one; a `workbook_only` dispatch that shows "Canceled" simply has to be started again. Say so in the guide.

### A2-10 `workbook_only` started from a branch does nothing and says it rebuilt (`s10`)

`Resolve` forces `dry_run=true` off `main` but still prints `::notice title=Workbook only::... the workbook is rebuilt from the data on main`, and the run ends green with outcome WORKBOOK. "Decide" is skipped by its `dry_run` guard. The guide tells the owner to leave "Use workflow from" on `main`; one wrong pick gives a green no-op. **Fix:** in the workbook_only branch of `Resolve`: `if [[ "$dry_run" == "true" ]]; then echo "::error title=Workbook only::started on ${REF#refs/heads/}, not main: nothing was rebuilt. Start it again from main."; out "decision=error"; exit 0; fi` (outcome ERROR is red and raises the alert, which is right).

### A2-11 Repository settings that would break the design are not checked (UNVERIFIED, owner action)

If the repository setting for **immutable releases** is on, a published release and its assets can no longer be changed, so `--clobber`, the PATCH rename and `gh release edit` would all be refused and the design (create published, then attach) fails on the first run. Tag rulesets that restrict creating tags would block `gh release create`. Neither can be checked from here. Ask the owner to confirm both are off (Settings, General, Releases and Rules); the check in A2-06 would turn them into a red run on day one instead of a silent problem.

### A2-12 Input and value hardening (no hole found; cheap to close)

Held up: values from `status.csv` (including `$(...)`, backticks, quotes, `-->`, `@mentions`, `::set-output` lines, a CR) were run through "Decide" and "Publish" (`s8`, nothing executed, notes carry the text literally, no extra output lines from `awk`'s one-line `$2`). Weak points that need write access or a changed writer: (a) `workflow_dispatch` input `seasons` containing a newline is written into `$GITHUB_OUTPUT` as extra lines (`s10`), later `out` calls win, so it cannot reach the release steps, but it is an unvalidated multi-line write; (b) a `\r` in a `status.csv` value would land in `$GITHUB_OUTPUT` and in the notes (the file has none today; the pipeline writes LF). (c) The tail of the export log is appended to the alert issue body without the backtick neutralisation that "Record outcome" applies; today only numbers and the pipeline's own file names appear in those messages. **Fix:** in "Resolve" `[[ "$seasons" =~ ^(current|all|[0-9]{4}(-[0-9]{4})?)$ ]] || { echo "::error::bad seasons"; exit 1; }`; in "Decide" `[[ "$run_id" =~ ^[0-9A-Za-z._-]+$ && "$version" =~ ^[0-9A-Za-z._-]+$ ]] || stop "status.csv run_id or pipeline_version has unexpected characters"`; in the "Build" `stop`, pipe the tail through `sed 's/```/'"'''"'/g'`.

### A2-13 The tests: rules that survive mutation (see table below)

Of 40 mutations of scratch copies of the two workflow files, the file `test_workflows.py` (157 tests) catches the large majority. The ones that survived name checks that do not exist yet. Result: 40 mutations, 31 caught, 9 survived. Survivors:

| # | Mutation | Verdict |
|---|---|---|
| 8, 9 | the "asset missing" / "release missing" branch of "Decide" made dead | Equivalent: the next branch (`current` false) still builds; only the reason text changes. Not a gap in behaviour. |
| 0 | key grep without the trailing space | Equivalent in practice (run ids are unique), untested. |
| 4 | workbook artifact `compression-level: 0` removed | Untested; only costs upload time on a 38 MB zip. |
| 15 | upload retry without `sleep` backoff | Untested; retries would hit the same 502 within a second. |
| 23 | a `pull_request:` trigger added to the weekly workflow | **Gap.** `ALLOWED_EVENTS` is one set for all files; the weekly and monthly workflows should be pinned to `schedule`, `push` (weekly only) and `workflow_dispatch`. The `main` guards still make such a run a dry run, so no damage today. |
| 25 | `z.testzip()` dropped from the zip sanity check | Untested (the member-name check is tested). |
| 30 | monthly `timeout-minutes` cut from 90 to 10 | Untested; the `all` run plus export could be killed mid-upload (see A2-02). |
| 34 | the size line of the build step removed | Untested; also no minimum size check on the built file. |

Also: the stand-in `gh` in the tests is a model of the author's assumption, not of `gh` (A2-02: it never deletes before uploading). Add a case where a failing upload removes the old asset, and have the test assert the swap sequence once A2-02 is fixed.

---

## What I tried that held up

- **Which workflow runs on merge.** Only CI (pytest). The weekly push filter ignores `NFL/02-config/README.md` (GitHub's path-filter table: `docs/**/*.md` matches `docs/README.md`). No scheduled or push path creates the release before Tuesday; that is A2-01.
- **Unknown is not "missing".** A 502, a 403 rate limit, a timeout and a reworded message all stop the run before `gh release create` (`s3`); no duplicate release or tag. A tag without a release goes through `gh release create`, which reuses the tag (from `create.go`, not executed). A hand-edited or garbled key, a CRLF body, a missing key line or a missing asset cause exactly one rebuild, after which the notes are rewritten (`s2`, `s5`). The prefix case `1.2.1` versus `1.2.10` cannot collide because the run id is unique per publish.
- **Latest flag.** `--prerelease` plus `--latest=false` on create; the GitHub REST description says drafts and prereleases cannot be set as Latest. `gh release edit` does not pass `--latest` or `--prerelease`, so it never changes either.
- **Overlap.** Weekly and monthly use the same concurrency group `nfl-pipeline-publish` with `cancel-in-progress: false`, so two publishes never overlap; the watchdog has its own group. Two dispatches run one after the other (but see A2-09 for the pending-slot rule).
- **Injection.** Nothing from `status.csv`, inputs, commit message or upstream data is placed in a `run:` text (every value goes through `env:`; the heredoc is unquoted but only expands the workflow's own variables; command substitution output is not re-expanded). `inputs.*` and `github.*` expressions appear in no `run:` block (the existing test checks this and I confirmed it by grep). `latest_season_type` is the only upstream-derived field in the notes and comes from season types the config restricts.
- **Reach.** Triggers are `schedule`, `push` (branch `main`), `workflow_dispatch`; CI has `pull_request` with a read-only token and no release step; no `pull_request_target`, no `release` or `workflow_run` trigger. A dispatch from a non-main branch is a dry run and "Decide" is guarded by `github.ref == 'refs/heads/main'`. A fork pull request cannot reach any release step.
- **Token scope.** `GH_TOKEN` is present only in the commit, decide, publish and alert steps; `persist-credentials: false`; the build and pipeline steps run without it; the job needs `contents: write` for release creation and `issues: write` for the alert only.
- **Loops.** Releases and tags created with `GITHUB_TOKEN` start no workflow, and the push triggers are limited to `main` branches, so a new tag starts nothing.
- **Limits.** Asset 39,760,580 bytes against GitHub's 2 GiB per-asset limit; the export takes 12 s and is byte-identical on a second run (same SHA-256); the workbook artifact is stored uncompressed for 7 days (at most a few 38 MB files at a time; whether artifact storage counts against a quota for a public repository is UNVERIFIED but the volume is small). File properties carry author `NFL-Analysis pipeline`, no personal data.
- **Heartbeat.** The 16th (HEARTBEAT) never builds the workbook; the heartbeat step runs after a failed workbook step (`!cancelled()`), so a broken upload cannot let the schedules lapse.
- **Static.** `actionlint` 1.7.12 reports nothing on all four workflows; all 157 workflow tests pass.

## Appendix: scratch files (all under `NFL/.work/a2x/`, git-ignored)

`gh` (stand-in), `a2.py` (step runner), `s1.py` ... `s10.py` with `*.log` (scenarios), `swap.sh` and `s7.py` (the proposed swap), `mutate.py` and `mutation.log` (mutations), `mut/` (scratch copy of the repository files the mutations ran on).
