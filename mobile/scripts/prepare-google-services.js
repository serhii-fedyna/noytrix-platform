const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const target = path.join(root, "android", "app", "google-services.json");
const local = path.join(root, "google-services.json");
const easFile = process.env.GOOGLE_SERVICES_JSON;
const easBase64 = process.env.GOOGLE_SERVICES_JSON_B64;

fs.mkdirSync(path.dirname(target), { recursive: true });

if (easFile && fs.existsSync(easFile)) {
  fs.copyFileSync(easFile, target);
  console.log("[google-services] copied from EAS file env");
} else if (easBase64) {
  fs.writeFileSync(target, Buffer.from(easBase64, "base64"));
  console.log("[google-services] restored from base64 env");
} else if (fs.existsSync(local)) {
  fs.copyFileSync(local, target);
  console.log("[google-services] copied from local project file");
} else if (fs.existsSync(target)) {
  console.log("[google-services] already present");
} else {
  throw new Error("google-services.json is missing. Set EAS file env GOOGLE_SERVICES_JSON or keep mobile/google-services.json locally.");
}
