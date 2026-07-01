const fs = require('fs');

const EN_PATH = 'app/i18n/locales/en.json';
const RU_PATH = 'app/i18n/locales/ru.json';
const MISSING_PATH = 'scripts/missing-en.txt'; 

function readJson(path){
  return JSON.parse(fs.readFileSync(path, 'utf8'));
}
function writeJson(path, obj){
  fs.writeFileSync(path, JSON.stringify(obj, null, 2), 'utf8');
}

function setDeep(obj, key, value){
  const parts = key.split('.');
  let cur = obj;
  for (let i=0;i<parts.length;i++){
    const p = parts[i];
    if (i === parts.length-1){
      if (cur[p] === undefined) cur[p] = value;
      return;
    }
    if (cur[p] === undefined || typeof cur[p] !== 'object' || cur[p] === null){
      cur[p] = {};
    }
    cur = cur[p];
  }
}

function guessText(lang, key){
  const k = key.toLowerCase();

  // Common-ish
  if (k.includes('errortitle')) return lang==='ru' ? '
