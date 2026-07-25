// app/lib/backend.js
import Constants from "expo-constants";

const EXTRA =
  Constants?.expoConfig?.extra ||
  Constants?.manifest?.extra ||
  Constants?.manifest2?.extra?.expoClient?.extra ||
  {};

export const BACKEND = String(EXTRA?.EXPO_PUBLIC_API || "https://noytrix.com").replace(/\/+$/, "");


export const CHAT_PATH   = "/api/chat";
export const EVENTS_PATH = "/events";
export const SCAN_PATH   = "/scan";          


export const API = {
  health:        `${BACKEND}/auth/health`,

  
  registerStart: `${BACKEND}/auth/register/start`,
  registerVerify:`${BACKEND}/auth/register/verify`,
  registerDone:  `${BACKEND}/auth/register/complete`, 
  login:         `${BACKEND}/auth/login`,
  googleLogin:   `${BACKEND}/auth/google`,

  
  resetStart:    `${BACKEND}/auth/reset/start`,
  resetConfirm:  `${BACKEND}/auth/reset/confirm`,

  
  tokenRefresh:  `${BACKEND}/auth/token/refresh`,

  
  events:        `${BACKEND}${EVENTS_PATH}`,

  
  scan:          `${BACKEND}${SCAN_PATH}`,

  
  chat:          `${BACKEND}${CHAT_PATH}`,
};














