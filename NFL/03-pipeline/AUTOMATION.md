# NFL automation: how GitHub runs the pipeline for you

GitHub runs everything. Your laptop does not need to be on, and you never need to install anything or open a command window. GitHub fetches the NFL statistics, scores them with the rules in `NFL/02-config`, checks the result, saves the scored files in `NFL/04-data`, and then builds the finished Excel workbook for you to download. The workbook holds values only: there is nothing to refresh in Excel.

Everything below is done on the GitHub website, in the repository `wes-blue/sports-analysis`.

## 0. Where is the latest workbook?

Always here (the link never changes, the file behind it is replaced each time):

**https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx**

- It opens as a download in your browser. Save it, open it in Excel. It has no queries, formulas or connections, so there is nothing to refresh, and Excel may show a "protected view" bar the first time: click **Enable Editing**.
- The file is about 38 MB, so the download takes a moment and Excel may need a minute to open it.
- The same file is on the repository's **Releases** page (the **Code** tab, then **Releases**, or `https://github.com/wes-blue/sports-analysis/releases`): the entry **NFL workbook (always the latest)**. Its text says which data the file holds: the season and week it runs through, when it was generated, the run that made it and how many checks passed. It is marked as a pre-release only so that it does not look like a software version; it is not one. (It may not appear in the sidebar of the repository's front page; the Releases page always lists it.)
- The **About** sheet inside the workbook says the same and tells you where to find this link again.
- **If the link says "not found"**, read "If the link says not found" below. It is one click to fix.

**When it is rebuilt.** Every time the data is published (the Tuesday, Wednesday and Thursday runs in season, the monthly run on the 1st, and after every change you make to `NFL/02-config`). A run that finds nothing new does not rebuild it, unless the file on the release is missing, empty, built from older data, or built by an older design of the workbook. In that case it rebuilds it then, so a change to how the workbook is made also reaches you without waiting for new data.

**How long after a scoring change.** You edit a file in `NFL/02-config` (section 3). The run starts within a minute, scores every season, checks and publishes, then builds the workbook. Expect roughly ten minutes from your commit to the new file (an estimate: a scoring change has not yet been timed on GitHub); the run's page shows its progress. When the run has a green tick, the link above gives the new workbook.

**Replacing the file never leaves the link empty.** The new file is uploaded first under a temporary name, checked, and only then does it take the place of the old one. The old workbook is deleted only after the new one is safely on the release, and the swap takes a second or two. If any step fails, the link keeps giving the old workbook. The run then ends red and says why (section 6). Only if the swap stops exactly halfway can the link answer "not found" until the next run puts the file back.

**If the link says not found.** Either the first build has not run yet, or a run failed halfway. Open the **Actions** tab, click **nfl-pipeline-weekly**, and look at the newest run: `https://github.com/wes-blue/sports-analysis/actions/workflows/nfl-pipeline-weekly.yml`. If it is red, click it and read the box on its summary page. Then start **Rebuild only the workbook** (section 5, one click) and open the link again when the run has a green tick. If there is a release called **nfl-workbook** that says **Draft** on the Releases page, click **Edit** and then **Publish release** (or delete it; the next run creates a proper one).

**Rebuilding it by hand, without a new data run.** Section 5, "Rebuild only the workbook".

## 1. What runs when

There are four workflows. You find them on the **Actions** tab, in the list on the left.

GitHub uses UTC. Eastern time is 4 hours behind UTC in September and October and 5 hours behind from November to February. GitHub often starts scheduled runs late, sometimes by an hour or more, so read the times as "not before".

| Workflow | When it runs | What it does |
|---|---|---|
| **nfl-pipeline-weekly** | Tuesday 15:17, Wednesday 10:17 and Thursday 10:17 UTC, September to February. **Also within a minute of every change you commit to `NFL/02-config`, to the pipeline's program code (`NFL/03-pipeline/nflpipe`) or to this workflow file**, all year. You can also start it by hand. | On a schedule it first asks "is there anything new?" (new NFL statistics, or scoring rules that differ from the ones last published). If yes, it rebuilds, checks and publishes; if not, it ends green with **SKIP** and a note saying why. After a change to `NFL/02-config` the pipeline compares your rules with the published ones: if they differ it rebuilds every season and publishes them, or tells you what is wrong with them; if they come out the same (for example a file re-saved from Excel without a change) it ends **SKIP**, because there is nothing to publish. After a change to the program code or the workflow it publishes only if something differs. In every case it then looks at the workbook and builds it if it is missing or out of date. Three attempts a week are safe: once a week is published, the later attempts skip. |
| **nfl-pipeline-monthly** | The 1st of every month at 11:23 UTC, all year, plus a short check on the 16th at 11:37 UTC. You can also start it by hand. | On the 1st it rebuilds every season, which picks up corrections the data source makes to old games. On both days it also keeps the automation switched on through the off-season (section 7). |
| **nfl-pipeline-watchdog** | Friday 14:41 and 21:47 UTC, September to February. You can also start it by hand. | Turns red if a week of games finished more than 72 hours ago and the published data still does not include it. It never changes anything. |
| **nfl-pipeline-ci** | Whenever a change to the NFL pipeline, its tests, the config or these workflows is committed or proposed in a pull request. | Runs the automatic tests. On a pull request it also does a trial run with the proposed config and shows **PASS** or **FAIL** before anything is published. |

The weekly and monthly runs wait for each other, so they never write `NFL/04-data` at the same time. A run that is already working is never stopped to make room for another one.

## 2. After the pull request is merged: the first time

Merging the pull request switched on the new workbook. **Step 1 is done:** the merge on 2026-11-21 started [run 44853664413](https://github.com/wes-blue/sports-analysis/actions/runs/44853664413), which built the workbook and uploaded it in 36 seconds, and the link in section 0 works. Steps 2 to 7 are still yours to do once, in this order. Step 1 stays here as a guide to reading a run.

1. **Watch the workbook get built (the first time, the whole run took 36 seconds).** This merge changes the pipeline's program code and the weekly workflow, and either one starts **nfl-pipeline-weekly** within a minute. Open the **Actions** tab: you should see **nfl-pipeline-ci** and **nfl-pipeline-weekly**, both named after the merge. Click the **nfl-pipeline-weekly** run (or open `https://github.com/wes-blue/sports-analysis/actions/workflows/nfl-pipeline-weekly.yml`). The result line at the top of its summary is usually **SKIP** ("the pipeline ran and found nothing to publish"); it is **PUBLISH** if NFL statistics changed in the meantime. Below it you should see `workbook: build=true; there is no nfl-workbook release yet`, then `workbook: built, ... bytes`, then `workbook: published at https://github.com/wes-blue/sports-analysis/releases/download/nfl-workbook/NFL-Analysis.xlsx`. **When the run has a green tick, the link works.** Open it and save the file. If nothing appears after five minutes, go to step 2.
   - If the run is **red**, click it and read the box on the summary page: it names the step that failed and why. Then see "If the link says not found" in section 0. Nothing you do can damage anything; a failed run leaves the data as it was.
   - If the run has no green tick but you do not want to investigate, start **Rebuild only the workbook** (section 5) and wait for its green tick.
2. **Check that Actions is allowed.** Click **Settings** (top right of the repository), then **Actions**, then **General** in the left menu.
   - **Actions permissions**: any choice that allows actions created by GitHub. The workflows use only three actions made by GitHub (checkout, setup-python, upload-artifact), each fixed to an exact version.
   - In the section about running workflows from **fork pull requests**, choose **Require approval for all external contributors**. Anyone can propose a change to a public repository; with this setting nothing they propose runs until you approve it.
   - **Workflow permissions**: leave **Read repository contents and packages permissions** selected. Each workflow asks for exactly the extra rights it needs (the weekly and monthly runs may save data, publish the workbook on the release and write alert issues; the others may not). Leave **Allow GitHub Actions to create and approve pull requests** unticked.
   - Click **Save** if you changed anything.
3. **Check two more settings.** **Settings**, **General**, scroll to **Features**: **Issues** must be ticked (problems are reported as issues, see the section Alert issues). On the same page, if you find an option about **immutable releases**, leave it off: the workbook file on the release is replaced each time, and that option forbids it. If your repository has a rule that restricts who may create tags, allow GitHub Actions to create the tag `nfl-workbook`. (Neither option is known to be on; this is a check, not a request.)
4. **Check the other checks.** The **nfl-pipeline-ci** run should have a green tick (it runs the automatic tests). If the weekly run ended **PUBLISH**, the **Code** tab also shows a newer commit by **github-actions[bot]** named `nfl-pipeline: publish NFL/04-data (weekly, push, run ...)`; after a **SKIP** there is no such commit, and that is correct.
5. **Make sure failures reach you by email.** Click your profile picture (top right), **Settings**, **Notifications**.
   - Under **System**, **Actions**: tick **Email** and choose **Only notify for failed workflows**.
   - Back on the repository page, click **Watch** (top right) and choose **All Activity**, or **Custom** with **Issues** ticked, so a new alert issue emails you.
   - GitHub sends the emails about failed *scheduled* runs to the person who last changed the schedule in the workflow files. If that is not you, the alert issues (step above) still reach you.
6. **Open the workbook in Excel and tell Claude what you see** (any message word for word, how long it took to open, whether `FF_ESPN_League` for a player and week you know matches ESPN). Excel may show a "protected view" bar: click **Enable Editing**. This is the one check only you can do.
7. **Run the watchdog once by hand** (section 5). It should end green with **HEALTHY**.

Nothing else is needed. From now on the schedule runs by itself.

## 3. Changing scoring on the GitHub website

### Editing a value

1. On the **Code** tab, open the folder `NFL`, then `02-config`, then the file, for example `scoring_weights.csv`.
2. Click the pencil icon (**Edit this file**) at the top right of the file.
3. Change the value. Keep the commas: each comma separates two cells.
4. Click **Commit changes...**. Write a short message if you like, keep **Commit directly to the main branch** selected, and click **Commit changes**.

What you will see:

- Within a minute, the **Actions** tab shows an **nfl-pipeline-weekly** run named after your commit message (and an **nfl-pipeline-ci** run with the tests).
- After a few minutes it turns green with **PUBLISH**, and a new commit by **github-actions[bot]** appears. A changed rule rebuilds every season, so all seasons get the new scores. A little later the run's summary says `workbook: published` and the link in section 0 gives the new workbook; the run is green only when the workbook is in place too. The **About** sheet's "Generated (UTC)" and run id tell you the file is the new one.
- Download the workbook again (section 0). If you changed a league that has stored test values, the run's summary lists the checks `G-GOLDEN` or `G-ESPN` as **WARN** "not applicable: rules for <League> changed". That is expected and does not stop the publish.

If you make two quick changes, the second run waits for the first. A run that is still waiting can be replaced by a newer one; it then shows as **cancelled** (grey). That is normal: the newer run includes your earlier change.

Editing the `README.md` in that folder does not start a run.

### Uploading a file saved from Excel

1. In Excel, use **File**, **Save As**, and choose **CSV UTF-8 (Comma delimited) (\*.csv)**. Do not choose "CSV (Comma delimited)": it uses a different text encoding, and any accented character then stops the run with "is not UTF-8".
2. Keep the exact file name, for example `scoring_weights.csv`. If your browser renamed a downloaded copy to `scoring_weights (1).csv`, rename it back first.
3. On GitHub open `NFL`, then `02-config`, click **Add file**, **Upload files**, drag the file in, keep **Commit directly to the main branch**, and click **Commit changes**. A file with the same name replaces the old one.

The same run starts as for an edit. Excel adds invisible extras when it saves (a marker at the start of the file, different line endings, empty trailing cells); the pipeline ignores them, so re-saving a file without changing a value changes nothing: the run ends **SKIP** with the note "no published file would change", and the workbook stays as it is.

### If you would rather check first

In step 4 of "Editing a value", choose **Create a new branch for this commit and start a pull request** instead. On the pull request page, wait for the check **nfl-pipeline-ci / config-check**. **PASS** means your change would publish cleanly. Click **Merge pull request** and the weekly run publishes it. **FAIL** means it would be held: click **Details** next to the check to see why, fix the file on the same branch, and the check runs again.

### When a change is wrong

If the file has a mistake (a misspelt statistic name, a letter where a number belongs, a league in one file but not the other, a file with the wrong name or encoding), nothing is published and the old data stays in place. You will notice in three ways:

- your commit shows a red cross on the **Code** tab and the **Actions** tab;
- GitHub emails you about the failed run (if you set that up in section 2);
- an issue named **NFL pipeline needs attention: nfl-pipeline-weekly** opens, or gets a new comment.

To see what is wrong, click the red run. The box on its summary page says, in words, what failed, for example `G-CONFIG FAIL (blocking): scoring_weights.csv: metric 'pasing_yards' is neither an nflverse column nor derived`. The same text is in the issue.

To get back to green, correct the file the same way you changed it (edit or upload) and commit to `main`. That starts a new run. When it ends **PUBLISH**, the issue closes by itself with a comment saying which run fixed it. Re-running the failed run does not help: it would check the same broken file again.

## 4. Seeing what was published

- `NFL/04-data/status.csv` shows when the data was last published and up to which week. The release text of the workbook (section 0) shows the same for the workbook.
- `NFL/04-data/run_log.csv` lists every publish.
- Each run's summary page lists the checks that warned or failed. The full check report is attached to the run as **gate-report-...** under **Artifacts** at the bottom of the summary page, kept for 30 days. In a public repository anyone signed in to GitHub can download it; it holds nothing that is not already in `NFL/04-data`.

## 5. Starting a run by hand

1. **Actions** tab, click the workflow in the list on the left (for example **nfl-pipeline-weekly**).
2. Click **Run workflow** on the right. Leave **Use workflow from** on `main`.
3. For the weekly run, fill in the form if you want:
   - **seasons**: leave `current`. `all`, a year such as `2025`, or a range such as `2017-2026` also work and skip the "is there anything new" question.
   - **dry_run**: tick it to do all the work and checks without publishing anything.
   - **force**: tick it to rebuild and publish even when nothing seems new.
   - **workbook_only**: see "Rebuild only the workbook" below.
4. Click the green **Run workflow** button. The run appears in the list after a few seconds.

A run started from any branch other than `main` is always a trial run: it checks everything and publishes nothing. **seasons** accepts only `current`, `all`, a year or a range; anything else ends red with "Bad seasons input" and does nothing.

If you start several runs quickly, GitHub keeps one waiting and drops the older waiting ones: a run that shows **Canceled** (grey) before it began was replaced by a newer one. If the newer one is not the run you wanted, start yours again.

### Rebuild only the workbook

Use this when the workbook is missing or looks wrong, and the data itself is fine.

1. **Actions** tab, click **nfl-pipeline-weekly** in the list on the left.
2. Click **Run workflow**, leave **Use workflow from** on `main`, tick **workbook_only**, and click the green **Run workflow** button. (**nfl-pipeline-monthly** has the same box; either one works.)
3. Wait for the green tick (a few minutes). The summary page says `workbook: published ...`, and the link in section 0 gives the new file.

This does not fetch new statistics and does not change `NFL/04-data`: it builds the workbook from the newest data on `main`, even if the run had to wait in the queue behind another one. The other boxes in the form are ignored when **workbook_only** is ticked. The result line is **WORKBOOK**.

If you leave **Use workflow from** on a branch other than `main`, the run cannot publish. It ends **red** with the message "workbook_only was started on ..., not main, so NOTHING was rebuilt". Start it again from `main`.

## 6. Reading the results

Each run writes a one-line result at the top of its summary page.

| Result | Colour | Meaning | What to do |
|---|---|---|---|
| PUBLISH | green | New data passed every check, was saved, and the workbook on the release was replaced. | Nothing. Download the workbook again (section 0) when you want the new data. |
| PUBLISH (dry run ...) | green | A trial run passed every check. Nothing was saved. | Nothing. |
| WORKBOOK | green | You asked for a workbook rebuild only (section 5). The workbook was rebuilt from the data on `main`. | Nothing. |
| SKIP | green | Nothing new. The note says why, for example "upstream not updated since last publish", "no published file would change" or "off-season". The workbook is only looked at: it is rebuilt just if it is missing, empty, older than the published data or built by an older design. | Nothing. |
| HEARTBEAT | green | The monthly workflow's mid-month check (section 7). | Nothing. |
| HOLD | red | A check failed, so nothing was published; the old data stays in place. | Read the box on the summary page. If it names `NFL/02-config`, fix the file (section 3). Otherwise pass the text on to whoever maintains the pipeline. |
| ERROR | red | The pipeline could not finish, for example because the data source could not be reached or a config file could not be read. Nothing was published. | Read the box on the summary page. A network problem usually clears at the next scheduled attempt. |
| STALE (watchdog) | red | A week finished more than 72 hours ago and is still not published. | Look at that week's weekly runs. The data source may simply be late. Otherwise start the weekly run by hand. |

### When the workbook fails but the data was published

The data is saved first and the workbook comes after. If the workbook step fails, the run turns **red** at the step **Decide whether to build the workbook**, **Build the workbook** or **Publish the workbook (release nfl-workbook)**, the box on the summary page says which step and why, and the issue **NFL pipeline needs attention: nfl-pipeline-weekly** (or **-monthly**) opens or gets a comment that says what failed (for example "the workbook could not be published"). The new data stays published.

What the link gives afterwards depends on where it stopped:

| Where it stopped | The link gives |
|---|---|
| Before or while uploading the new file (the usual case) | The previous workbook, unchanged. A half-finished temporary file is removed by the next run. |
| After the new file was uploaded but before the old one was removed | The previous workbook. |
| After the old one was removed and the new one could not take its name (rare) | A one-off second upload under the right name is tried at once; if that works, the new workbook. If not, "not found" until the next run, which notices the missing file and puts it back. |
| After the swap, when the check of the public address or the update of the release text failed | The new workbook if the address answers. The run is red because the text of the release still shows the older data; the next run builds the workbook once more. |

If the workbook was built but not uploaded, the run page also holds the finished file under **Artifacts** as **workbook-RUN-ATTEMPT** for 7 days, so you can still download it there. A failure of this convenience copy never turns a run red.

What to do: start **Rebuild only the workbook** (section 5). If it ends green, the problem was temporary; close the issue yourself (a rebuild by hand does not close it, because it proves nothing about the data). If it fails the same way twice, pass the text from the summary page on to whoever maintains the pipeline. You do not need to do anything for the next scheduled run: it notices that the release does not hold the published data and builds the workbook again. If you press **Re-run failed jobs** on the red run instead, that works too: it checks again and repairs what is missing.

## Alert issues

Each scheduled workflow has one alert issue of its own:

| Label | Opened when | Closed when |
|---|---|---|
| `nfl-pipeline-alert-weekly` | a weekly run ends HOLD or ERROR (for example after a wrong config change), or its workbook could not be built or uploaded | a later weekly run ends **PUBLISH** |
| `nfl-pipeline-alert-monthly` | a monthly run ends HOLD or ERROR, or its workbook could not be built or uploaded, or its heartbeat could not be saved | a later monthly run ends **PUBLISH** |
| `nfl-pipeline-alert-watchdog` | the watchdog ends STALE or ERROR | a later watchdog run ends **HEALTHY** |

The issue is titled **NFL pipeline needs attention: nfl-pipeline-...**. The first failure opens it; every further failure of the same workflow adds a comment that says what failed (the pipeline's result, or for example "the workbook could not be published") and links to the run, so you never get a pile of duplicates. It closes by itself, with a comment, only when a run of the *same* workflow proves the problem is gone. A SKIP, a heartbeat, a workbook-only rebuild or a trial run never closes it, because they prove nothing. So after a workbook failure, once the workbook is fine again, close the issue yourself unless a PUBLISH comes first. For example, while the data source is late, the weekly runs skip and the watchdog's issue stays open until the week is published and a watchdog run is healthy.

To clear an issue: fix the cause (section 3 for config mistakes), then let the next scheduled run close it, or start that workflow by hand (section 5). For the monthly issue, a hand-started monthly run that ends PUBLISH closes it. You can also close an issue yourself; the next failure opens a new one.

Only issues opened by the workflows count. In a public repository anyone can open an issue; an issue someone else opens is never touched by the automation.

## 7. The off-season

From March to August there are no games. The weekly and watchdog workflows do not run at all. The monthly workflow still runs on the 1st (it usually ends **SKIP**, or **PUBLISH** when old games were corrected) and checks again on the 16th.

GitHub switches off all scheduled workflows of a public repository after 60 days without activity in the repository (GitHub documentation, "Disabling and enabling a workflow"). To prevent that, the monthly workflow looks at the newest commit on `main` each time it runs. If nothing has been committed for 21 days, it adds one empty commit named `nfl-pipeline: heartbeat ...` that changes no file. In season, or whenever you commit something yourself, no heartbeat is needed and none is made. You will see about one heartbeat commit a month between March and August.

Changing scoring in the off-season works exactly as in season (section 3): your commit starts a run and publishes.

In late August or early September the new season's data appears and the weekly runs pick it up by themselves.

## 8. What could stop the automation, and how you would notice

| What | How you would notice | What to do |
|---|---|---|
| GitHub switched the schedules off after 60 days without activity (should not happen thanks to the heartbeat; it could if several runs in a row were dropped by GitHub) | No new runs on the **Actions** tab; a yellow banner on the workflow's page saying it was disabled. | Click the workflow, then **Enable workflow**. Do it for each NFL workflow. Then start **nfl-pipeline-monthly** by hand. |
| Actions or Issues were switched off in **Settings** | No runs at all, or red runs that say "could not list issues". | Section 2, steps 2 and 3. |
| The workbook file is missing from the release, or the release was deleted, or the release was turned into a draft | The link in section 0 answers "not found". | Nothing: the next weekly or monthly run notices and builds it again (a draft release makes the run red with a message, see "If the link says not found" in section 0). Or start **Rebuild only the workbook** (section 5) to get it now. Do not delete the release on purpose; if you do, the same applies. |
| A rule on the `main` branch requires pull requests or reviews | Weekly and monthly runs turn red at the step **Commit 04-data** or **Heartbeat** with "push rejected" or "protected branch". | Allow GitHub Actions to bypass the rule, or ask for the workflows to be changed to open pull requests. |
| GitHub dropped or delayed a scheduled run (GitHub warns this can happen at busy times) | A day without a run. | Nothing: there are three weekly attempts, two Friday watchdogs, and the watchdog turns red if a whole week is missed. |
| The data source is late or changed its files | Weekly SKIPs while games have finished; then a red watchdog with a STALE issue; or a red HOLD or ERROR naming a check. | Wait a day for lateness. A HOLD or ERROR that repeats needs the pipeline to be updated. |
| GitHub retires the versions of the three actions the workflows use | Runs turn red at **Check out repository** or **Set up Python**, with a message about a deprecated version. | Ask for the pinned action versions to be updated. |
| Failure emails go to someone else | You get no email, but the alert issues still open. | Section 2, step 6. |

Actions are free for public repositories, so there is no bill to watch.

## 9. Pausing or switching off

To pause one workflow: **Actions** tab, click the workflow, click the **...** button at the top right, **Disable workflow**. **Enable workflow** in the same place switches it back on.

To remove the automation completely, delete the four files `nfl-pipeline-*.yml` in `.github/workflows` (open each file, click the **...** button, **Delete file**, commit to `main`).

## 10. Who can do what in this public repository

- Anyone can read the code and the published data, and can open issues or propose changes.
- Only you (and anyone you give write access) can start a run by hand, change the config, or merge a proposed change.
- A change proposed by someone else runs only the tests, with read-only access, and only after you approve it (section 2, step 2). It can never publish data, change files or see anything secret. There are no secrets in these workflows.
- The workflows save only `NFL/04-data` (and the empty heartbeat commit), and replace the one file `NFL-Analysis.xlsx` on the release `nfl-workbook`. The workbook is not stored in the repository itself, so the repository does not grow by about 38 MB every week. A commit, tag or release made by a workflow never starts another workflow, so a publish cannot loop.
