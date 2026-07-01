from __future__ import annotations
import gzip, json, re, urllib.request
from pathlib import Path
from scamshield.intelligence.postgres_intelligence import connect, normalize_entity

URL="http://data.phishtank.com/data/online-valid.json.gz"
OUT=Path("data/public_feeds/phishtank_online-valid.json.gz")

def feed_id(cur):
    cur.execute("SELECT id FROM source_feeds WHERE name=%s", ("phishtank",))
    r=cur.fetchone()
    return r["id"] if r else None

def insert(cur,fid,url,row):
    n=normalize_entity(url)
    if not n: return False
    cur.execute("""
    INSERT INTO raw_indicators
    (feed_id,source_name,raw_value,normalized_value,indicator_type,status,confidence,risk_score,raw_record,metadata)
    VALUES (%s,'phishtank',%s,%s,'url','quarantine',70,70,%s::jsonb,%s::jsonb)
    ON CONFLICT (source_name, normalized_value, indicator_type)
    DO UPDATE SET last_seen_at=now(), seen_count=raw_indicators.seen_count+1,
      confidence=GREATEST(raw_indicators.confidence,EXCLUDED.confidence),
      risk_score=GREATEST(raw_indicators.risk_score,EXCLUDED.risk_score),
      metadata=raw_indicators.metadata || EXCLUDED.metadata
    """,(fid,url,n,json.dumps(row,ensure_ascii=False),json.dumps({"importer":"phishtank","mode":"quarantine"},ensure_ascii=False)))
    return True

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(URL, OUT)
    data=json.loads(gzip.open(OUT,"rt",encoding="utf-8",errors="ignore").read())
    imported=0; batch=0
    with connect() as conn:
      with conn.cursor() as cur:
        fid=feed_id(cur)
        for row in data:
          u=(row.get("url") or "").strip()
          if not u: continue
          if insert(cur,fid,u,row):
            imported+=1; batch+=1
            if batch>=1000:
              conn.commit(); print(json.dumps({"phishtank_progress":imported}), flush=True); batch=0
        cur.execute("UPDATE source_feeds SET last_import_at=now() WHERE name=%s", ("phishtank",))
      conn.commit()
    print(json.dumps({"feed":"phishtank","imported_or_updated":imported,"mode":"quarantine"},indent=2))
if __name__=="__main__": main()
