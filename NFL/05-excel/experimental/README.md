# Experimental: the workbook with the queries already installed

**File:** `NFL/05-excel/NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx`, one folder up from this page. Its version reads **`2.001-experimental`**: it is **not a release**. The release 2.001 is the paste-ready `NFL-Analysis-2.001.xlsx` in the same folder.

## What this is

This is your own workbook (the 1.004 you built and refreshed in Excel, with the 1.005 tables added). Claude has put all 15 Power Query queries of version 2.001 inside it, so you don't paste anything. The queries read the published data **from GitHub over the web**, so the file works from any folder on your laptop, with nothing else to download.

**It has never been opened in Excel.** There is no Excel where Claude works. Everything that can be checked without Excel has been checked (section 8), but only you can find out whether Excel accepts it. If it fails, nothing is lost: the paste-ready workbook (about 30 minutes of pasting, steps on its Start_Here sheet) is the fallback.

> **Known differences from the paste-ready workbook** (also on its Cover):
> 1. Plan, Requirements, RAID, Data_Dictionary and M_Code are 1.x snapshots, for reference only.
> 2. `tblScoring` sits just below `tblLeagues`: insert sheet rows above row 17 before adding more than one new league.
> 3. There is no Start_Here sheet: this page is its guide. `../powerquery/README.md` (the runbook) explains the checks (section 5), changing scoring (section 8) and every error message (section 9).
> 4. `Metric_Check` on the Scoring sheet (a 1.x column) looks each metric up in the 1.x Data_Dictionary snapshot, so it says `NOT IN DATASET` for `dst_points_allowed_excl_def`, which the pipeline derives. Ignore it: `Check_Metrics` on the Checks sheet is the check that counts. (Left as it is because changing it would touch two more parts of the file.)

## 1. Before you start

- The data must be on GitHub's `main` branch: the pull request that brings this project there must be merged (`BLOCKERS.csv` Q-015). Until then the refresh stops with `HTTP 404 ... Nothing is published at that address` (section 6).
- Windows desktop Excel for Microsoft 365, and an internet connection.

## 2. Download and open

1. On this repository's page on GitHub, open the folder `NFL`, then `05-excel`, and click `NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx`.
2. Click the **Download raw file** button (the arrow pointing down, at the top right of the file view). Save the file anywhere, for example in Documents.
3. Open it in Excel. If Excel offers to **repair** the file, stop and go to section 6.
4. Excel opens downloaded files in **Protected View**: click **Enable Editing**. If a yellow bar says that external data connections have been disabled, click **Enable Content**.

## 3. Refresh, and answer Excel's two questions

1. **Data › Refresh All.**
2. **Credentials** (dialog *Access Web content*): choose **Anonymous** on the left; in *Select which level to apply these settings to* choose `https://raw.githubusercontent.com/`; click **Connect**. Do not choose Windows, Basic or Organizational account: the data is public.
3. **Privacy** (*Information is required about data privacy*): set **Current Workbook** to **Public** and `https://raw.githubusercontent.com/` to **Public**, then **Save**. If Excel asks you to, click Refresh All again.
   - Only if a privacy or `Formula.Firewall` message keeps coming back: Data › Get Data › Query Options › Current Workbook › Privacy › *Ignore the Privacy Levels and potentially improve performance* › OK, then Refresh All.
4. Wait. The first refresh downloads about 45 MB from GitHub and scores about 180,000 rows for five leagues. Several minutes is normal; please note how long it took.

Excel remembers both answers on this laptop. Saving the workbook is not needed for the refresh; save it afterwards if you like.

**If it worked**, the Checks sheet shows (status words and colours are explained in the runbook, section 5; the numbers grow each week):

| Table (Checks sheet) | Where | What you should see |
|---|---|---|
| `Check_Metrics` | A5 | One row per scoring statistic, every Status `OK` |
| `Check_Reconciliation` | H5 | Standard and PPR `PASS`, 100% |
| `Check_RowCounts` | R5 | 19 rows (2017–2025 REG and POST, 2026 REG), every Status `PASS`, 2026 `in_progress` |
| `Check_Golden` | AB5 | 5 leagues, each 25 of 25 matched, `PASS` |

Data › Queries & Connections should list 15 queries.

## 4. Load the other four checks (about 2 minutes)

Four check tables were installed as **connection-only** queries rather than built as sheet tables by hand (the smaller change, which cannot break the file). For each one: **Data › Queries & Connections** › right-click the query › **Load To…** › **Table** › **Existing worksheet** › type the cell › **OK**.

| Query | Cell | You should see |
|---|---|---|
| `Pipeline_Status` | `=Checks!$AI$5` | First row `Data read from` = the GitHub address; Data contract version `1` / `OK`; every league contract `OK`; every gate `PASS` |
| `Check_Parity` | `=Checks!$AO$5` | 5 rows, each `matches pipeline`, Rows_Different 0 |
| `Check_Rules_Drift` | `=Checks!$AY$5` | One row: `Workbook rules equal the rules of the published data` / `same` |
| `Check_Integrity` | `=Checks!$BF$5` | `PASS`, `PASS`, then `INFO` with the number of D/ST rows |

The target cells are labelled in row 4 of the Checks sheet. Then **save** (File › Save; keep the .xlsx format).

## 5. Check the Data Model (one look)

`Stats_Scored` also loads into the Data Model, which still holds the 1.004 version of that table. Excel should replace it at the refresh, but that can't be confirmed without Excel, so please check: **Data › Data Tools › Manage Data Model** (the Power Pivot window) › tab `Stats_Scored`. The **new** table ends with the columns `FF_Standard … FF_ESPN_League`, has **no** `headshot_url` column, and shows about **180,000** records at the bottom.

- **If you see `headshot_url`, about 174,033 records, or an error such as "The query 'Stats_Scored' or one of its inputs was modified in Power Query after this connection was added"**, rebuild the model table: Queries & Connections › right-click `Stats_Scored` › **Load To…** › untick **Add this data to the Data Model** › OK (accept the warning) › then **Load To…** again › keep *Only Create Connection* › tick **Add this data to the Data Model** › OK. The Checks tables don't use the Data Model, so they are right either way.
- **If Excel says the Data Model cannot be loaded or is damaged**, tell Claude the exact message (section 7). Claude replaced two names inside the Data Model's file (section 8); this is where that would show.

## 6. If something goes wrong

| What you see | What to do |
|---|---|
| **"We found a problem with some content … Do you want us to try to recover as much as we can?"** | Click **No**, close the file, don't save. Use the paste-ready workbook. Tell Claude the exact text. If you clicked Yes by mistake, Excel lists "Removed Records" or "Repaired Records": that list is the most useful thing to send. |
| `DataLocation.Error: HTTP 404 reading https://raw.githubusercontent.com/... Nothing is published at that address ...` | The data is not on `main` yet. Merge the pull request (Q-015), wait a minute, Refresh All. |
| `We couldn't authenticate with the credentials provided` | Data › Get Data › Data Source Settings › `https://raw.githubusercontent.com/` › Edit Permissions › Credentials › Edit › **Anonymous** › Save, then Refresh All. |
| Any other error on a query | Note the query name and the message; the runbook, section 9, lists the messages and their fixes. |

## 7. What to tell Claude

Reply in chat or in `BLOCKERS.csv` (Q-020), in this order:
1. Did it open **without a repair message**? If not, the message word for word (section 6).
2. Did **Refresh All** finish? How long did it take? Which questions did Excel ask (credentials, privacy), and what did you answer?
3. What do the Checks tables show (sections 3 and 4)? Anything not green: the table, the row and its Status or Worst_Examples text. A screenshot is fine.
4. The Data Model check (section 5): what the `Stats_Scored` tab showed, and whether you had to rebuild it.
5. Any error message, word for word, with the query name.

If it works and you save it, the saved file can become the next version: Claude checks it against the source first. The file itself is never released as 2.001.

## 8. Technical note (what Claude changed inside the file)

Built by `build_queries_installed.py` from the owner's private Excel-authored 1.005 workbook, passed with `--base` (it is never copied into this repository and never modified; the build checks its SHA-256). The build edits the XML directly (no openpyxl save) and gives the same output bytes on every run. The base's query package, Data Model and Checks parts come from the Excel-saved release 1.004.

**Power Query package** (`customXml/item1.xml`, the DataMashup, format MS-QDEFF):
- `Formulas/Section1.m` replaced: `section Section1;` then `shared <Name> = <exact bytes of <Name>.pq>;` for the 15 queries in `manifest.json` order (Excel's own layout, CRLF between members; the `.pq` text keeps its LF line endings).
- Metadata: one item per query. Excel's items for the 8 existing queries are kept with their load settings (`Stats_Scored` → Data Model; four Checks tables; three connection-only queries), except that `Check_RowCounts` gets its 9 column names and types and `Check_Golden`'s recovery column becomes AB. The 7 new queries get connection-only items cloned from Excel's own `Golden_Keys` item. The 66 step-level items of the old queries are dropped; Excel rebuilds them.
- Kept byte-identical: `Config/Package.xml`, the package's `[Content_Types].xml`, the permissions (firewall on, Public), the permission bindings and the metadata content block. The bindings no longer match the changed package; Microsoft's `@microsoft/connected-workbooks` library does the same and Excel opens its output. Excel then uses default privacy settings, which is why it asks the privacy question.

**Workbook parts:**
- `xl/connections.xml`: 7 connection-only connections added, in the form Excel wrote for `Golden_Keys`.
- Checks sheet: cached 1.004 results cleared; `Check_RowCounts` widened from 3 to 9 columns (table and queryTable); `Check_Golden` moved to AB5; labelled anchors for the four checks of section 4.
- Data: `tblConfig` (adds `ReconcileTolerance`, and `DataLocation` = `https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/`), the `WorkbookFolder` name, `tblLeagues`, `tblScoring` and `tblBonus` rewritten from `NFL/02-config/` (rows added or removed as the files need), `tblGolden` from `NFL/06-qa/fixtures/golden_sample.csv`, the new table `tblGoldenRules` beside it from `fixture_contracts.csv` (read by `Pipeline_Status`), notes, the nflverse attribution with the licence's and the repository's addresses on the Cover (B36), version strings `2.001-experimental` (Cover B4 `WorkbookVersion`, Version_Log, file Title and Version), the missing 1.006 row in Version_Log (from `../build/version_history.csv`) and the "Known differences" box.
- 1.x snapshot sheets (Plan, Requirements, RAID): 58 cells (Plan 25, Requirements 18, RAID 15; 57 shared strings) cited the owner's private 1.x source transcript by line, quoted the owner's chat answers, or repeated a critical remark about a third-party project. Their text is reworded neutrally (a citation becomes "1.x brief" or is dropped). Only the text of those shared strings changes, not the sheets themselves; the build checks that no other sheet uses them.
- **Storage:** every part is stored the way the base stores it: `xl/model/item.data` uncompressed (STORED, as Excel wrote it), every other part deflated, with the base entries' dates and attributes.
- One part added (`tblGoldenRules`, with its relationship and content type); none removed.

**Personal data.** The base file is the owner's, and Excel stores personal details in such files. Every part was searched, including the inside of the Power Query package and the readable strings of the Data Model:

| Found in the base | Done |
|---|---|
| `docProps/core.xml` *last modified by*: the owner's full name | Replaced by `NFL-Analysis build_queries_installed.py` |
| `xl/workbook.xml` `x15ac:absPath`: the folder the file was last saved in, which includes the Windows user name | Removed (Excel writes it again at the next save, on your laptop only) |
| Data Model (`xl/model/item.data`) backup log: the Windows user folder in 8.3 short form, 797 times, in the temporary paths Excel wrote when it saved the model | Each occurrence overwritten in place by a neutral placeholder of the same length (`U0000000`), so no size or offset in the Data Model changes |
| Data Model partition list: the machine name, once | Overwritten in place by `PC0000000000` (same length) |
| (consequence of the two rows above) The Data Model keeps a CRC-32 checksum after each of its 790 inner files, including the two edited ones (the backup log `LOG` and the partition list `PARTITIONS`) | Both checksums recomputed, so all 790 are valid, as in the base. (Builds before this one left these two checksums stale.) |
| 1.x snapshot text (Requirements, M_Code and Data_Dictionary sheets): four mentions of private-repository folder names | Replaced by neutral words |

Not found: comments, people lists, revision logs, printer settings, custom properties, external links, e-mail addresses, other user folders; all data connections point inside the workbook; all defined names refer to cells in the workbook. The Data Model's 788 compressed inner files (the 1.004 `Stats_Scored` table, public NFL statistics, and the model definition) are decompressed by the scan and searched too: no user folder, machine name or other personal data. **What remains and why:** the workbook keeps a random document GUID and the save timestamps Excel wrote, which identify no person.

**How it was checked here** (`verify_queries_installed.py`, `verify_mashup.js`; both pass, and both fail if personal data reappears):
- The package was read back with Microsoft's own connected-workbooks parser plus jszip and xmldom, none of which the build uses. Each `.pq` appears byte-identical exactly once and `Section1.m` contains nothing else; Microsoft's `@microsoft/powerquery-parser` parses it as 15 shared members in manifest order; the metadata lists the same 15 names with the expected load settings.
- Open XML: 117 parts, valid CRCs, every XML part well formed, every part has a content type, every relationship resolves; table ids and names unique; each query table's fields match its columns, connection and `ExternalData` name.
- Compared with the base: the changed parts are exactly the intended ones; every part has the base's compression method (and so does each part inside the Power Query package); the Data Model has the same size, header and file directory, every changed byte belongs to a neutral placeholder or to the checksum of one of the two edited inner files, all 790 checksums are valid, every path in its backup log still starts with the log's own root folder, and all 788 data files decompress to the sizes the log records.
- Data: the tables equal `NFL/02-config/` and the fixtures, cell for cell.
- Personal data: `NFL/05-excel/build/pii_scan.py --candid` over every part and every Data Model inner file (it also fails if a private-transcript reference or the third-party remark comes back), plus the independent check in `verify_mashup.js`.
- LibreOffice headless recalculation (ignores Power Query): 267 formulas, 0 errors.

**Only Excel can confirm these, most likely to cause trouble first:**
1. **The first web refresh**: the credentials and privacy questions (section 3), and that every file arrives. The web reading uses the same Power Query function that read nflverse from github.com in real Excel in 1.003 and 1.004.
2. **Data Model refresh of `Stats_Scored`** (section 5), including the two names overwritten inside the Data Model's file. Their checksums are now correct, and the change is the same kind of difference as a workbook saved by another user on another PC, which Excel opens routinely; Excel's restore of the edited model itself is still untested.
3. **The privacy prompt** after the stale permission bindings: expected to be a question, not a refusal (connected-workbooks precedent, not tested on this file).
4. **The edited query tables** (`Check_RowCounts` widened, `Check_Golden` moved) and the added table `tblGoldenRules`.
5. **Mixed line endings in `Section1.m`** (M accepts both; Excel may rewrite them as CRLF when it saves) and the dropped step-level metadata.

**Rebuilding** (needs the owner's private base file; a session without it gets a clear message): from the repository root,
`python3 NFL/05-excel/experimental/build_queries_installed.py --base <path to the owner's 1.005 workbook>`, then
`python3 NFL/05-excel/experimental/verify_queries_installed.py --base <same path>` and
`node NFL/05-excel/experimental/verify_mashup.js NFL/.work/rc/NFL-Analysis-2.001-queries-installed-EXPERIMENTAL.xlsx <same path>`.
The output goes to `NFL/.work/rc/`; the orchestrator promotes the verified file into this folder.
