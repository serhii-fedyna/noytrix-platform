from scamshield.intelligence.postgres_intelligence import connect, init_schema

SQL = """
CREATE TABLE IF NOT EXISTS source_feeds (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT 'public_database',
    url TEXT,
    trust_level INTEGER NOT NULL DEFAULT 50,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_import_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS raw_indicators (
    id BIGSERIAL PRIMARY KEY,
    feed_id BIGINT REFERENCES source_feeds(id) ON DELETE SET NULL,
    source_name TEXT NOT NULL,
    raw_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    indicator_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'quarantine',
    confidence INTEGER NOT NULL DEFAULT 50,
    risk_score INTEGER NOT NULL DEFAULT 0,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    seen_count INTEGER NOT NULL DEFAULT 1,
    raw_record JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(source_name, normalized_value, indicator_type)
);

CREATE INDEX IF NOT EXISTS idx_raw_indicators_norm ON raw_indicators(normalized_value);
CREATE INDEX IF NOT EXISTS idx_raw_indicators_type ON raw_indicators(indicator_type);
CREATE INDEX IF NOT EXISTS idx_raw_indicators_status ON raw_indicators(status);
CREATE INDEX IF NOT EXISTS idx_raw_indicators_score ON raw_indicators(risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_raw_indicators_seen ON raw_indicators(last_seen_at DESC);
"""

def main():
    init_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL)
        conn.commit()
    print("PUBLIC_SCAM_FEEDS_SCHEMA_OK")

if __name__ == "__main__":
    main()
