// scripts/i18n-locate-missing.js
const fs = require("fs");
const path = require("path");

const root = process.cwd();
const missingEnPath = path.join(root, "scripts", "missing-en.txt");
const missingRuPath = path.join(root, "scripts", "missing-ru.txt");

function listSourceFiles(dir) {
  const out = [];
  const stack = [dir];
  const exts = new Set([".js", ".jsx", ".ts", ".tsx"]);

  while (stack.length) {
    const cur = stack.pop();
    for (const ent of fs.readdirSync(cur, { withFileTypes: true })) {
      const p = path.join(cur, ent.name);
      if (ent.isDirectory()) out.push(...listSourceFiles(p));
      else if (exts.has(path.extname(ent.name))) out.push(p);
    }
  }
  return out;
}

function readLines(p) {
  return fs.readFileSync(p, "utf8").split(/\r?\n/);
}

function main() {
  if (!fs.existsSync(missingEnPath) || !fs.existsSync(missingRuPath)) {
    console.error("Run: node scripts/i18n-audit.js first (missing-en/ru.txt).");
    process.exit(1);
  }

  const missing = new Set(
    [...readLines(missingEnPath), ...readLines(missingRuPath)]
      .map((s) => s.trim())
      .filter(Boolean)
  );

  const files = listSourceFiles(path.join(root, "app"));

  const results = [];
  for (const file of files) {
    const text = fs.readFileSync(file, "utf8");
    
    const re = /(\bt\(|\bi18n\.t\()\s*["']([^"']+)["']/g;
    let m;
    while ((m = re.exec(text))) {
      const key = m[2];
      if (!missing.has(key)) continue;

      
      const before = text.slice(0, m.index);
      const line = before.split(/\r?\n/).length;

      results.push({
        key,
        file: path.relative(root, file).replace(/\\/g, "/"),
        line,
      });
    }
  }

  results.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : a.file.localeCompare(b.file) || a.line - b.line));

  const outDir = path.join(root, "scripts");
  fs.mkdirSync(outDir, { recursive: true });

  
  const csv = ["key,file,line"]
    .concat(results.map((r) => `"${r.key}","${r.file}",${r.line}`))
    .join("\n");

  fs.writeFileSync(path.join(outDir, "missing-usage.csv"), csv, "utf8");

  
  const grouped = new Map();
  for (const r of results) {
    if (!grouped.has(r.key)) grouped.set(r.key, []);
    grouped.get(r.key).push(`${r.file}:${r.line}`);
  }
  const txt = [...grouped.entries()]
    .map(([k, arr]) => `${k}\n  ${arr.join("\n  ")}\n`)
    .join("\n");
  fs.writeFileSync(path.join(outDir, "missing-usage.txt"), txt, "utf8");

  console.log(`✅ Missing usage saved: scripts/missing-usage.csv + scripts/missing-usage.txt`);
  console.log(`Keys: ${missing.size}, Occurrences: ${results.length}`);
}

main();





