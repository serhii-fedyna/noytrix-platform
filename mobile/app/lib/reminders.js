import { ensurePushReady } from "./notifications";


export async function scheduleEventReminder({
  id,
  title,
  body,
  startISO,
  offsetMin = 30,
}) {
  const ok = await ensurePushReady({ request: true });
  if (!ok) {
    throw new Error("");
  }

  const start = new Date(startISO);
  if (isNaN(start.getTime())) {
    throw new Error("");
  }

  const fireAt = new Date(start.getTime() - offsetMin * 60 * 1000);
  const minFire = Date.now() + 15000;
  if (fireAt.getTime() < minFire) {
    throw new Error("");
  }

  console.log("[reminders] scheduleEventReminder skipped (OneSignal/server mode)", {
    id: id ?? null,
    title: title ?? null,
    body: body ?? null,
    startISO: startISO ?? null,
    offsetMin,
    fireAt: fireAt.toISOString(),
  });

  return null;
}

export async function cancelReminder(notifId) {
  try {
    console.log("[reminders] cancelReminder noop", { notifId: notifId ?? null });
  } catch {}
}




