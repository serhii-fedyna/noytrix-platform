# Noytrix Intelligence Implementation Status

## Completed

- Step 1: Internal verdict core foundation.
  - Added `scamshield/intelligence/verdict_core.py`.
  - URL/domain scan now writes `details.internal_verdict`.
  - Exact Noytrix Scam Database quick results also write `details.internal_verdict`.
  - External API evidence is marked as reference-only inside the internal verdict envelope.
- Step 2: Noytrix Scam Database v2 deduplication model.
  - Added `scamshield/intelligence/scam_database_v2.py`.
  - Added `scripts/upgrade_scam_database_v2.py`.
  - Added `dedupe_key` support for `entities` and `raw_indicators`.
  - Added `entity_aliases`, `indicator_observations`, and `source_reputation`.
  - Noytrix Scam Database lookup can now resolve canonical entities through aliases.
- Step 3: Source reputation and confidence scoring.
  - Added `scamshield/intelligence/source_reputation.py`.
  - Source reputation now scores feed trust from volume, promoted entities, confidence, risk consistency, and future true/false-positive counters.
  - Noytrix Scam Database matches now include `source_reputation` with adjusted confidence, source trust, aligned/conflicting observations, and top contributing sources.
  - URL/domain quick results and full scan results expose reputation context under `details.source_reputation` and `details.internal_verdict.reputation_context`.
- Step 4: Self-learning entity reputation with time decay.
  - Added `scamshield/intelligence/reputation_graph.py`.
  - Added `scripts/run_reputation_graph_cycle.py`.
  - Entity reputation now learns from status, confidence, source count, seen count, graph neighbors, propagated risk, trust overrides, and last-seen age.
  - Reputation changes are written to `reputation_history` with `self_learning_time_decay_v4` metadata.
- Step 5: Full graph risk propagation.
  - The same v4 cycle maintains `entity_edges`, graph metrics, and `metadata.risk_propagation`.
  - Risk now propagates across campaign, brand, shared-source, URL/domain, and wallet-cluster edges with trusted/safe protection.
  - API responses now expose graph/reputation context inside `details.internal_verdict`.
- Step 6: Scam campaign and network clustering.
  - Added `scamshield/intelligence/campaign_network.py`.
  - Added `scripts/run_campaign_network_clustering.py`.
  - Malicious connected components are now promoted into `campaign:network:*` campaign entities.
  - Cluster members get `campaign_id`, `metadata.network_cluster`, and `network_part_of_campaign` graph edges.
- Step 7: Runtime Web3 integration from extension/mobile to backend.
  - Added `scamshield/runtime/contract.py`.
  - `/runtime/analyze` now emits a stable `runtime_contract` for products.
  - Added `/runtime/web3/analyze` and `/mobile/runtime/analyze` aliases over the same backend truth.
  - `details.internal_verdict.runtime_context` exposes source, method, domain, wallet, spender, and warn/block decisions.

## Remaining

- Step 8: Deep approve/sign simulation for all supported signature types.
- Step 9: Headless site sandbox and JavaScript behavior capture.
- Step 10: Obfuscated JavaScript detection and deobfuscation.
- Step 11: Scam family classifier.
- Step 12: Autonomous threat collectors.
- Step 13: Compromised legitimate site detection.
- Step 14: Multi-chain intelligence beyond EVM.
- Step 15: AI investigation layer with evidence-linked explanations.
- Step 16: Active attack map and investigation UI.
- Step 17: Product-wide rendering of graph, reputation, runtime impact, and AI evidence.

## Current Contract Rule

All products must render backend truth. Products must not calculate their own verdict.
