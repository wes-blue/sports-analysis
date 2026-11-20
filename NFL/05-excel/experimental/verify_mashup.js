// Independent re-extraction of the Power Query package from an .xlsx (E2 proof).
// Reader: Microsoft's own @microsoft/connected-workbooks parser (getPackageComponents) + jszip + xmldom,
// none of which the Python build uses. Parser: Microsoft's @microsoft/powerquery-parser.
// Also an independent personal-data check (section 5): the document properties, the last-saved folder and every
// readable text of the package, the Power Query package and the Data Model; it fails if personal data reappears.
// Usage: node verify_mashup.js <workbook.xlsx> [<base.xlsx>]
//   base = the owner's private 1.005 workbook (optional; never stored in this repository).
//   Extra forbidden words (for example the owner's name, which must not be written in this public file):
//   environment variable PII_FORBID, comma-separated.
// Needs: NFL/.work/e2/cw/node_modules (npm i @microsoft/connected-workbooks) and
//        NFL/.work/legacy-1.x/t3/node_modules (@microsoft/powerquery-parser).
const fs = require("fs"), path = require("path");
const P = path.resolve(__dirname, "../..");
const CW = path.join(P, ".work/e2/cw/node_modules");
const JSZip = require(path.join(CW, "jszip"));
const { DOMParser } = require(path.join(CW, "@xmldom/xmldom"));
const { getPackageComponents } = require(path.join(CW, "@microsoft/connected-workbooks/dist/utils/mashupDocumentParser.js"));
const PQP = require(path.join(P, ".work/legacy-1.x/t3/node_modules/@microsoft/powerquery-parser"));

let failures = 0;
const ok = (cond, msg) => { console.log((cond ? "PASS  " : "FAIL  ") + msg); if (!cond) failures++; };

async function readMashup(file) {
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  let found = null;
  for (const name of Object.keys(zip.files).filter(n => /^customXml\/item\d+\.xml$/.test(n))) {
    const buf = Buffer.from(await zip.file(name).async("uint8array"));
    const text = buf[0] === 0xff && buf[1] === 0xfe ? buf.toString("utf16le").replace(/^﻿/, "") : buf.toString("utf8");
    const doc = new DOMParser().parseFromString(text, "text/xml");
    if (doc.documentElement.namespaceURI === "http://schemas.microsoft.com/DataMashup") {
      if (found) throw new Error("two DataMashup parts");
      found = { name, b64: doc.documentElement.textContent };
    }
  }
  if (!found) throw new Error("no DataMashup part");
  const c = getPackageComponents(found.b64);
  const pkg = await JSZip.loadAsync(c.packageOPC);
  const parts = {};
  for (const n of Object.keys(pkg.files)) parts[n] = Buffer.from(await pkg.file(n).async("uint8array"));
  // metadata: version(4) | xml length(4) | xml | rest
  const meta = Buffer.from(c.metadata);
  const xmlLen = meta.readUInt32LE(4);
  const metaXml = meta.slice(8, 8 + xmlLen).toString("utf8").replace(/^﻿/, "");
  return { part: found.name, c, parts, metaXml, metaRest: meta.slice(8 + xmlLen) };
}

(async () => {
  const [file, baseFile] = process.argv.slice(2);
  const mf = JSON.parse(fs.readFileSync(path.join(P, "05-excel/powerquery/manifest.json"), "utf8")).queries;
  const mash = await readMashup(file);
  console.log(`DataMashup in ${mash.part}; package parts: ${Object.keys(mash.parts).join(", ")}`);
  const s1 = mash.parts["Formulas/Section1.m"];
  ok(!!s1, "Formulas/Section1.m present");

  // 1. each query byte-identical, and nothing else in the section
  let expected = Buffer.from("section Section1;\r\n");
  for (const q of mf) {
    const pq = fs.readFileSync(path.join(P, "05-excel/powerquery", q.file));
    const member = Buffer.concat([Buffer.from(`shared ${q.name} = `), pq, Buffer.from(";")]);
    const at = s1.indexOf(member);
    ok(at >= 0 && s1.indexOf(member, at + 1) < 0, `${q.name}: '${q.file}' (${pq.length} bytes) appears byte-identical exactly once`);
    expected = Buffer.concat([expected, Buffer.from("\r\n"), member, Buffer.from("\r\n")]);
  }
  expected = expected.slice(0, expected.length - 2);
  ok(expected.equals(s1), `Section1.m (${s1.length} bytes) = section header + the ${mf.length} members and separators only`);

  // 2. Microsoft's parser: the whole section document, and its shared members
  const r = await PQP.TaskUtils.tryLexParse(PQP.DefaultSettings, s1.toString("utf8"));
  ok(r.resultKind === "Ok", "Section1.m parses with @microsoft/powerquery-parser" + (r.resultKind === "Ok" ? "" : ": " + (r.error && r.error.message)));
  let members = [];
  if (r.resultKind === "Ok") {
    const root = r.ast;
    ok(root.kind === "Section", `parsed root is a Section document (${root.kind})`);
    const arr = root.sectionMembers.elements;
    members = arr.map(m => ({ name: m.namePairedExpression.key.literal, shared: !!m.maybeSharedConstant || !!m.sharedConstant }));
    ok(members.length === 15, `parser finds ${members.length} section members`);
    ok(JSON.stringify(members.map(m => m.name)) === JSON.stringify(mf.map(q => q.name)), "member names and order = manifest");
    ok(members.every(m => m.shared), "every member is 'shared'");
  }
  for (const q of mf) {
    const one = await PQP.TaskUtils.tryLexParse(PQP.DefaultSettings, fs.readFileSync(path.join(P, "05-excel/powerquery", q.file), "utf8"));
    if (one.resultKind !== "Ok") ok(false, `${q.file} parses alone`);
  }
  ok(true, "each .pq parses on its own");

  // 3. metadata consistent with the section
  const md = new DOMParser().parseFromString(mash.metaXml, "text/xml");
  const paths = Array.from(md.getElementsByTagName("ItemPath")).map(e => e.textContent);
  const queryPaths = paths.filter(p => p.split("/").length === 2).map(p => p.split("/")[1]);
  ok(JSON.stringify(queryPaths) === JSON.stringify(mf.map(q => q.name)), `metadata query items (${queryPaths.length}) = manifest names, same order`);
  ok(paths.filter(p => p.split("/").length > 2).length === 0, "no step-level items left over");
  const ids = [];
  const items = Array.from(md.getElementsByTagName("Item"));
  const entry = (it, t) => { const e = Array.from(it.getElementsByTagName("Entry")).find(x => x.getAttribute("Type") === t); return e ? e.getAttribute("Value") : null; };
  for (const it of items) {
    const p = it.getElementsByTagName("ItemPath")[0].textContent;
    if (p.split("/").length !== 2) continue;
    const name = p.split("/")[1];
    const q = mf.find(x => x.name === name);
    ids.push(entry(it, "QueryID"));
    const fillEnabled = entry(it, "FillEnabled"), toModel = entry(it, "FillToDataModelEnabled"), objType = entry(it, "FillObjectType");
    const target = entry(it, "FillTarget");
    let want;
    if (name === "Stats_Scored") want = fillEnabled === "l0" && toModel === "l1" && objType === "sConnectionOnly";
    else if (["Check_Metrics", "Check_Reconciliation", "Check_RowCounts", "Check_Golden"].includes(name))
      want = fillEnabled === "l1" && objType === "sTable" && target === "s" + name;
    else want = fillEnabled === "l0" && objType === "sConnectionOnly" && toModel === "l0";
    ok(want, `${name}: metadata load = ${objType}${toModel === "l1" ? " + Data Model" : ""}${target ? " -> table " + target.slice(1) : ""} (manifest: ${q.load_as})`);
  }
  ok(new Set(ids).size === ids.length && ids.every(Boolean), "QueryIDs present and unique");

  // 4. compared with the base workbook: what must be byte-identical
  if (baseFile) {
    const base = await readMashup(baseFile);
    const same = (a, b) => Buffer.from(a).equals(Buffer.from(b));
    ok(same(mash.c.version, base.c.version), "version field identical to base");
    ok(same(mash.c.permissions, base.c.permissions), `permissions identical to base (${mash.c.permissionsSize} bytes)`);
    ok(same(mash.c.endBuffer, base.c.endBuffer), `permission bindings identical to base (${mash.c.endBuffer.length} bytes incl. length)`);
    ok(same(mash.parts["Config/Package.xml"], base.parts["Config/Package.xml"]), "Config/Package.xml identical to base");
    ok(same(mash.parts["[Content_Types].xml"], base.parts["[Content_Types].xml"]), "package [Content_Types].xml identical to base");
    ok(same(mash.metaRest, base.metaRest), "metadata content block identical to base");
    console.log("permissions:", Buffer.from(mash.c.permissions).toString("utf8").replace(/^﻿/, ""));
  }
  // 5. personal data (independent of pii_scan.py)
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  const core = await zip.file("docProps/core.xml").async("string");
  const tag = t => { const m = core.match(new RegExp(`<${t}[^>]*>([^<]*)</${t}>`)); return m ? m[1] : ""; };
  const allowed = ["", "NFL-Analysis Committee (Claude)", "NFL-Analysis build_queries_installed.py", "NFL-Analysis build_workbook.py", "wes-blue"];
  ok(allowed.includes(tag("dc:creator")) && allowed.includes(tag("cp:lastModifiedBy")),
     `document properties name no person (creator '${tag("dc:creator")}', lastModifiedBy '${tag("cp:lastModifiedBy")}')`);
  const wbxml = await zip.file("xl/workbook.xml").async("string");
  ok(!/absPath/.test(wbxml), "workbook.xml has no x15ac:absPath (folder where the file was last saved)");
  ok(!Object.keys(zip.files).some(n => /^(xl\/comments|xl\/threadedComments\/|xl\/persons\/|xl\/revisions\/|xl\/printerSettings\/|docProps\/custom\.xml)/.test(n)),
     "no comments, persons, revisions, printer settings or custom properties parts");
  const forbid = (process.env.PII_FORBID || "").split(",").map(x => x.trim().toLowerCase()).filter(x => x.length >= 3);
  const userRx = /[A-Za-z]:\\(?:Users|Documents and Settings)\\([^\\\/"<>|:*?\r\n]+)/gi, machRx = /<ObjectPath>([^\\<]+)\\LocalCube/g;
  const texts = [];
  for (const n of Object.keys(zip.files)) {
    if (zip.files[n].dir) continue;
    const b = Buffer.from(await zip.file(n).async("uint8array"));
    texts.push([n, b.toString("latin1").replace(/[^\x20-\x7e\r\n\t]/g, " ")]);                   // ASCII view
    for (const off of [0, 1]) texts.push([n + " (utf-16 view)", b.slice(off).toString("utf16le")]); // UTF-16LE views
  }
  for (const [n, buf] of Object.entries(mash.parts)) texts.push(["DataMashup " + n, buf.toString("utf8")]);
  texts.push(["DataMashup metadata", mash.metaXml]);
  const hits = [];
  for (const [n, t] of texts) {
    for (const m of t.matchAll(userRx)) if (!/^(U0+|you|USER)$/i.test(m[1].trim())) hits.push(`${n}: ${m[0]}`);
    for (const m of t.matchAll(machRx)) if (!/^PC0+$/.test(m[1])) hits.push(`${n}: machine ${m[1]}`);
    const low = t.toLowerCase();
    for (const w of forbid) if (low.includes(w)) hits.push(`${n}: forbidden word #${forbid.indexOf(w) + 1}`);
  }
  ok(hits.length === 0, `no Windows user folder, Data Model machine name or forbidden word (${forbid.length} words) in any part` + (hits.length ? ": " + [...new Set(hits)].slice(0, 5).join("; ") : ""));

  console.log(failures ? `${failures} FAILED` : "ALL PASS");
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
