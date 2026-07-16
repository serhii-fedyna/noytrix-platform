export function normalizeLang(value) {
  const raw = String(value || "en").toLowerCase();
  if (raw.startsWith("ru")) return "ru";
  if (raw.startsWith("uk") || raw.startsWith("ua")) return "uk";
  return "en";
}

export function pickLang(lang, ru, en, uk) {
  const normalized = normalizeLang(lang);
  if (normalized === "ru") return ru ?? en ?? uk ?? "";
  if (normalized === "uk") return uk ?? en ?? ru ?? "";
  return en ?? ru ?? uk ?? "";
}
