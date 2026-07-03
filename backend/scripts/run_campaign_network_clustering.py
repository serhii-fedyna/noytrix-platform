from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scamshield.intelligence.campaign_network import run_campaign_network_clustering  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(run_campaign_network_clustering(), ensure_ascii=False, indent=2, default=str))
