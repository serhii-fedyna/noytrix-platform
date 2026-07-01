import AsyncStorage from "@react-native-async-storage/async-storage";

const K = {
  SHIELD: "history.scamshield",
  EXPLAIN: "history.explain",
  TRADES: "history.trades",
};
const safeParse = (v) => { try { return JSON.parse(v); } catch { return null; } };

async function push(key, item, limit = 200) {
  const arr = safeParse(await AsyncStorage.getItem(key)) || [];
  arr.unshift({ ...item, ts: item.ts ?? Date.now() });
  if (arr.length > limit) arr.length = limit;
  await AsyncStorage.setItem(key, JSON.stringify(arr));
  return arr;
}

export async function addShieldResult({ url, result }) {
  return push(K.SHIELD, { url, result });
}
export async function addExplainView({ symbol, verdict }) {
  return push(K.EXPLAIN, { symbol, verdict });
}
export async function addTrade({ symbol, side, pnlPct, riskPct }) {
  return push(K.TRADES, { symbol, side, pnlPct, riskPct });
}
















