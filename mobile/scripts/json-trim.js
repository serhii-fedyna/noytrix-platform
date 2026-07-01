const fs = require('fs');

function trimJsonFile(path) {
  const txt = fs.readFileSync(path, 'utf8');

  
  let depth = 0;
  let inStr = false;
  let esc = false;
  let started = false;

  for (let i = 0; i < txt.length; i++) {
    const ch = txt[i];

    if (!started) {
      if (ch === '{') { started = true; depth = 1; }
      else continue;
    } else {
      if (inStr) {
        if (esc) esc = false;
        else if (ch === '\\') esc = true;
        else if (ch === '"') inStr = false;
      } else {
        if (ch === '"') inStr = true;
        else if (ch === '{') depth++;
        else if (ch === '}') {
          depth--;
          if (depth === 0) {
            const slice = txt.slice(0, i + 1);
            
            const obj = JSON.parse(slice);
            fs.writeFileSync(path, JSON.stringify(obj, null, 2), 'utf8');
            console.log('✅ trimmed:', path);
            return;
          }
        }
      }
    }
  }
  throw new Error('Could not find end of first JSON object in ' + path);
}

const files = process.argv.slice(2);
if (!files.length) {
  console.log('Usage: node scripts/json-trim.js <file1> <file2> ...');
  process.exit(1);
}
for (const f of files) trimJsonFile(f);





