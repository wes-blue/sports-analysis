# NFL/02-config: the scoring rules you edit

These four CSV files are the pipeline's only source of scoring rules. Their columns and allowed values are defined in [`../CONTRACTS.md`](../CONTRACTS.md) §1.

| File | What it controls |
|---|---|
| `pipeline_config.csv` | Season window (`StartSeason`, `EndSeason`), season types, rounding (`RoundDecimals`), extra published columns, reconciliation tolerance |
| `leagues.csv` | The list of leagues and which are active |
| `scoring_weights.csv` | Points per unit of each statistic, one column per league, with a position gate (`Applies_To`) |
| `bonus_rules.csv` | Bonus bands per league: yardage bonuses, long-touchdown bonuses, D/ST points-allowed and yards-allowed tiers |

**This repository is public**, so these rules can be read by anyone.

## Saving a change on `main` publishes it

A change to any file in this folder that reaches the `main` branch starts the weekly workflow straight away. It re-scores every season with the new rules and, if every blocking gate passes, commits the new data to [`../04-data/`](../04-data/README.md). The workbook picks it up at its next Refresh All. Nothing needs your computer.

Because of that, change these files deliberately. A mistake that the gates catch publishes nothing; a mistake they cannot catch (for example a wrong but valid weight) is published until you correct it. Every change is kept in the file's history on GitHub, so it can always be undone.

As of 2026-11-20 this has not yet run on GitHub: it starts working once the pull request is merged into `main` ([`/BLOCKERS.csv`](../../BLOCKERS.csv) Q-015).

## How to edit a file on GitHub

1. On GitHub, open this folder on the `main` branch and click the file, for example `scoring_weights.csv`.
2. Click the pencil icon (**Edit this file**). You see the file as plain text, one row per line, values separated by commas.
3. Change only the value you mean to change. Keep every comma: each row must keep the same number of values as the header row.
4. Click **Commit changes…**, write a short message (for example "ESPN_League: 6 points per passing TD"), leave **Commit directly to the `main` branch** selected, and click **Commit changes**.
5. Open the **Actions** tab. A run of the weekly NFL workflow, started by your commit, appears there. When it ends green, the new data is published.

**Safer for a bigger change:** at step 4 choose **Create a new branch … and start a pull request** instead. The tests run on the pull request, nothing is published, and merging the pull request then publishes the change.

**Editing in Excel instead:** download the file, edit it, save it with **File › Save As › CSV UTF-8 (Comma delimited) (\*.csv)**, and upload it back to this folder on GitHub (**Add file › Upload files**) under the same name. Do not choose "CSV (Comma delimited)": it writes a different text encoding, and any accented or special character then stops the pipeline with "is not UTF-8". Re-saving a file from Excel without changing a value does not count as a change.

[`../03-pipeline/AUTOMATION.md`](../03-pipeline/AUTOMATION.md) explains the workflow in more detail, including how to start a run by hand.

## What you will see afterwards

- **A mistake the pipeline can detect** (for example a misspelt statistic name or a league without a weight column) makes gate `G-CONFIG` fail. Nothing is published, the last good data stays in place, the workflow run is red, and an issue labelled `nfl-pipeline-alert-*` explains what went wrong. Fix the file the same way and the next run publishes.
- **A league whose rules you changed** no longer matches the test values stored for it (the golden sample and your ESPN lineup values were worked out with the old rules). The gates `G-GOLDEN` and `G-ESPN` then report `WARN` "not applicable" for that league and the run still publishes. Leagues you did not change keep their tests. This is the behaviour you chose ([`/BLOCKERS.csv`](../../BLOCKERS.csv) Q-013).
- **In the workbook**, after Refresh All, the Checks sheet compares the workbook's own Scoring and Bonus sheets with the rules used here and shows each difference until you make the same change there. The workbook's runbook, [`../05-excel/powerquery/README.md`](../05-excel/powerquery/README.md), lists what each check shows after a change.

## Running the pipeline by hand

Not needed: GitHub runs it. A developer with Python 3.11 or later can run it with the commands in [`../03-pipeline/README.md`](../03-pipeline/README.md).
