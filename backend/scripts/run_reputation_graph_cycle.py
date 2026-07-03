from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scamshield.intelligence.reputation_graph import run_reputation_graph_cycle  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(run_reputation_graph_cycle(), ensure_ascii=False, indent=2, default=str))
