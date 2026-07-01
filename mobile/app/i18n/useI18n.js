// app/i18n/useI18n.js
import { useTranslation } from "react-i18next";

export function useI18n() {
  const { t, i18n } = useTranslation();
  const lang = (i18n.language || "en").toLowerCase();
  const isRu = lang.startsWith("ru");

  const setLang = async (next) => {
    const v = (next || "en").toLowerCase();
    if (v === i18n.language) return;
    await i18n.changeLanguage(v);
  };

  return { t, i18n, lang, isRu, setLang };
}














