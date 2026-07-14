// app/i18n/useI18n.js
import { useTranslation } from "react-i18next";

export function useI18n() {
  const { t, i18n } = useTranslation();
  const rawLang = (i18n.language || "en").toLowerCase();
  const lang = rawLang.startsWith("ru") ? "ru" : rawLang.startsWith("uk") || rawLang.startsWith("ua") ? "uk" : "en";
  const isRu = lang === "ru";
  const isUk = lang === "uk";

  const setLang = async (next) => {
    const raw = (next || "en").toLowerCase();
    const v = raw.startsWith("ru") ? "ru" : raw.startsWith("uk") || raw.startsWith("ua") ? "uk" : "en";
    if (v === i18n.language) return;
    await i18n.changeLanguage(v);
  };

  return { t, i18n, lang, isRu, isUk, setLang };
}














