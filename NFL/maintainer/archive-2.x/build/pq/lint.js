// Usage: node 05-excel/archive-2.x/build/pq/lint.js <folder with .pq files>. Needs the M parser installed under .work/legacy-1.x/t3 (npm i @microsoft/powerquery-parser).
// Scope-aware lint: flags identifier references not bound by let / function parameter / each / record field,
// unless dotted (library, e.g. Table.Join) or a known query name. Also reports which query names each file references.
const fs=require("fs"),path=require("path");
const P=require(path.resolve(__dirname,"../../../../.work/legacy-1.x/t3/node_modules/@microsoft/powerquery-parser"));
const dir=process.argv[2];
const files=fs.readdirSync(dir).filter(f=>f.endsWith(".pq")).sort();
const queries=new Set(files.map(f=>f.replace(/\.pq$/,"")));
const keyName=k=>k&&(k.literal!==undefined?k.literal:(k.identifier?k.identifier.literal:undefined));
(async()=>{
 let bad=0;
 for(const f of files){
  const src=fs.readFileSync(path.join(dir,f),"utf8");
  const r=await P.TaskUtils.tryLexParse(P.DefaultSettings,src);
  const undef=new Set(), refs=new Set();
  function els(arr){ return (arr&&arr.elements||[]).map(c=>c.node); }
  function walk(n,scope){
   if(!n||typeof n!=="object")return;
   switch(n.kind){
    case "LetExpression":{ const s=new Set(scope); const pairs=els(n.variableList); pairs.forEach(p=>s.add(keyName(p.key)));
      pairs.forEach(p=>walk(p.value,s)); walk(n.expression,s); return; }
    case "RecordExpression":{ const s=new Set(scope); const pairs=els(n.content); pairs.forEach(p=>s.add(keyName(p.key)));
      pairs.forEach(p=>walk(p.value,s)); return; }
    case "FunctionExpression":{ const s=new Set(scope); els(n.parameters.content).forEach(p=>s.add(keyName(p.name))); walk(n.expression,s); return; }
    case "EachExpression":{ const s=new Set(scope); s.add("_"); walk(n.paramater||n.expression,s); for(const k of Object.keys(n)) if(k!=="parent"&&k!=="expression") walk(n[k],s); walk(n.expression,s); return; }
    case "IdentifierExpression":{ const id=n.identifier.literal;
      if(queries.has(id)&&!scope.has(id)) refs.add(id);
      else if(!scope.has(id)&&!id.includes(".")) undef.add(id); return; }
   }
   for(const k of Object.keys(n)){ if(k==="parent")continue; const v=n[k]; if(Array.isArray(v))v.forEach(x=>walk(x,scope)); else if(v&&typeof v==="object")walk(v,scope); }
  }
  walk(r.ast,new Set());
  const srcAccess=/Excel\.CurrentWorkbook|File\.Contents|Web\.Contents|Csv\.Document/.test(src.replace(/\/\*[\s\S]*?\*\//g,"").replace(/\/\/.*$/gm,""));
  const fw = srcAccess&&refs.size? "FIREWALL VIOLATION":"ok";
  if(undef.size||fw!=="ok")bad++;
  console.log(`${f.padEnd(26)} source=${srcAccess?"yes":"no "} refs=[${[...refs].join(",")}] firewall=${fw}${undef.size?" UNDEFINED="+[...undef].join(","):""}`);
 }
 console.log(bad?bad+" problem file(s)":"lint clean");
})();
