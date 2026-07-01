from scamshield.intelligence.postgres_intelligence import connect, init_schema

SQL = """
ALTER TABLE entities
ADD COLUMN IF NOT EXISTS roles JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE entities
ADD COLUMN IF NOT EXISTS cache_verdict JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE entities
ADD COLUMN IF NOT EXISTS last_verdict_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_entities_roles ON entities USING GIN (roles);
CREATE INDEX IF NOT EXISTS idx_entities_cache_verdict ON entities USING GIN (cache_verdict);

UPDATE entities
SET roles = to_jsonb(ARRAY[entity_type])
WHERE roles = '[]'::jsonb OR roles IS NULL;
"""

def main():
    init_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL)
        conn.commit()
    print("PG_INTELLIGENCE_ROLES_OK")

if __name__ == "__main__":
    main()
