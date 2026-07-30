const fs = require("fs");
const path = require("path");

const localesDir = path.join(__dirname, "..", "app", "i18n", "locales");
const readLocale = (name) => JSON.parse(fs.readFileSync(path.join(localesDir, `${name}.json`), "utf8"));

function flatten(value, prefix = "", out = {}) {
  for (const [key, child] of Object.entries(value || {})) {
    const next = prefix ? `${prefix}.${key}` : key;
    if (child && typeof child === "object") flatten(child, next, out);
    else out[next] = child;
  }
  return out;
}

const locales = Object.fromEntries(["en", "ru", "uk"].map((name) => [name, flatten(readLocale(name))]));
const referenceKeys = Object.keys(locales.en).sort();
const errors = [];

for (const [name, entries] of Object.entries(locales)) {
  const keys = Object.keys(entries).sort();
  const missing = referenceKeys.filter((key) => !(key in entries));
  const extra = keys.filter((key) => !(key in locales.en));
  const empty = keys.filter((key) => {
    const reference = locales.en[key];
    return typeof reference === "string" && reference.trim() && (typeof entries[key] !== "string" || !entries[key].trim());
  });
  if (missing.length) errors.push(`${name}: missing ${missing.join(", ")}`);
  if (extra.length) errors.push(`${name}: extra ${extra.join(", ")}`);
  if (empty.length) errors.push(`${name}: empty ${empty.join(", ")}`);
}

// These are high-confidence Russian-only words that have previously leaked
// into the Ukrainian file. Keep the rule focused so valid Ukrainian cognates
// and product names are not falsely rejected.
const russianInUkrainian = new RegExp(
  [
    "\\b\\u0441\\u0435\\u0441\\u0441\\u0438\\u044f\\b", // сессия
    "\\b\\u0441\\u043e\\u0445\\u0440\\u0430\\u043d\\u0438\\u0442\\u044c\\b", // сохранить
    "\\b\\u0432\\u043e\\u0441\\u0441\\u0442\\u0430\\u043d\\u043e\\u0432\\u0438\\u0442\\u044c\\b", // восстановить
    "\\b\\u043e\\u0431\\u043d\\u043e\\u0432\\u043b\\u0435\\u043d\\u0438\\u044f\\b", // обновления
    "\\b\\u043f\\u043e\\u043b\\u044c\\u0437\\u043e\\u0432\\u0430\\u0442\\u0435\\u043b\\u044c\\b", // пользователь
    "\\b\\u0432\\u044b\\u0431\\u0435\\u0440\\u0438\\u0442\\u0435\\b", // выберите
    "\\b\\u043d\\u0430\\u0436\\u043c\\u0438\\u0442\\u0435\\b", // нажмите
    "\\b\\u0441\\u0435\\u0439\\u0447\\u0430\\u0441\\b", // сейчас
    "\\b\\u043e\\u0448\\u0438\\u0431\\u043a\\u0430\\b", // ошибка
    "\\b\\u043f\\u0440\\u043e\\u0432\\u0435\\u0440\\u043a\\u0430\\b", // проверка
    "\\b\\u043f\\u043e\\u0434\\u043f\\u0438\\u0441\\u043a\\u0430\\b", // подписка
    "\\b\\u0431\\u0435\\u0441\\u043f\\u043b\\u0430\\u0442\\u043d\\u044b\\u0439\\b", // бесплатный
    "\\b\\u043d\\u043e\\u0440\\u043c\\u0430\\u043b\\u0438\\u0437\\u0430\\u0446\\u0438\\u044f\\b", // нормализация
    "\\b\\u0440\\u0435\\u0434\\u0438\\u0440\\u0435\\u043a\\u0442\\u044b\\b", // редиректы
    "\\b\\u0433\\u043e\\u043b\\u043e\\u0441\\u0430\\b", // голоса
    "\\b\\u0441\\u0438\\u043c\\u0443\\u043b\\u044f\\u0446\\u0438\\u044f\\b", // симуляция
    "\\b\\u043d\\u0435\\u0439\\u0442\\u0440\\u0430\\u043b\\u044c\\u043d\\u043e\\b", // нейтрально
    "\\b\\u0441\\u0434\\u0435\\u043b\\u043a\\u0430\\b", // сделка
    "\\b\\u043e\\u0442\\u043c\\u0435\\u043d\\u0430\\b", // отмена
    "\\b\\u0441\\u0446\\u0435\\u043d\\u0430\\u0440\\u0438\\u044f\\b", // сценария
    "\\b\\u0434\\u043e\\u0433\\u0430\\u0434\\u043e\\u043a\\b", // догадок
    "\\b\\u043f\\u043e\\u043a\\u0443\\u043f\\u043a\\u0430\\b", // покупка
    "\\b\\u0440\\u0430\\u0437\\u043e\\u0432\\u0430\\u044f\\b", // разовая
    "\\b\\u0446\\u0435\\u043d\\u0430\\b", // цена
  ].join("|"),
  "iu"
);
for (const [key, value] of Object.entries(locales.uk)) {
  if (typeof value === "string" && russianInUkrainian.test(value)) errors.push(`uk: Russian fragment in ${key}`);
}

if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log(`Locale parity passed: ${referenceKeys.length} keys in en, ru and uk.`);
