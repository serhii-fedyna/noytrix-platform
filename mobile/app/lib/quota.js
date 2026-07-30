export const FREE_DAILY_LIMIT = 4;

function asWholeNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : fallback;
}

// The API is authoritative, but a malformed or legacy unlimited response must
// never turn a FREE account into an unlimited account in the client UI.
export function normalizeFreeQuota(raw = {}, fallbackLimit = FREE_DAILY_LIMIT) {
  const allowedLimit = Math.max(1, asWholeNumber(fallbackLimit, FREE_DAILY_LIMIT));
  const requestedLimit = asWholeNumber(raw?.freeLimit ?? raw?.limit, allowedLimit);
  const limit = requestedLimit > 0 && requestedLimit <= allowedLimit ? requestedLimit : allowedLimit;
  const used = Math.min(limit, asWholeNumber(raw?.used, 0));
  const left = Math.min(limit, asWholeNumber(raw?.left, Math.max(0, limit - used)));

  return {
    used,
    limit,
    left,
    dayKey: String(raw?.day ?? raw?.dayKey ?? ""),
  };
}
