import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brain import config, db, repository, service


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_path = config.BRAIN_DB_PATH
        self.previous_db_path = db.BRAIN_DB_PATH
        config.BRAIN_DB_PATH = Path(self.temp.name) / "brain.sqlite3"
        db.BRAIN_DB_PATH = config.BRAIN_DB_PATH
        db.init_db()

    def tearDown(self):
        config.BRAIN_DB_PATH = self.previous_path
        db.BRAIN_DB_PATH = self.previous_db_path
        self.temp.cleanup()

    def test_sources_and_opportunity_are_deduplicated(self):
        repository.sync_sources([{"source_key": "wallet", "name": "Wallet", "url": "https://wallet.example", "category": "wallet"}])
        source = repository.active_sources(1)[0]
        prospect_id = repository.upsert_prospect(pipeline="noytrix_partnerships", name="Wallet", domain="wallet.example", website_url="https://wallet.example", category="wallet", summary="Wallet with API")
        repository.add_evidence(prospect_id, source_url="https://wallet.example", claim_type="description", excerpt="Public API and partner programme")
        repository.add_evidence(prospect_id, source_url="https://wallet.example", claim_type="description", excerpt="Public API and partner programme")
        contact_id = repository.add_contact(prospect_id, email="partner@wallet.example", source_url="https://wallet.example")
        score = {"fit_score": 80, "revenue_score": 70, "technical_score": 75, "timing_score": 65, "contact_score": 70, "risk_penalty": 0, "overall_score": 74, "decision": "automatic_delivery", "rationale": ["evidence"]}
        repository.upsert_opportunity(prospect_id, score)
        self.assertEqual(len(repository.evidence_for_prospect(prospect_id)), 1)
        self.assertEqual(repository.first_contact(prospect_id)["id"], contact_id)
        self.assertEqual(source["source_key"], "wallet")

    @patch("brain.service.load_sources")
    @patch("brain.service.fetch_public_source")
    @patch("brain.service.generate_partnership_draft")
    @patch("brain.service._research_github_candidates", return_value={"github_candidates": 0, "github_qualified": 0, "github_drafts": 0})
    @patch("brain.service.sync_public_investor_catalog", return_value={"cataloged": 0, "errors": []})
    @patch("brain.service.auto_send_draft", return_value={"status": "sent"})
    def test_pipeline_creates_a_review_draft_from_evidence(self, auto_send, investor_sync, github_research, writer, fetch, sources):
        sources.return_value = [{"source_key": "one", "name": "Example Wallet", "url": "https://example.test", "category": "wallet"}]
        fetch.return_value = {"url": "https://example.test", "domain": "example.test", "title": "Example Wallet API", "description": "Partner ecosystem and developer API.", "text": "Developer API partnership ecosystem.", "emails": ["partners@example.test"], "relevant_links": ["https://example.test/developers"]}

        async def generated(**_kwargs):
            return {"subject": "Noytrix and Example Wallet", "body": "Hello team, we noticed your developer API and ecosystem work. Noytrix could add a practical risk-intelligence layer for suspicious links and Web3 signing flows. Would a brief 15-minute conversation next week be useful?", "model": "test"}

        writer.side_effect = generated
        result = service.run_partnership_pipeline(limit=1)
        self.assertEqual(result["prospects_seen"], 1)
        self.assertEqual(result["prospects_qualified"], 1)
        self.assertEqual(result["drafts_created"], 1)

    def test_score_thresholds_route_auto_and_manual_candidates(self):
        from brain.scoring import score_partnership

        auto_score = score_partnership(
            category="wallet",
            text="Developer API and partnership ecosystem.",
            has_business_contact=True,
            relevant_links=["https://wallet.example/developers"],
        )
        manual_score = score_partnership(
            category="web3",
            text="Open source project.",
            has_business_contact=True,
            relevant_links=[],
        )
        self.assertGreaterEqual(auto_score["overall_score"], 71)
        self.assertEqual(auto_score["decision"], "automatic_delivery")
        self.assertLessEqual(manual_score["overall_score"], 70)
        self.assertEqual(manual_score["decision"], "manual_review")

    def test_daily_delivery_summary_counts_only_recorded_facts(self):
        prospect_id = repository.upsert_prospect(
            pipeline="noytrix_partnerships", name="Example", domain="example.test",
            website_url="https://example.test", category="wallet", summary="Example",
        )
        contact_id = repository.add_contact(prospect_id, email="partner@example.test", source_url="https://example.test")
        opportunity_id = repository.upsert_opportunity(prospect_id, {
            "fit_score": 80, "revenue_score": 70, "technical_score": 75, "timing_score": 65,
            "contact_score": 70, "risk_penalty": 0, "overall_score": 74,
            "decision": "automatic_delivery", "rationale": ["evidence"],
        })
        draft_id = repository.create_draft(
            opportunity_id=opportunity_id, contact_id=contact_id, subject="Hello", body="Message body",
            evidence_ids=[], model="test",
        )
        self.assertTrue(repository.record_approval(draft_id, decision="approved", actor="test"))
        self.assertTrue(repository.start_outreach_message(draft_id, provider="smtp", idempotency_key="summary-test"))
        repository.finish_outreach_message(draft_id, sent=True, provider_message_id="<summary-test@noytrix.app>")
        self.assertTrue(repository.record_inbound_reply(
            imap_uid="1", draft_id=draft_id, kind="reply", sender="partner@example.test",
            subject="Re: Hello", snippet="Interested", received_at=db.now_iso(),
        ))
        summary = repository.outreach_daily_summary(start_at="2000-01-01T00:00:00+00:00", end_at="2100-01-01T00:00:00+00:00")
        self.assertEqual(summary, {"sent": 1, "failed": 0, "bounced": 0, "replies": 1})


if __name__ == "__main__":
    unittest.main()
