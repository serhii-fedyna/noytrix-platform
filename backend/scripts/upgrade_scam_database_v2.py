from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scamshield.intelligence.scam_database_v2 import run_upgrade  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Upgrade Noytrix Scam Database to v2 deduplication model.")
    parser.add_argument("--batch-limit", type=int, default=250000)
    args = parser.parse_args()

    result = run_upgrade(batch_limit=args.batch_limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
