#!/usr/bin/env python3
import argparse
import sqlite3

DB = "/root/backend/data/api_keys.sqlite3"

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def list_keys():
    c = conn()
    rows = c.execute("""
        SELECT id, key_prefix, owner_email, company_name, plan_code, status,
               requests_used_month, monthly_limit, current_month, last_used_at, created_at
        FROM api_keys
        ORDER BY id DESC
    """).fetchall()
    c.close()

    for r in rows:
        print(
            f"#{r['id']} {r['key_prefix']} | {r['status']} | {r['plan_code']} | "
            f"{r['owner_email']} | {r['company_name']} | "
            f"{r['requests_used_month']}/{r['monthly_limit']} | last={r['last_used_at']}"
        )

def set_status(key_prefix, status):
    c = conn()
    cur = c.execute(
        "UPDATE api_keys SET status=?, updated_at=datetime('now') WHERE key_prefix=?",
        (status, key_prefix)
    )
    c.commit()
    c.close()
    print(f"updated={cur.rowcount} status={status} key_prefix={key_prefix}")

def usage(key_prefix, limit):
    c = conn()
    rows = c.execute("""
        SELECT created_at, endpoint, status_code, input_kind, verdict_level, score,
               latency_ms, ip, error_code
        FROM api_usage_logs
        WHERE key_prefix=?
        ORDER BY id DESC
        LIMIT ?
    """, (key_prefix, limit)).fetchall()
    c.close()

    for r in rows:
        print(
            f"{r['created_at']} | {r['status_code']} | {r['endpoint']} | "
            f"{r['input_kind']} | {r['verdict_level']} | score={r['score']} | "
            f"{r['latency_ms']}ms | {r['ip']} | {r['error_code']}"
        )

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    d = sub.add_parser("disable")
    d.add_argument("key_prefix")

    e = sub.add_parser("enable")
    e.add_argument("key_prefix")

    u = sub.add_parser("usage")
    u.add_argument("key_prefix")
    u.add_argument("--limit", type=int, default=20)

    args = p.parse_args()

    if args.cmd == "list":
        list_keys()
    elif args.cmd == "disable":
        set_status(args.key_prefix, "disabled")
    elif args.cmd == "enable":
        set_status(args.key_prefix, "active")
    elif args.cmd == "usage":
        usage(args.key_prefix, args.limit)

if __name__ == "__main__":
    main()
