#!/usr/bin/env bash
set +e
cd /root/backend
mkdir -p logs/feed_imports

run_import () {
  NAME="$1"
  SCRIPT="$2"
  echo
  echo "==============================="
  echo "IMPORT: $NAME"
  echo "==============================="
  if [ ! -f "$SCRIPT" ]; then
    echo "SKIP: $SCRIPT not found"
    return
  fi
  PYTHONPATH=/root/backend ./venv/bin/python3 "$SCRIPT" 2>&1 | tee "logs/feed_imports/${NAME}.log"
}

run_import scamsniffer_scam_database scripts/import_scamsniffer_feed.py
run_import phishing_database scripts/import_phishing_database_feed.py
run_import forta_labelled_datasets scripts/import_forta_labelled_datasets.py
run_import cryptoscamdb scripts/import_cryptoscamdb_feed.py
run_import phishtank scripts/import_phishtank_feed.py
run_import openphish scripts/import_openphish_feed.py

DB_PASS="$(cat /root/backend/.noytrix_pg_password)"

echo
echo "==============================="
echo "FINAL COUNTS"
echo "==============================="
PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -U noytrix_intel -d noytrix_intelligence -c "
SELECT source_name, indicator_type, status, COUNT(*) AS count
FROM raw_indicators
GROUP BY source_name, indicator_type, status
ORDER BY source_name, count DESC;
"

echo "ALL_IMPORTS_FINISHED"
