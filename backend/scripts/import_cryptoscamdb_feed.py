from __future__ import annotations
import json, re, subprocess
from pathlib import Path
from scamshield.intelligence.postgres_intelligence import connect, normalize_entity

RE_EVM = re.compile(r"0x[a-fA-F0-9]{40}")
REPO_URL = "https://github.com/CryptoScamDB/blacklist.git"
REPO_DIR = Path("data/public_feeds/cryptoscamdb_blacklist")

def ensure_repo():
    if REPO_DIR.exists():
        subprocess.run(["git","-C",str(REPO_DIR),"pull","--ff-only"], check=False)
    else:
        subprocess.run(["git","clone","--depth","1",REPO_URL,str(REPO_DIR)], check=True)

def feed_id(cur):
    cur.execute("SELECT id FROM source_feeds WHERE name=%s", ("cryptoscamdb",))
    r=cur.fetchone()
    return r["id"] if r else None

def typ(v):
    x=(v or "").strip().lower()
    if RE_EVM.fullmatch(x): return "evm_address"
    if x.startswith(("http://","https://")): return "url"
    if "." in x and " " not in x and len(x) <= 253: return "domain"
    return "unknown"

def insert(cur, fid, v, raw):
    v=(v or "").strip().strip('"').strip("'")
    t=typ(v)
    if t=="unknown": return False
    n=normalize_entity(v)
    if not n: return False
    cur.execute("""
    INSERT INTO raw_indicators
    (feed_id,source_name,raw_value,normalized_value,indicator_type,status,confidence,risk_score,raw_record,metadata)
    VALUES (%s,'cryptoscamdb',%s,%s,%s,'quarantine',75,75,%s::jsonb,%s::jsonb)
    ON CONFLICT (source_name, normalized_value, indicator_type)
    DO UPDATE SET last_seen_at=now(), seen_count=raw_indicators.seen_count+1,
      confidence=GREATEST(raw_indicators.confidence,EXCLUDED.confidence),
      risk_score=GREATEST(raw_indicators.risk_score,EXCLUDED.risk_score),
      metadata=raw_indicators.metadata || EXCLUDED.metadata
    """,(fid,v,n,t,json.dumps(raw,ensure_ascii=False),json.dumps({"importer":"cryptoscamdb","mode":"quarantine"},ensure_ascii=False)))
    return True

def main():
    ensure_repo()
    imported=0; files=0; batch=0
    with connect() as conn:
      with conn.cursor() as cur:
        fid=feed_id(cur)
        for p in REPO_DIR.rglob("*"):
          if not p.is_file() or p.suffix.lower() not in {".yaml",".yml",".txt",".json",".csv"}: continue
          files+=1
          text=p.read_text(encoding="utf-8",errors="ignore")
          values=set()
          values.update(re.findall(r"https?://[^\s\"']+", text))
          values.update(RE_EVM.findall(text))
          for m in re.findall(r"\b[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", text):
            values.add(m)
          for v in values:
            if insert(cur,fid,v,{"file":str(p),"value":v}):
              imported+=1; batch+=1
              if batch>=1000:
                conn.commit(); print(json.dumps({"cryptoscamdb_progress":imported,"files":files}), flush=True); batch=0
        cur.execute("UPDATE source_feeds SET last_import_at=now() WHERE name=%s", ("cryptoscamdb",))
      conn.commit()
    print(json.dumps({"feed":"cryptoscamdb","scanned_files":files,"imported_or_updated":imported,"mode":"quarantine"},indent=2))
if __name__=="__main__": main()
