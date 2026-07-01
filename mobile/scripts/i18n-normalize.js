const fs = require("fs");

const files = ["app/i18n/locales/en.json", "app/i18n/locales/ru.json"];

function readJson(path){
  return JSON.parse(fs.readFileSync(path,"utf8"));
}
function sortObj(obj){
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return obj;
  const out = {};
  for (const k of Object.keys(obj).sort()){
    out[k] = sortObj(obj[k]);
  }
  return out;
}
for (const f of files){
  const obj = readJson(f);
  const sorted = sortObj(obj);
  fs.writeFileSync(f, JSON.stringify(sorted, null, 2), "utf8");
}
console.log("✅ i18n normalized: en.json + ru.json updated");





