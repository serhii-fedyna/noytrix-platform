import sqlite3
import tempfile
import unittest
from pathlib import Path

import subscriptions


class SubscriptionGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_path = subscriptions.SUBSCRIPTIONS_DB_PATH
        subscriptions.SUBSCRIPTIONS_DB_PATH = Path(self.temp.name) / "subscriptions.sqlite3"
        subscriptions.init_subscriptions_db()

    def tearDown(self):
        subscriptions.SUBSCRIPTIONS_DB_PATH = self.previous_path
        self.temp.cleanup()

    def test_store_token_cannot_move_between_accounts(self):
        subscriptions.upsert_subscription(
            user_id="account-a",
            provider="google_play",
            product_id="pro_access",
            status="active",
            purchase_token="token-1",
        )
        with self.assertRaises(subscriptions.SubscriptionOwnershipError):
            subscriptions.upsert_subscription(
                user_id="account-b",
                provider="google_play",
                product_id="pro_access",
                status="active",
                purchase_token="token-1",
            )
        self.assertEqual("account-a", subscriptions.subscription_owner_for_purchase("google_play", "token-1"))

    def test_google_purchase_event_is_idempotent(self):
        payload = {"orderId": "GPA.1", "purchaseTimeMillis": "1710000000000"}
        for _ in range(2):
            subscriptions.sync_google_play_purchase(
                user_id="account-a",
                product_type="subs",
                product_id="pro_access",
                purchase_token="token-2",
                data=payload,
                active=True,
                status="active",
                expires_at="2099-01-01T00:00:00+00:00",
            )
        conn = sqlite3.connect(subscriptions.SUBSCRIPTIONS_DB_PATH)
        try:
            count = conn.execute("SELECT COUNT(1) FROM purchase_events WHERE purchase_token='token-2'").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(1, count)

    def test_non_pro_product_does_not_grant_pro(self):
        subscriptions.sync_google_play_purchase(
            user_id="account-a",
            product_type="inapp",
            product_id="pro_ai_bot",
            purchase_token="token-bot",
            data={"orderId": "GPA.bot"},
            active=True,
            status="active",
            expires_at=None,
            grant_pro=False,
        )
        self.assertFalse(subscriptions.entitlement_status_for_user("account-a", "pro")["active"])

    def test_active_bot_cannot_keep_an_expired_pro_entitlement_alive(self):
        subscriptions.sync_google_play_purchase(
            user_id="account-a",
            product_type="subs",
            product_id="pro_access",
            purchase_token="token-pro",
            data={"orderId": "GPA.pro"},
            active=True,
            status="active",
            expires_at="2099-01-01T00:00:00+00:00",
        )
        subscriptions.sync_google_play_purchase(
            user_id="account-a",
            product_type="inapp",
            product_id="pro_ai_bot",
            purchase_token="token-bot-active",
            data={"orderId": "GPA.bot.active"},
            active=True,
            status="active",
            expires_at=None,
            grant_pro=False,
        )
        subscriptions.sync_google_play_purchase(
            user_id="account-a",
            product_type="subs",
            product_id="pro_access",
            purchase_token="token-pro",
            data={"orderId": "GPA.pro"},
            active=False,
            status="expired",
            expires_at="2020-01-01T00:00:00+00:00",
        )
        self.assertFalse(subscriptions.entitlement_status_for_user("account-a", "pro")["active"])

    def test_expired_entitlement_is_disabled_when_read(self):
        subscriptions.set_entitlement(
            user_id="account-a",
            entitlement="pro",
            is_active=True,
            expires_at="2020-01-01T00:00:00+00:00",
            source="test",
        )
        self.assertFalse(subscriptions.entitlement_status_for_user("account-a", "pro")["active"])


if __name__ == "__main__":
    unittest.main()
