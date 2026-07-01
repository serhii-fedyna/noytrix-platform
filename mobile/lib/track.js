import AsyncStorage from "@react-native-async-storage/async-storage";

const HK = (uid) => `profile.${uid}:history`;
const AK = (uid) => `profile.${uid}:achievements`;

export async function track(uid, type, meta = {}) {
  if (!uid) return;
  const ev = { id: String(Date.now()), type, meta, at: new Date().toISOString() };
  try {
    const raw = await AsyncStorage.getItem(HK(uid));
    const list = raw ? JSON.parse(raw) : [];
    list.unshift(ev);
    await AsyncStorage.setItem(HK(uid), JSON.stringify(list.slice(0, 100)));
  } catch {}
}

export async function getHistory(uid) {
  try {
    const raw = await AsyncStorage.getItem(HK(uid));
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export async function getAchievements(uid) {
  try {
    const raw = await AsyncStorage.getItem(AK(uid));
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}
