// app/i18n/index.js
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import * as Localization from "expo-localization";

import en from "./locales/en.json";
import ru from "./locales/ru.json";

const resources = {
  en: { translation: en },
  ru: { translation: ru },
};

const locales = Localization.getLocales?.() || [];
const deviceLanguage =
  (locales[0]?.languageCode || locales[0]?.languageTag || "en")
    .toString()
    .split("-")[0]
    .toLowerCase();

i18n.use(initReactI18next).init({
  resources,

  lng: deviceLanguage,
  fallbackLng: "en",
  supportedLngs: ["en", "ru"],

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














