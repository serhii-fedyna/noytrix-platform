const fs = require("fs");
const path = require("path");

const ROOT = process.cwd();
const APP = path.join(ROOT, "app");

function walk(dir){
  let out = [];
  for (const name of fs.readdirSync(dir)){
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) out = out.concat(walk(p));
    else if (/\.(js|jsx|ts|tsx)$/.test(p)) out.push(p);
  }
  return out;
}


function cleanComments(src){
  
  src = src.replace(/^[ \t]*\/\/.*(?:"");
  
  src = src.replace(/\{\s*\/\*[^]*?(?:"");
  
  src = src.replace(/\/\*[^]*?(?:"");
  return src;
}

let changed = 0;
const changedFiles = [];

for (const file of walk(APP)){
  const before = fs.readFileSync(file, "utf8");
  const after = cleanComments(before);
  if (after !== before){
    fs.writeFileSync(file, after, "utf8");
    changed++;
    changedFiles.push(path.relative(ROOT, file));
  }
}

fs.mkdirSync(path.join(ROOT,"scripts"), {recursive:true});
fs.writeFileSync(path.join(ROOT,"scripts/comments-cleaned.txt"), changedFiles.join("\n"), "utf8");

console.log("✅ comments cleaned in files:", changed);
console.log("Saved list -> scripts/comments-cleaned.txt");





