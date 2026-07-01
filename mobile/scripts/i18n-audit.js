const fs = require("fs");
const path = require("path");

const ROOT = process.cwd();
const SRC_DIR = path.join(ROOT, "app");
const EN_PATH = path.join(ROOT, "app/i18n/locales/en.json");
const RU_PATH = path.join(ROOT, "app/i18n/locales/ru.json");

function walk(dir){
  const res=[];
  for (const item of fs.readdirSync(dir)){
    const p = path.join(dir,item);
    const st = fs.statSync(p);
    if (st.isDirectory()) res.push(...walk(p));
    else if (/\.(js|jsx|ts|tsx)$/.test(p)) res.push(p);
  }
  return res;
}

function readJson(p){ return JSON.parse(fs.readFileSync(p,"utf8")); }

function flatten(obj, prefix=""){
  const out = [];
  for (const k of Object.keys(obj||{})){
    const v = obj[k];
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) out.push(...flatten(v, key));
    else out.push(key);
  }
  return out;
}

function extractKeysFromCode(files){
  const keys = new Set();
  const re = /(\bt\(|\bi18n\.t\()\s*["'`]([^"'`]+?)["'`]\s*[\),]/g;
  for (const f of files){
    const txt = fs.readFileSync(f,"utf8");
    let m;
    while((m=re.exec(txt))!==null){
      const k = (m[2]||"").trim();
      if (k) keys.add(k);
    }
  }
  return [...keys].sort();
}

function main(){
  const files = walk(SRC_DIR);
  const codeKeys = extractKeysFromCode(files);

  fs.mkdirSync(path.join(ROOT,"scripts"), {recursive:true});
  fs.writeFileSync(path.join(ROOT,"scripts/keys-from-code.txt"), codeKeys.join("\n"), "utf8");

  const en = readJson(EN_PATH);
  const ru = readJson(RU_PATH);
  const enKeys = new Set(flatten(en));
  const ruKeys = new Set(flatten(ru));

  const missingEn = codeKeys.filter(k=>!enKeys.has(k));
  const missingRu = codeKeys.filter(k=>!ruKeys.has(k));
  const enNotRu = [...enKeys].filter(k=>!ruKeys.has(k)).sort();
  const ruNotEn = [...ruKeys].filter(k=>!enKeys.has(k)).sort();

  fs.writeFileSync(path.join(ROOT,"scripts/missing-en.txt"), missingEn.join("\n"), "utf8");
  fs.writeFileSync(path.join(ROOT,"scripts/missing-ru.txt"), missingRu.join("\n"), "utf8");
  fs.writeFileSync(path.join(ROOT,"scripts/en-not-ru.txt"), enNotRu.join("\n"), "utf8");
  fs.writeFileSync(path.join(ROOT,"scripts/ru-not-en.txt"), ruNotEn.join("\n"), "utf8");

  console.log("✅ Audit done");
  console.log("Code keys:", codeKeys.length);
  console.log("Missing EN:", missingEn.length, "-> scripts/missing-en.txt");
  console.log("Missing RU:", missingRu.length, "-> scripts/missing-ru.txt");
  console.log("EN not RU:", enNotRu.length, "-> scripts/en-not-ru.txt");
  console.log("RU not EN:", ruNotEn.length, "-> scripts/ru-not-en.txt");
}

main();





