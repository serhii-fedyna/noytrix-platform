from __future__ import annotations

import json
from scamshield.intelligence.postgres_intelligence import connect, upsert_entity


def main():
    promoted_multi_source = 0

    with connect() as conn:
        with conn.cursor() as cur:
            # SAFE RULE:
            # Only promote to malicious when indicator exists in 2+ independent sources.
            # Keywords/brand names are NOT enough for malicious verdict.
            cur.execute("""
                SELECT
                    normalized_value,
                    indicator_type,
                    array_agg(DISTINCT source_name ORDER BY source_name) AS sources,
                    COUNT(DISTINCT source_name) AS source_count,
                    MAX(risk_score) AS risk_score,
                    MAX(confidence) AS confidence
                FROM raw_indicators
                WHERE status='quarantine'
                  AND indicator_type IN ('url','domain','evm_address')
                  AND normalized_value IS NOT NULL
                  AND normalized_value <> ''
                GROUP BY normalized_value, indicator_type
                HAVING COUNT(DISTINCT source_name) >= 2
                LIMIT 50000
            """)

            for r in cur.fetchall():
                sources = list(r.get("sources") or [])
                value = r.get("normalized_value")
                typ = r.get("indicator_type")
                risk_score = int(r.get("risk_score") or 85)
                confidence = min(95, int(r.get("confidence") or 80) + 10)

                upsert_entity(
                    entity=value,
                    entity_type=typ,
                    source_name="noytrix_public_intel_multi_source",
                    status="malicious",
                    risk_score=max(85, risk_score),
                    confidence=confidence,
                    evidence=[{
                        "code": "multi_source_public_scam_match",
                        "severity": max(85, risk_score),
                        "text": "Indicator appears in multiple independent scam/phishing datasets.",
                        "sources": sources,
                    }],
                    metadata={
                        "promotion": "multi_source",
                        "sources": sources,
                        "source_count": len(sources),
                        "quarantine_origin": True,
                        "anti_false_positive_guard": True,
                    },
                )
                promoted_multi_source += 1

            # Clean old unsafe keyword-only promotions.
            cur.execute("""
                UPDATE entities
                SET
                    status = CASE
                        WHEN source_count >= 2 THEN status
                        ELSE 'observed'
                    END,
                    risk_score = CASE
                        WHEN source_count >= 2 THEN risk_score
                        ELSE LEAST(COALESCE(risk_score, 0), 45)
                    END,
                    confidence = CASE
                        WHEN source_count >= 2 THEN confidence
                        ELSE LEAST(COALESCE(confidence, 0), 55)
                    END,
                    metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
                        'anti_false_positive_cleanup',
                        jsonb_build_object(
                            'applied', true,
                            'reason', 'disabled keyword-only malicious promotion',
                            'applied_at', now()
                        )
                    )
                WHERE metadata->>'promotion' = 'obvious_scam_pattern'
            """)
            cleaned_obvious_pattern = cur.rowcount

        conn.commit()

    print(json.dumps({
        "promoted_multi_source": promoted_multi_source,
        "cleaned_old_keyword_only_promotions": cleaned_obvious_pattern,
        "mode": "anti_false_positive_safe_promotion"
    }, indent=2))


if __name__ == "__main__":
    main()
