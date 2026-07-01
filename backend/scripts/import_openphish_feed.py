from __future__ import annotations
import json, urllib.request
from pathlib import Path
from scamshield.intelligence.postgres_intelligence import connect, normalize_entity

URLS=[
  "https://openphish.com/feed.txt",
]

def feed_id(cur):
    cur.execute("SELECT id FROM source_feeds WHERE name=%s", ("openphish",))
    r=cur.fetchone()
    if r: return r["id"]
    cur.execute("""
      INSERT INTO source_feeds (name,source_type,url,trust_level,metadata)
      VALUES ('openphish','public_database','https://openphish.com',70,'{"category":"phishing"}'::jsonb)
      ON CONFLICT (name) DO UPDATE SET active=true
      RETURNING id
    """)
    return cur.fetchone()["id"]

def insert(cur,fid,u):
    u=(u or "").strip()
    if not u.startswith(("http://","https://")): return False
    n=normalize_entity(u)
    if not n: return False
    cur.execute("""
    INSERT INTO raw_indicators
    (feed_id,source_name,raw_value,normalized_value,indicator_type,status,confidence,risk_score,raw_record,metadata)
    VALUES (%s,'openphish',%s,%s,'url','quarantine',70,70,%s::jsonb,%s::jsonb)
    ON CONFLICT (source_name, normalized_value, indicator_type)
    DO UPDATE SET last_seen_at=now(), seen_count=raw_indicators.seen_count+1,
      confidence=GREATEST(raw_indicators.confidence,EXCLUDED.confidence),
      risk_score=GREATEST(raw_indicators.risk_score,EXCLUDED.risk_score),
      metadata=raw_indicators.metadata || EXCLUDED.metadata
    """,(fid,u,n,json.dumps({"url":u},ensure_ascii=False),json.dumps({"importer":"openphish","mode":"quarantine"},ensure_ascii=False)))
    return True

def main():
    imported=0
    with connect() as conn:
      with conn.cursor() as cur:
        fid=feed_id(cur)
        for feed in URLS:
          try:
            text=urllib.request.urlopen(feed,timeout=45).read().decode("utf-8","ignore")
          except Exception as e:
            print("SKIP_FEED",feed,e,flush=True); continue
          for line in text.splitlines():
            if insert(cur,fid,line): imported+=1
          conn.commit()
        cur.execute("UPDATE source_feeds SET last_import_at=now() WHERE name=%s", ("openphish",))
      conn.commit()
    print(json.dumps({"feed":"openphish","imported_or_updated":imported,"mode":"quarantine"},indent=2))
if __name__=="__main__": main()
