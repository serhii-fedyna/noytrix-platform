const fs = require("fs");
const path = require("path");

let parser;
try {
  parser = require("@babel/parser");
} catch (e) {
  console.error("❌ Can't find @babel/parser. Install: npm i -D @babel/parser");
  process.exit(2);
}

const ROOT = process.cwd();
const APP = path.join(ROOT, "app");

function walk(dir){
  let out = [];
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) out = out.concat(walk(p));
    else if (/\.(js|jsx|ts|tsx)$/.test(p)) out.push(p);
  }
  return out;
}

function parseFile(file, code){
  const isTS = /\.tsx?$/.test(file);
  parser.parse(code, {
    sourceType: "module",
    sourceFilename: file,
    plugins: [
      "jsx",
      isTS ? "typescript" : null,
      "classProperties",
      "classPrivateProperties",
      "classPrivateMethods",
      "dynamicImport",
      "optionalChaining",
      "nullishCoalescingOperator",
      "objectRestSpread",
      "topLevelAwait",
    ].filter(Boolean),
    errorRecovery: false,
    allowReturnOutsideFunction: false,
  });
}

const files = fs.existsSync(APP) ? walk(APP) : [];
const errors = [];

for (const file of files) {
  const code = fs.readFileSync(file, "utf8");
  try {
    parseFile(file, code);
  } catch (e) {
    const loc = e.loc ? `${e.loc.line}:${e.loc.column}` : "";
    errors.push({
      file: path.relative(ROOT, file),
      loc,
      message: String(e.message || e),
    });
  }
}

if (errors.length) {
  console.log("❌ Syntax errors found:", errors.length);
  for (const er of errors) {
    console.log(`- ${er.file} ${er.loc}\n  ${er.message}\n`);
  }
  fs.mkdirSync(path.join(ROOT, "scripts"), { recursive: true });
  fs.writeFileSync(
    path.join(ROOT, "scripts", "syntax-errors.json"),
    JSON.stringify(errors, null, 2),
    "utf8"
  );
  console.log("Saved -> scripts/syntax-errors.json");
  process.exit(1);
}

console.log("✅ Syntax OK: no parse errors in app/**");





