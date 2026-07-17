// app/i18n/useI18n.js
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useTranslation } from "react-i18next";
import { normalizeLang } from "./lang";

export function useI18n() {
  const { t, i18n } = useTranslation();
  const lang = normalizeLang(i18n.language);
  const isRu = lang === "ru";
  const isUk = lang === "uk";

  const setLang = async (next) => {
    const v = normalizeLang(next);
    await AsyncStorage.multiSet([
      ["app.language", v],
      ["app_lang", v],
    ]);
    if (v !== normalizeLang(i18n.language)) {
      await i18n.changeLanguage(v);
    }
  };

  return { t, i18n, lang, language: lang, isRu, isUk, setLang };
}














