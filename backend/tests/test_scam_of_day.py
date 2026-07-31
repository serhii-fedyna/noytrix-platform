import unittest

from scamshield.scam_of_day import _card, normalize_language, signal_id_for


class ScamOfDayTests(unittest.TestCase):
    def test_signal_id_is_stable_for_normalized_url(self):
        first = signal_id_for("reddit", "https://reddit.example/post", "https://Example.com/path/")
        second = signal_id_for("reddit", "https://reddit.example/post", "https://example.com/path")
        self.assertEqual(first, second)

    def test_language_normalization(self):
        self.assertEqual(normalize_language("ua"), "uk")
        self.assertEqual(normalize_language("ru-RU"), "ru")
        self.assertEqual(normalize_language("de"), "en")

    def test_card_uses_localized_copy_not_raw_source_title(self):
        card = _card({"id": "sod_1", "target": "bad.example", "source_title": "Raw English post", "risk_score": 90, "risk_level": "critical"}, "uk")
        self.assertEqual(card["title"], "Скам дня")
        self.assertNotIn("Raw English", card["summary"])


if __name__ == "__main__":
    unittest.main()
