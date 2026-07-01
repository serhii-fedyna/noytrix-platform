const fs = require("fs");

function read(p){ return fs.readFileSync(p, "utf8"); }
function write(p,s){ fs.writeFileSync(p, s, "utf8"); }

function stripControlChars(s){
  
  return s.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "");
}

function fixBrokenPlaceholders(s){
  // placeholder="""""""""" -> placeholder=""
  s = s.replace(/placeholder\s*=\s*"{3,}"/g, 'placeholder=""');
  s = s.replace(/placeholder\s*=\s*"{2,}/g, 'placeholder="'); 
  return s;
}

function fixStoreAuthSemicolon(p){
  let s = read(p);
  s = stripControlChars(s);

  const lines = s.split(/\r?\n/);
  const i = 18; // line 19 (0-based 18)
  if (lines[i] && !lines[i].trim().endsWith(";") && /const |let |var |create\(|persist\(|export /.test(lines[i])) {
    lines[i] = lines[i] + ";";
  }
  s = lines.join("\n");
  write(p, s);
  console.log("✅ patched:", p);
}

function fixExplainLinearGradient(p){
  let s = read(p);
  s = stripControlChars(s);

  const openCount = (s.match(/<LinearGradient\b/g) || []).length;
  const closeCount = (s.match(/<\/LinearGradient>/g) || []).length;

  if (openCount > closeCount) {
    
    const lastOpen = s.lastIndexOf("<LinearGradient");
    const after = s.slice(lastOpen);
    const hasCloseAfter = after.includes("</LinearGradient>");
    if (!hasCloseAfter) {
      
      const idxModal = s.indexOf("</Modal>", lastOpen);
      const idxSafe = s.indexOf("</SafeAreaView>", lastOpen);
      let insertAt = -1;
      if (idxModal !== -1) insertAt = idxModal;
      else if (idxSafe !== -1) insertAt = idxSafe;
      else insertAt = s.length;

      s = s.slice(0, insertAt) + "\n      </LinearGradient>\n" + s.slice(insertAt);
      console.log("✅ inserted missing </LinearGradient> in:", p);
    } else {
      console.log("ℹ️ LinearGradient seems closed after last open:", p);
    }
  } else {
    console.log("ℹ️ LinearGradient tags look balanced:", p);
  }

  s = fixBrokenPlaceholders(s);
  write(p, s);
}

function genericClean(p){
  let s = read(p);
  s = stripControlChars(s);
  s = fixBrokenPlaceholders(s);
  write(p, s);
  console.log("✅ cleaned:", p);
}

function showSnippet(p, line, ctx=10){
  const lines = read(p).split(/\r?\n/);
  const start = Math.max(0, line-1-ctx);
  const end = Math.min(lines.length-1, line-1+ctx);
  console.log("\n--- SNIPPET:", p, "around line", line, "---");
  for (let i=start;i<=end;i++){
    const n = String(i+1).padStart(5," ");
    console.log(`${n}: ${lines[i]}`);
  }
}

const targets = [
  "app/calendar.js",
  "app/explain-pro.js",
  "app/futures-pro.js",
  "app/lib/store.auth.js",
  "app/shield.js",
];


for (const p of targets){
  if (!fs.existsSync(p)) { console.log("⚠️ missing:", p); continue; }
  genericClean(p);
}


if (fs.existsSync("app/lib/store.auth.js")) fixStoreAuthSemicolon("app/lib/store.auth.js");
if (fs.existsSync("app/explain-pro.js")) fixExplainLinearGradient("app/explain-pro.js");

console.log("\n✅ done. Re-run syntax checker now.\n");





