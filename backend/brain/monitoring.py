from __future__ import annotations

import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo

from auth.emailer import outbound_sender_address

from .config import daily_report_hour, inbox_poll_seconds, report_timezone
from .inbound import process_inbound_mail_once
from .reports import notify_daily_outreach_report
from .repository import outreach_daily_summary, runtime_state, set_runtime_state


def send_daily_outreach_report_if_due(now: datetime | None = None) -> bool:
    zone = ZoneInfo(report_timezone())
    local_now = now.astimezone(zone) if now else datetime.now(zone)
    if local_now.hour < daily_report_hour():
        return False
    report_date = local_now.date().isoformat()
    state_key = "brain_daily_outreach_report_date"
    if runtime_state(state_key) == report_date:
        return False
    start = datetime.combine(local_now.date(), time.min, tzinfo=zone).astimezone(ZoneInfo("UTC"))
    end = local_now.astimezone(ZoneInfo("UTC"))
    summary = outreach_daily_summary(start_at=start.replace(microsecond=0).isoformat(), end_at=end.replace(microsecond=0).isoformat())
    notify_daily_outreach_report(report_date=report_date, sender_address=outbound_sender_address(), summary=summary)
    set_runtime_state(state_key, report_date)
    return True


async def brain_delivery_monitor_loop() -> None:
    """Run inbox and report tasks independently in the permanent worker."""
    await asyncio.sleep(30)
    next_inbox_check = 0.0
    while True:
        try:
            loop = asyncio.get_running_loop()
            now_seconds = loop.time()
            if now_seconds >= next_inbox_check:
                next_inbox_check = now_seconds + inbox_poll_seconds()
                try:
                    await asyncio.to_thread(process_inbound_mail_once)
                except Exception as exc:
                    print("[noytrix_brain] inbox monitor error:", str(exc)[:180])
            try:
                await asyncio.to_thread(send_daily_outreach_report_if_due)
            except Exception as exc:
                print("[noytrix_brain] daily report error:", str(exc)[:180])
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print("[noytrix_brain] delivery monitor loop error:", str(exc)[:180])
            await asyncio.sleep(60)
