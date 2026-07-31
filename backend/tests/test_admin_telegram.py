import os
import sqlite3
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import admin_telegram
import product_analytics


class AdminTelegramTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_alerts_path = admin_telegram.ADMIN_ALERTS_DB_PATH
        self.previous_analytics_path = product_analytics.ANALYTICS_DB_PATH
        self.previous_env = {
            name: os.environ.get(name)
            for name in (
                "NOYTRIX_ADMIN_TELEGRAM_ENABLED",
                "NOYTRIX_ADMIN_TELEGRAM_TOKEN",
                "NOYTRIX_ADMIN_TELEGRAM_CHAT_ID",
                "NOYTRIX_ADMIN_TELEGRAM_TIMEZONE",
            )
        }
        admin_telegram.ADMIN_ALERTS_DB_PATH = Path(self.temp.name) / "alerts.sqlite3"
        product_analytics.ANALYTICS_DB_PATH = Path(self.temp.name) / "analytics.sqlite3"
        admin_telegram.init_admin_telegram_db()
        product_analytics.init_product_analytics_db()
        os.environ["NOYTRIX_ADMIN_TELEGRAM_ENABLED"] = "0"
        os.environ.pop("NOYTRIX_ADMIN_TELEGRAM_TOKEN", None)
        os.environ.pop("NOYTRIX_ADMIN_TELEGRAM_CHAT_ID", None)
        os.environ["NOYTRIX_ADMIN_TELEGRAM_TIMEZONE"] = "UTC"

    def tearDown(self):
        admin_telegram.ADMIN_ALERTS_DB_PATH = self.previous_alerts_path
        product_analytics.ANALYTICS_DB_PATH = self.previous_analytics_path
        for name, value in self.previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.temp.cleanup()

    def test_notification_is_audited_and_idempotent_without_credentials(self):
        self.assertTrue(admin_telegram.queue_admin_notification("one", "test", "hello"))
        self.assertFalse(admin_telegram.queue_admin_notification("one", "test", "hello again"))
        conn = sqlite3.connect(admin_telegram.ADMIN_ALERTS_DB_PATH)
        try:
            rows = conn.execute("SELECT event_key, status FROM admin_telegram_events").fetchall()
        finally:
            conn.close()
        self.assertEqual(rows, [("one", "queued")])

    def test_daily_summary_counts_only_backend_scans(self):
        day = date(2026, 7, 31)
        for event_id, event_name, source, kind, level, user_id in (
            ("backend-1", "scan_completed", "backend_scan", "url", "critical", "a"),
            ("backend-2", "scan_completed", "backend_scan", "wallet", "safe", "b"),
            ("backend-3", "scan_failed", "backend_scan", "contract", "", "b"),
            ("frontend-1", "scan_completed", "mobile", "token", "critical", "c"),
        ):
            product_analytics.record_product_event({
                "event_id": event_id,
                "event_name": event_name,
                "event_time": f"{day.isoformat()}T12:00:00+00:00",
                "source": source,
                "user_id": user_id,
                "properties": {"kind": kind, "level": level},
            })
        _, summary = admin_telegram.build_daily_scan_summary(day)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["completed"], 2)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["dangerous"], 1)
        self.assertEqual(summary["counts"]["links"], 1)
        self.assertEqual(summary["counts"]["wallets"], 1)
        self.assertEqual(summary["counts"]["tokens"], 0)

    @patch("admin_telegram.urlopen")
    def test_delivery_uses_telegram_only_when_enabled(self, mocked_open):
        mocked_open.return_value.__enter__.return_value.read.return_value = b'{"ok": true, "result": {"message_id": 12}}'
        os.environ["NOYTRIX_ADMIN_TELEGRAM_ENABLED"] = "1"
        os.environ["NOYTRIX_ADMIN_TELEGRAM_TOKEN"] = "test-token"
        os.environ["NOYTRIX_ADMIN_TELEGRAM_CHAT_ID"] = "123"
        event_id = admin_telegram._store_event("send-one", "test", "message")
        admin_telegram._deliver_event(event_id)
        mocked_open.assert_called_once()
        conn = sqlite3.connect(admin_telegram.ADMIN_ALERTS_DB_PATH)
        try:
            status = conn.execute("SELECT status FROM admin_telegram_events WHERE id=?", (event_id,)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(status, "sent")

    @patch("admin_telegram.urlopen")
    def test_concurrent_delivery_sends_one_telegram_message(self, mocked_open):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"ok": true, "result": {"message_id": 15}}'

        started = threading.Event()
        release = threading.Event()

        def delayed_open(*_args, **_kwargs):
            started.set()
            release.wait(timeout=2)
            return Response()

        mocked_open.side_effect = delayed_open
        os.environ["NOYTRIX_ADMIN_TELEGRAM_ENABLED"] = "1"
        os.environ["NOYTRIX_ADMIN_TELEGRAM_TOKEN"] = "test-token"
        os.environ["NOYTRIX_ADMIN_TELEGRAM_CHAT_ID"] = "123"
        event_id = admin_telegram._store_event("send-once", "test", "message")
        first = threading.Thread(target=admin_telegram._deliver_event, args=(event_id,))
        second = threading.Thread(target=admin_telegram._deliver_event, args=(event_id,))
        first.start()
        self.assertTrue(started.wait(timeout=1))
        second.start()
        second.join(timeout=1)
        release.set()
        first.join(timeout=2)
        mocked_open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
