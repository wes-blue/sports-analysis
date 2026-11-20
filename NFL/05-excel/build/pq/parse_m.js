// Usage: node NFL/05-excel/build/pq/parse_m.js [dir-or-file.pq ...]   (default: NFL/05-excel/powerquery)
// Lex+parse each .pq with Microsoft's @microsoft/powerquery-parser; prints PASS/FAIL with error details; exit code 1
// on any FAIL. The parser is not committed: install it once into scratch space with
//   npm install --prefix NFL/.work/mparser @microsoft/powerquery-parser@5.0.0
// or point NFL_M_PARSER at an existing node_modules/@microsoft/powerquery-parser folder.
const fs = require("fs"), path = require("path");
const candidates = [process.env.NFL_M_PARSER, path.join(__dirname, "../../../.work/mparser/node_modules/@microsoft/powerquery-parser"),
  path.join(__dirname, "../../../.work/legacy-1.x/t3/node_modules/@microsoft/powerquery-parser")].filter(Boolean);
const found = candidates.find(c => fs.existsSync(c));
if (!found) { console.error("Microsoft M parser not found. See the install line at the top of this file."); process.exit(2); }
const { DefaultSettings, TaskUtils } = require(found);
const args = process.argv.slice(2);
if (!args.length) args.push(path.join(__dirname, "../../powerquery"));
const files = [];
for (const a of args) {
  if (fs.statSync(a).isDirectory()) fs.readdirSync(a).filter(f => f.endsWith(".pq")).sort().forEach(f => files.push(path.join(a, f)));
  else files.push(a);
}
(async () => {
  let fail = 0;
  for (const f of files) {
    const r = await TaskUtils.tryLexParse(DefaultSettings, fs.readFileSync(f, "utf8"));
    if (r.resultKind === "Ok") console.log("PASS  " + path.basename(f));
    else { fail++; console.log("FAIL  " + path.basename(f) + " [" + r.stage + "]\n      " + (r.error && r.error.message)); }
  }
  console.log(fail ? `${fail} FAILED` : `All ${files.length} files PASS`);
  process.exit(fail ? 1 : 0);
})();
