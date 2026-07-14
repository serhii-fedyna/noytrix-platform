// app/i18n/index.js
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import * as Localization from "expo-localization";

import en from "./locales/en.json";
import ru from "./locales/ru.json";
import uk from "./locales/uk.json";

const resources = {
  en: { translation: en },
  ru: { translation: ru },
  uk: { translation: uk },
};

const locales = Localization.getLocales?.() || [];
const deviceLanguage =
  (locales[0]?.languageCode || locales[0]?.languageTag || "en")
    .toString()
    .split("-")[0]
    .toLowerCase();

const initialLanguage =
  deviceLanguage === "ru" ? "ru" : deviceLanguage === "uk" || deviceLanguage === "ua" ? "uk" : "en";

i18n.use(initReactI18next).init({
  resources,

  lng: initialLanguage,
  fallbackLng: "en",
  supportedLngs: ["en", "ru", "uk"],

  ignoreJSONStructure: true,
  keySeparator: ".",

  returnNull: false,
  returnEmptyString: false,

  compatibilityJSON: "v3",
  interpolation: { escapeValue: false },

  
  saveMissing: true,
  missingKeyHandler: (lngs, ns, key) => {
    const lng = Array.isArray(lngs) ? lngs[0] : lngs;
    
    console.log(`[i18n-missing] ${lng}:${ns}:${key}`);
  },

  
  parseMissingKeyHandler: (key) => key,
});

export default i18n;














