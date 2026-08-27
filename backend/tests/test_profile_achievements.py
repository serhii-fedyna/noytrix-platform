import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.profile import create_profile_router


class ProfileAchievementPushTests(unittest.TestCase):
    def test_achievement_notification_is_sent_once(self):
        sent = []

        async def send_push(user_id, title, body, data):
            sent.append((user_id, title, body, data))
            return {"ok": True}

        with tempfile.TemporaryDirectory() as directory:
            app = FastAPI()
            app.include_router(create_profile_router(
                lambda _uid: {"identity": {"plan": "free"}},
                lambda _uid: [{"code": "first_scan", "title_en": "First Scan", "title_ru": "Первая проверка", "text_en": "Done", "text_ru": "Готово"}],
                lambda items, _lang: [{"code": item["code"], "title": item["title_en"], "text": item["text_en"]} for item in items],
                profile_db_path=Path(directory) / "profile.sqlite3",
                authenticated_user=lambda _request: "usr_test",
                authenticated_aliases=lambda _request: ["usr_test", "test@example.com"],
                send_push=send_push,
            ))
            client = TestClient(app)
            self.assertEqual(client.get("/profile/overview", params={"userId": "usr_test", "lang": "en"}).status_code, 200)
            self.assertEqual(client.get("/profile/overview", params={"userId": "usr_test", "lang": "en"}).status_code, 200)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][3]["dedupe_key"], "achievement:first_scan")


if __name__ == "__main__":
    unittest.main()
