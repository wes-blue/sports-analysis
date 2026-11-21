    // ===== DataLocation resolver 2.001: IDENTICAL in every query that reads published CSVs. Never edit one copy alone. =====
    // tblConfig as a record [Setting = Value]; blank Setting rows are ignored.
    DL_ConfigTable = Table.SelectRows(
        Excel.CurrentWorkbook(){[Name = "tblConfig"]}[Content],
        each [Setting] <> null and Text.Trim(Text.From([Setting])) <> ""
    ),
    DL_Config = Record.FromList(DL_ConfigTable[Value], List.Transform(DL_ConfigTable[Setting], each Text.Trim(Text.From(_)))),
    // DataLocation: a web address starting with http (shipped: the published data on GitHub); a folder path; or blank = automatic local search
    DL_Setting = let v = Record.FieldOrDefault(DL_Config, "DataLocation", null) in if v = null then "" else Text.Trim(Text.From(v)),
    DL_IsWeb = Text.StartsWith(Text.Lower(DL_Setting), "http"),
    DL_Shipped = "https://raw.githubusercontent.com/wes-blue/sports-analysis/main/NFL/04-data/",
    // Named cell WorkbookFolder: the folder that holds this workbook (formula on the Config sheet); "" when unreadable
    DL_WorkbookFolder =
        let
            t = try Excel.CurrentWorkbook(){[Name = "WorkbookFolder"]}[Content] otherwise null,
            v = if t = null then null else (try Table.Column(t, Table.ColumnNames(t){0}){0} otherwise null)
        in
            if v = null then "" else Text.Trim(Text.From(v)),
    DL_AsFolder = (p as text) as text => let s = Text.Replace(p, "/", "\") in if Text.EndsWith(s, "\") then s else s & "\",
    DL_Parent = (folder as text) as text =>
        let f = Text.TrimEnd(Text.Replace(folder, "/", "\"), "\")
        in if Text.Contains(f, "\") then Text.BeforeDelimiter(f, "\", {0, RelativePosition.FromEnd}) & "\"
           else error Error.Record("DataLocation.Error", "Cannot work out the parent of the workbook folder '" & folder & "'. On the Config sheet, set DataLocation to " & DL_Shipped & " (the published data) or to the full path of a 04-data folder."),
    // Local search (DataLocation blank): the 04-data folder beside the workbook's folder (05-excel or 08-releases in a copy of NFL), or inside it
    DL_Candidates =
        if DL_IsWeb then {}
        else if DL_Setting <> "" then {DL_AsFolder(DL_Setting)}
        else if DL_WorkbookFolder = "" then
            error Error.Record("DataLocation.Error", "DataLocation on the Config sheet is blank, so the workbook looks for a 04-data folder on this PC, but the named cell WorkbookFolder is blank or shows an error (has the workbook been saved?). To read the published data from the web, set DataLocation to " & DL_Shipped & " ; to read a folder, save the workbook or type the folder's full path into DataLocation.")
        else if Text.StartsWith(Text.Lower(DL_WorkbookFolder), "http") then
            error Error.Record("DataLocation.Error", "DataLocation on the Config sheet is blank, so the workbook looks for a 04-data folder on this PC, but Excel reports this workbook's folder as a web address (" & DL_WorkbookFolder & "), as it does in a OneDrive or SharePoint folder. Set DataLocation to " & DL_Shipped & " to read the published data from the web, or to the LOCAL path of a 04-data folder.")
        else {DL_Parent(DL_WorkbookFolder) & "04-data\", DL_AsFolder(DL_WorkbookFolder) & "04-data\"},
    // A folder counts as found when it holds a non-empty status.csv (the pipeline always publishes it)
    DL_HasData = (folder as text) as logical => (try Binary.Length(File.Contents(folder & "status.csv")) otherwise 0) > 0,
    DL_Folder =
        if DL_IsWeb then null
        else
            let Found = List.Select(DL_Candidates, DL_HasData)
            in if List.Count(Found) > 0 then Found{0}
               else error Error.Record("DataLocation.Error", "No published pipeline data (status.csv) found in: " & Text.Combine(DL_Candidates, "  and  ") & ". On the Config sheet, set DataLocation to " & DL_Shipped & " (the published data, read from the web) or to the full path of a folder that holds status.csv."),
    // Web: a fixed site (scheme + host, e.g. https://raw.githubusercontent.com) plus RelativePath, so Excel asks for
    // credentials (Anonymous) and the privacy level once, for the site, whatever the rest of the address is.
    DL_WebBase = if Text.EndsWith(DL_Setting, "/") then DL_Setting else DL_Setting & "/",
    DL_WebRest = Text.AfterDelimiter(DL_WebBase, "://"),
    DL_WebSite =
        if not Text.Contains(DL_WebBase, "://") or Text.BeforeDelimiter(DL_WebRest, "/") = ""
        then error Error.Record("DataLocation.Error", "DataLocation on the Config sheet starts with http but is not a web address: '" & DL_Setting & "'. The published data is at " & DL_Shipped)
        else Text.BeforeDelimiter(DL_WebBase, "://") & "://" & Text.BeforeDelimiter(DL_WebRest, "/"),
    DL_WebPath = Text.AfterDelimiter(DL_WebRest, "/"),
    DL_WebAdvice = (status as number) as text =>
        if status = 404 then
            ". Nothing is published at that address. If you are setting the workbook up and this is the shipped address, the data is not on GitHub's main branch yet (the pull request has not been merged): Refresh All again once it is. Otherwise check DataLocation on the Config sheet: it must be the address of the folder that holds status.csv (shipped value " & DL_Shipped & "). A private repository also answers 404."
        else if status = 401 or status = 403 then
            ". GitHub refused the request: the address needs a login (a private repository cannot be read this way) or GitHub is limiting requests. Wait a few minutes and Refresh All again; if it stays, check DataLocation on the Config sheet."
        else if status = 408 or status = 429 or status >= 500 then
            ". GitHub is busy or limiting requests. Wait a few minutes and Refresh All again."
        else ". Check DataLocation on the Config sheet.",
    ReadData = (relativePath as text) as binary =>
        if DL_IsWeb then
            let
                Response = Web.Contents(DL_WebSite, [RelativePath = DL_WebPath & relativePath, ManualStatusHandling = {400, 401, 403, 404, 408, 429, 500, 502, 503, 504}]),
                Status = Value.Metadata(Response)[Response.Status]
            in
                if Status = 200 then Response
                else error Error.Record("DataLocation.Error", "HTTP " & Number.ToText(Status) & " reading " & DL_WebBase & relativePath & DL_WebAdvice(Status))
        else File.Contents(DL_Folder & Text.Replace(relativePath, "/", "\")),
    // Published CSV: UTF-8, comma, RFC 4180 quoting, header row; every value still text here
    ReadCsv = (relativePath as text) as table =>
        Table.PromoteHeaders(
            Csv.Document(ReadData(relativePath), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
            [PromoteAllScalars = true]
        ),
    // ===== end of DataLocation resolver =====
