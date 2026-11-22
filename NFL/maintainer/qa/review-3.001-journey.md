# Review 3.001, R2: the owner's journey and the documents

Reviewer: Q1 QA Reviewer, seat R2 of the review committee. Repository commit `dd05adb`, branch `agents/pensive-noether-dxfoz6`. Date: 2026-11-21.
Lens: a Windows owner with Excel for Microsoft 365, who prefers everything on GitHub and follows written steps literally. Nothing was changed except this report and the scratch folder `NFL/.work/r2/` (not committed).

## Verdict

**Ready after named fixes.** The workbook itself is sound: it builds in 12.5 seconds, has the sheets the contract names, opens and converts in LibreOffice without error, and its numbers are plain number cells. The documents lead with the right link and agree on the link, the file name, the version, the sheet list and the retirement of Power Query. But the first thing the owner does after the merge, following `AUTOMATION.md` section 2, will not go as written, the owner is told "about 20 MB" for a 38 MB file, and `NFL/02-config/README.md` still tells them to Refresh All. None of this is Critical, because a documented workaround for each exists, but each can leave the owner stuck or misled.

| Grade | Count |
|---|---|
| Critical | 0 |
| Major | 6 |
| Minor | 11 |

## What I ran

- `python -m nflpipe export --out NFL/.work/r2/NFL-Analysis.xlsx` from `NFL/03-pipeline`: 12.5 s, 39,760,580 bytes ("37.9 MB"), PlayerGames 180,301 rows x 98 columns, SeasonTotals 24,250 rows.
- Read every sheet with openpyxl; read the sheet XML, styles and table definitions directly from the zip; converted all sheets with LibreOffice headless (24 s, no error, all 8 sheets written).
- Counted cells in the sheet XML; estimated the effect of dropping zero cells (see "Improvements").
- Resolved every relative Markdown link and every backticked repository path in 17 documents; ran `python3 NFL/01-plan/validate_plan.py` (PASS, 0 errors); compared `BLOCKERS.csv` with its state at the merge commit `5fbad73` field by field; checked SHA-256 of both 2.001 copies.
- Read the weekly workflow's triggers and its workbook steps, and the monthly workflow's `workbook_only` input.

## The journey, followed literally

1. **Root `README.md`.** First screen: "Download NFL-Analysis.xlsx" with the stable link, then a status line saying that until the first upload the link answers "not found". Clear, and the file name matches the link. It does not say what to do about "not found". (R2-02)
2. **`NFL/README.md`.** The same link and the same warning, in the first screen. "Start here" table points to `05-excel/README.md`. All links resolve.
3. **`NFL/05-excel/README.md`.** Link, release page address, sheet table (matches the file: 8 sheets, same order), rebuild times, "Changing scoring". It says "about 20 MB" (R2-03) and "has not yet been opened in Excel" but never asks the owner to say what happens (R2-05). It does not mention the Excel "protected view" bar (R2-12).
4. **`NFL/03-pipeline/AUTOMATION.md`.** Section 0 is the best text in the set: link, what the release page shows, how long a scoring change takes. Section 2 ("After the pull request is merged: the first time") is wrong for this merge (R2-01).

Mentions of Power Query, Refresh All, privacy prompts, pasting, cloning, syncing or running Python as something the owner should do: outside `archive-2.x/` and historical records (BLOCKERS, RELEASES, MEMORY, plan.json history, QA reports) there is exactly one live instruction left: `NFL/02-config/README.md` line 16, "The workbook picks it up at its next Refresh All" (R2-06). The root README contains the phrase "no Enable Content step" (a denial, but a literal search for it, which `FR-51` names as its acceptance test, finds it; R2-12).

## Findings

### Major

**R2-01. `AUTOMATION.md` section 2 describes runs that will not start.**
Where: `NFL/03-pipeline/AUTOMATION.md` section 2, steps 1, 4, 5 and 7.
What happens: step 1 says merging "adds the files in `NFL/02-config` to `main`, which counts as a config change, so two runs start straight away: nfl-pipeline-ci and nfl-pipeline-weekly". That was true of the first merge (2026-11-20). The 3.001 merge changes only `NFL/02-config/README.md` among those files, and `nfl-pipeline-weekly.yml` excludes `*.md` from its push filter. So only `nfl-pipeline-ci` starts (the workflow files and `03-pipeline` changed). The owner sees one run, not two, is told to go to the Settings step after five minutes, and step 4 ("a newer commit by github-actions[bot]") can never be satisfied. Step 7, the only step that actually produces the workbook, comes sixth in a list of eight.
Should happen: the first action after the merge is the one that makes the link work.
Fix: rewrite section 2 for the 3.001 merge. Step 1: "Start the first workbook build" (Actions, nfl-pipeline-weekly, Run workflow, tick workbook_only), with the expected result (green tick, `workbook: published`, then the link works). Then the settings checks. Or have the orchestrator start that run itself right after the merge and tell the owner the link is live. Keep the "first merge" text only as history.

**R2-02. The "not found" warning gives the owner no action.**
Where: root `README.md` status line; `NFL/README.md` status; `NFL/05-excel/README.md` status.
What happens: all three say the link answers "not found" until the first upload, and stop. An owner who clicks the link first sees a GitHub 404 page and has no next step in the document in front of them. The remedy lives only in `AUTOMATION.md` section 2 step 7 / section 5 (see R2-01).
Fix: one added sentence in each of the three places: "If you see 'not found', the first build has not run yet: start it as in `NFL/03-pipeline/AUTOMATION.md` section 5, 'Rebuild only the workbook'." Better still, make the orchestrator run it before pointing the owner at the link, and remove the warning at release.

**R2-03. The file is about 38 MB, the documents say about 20 MB.**
Where: `NFL/05-excel/README.md` ("about 20 MB"); `AUTOMATION.md` section 10 ("about 20 MB every week"); `00-Governance/DECISIONS.md` D-042 ("about 20 MB"); `NFL/PLAN.md` lines 57, 324, 469, 471 ("20 MB ... UNVERIFIED until built"). `NFL/CONTRACTS.md` 13.5 already says "about 38 MB".
What happens: the owner is told 20 MB and downloads 38 MB (39.8 million bytes); the contract and the documents disagree. The PLAN text still calls the number unverified though it has now been measured.
Fix: replace with "about 38 MB" everywhere; in `PLAN.md` replace the "UNVERIFIED" notes with the measured figure and its date; add that it unpacks to about 400 MB of sheet data (R2-04). D-042's reasoning (over a gigabyte of history a season if committed) is stronger at 38 MB, so the decision stands.

**R2-04. Opening the file may be the same experience as the Power Query refresh, and nothing warns the owner.**
Where: the file as built; `NFL/05-excel/README.md`.
What I measured: `PlayerGames` sheet XML is 409,011,563 bytes uncompressed (38.1 MB compressed). 14.17 million cells are written (not the 17.7 million of rows x columns, because D/ST-only columns are blank on player rows). Of the 12.9 million numeric cells, 11.5 million (89%) are the number 0, and 54 of the 91 numeric columns are more than 95% zeros. LibreOffice loaded and converted the whole file in 24 s on this machine. **UNVERIFIED:** Excel's open time and memory. My estimate, from the size, is tens of seconds to a couple of minutes and one to two gigabytes of memory; 32-bit Excel or an 8 GB laptop could struggle. The owner's last attempt was abandoned at five minutes, so the first open is the real test.
Should happen: the owner is told roughly what to expect (a large file, a progress bar, do not close it), and the file is no bigger than it needs to be.
Fix: add one sentence to `05-excel/README.md` ("It is a large file, about 38 MB; Excel may take a minute to open it. If it is too slow, tell Claude."). Then consider the improvements below, the first of which cuts the sheet XML to about 117 MB.

**R2-05. No one asks the owner to report the first open, and there is no row for it in `BLOCKERS.csv`.**
Where: `00-Governance/MEMORY.md` next step 2 says "Ask the owner to open the downloaded workbook in desktop Excel and report any repair message". `BLOCKERS.csv` gained only Q-023 in this change. `NFL/05-excel/README.md` says "has not yet been opened in Excel" without a request.
What happens: the one check that only the owner can do (control C-32, NFR-15) has no row, no wording and no place to answer.
Fix: add `Q-024` ("Download the workbook from the link in `NFL/05-excel/README.md`, open it in Excel, and tell me: any repair or error message word for word; how long it took to open; whether `FF_ESPN_League` for a player you know matches ESPN"), with a default and the status "Action needed". Mention it in the root README status line.

**R2-06. `NFL/02-config/README.md` still says the workbook "picks it up at its next Refresh All".**
Where: `NFL/02-config/README.md` line 16 (section "Saving a change on `main` publishes it"). Line 40 of the same file correctly says the workflow rebuilds and replaces the workbook.
What happens: the document the owner opens to change a weight contradicts itself and tells them to do a Power Query action that no longer exists.
Fix: replace line 16's last two sentences with "The workflow then rebuilds the workbook; download it again a few minutes later (`../05-excel/README.md`)." Also line 20, "As of 2026-11-20 this has not yet run on GitHub ... Q-015", is out of date: the first run happened on 2026-11-20 (Q-015 is answered).

### Minor

**R2-07. Time for a scoring change is stated three ways.** Root README and `05-excel/README.md`: "a few minutes". `AUTOMATION.md` section 0: "about ten minutes". Neither is measured for a scoring change: a changed rule rebuilds every season, and the only measured run (the first merge) was the current season only (17 s). The export step took 12.5 s here. Fix: do one all-seasons run (`seasons: all`, dry run) and quote its time, or say "about 10 minutes" everywhere and mark it unmeasured.

**R2-08. `NFL/04-data/README.md` line 15** says the data address "is the address the NFL workbook reads by default". The workbook reads nothing. Fix: delete the clause.

**R2-09. `NFL/CONTRACTS.md` line 239** (in the retired section 9) names `05-excel/build/pq/templates/` and `05-excel/build/pq/build_pq.py`, which are now under `archive-2.x/`. This is the only live pointer to the old paths outside the archive. (`NFL/03-pipeline/tests/test_workflows.py:233` also contains `NFL/05-excel/build/x.py`, but only as a made-up test string.) Fix: prefix `archive-2.x/`, or delete the line.

**R2-10. `BLOCKERS.csv`.** Owner-written answers are intact: I compared every field against `5fbad73`; no `Answer` that the owner wrote changed. Remarks on the Claude-written fields:
- Q-015 has `Status` Answered but an empty `Answer` (the merge is the answer, visible only in git); its `Claude_Response` ends "Next: try the experimental workbook (Q-020)", which is now the wrong advice.
- Q-020's `Answer` was filled in by Claude ("Given in chat ... recorded by Claude"); it is labelled as such, which is acceptable. Its `Claude_Response` says the workbook "is published at a stable download link after every pipeline run"; nothing has been published yet. Its `Type` ("Action needed"), `Default_Used_Meanwhile` and `Options` still describe the Power Query test.
Fix: edit the Claude-written fields only; say "will be published" until it is.

**R2-11. `MEMORY.md` and `RELEASES.md` carry stale data counts.** `MEMORY.md` "Pipeline 1.2.1" bullet: "174,945 player rows plus 5,288 D/ST rows, through week 10"; `status.csv` now says week 11 (the workbook holds 180,301 rows). `RELEASES.md` repeats the week-10 counts, as written at the 2.001 release; add "(as released)". `RELEASES.md` says the workflows were "Never run on GitHub"; true at release, add the date. The 3.001 register row is an explicit placeholder; fine until release.

**R2-12. "Enable Editing" is mentioned in one place only.** `AUTOMATION.md` section 0 says Excel may show a protected view bar: click Enable Editing. The root README says "There is no Enable Content step" and the `05-excel` README says nothing. A downloaded 38 MB file will open in Protected View, where sorting and filtering do not work until Enable Editing is clicked; a literal-minded owner may think the file is broken. Fix: one line in `05-excel/README.md`, and reword the root README so it does not contain the string "Enable Content" (`FR-51` acceptance searches for it).

**R2-13. The `About` sheet is good but incomplete for this owner.** It states what the file is, version, data through ("2026 week 11 (REG)"), generated time, run id, gates, source and licence, the latest-file link (a live hyperlink), how to change scoring, and a line per sheet. Missing: (a) which column is the owner's league: the sheet line says "your leagues' fantasy points" but never names `FF_ESPN_League`; (b) "Generated (UTC)" is when the data was published, not when the workbook was built, and nothing says the latest week may still be in progress (week 11 is being played now); (c) the D/ST scale: ESPN-league D/ST points are about 100 to 300 a game (tackles and return yards count one point each, D-021), against single digits for a kicker, which will look like an error unless it is said once. Fix: three more rows in the `About` table.

**R2-14. The `Dictionary` sheet defines the 82 statistic columns only.** It does not define `FF_<League>`, `fantasy_points`, `fantasy_points_ppr`, `player_id`, `season_type`, `position_group`, `opponent_team`; the `applies_to` column is blank for nflverse rows. The `About` line says "What every stat column in PlayerGames means", which is accurate but the first column the owner wants explained is `FF_ESPN_League`. Fix: add rows for the identity and `FF_` columns (generated from the config, so they stay true).

**R2-15. Layout choices that make the first screen less useful** (all verified in the file's settings):
- Columns: `FF_Standard, FF_Half_PPR, FF_PPR, FF_League_1, FF_ESPN_League` are columns J to N; the owner's league is the fifth and is not frozen, so at 100% zoom it sits off to the right of the five frozen columns (about 67 characters wide). `position` and `team` are also scrolled away.
- Rows: `PlayerGames` is oldest first (2017 week 1) and by player id, so the first screen shows a kicker from 2017 with zeros. `SeasonTotals` sorts `POST` before `REG` within a season, so the first rows are 2017 playoffs.
- Formats: whole numbers without decimals, `FF_` with two decimals, text left, wide columns set: good. Headers are plain text with Excel's table style (banded, filter buttons): good. Headers carry raw column names (`passing_2pt_conversions`), no wrap; fine for a data sheet.
Fix: see improvements 2 and 3.

**R2-16. `Leagues`/`Scoring` notes still use Power Query-era wording.** The `Leagues` sheet note for `League_1` says "keep the League name identical in tblScoring": a table that exists in the workbook but is meaningless to a reader who cannot edit it. The `ESPN_League` note cites `06-qa/fixtures` and `06-qa/evidence` with no repository prefix. Fix: reword in `02-config/leagues.csv` (this is a config change and starts a run; do it with the next scoring edit) or tolerate.

**R2-17. `AUTOMATION.md` section 0 claims the release appears "on the right-hand side under Releases" as "NFL workbook (always the latest)".** The workflow marks it a pre-release and never Latest (`--prerelease --latest=false`). **UNVERIFIED:** whether the sidebar shows a pre-release when there is no ordinary release. The stable link does not depend on it, but the owner is told where to look. Fix: confirm on GitHub after the first upload; otherwise say "the Releases page".

### Consistency results (what agrees)

- **Link:** `https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx`, identical in every document, the workflows and the workbook's `About` sheet (307 occurrences, no variant). Tag `nfl-workbook`, file `NFL-Analysis.xlsx`, release title "NFL workbook (always the latest)": agree.
- **Version:** 3.001 is the design version in `About`, file properties (Title `NFL-Analysis 3.001`), contract 13.4, `VERSIONING.md`, `RELEASES.md` (placeholder, In progress), `PLAN.md`, `plan.json` (validator PASS). 2.001 is "Superseded by 3.001" in `RELEASES.md`.
- **Sheets:** About, PlayerGames, SeasonTotals, Leagues, Scoring, Bonus, Checks, Dictionary: same list and order in the file, `05-excel/README.md`, contract 13.2 and `PLAN.md`.
- **Rebuild times:** Tue/Wed/Thu in season, 1st of the month, and on a config change: same in README, `05-excel/README.md`, `AUTOMATION.md` and the workflows. (Cron times in `AUTOMATION.md` match the weekly file.)
- **`workbook_only`:** exists in both weekly and monthly workflows; `AUTOMATION.md` sections 0, 5, 6, 8 and contract 13.5 agree (result line WORKBOOK, never closes an alert).
- **Power Query:** described as retired in README, `NFL/README.md`, `05-excel/README.md`, `VERSIONING.md`, `CHARTER.md`, role cards, contract, `RELEASES.md`, MEMORY and plan; `plan.json` requirements and RAID entries are marked Retired or Closed. The one exception is R2-06.
- **Links and paths:** all relative Markdown links in 17 documents resolve; every backticked repository path resolves, except R2-09 and a few `.work/` scratch paths that are meant to be ignored by git.

## The archive move

- Outside `NFL/05-excel/archive-2.x/`, nothing points at the old paths except R2-09 (and the historical rows of `BLOCKERS.csv` Q-011 and Q-020, which are the owner's own questions as asked; leave them).
- `NFL/08-releases/NFL-Analysis-2.001.xlsx` exists, unmodified since commit `66adc25`, SHA-256 `ac72364839f46e35b68a2594ffcfcf50960081e12cdb08590da897eb7899da87` (matches). The archive copy has the same hash; the experimental copy is `5a254114...1d` as `RELEASES.md` and `MEMORY.md` state.
- `archive-2.x/README.md` says plainly that the folder is not maintained, why, and that the scripts were moved but not run again.

## Changing scoring (`AUTOMATION.md` section 3 and `02-config/README.md`)

The steps are clear and click-level (Code tab, `NFL`, `02-config`, pencil icon, Commit changes). What happens next is described well: within a minute a run starts, a bot commit appears, `workbook: published` on the summary, download again. Gaps: the time is unmeasured and stated two ways (R2-07); `02-config/README.md` contradicts it (R2-06); neither says that the link may briefly answer "not found" while the file is replaced (only `AUTOMATION.md` section 0 does), and the owner is not told how to confirm the new file is the new one (the `About` sheet "Generated (UTC)" and run id are the answer; say so in section 3). A wrong edit is handled well (red run, issue, plain-words box).

## Improvements to the workbook itself, with cost

1. **Write zeros in the sparse statistic columns as empty cells (columns Q onward).** Measured on the real sheet XML: 409 MB becomes about 117 MB, and deflated about 13 MB for the sheet, so the file would be about 15 MB; written cells fall from 14.2 million to about 2.8 million. This is the largest single lever on open time and memory. Cost: contract 13.3 changes ("a blank CSV value is an empty cell" becomes "...and a zero in a statistic column"), exporter and tests change, design version 3.002, a documented trade-off (a PivotTable average over a blank counts only games where the player had the statistic; sums are unchanged; `FF_` points and identity columns stay as they are). Needs the owner's say-so because it changes what AVERAGE shows. Roughly half a day.
2. **Put the owner's league first and sort for reading.** Move `FF_ESPN_League` (or the first "owner" league) directly after `player_display_name` and into the frozen block; sort `PlayerGames` newest season and week first and `SeasonTotals` `REG` before `POST` and by ESPN total descending. Cost: contract 13.2 and tests, a small exporter change, no change to values; about two hours.
3. **Offer a small second file, the latest three seasons**, as a second asset on the same release (for a laptop where the full file is slow): about a third of the rows, so roughly 5 to 12 MB (**estimate, unverified**) and a few seconds to open. Cost: an exporter option, a second upload step, a second link and one more line in each document; about half a day. Worth doing only if the first owner open of the full file is slow (R2-05, R2-04).
4. Cheap `About`/`Dictionary` additions (R2-13, R2-14): about an hour, no design change if done as content.

## What only GitHub or Excel can show

**Only GitHub:**
- That the link downloads a real file after the first run (HTTP 200 after the redirect), and that it answers 404 before it. Nobody has run the new workflow steps on GitHub: `gh release create`, `upload --clobber` and `release edit` are unexercised there.
- Whether the Releases sidebar shows a pre-release when there is no ordinary release (R2-17).
- That a `workbook_only` run started from the web form (the weekly one) is accepted and goes green, and how long the build and upload take on a runner for the 38 MB file; the contract's "well under 5 minutes" is met locally (12.5 s) but not measured there.
- How long an all-seasons scoring-change run takes (R2-07).
- That one workbook upload does not push the run past any release asset limit (limit is far above 38 MB; unverified).
- That the 3.001 merge starts only the CI run and not the weekly run (my reading of the push filter; confirm on the Actions tab).

**Only Excel (the owner's):**
- Whether the file opens with no repair message (control C-32). I can say only that the zip, the XML, the 8 tables and their column names read cleanly in openpyxl and LibreOffice; LibreOffice is more forgiving than Excel.
- How long it takes to open and how much memory it uses on the owner's laptop (R2-04), and whether Protected View behaves as R2-12 assumes.
- Whether filters, frozen panes and the 5 frozen columns look right on the owner's screen size, and whether the table style renders as banded rows.
- Whether `FF_ESPN_League` for a player and week the owner knows matches the number on ESPN's page, and whether D/ST values of 100 to 300 a game match what the owner sees (R2-13).
- Whether a PivotTable over `tblPlayerGames` is quick enough to use.

## Privacy

The report names no person. The workbook's file properties (author "NFL-Analysis pipeline"), the `About` sheet and the `Leagues` notes contain only the GitHub username in links and the phrase "the owner's ESPN league"; no name, address or local path was found in the workbook's text. The `.work/r2/` scratch files are ignored by git.
