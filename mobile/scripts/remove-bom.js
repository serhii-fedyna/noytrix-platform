const fs = require("fs");

const file = process.argv[2];
if (!file) {
  console.log("Usage: node scripts/remove-bom.js <path>");
  process.exit(1);
}
const buf = fs.readFileSync(file);
const BOM = Buffer.from([0xEF,0xBB,0xBF]);

let out = buf;
if (buf.slice(0,3).equals(BOM)) out = buf.slice(3);

fs.writeFileSync(file, out);
console.log("BOM cleanup finished:", file);





