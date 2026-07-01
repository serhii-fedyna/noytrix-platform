#!/usr/bin/env python3
import argparse
import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone

DB = "/root/backend/data/api_keys.sqlite3"

PLANS = {
    "starter": {"monthly_limit": 10000, "rpm": 60},
    "pro": {"monthly_limit": 100000, "rpm": 180},
    "business": {"monthly_limit": 500000, "rpm": 600},
    "enterprise": {"monthly_limit": 0, "rpm": 1200},
}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def month():
    return datetime.now(timezone.utc).strftime("%Y-%m")

def sha256(v):
    return hashlib.sha256(v.encode("utf-8")).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--company", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--plan", default="starter", choices=PLANS.keys())
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--rpm", type=int, default=None)
    ap.add_argument("--expires", default=None)
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    cfg = PLANS[args.plan]
    raw_key = "nx_" + secrets.token_urlsafe(32)
    key_hash = sha256(raw_key)
    prefix = raw_key[:10]
    monthly_limit = args.limit if args.limit is not None else cfg["monthly_limit"]
    rpm = args.rpm if args.rpm is not None else cfg["rpm"]
    ts = now_iso()

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO api_keys (
          key_prefix, key_hash, owner_email, owner_name, company_name,
          plan_code, status, monthly_limit, requests_used_month,
          current_month, rate_limit_per_minute, created_at, updated_at,
          expires_at, notes
        ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, 0, ?, ?, ?, ?, ?, ?)
    """, (
        prefix, key_hash, args.email, args.name, args.company,
        args.plan, monthly_limit, month(), rpm, ts, ts, args.expires, args.notes
    ))
    conn.commit()
    conn.close()

    print("")
    print("✅ NOYTRIX API KEY CREATED")
    print("Important: show this key only once.")
    print("")
    print(f"Client: {args.email}")
    print(f"Company: {args.company or '-'}")
    print(f"Plan: {args.plan}")
    print(f"Monthly limit: {monthly_limit if monthly_limit > 0 else 'unlimited'}")
    print(f"Rate/min: {rpm}")
    print("")
    print(raw_key)
    print("")

if __name__ == "__main__":
    main()
