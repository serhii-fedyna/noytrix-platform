# Noytrix Intelligence Platform Roadmap

## Target

Noytrix must become a first-party crypto threat-intelligence platform, not a thin wrapper over external APIs.

The final system must provide:

- a fully internal verdict engine;
- a deduplicated Noytrix Scam Database with millions of indicators;
- self-learning reputation for domains, wallets, contracts, spenders, transactions, campaigns, and sources;
- an entity graph connecting domains, URLs, wallet addresses, contracts, signatures, scripts, IPs, reports, and campaigns;
- campaign and scam-network discovery;
- risk propagation across connected entities;
- runtime Web3 analysis before approve/sign;
- wallet-drain simulation before user confirmation;
- hidden and obfuscated JavaScript analysis;
- scam-family classification;
- AI explanations in simple human language;
- one backend contract consumed by web, mobile, extension, Telegram bot, and API clients.

## Current Foundation

The backend already contains important foundation pieces:

- `scamshield/intelligence/noytrix_scam_database.py`
  - internal exact-match database lookup;
  - trusted official crypto domain handling;
  - PostgreSQL/raw-indicator lookup path.
- `scamshield/intelligence/threat_memory.py`
  - local threat memory;
  - entity history;
  - graph edge persistence.
- `scamshield/intelligence/postgres_intelligence.py`
  - entity storage;
  - raw indicators;
  - cached verdicts;
  - graph context helpers.
- `scamshield/runtime/approve.py`
  - approve risk analysis.
- `scamshield/runtime/drain_simulator.py`
  - wallet-drain impact estimation.
- `scamshield/runtime/execution_graph.py`
  - execution-chain graph scoring.
- `main.py`
  - unified scan endpoint;
  - evidence trace;
  - false-positive safety gate;
  - spender reputation;
  - verdict compatibility output.

This means the correct next step is not a rewrite. The next step is to separate the internal intelligence core from external-source adapters and make every final verdict pass through the internal core.

## Architecture

```mermaid
flowchart TD
  input["Scan input: URL / domain / wallet / contract / tx / signature"] --> normalize["Entity normalization"]
  normalize --> internal_db["Noytrix Scam Database"]
  normalize --> reputation["Reputation engine"]
  normalize --> graph["Entity graph"]
  normalize --> runtime["Runtime Web3 engine"]
  normalize --> sandbox["Site behavior sandbox"]
  normalize --> collectors["Threat collectors"]

  collectors --> raw_indicators["Raw indicators"]
  raw_indicators --> dedupe["Deduplication and canonical entities"]
  dedupe --> internal_db
  dedupe --> graph

  internal_db --> verdict_core["Internal verdict core"]
  reputation --> verdict_core
  graph --> verdict_core
  runtime --> verdict_core
  sandbox --> verdict_core

  external["External APIs"] --> external_evidence["Reference evidence only"]
  external_evidence --> verdict_core

  verdict_core --> ai["AI explanation layer"]
  ai --> api["Unified API contract"]
  api --> web["Web"]
  api --> mobile["Mobile"]
  api --> extension["Extension"]
  api --> bot["Telegram bot"]
```

## Non-Negotiable Verdict Rule

External APIs may add evidence, but must not be the authority for the final verdict.

Final verdict must be based on:

1. Noytrix database match.
2. Internal reputation.
3. Graph relationships.
4. Runtime wallet/signature impact.
5. Site behavior and JavaScript evidence.
6. Historical confidence and false-positive controls.
7. External sources as supporting context only.

## Phase 1: Internal Verdict Core

Goal: all scan types produce a first-party verdict object before compatibility fields are attached.

Deliverables:

- create `scamshield/intelligence/verdict_core.py`;
- define one internal verdict schema:
  - `level`;
  - `score`;
  - `confidence`;
  - `risk_family`;
  - `risk_reasons`;
  - `evidence`;
  - `source_weights`;
  - `internal_decision_trace`;
  - `false_positive_controls`;
  - `graph_context`;
  - `reputation_context`;
  - `runtime_context`;
- convert current URL/domain scan scoring to call the core;
- keep existing API response fields stable;
- place diagnostics under `details.internal_verdict`.

Done when:

- `/scan` and `/v1/scan` still return the old top-level contract;
- frontend does not need breaking changes;
- internal verdict trace shows why Noytrix decided safe/suspicious/danger/critical;
- external APIs are clearly marked as reference evidence.

## Phase 2: Noytrix Scam Database v2

Goal: one deduplicated intelligence database for all indicators.

Data model:

- `raw_indicators`
  - raw value;
  - normalized value;
  - type;
  - status;
  - first seen;
  - last seen;
  - source;
  - confidence;
  - raw metadata hash.
- `entities`
  - canonical entity;
  - entity type;
  - reputation score;
  - risk score;
  - status;
  - campaign id;
  - dedupe key.
- `entity_aliases`
  - raw variants mapped to canonical entity.
- `indicator_observations`
  - every sighting over time.
- `source_reputation`
  - reliability and false-positive rate per source.

Done when:

- duplicate indicators merge into one canonical entity;
- an entity can have many raw observations;
- conflicting reports do not overwrite each other blindly;
- the verdict uses entity reputation, not only raw rows.

## Phase 3: Reputation Engine

Goal: reputation changes over time from evidence, user telemetry, source reliability, and graph context.

Signals:

- confirmed malicious indicators;
- trusted allowlist signals;
- user votes with trust weighting;
- source reliability;
- repeated sightings;
- campaign membership;
- neighbor risk;
- age and decay;
- recovery signals for compromised legitimate sites.

Done when:

- a normal legitimate site is not permanently marked critical because of one weak signal;
- a known scam remains dangerous even if external APIs are silent;
- reputation has history and explainable changes.

## Phase 4: Graph Intelligence

Goal: detect networks, not only isolated objects.

Entities:

- domains;
- URLs;
- wallets;
- contracts;
- spenders;
- transaction hashes;
- IPs;
- nameservers;
- scripts;
- Telegram handles;
- X accounts;
- Reddit posts;
- scam reports;
- campaign ids.

Relations:

- resolves_to;
- redirects_to;
- hosts_script;
- uses_spender;
- deploys_contract;
- sends_to;
- receives_from;
- shares_template;
- same_campaign;
- reported_with;
- impersonates_brand.

Done when:

- checking one suspicious domain can surface related wallets/contracts/domains;
- risk can propagate with decay and confidence;
- the API can return `graph_context` and `campaign_context`.

## Phase 5: Scam Campaign Discovery

Goal: automatically group related entities into scam families and campaigns.

Detection methods:

- shared domain patterns;
- shared scripts;
- shared wallet/spender;
- shared contract bytecode/function selectors;
- same hosting/IP/name servers;
- same phishing text/templates;
- same Telegram/X promotion accounts;
- same victim reports;
- graph clustering.

Done when:

- a new scam domain can be linked to an existing campaign before external APIs flag it;
- the verdict can say: "This looks like Campaign X / wallet-drainer family Y."

## Phase 6: Runtime Web3 Defense

Goal: protect the user before sign/approve.

Extension and mobile wallet flows must send:

- chain id;
- method;
- spender;
- token;
- value;
- calldata;
- typed data;
- domain separator;
- verifying contract;
- dApp origin;
- connected wallet metadata.

Backend must return:

- what can be stolen;
- whether approval is unlimited;
- whether NFTs can be transferred;
- whether delayed drain is possible;
- whether hidden nested execution is likely;
- spender reputation;
- graph context;
- user-facing explanation.

Done when:

- user sees the real impact before signing;
- approve/sign verdict is based on transaction semantics, not only domain reputation.

## Phase 7: Site Sandbox And JavaScript Analysis

Goal: analyze page behavior, not only URL text.

Required components:

- headless browser sandbox;
- script capture;
- DOM mutation tracking;
- wallet-provider API hook detection;
- obfuscated JavaScript deobfuscation;
- dynamic import and remote script tracking;
- wallet-drainer pattern detection;
- fake wallet connect detection;
- seed/private-key request detection;
- clipboard and download abuse detection.

Done when:

- hidden drainer behavior is detected even if the domain is new;
- legitimate sites are not flagged just because they mention Web3.

## Phase 8: Autonomous Threat Collection

Goal: build Noytrix intelligence from the open internet.

Collectors:

- Reddit;
- Telegram;
- Twitter/X;
- scam report sites;
- crypto forums;
- GitHub issue reports;
- public block explorers;
- public phishing feeds;
- user submissions;
- extension telemetry.

Pipeline:

- collect;
- normalize;
- deduplicate;
- extract entities;
- classify source reliability;
- store raw evidence;
- link graph;
- update reputation;
- schedule re-checks.

Done when:

- the database grows continuously;
- source quality is measured;
- duplicates do not inflate risk;
- every indicator has provenance.

## Phase 9: AI Investigation Layer

Goal: AI explains and investigates, but does not replace evidence.

AI responsibilities:

- summarize risk in human language;
- classify scam family;
- explain evidence;
- suggest user action;
- generate investigation notes;
- cluster similar incidents;
- identify missing evidence to collect.

AI must not:

- hallucinate verdicts;
- override hard evidence without trace;
- hide uncertainty.

Done when:

- every AI explanation is backed by structured evidence IDs;
- frontend can show both explanation and machine trace.

## Phase 10: Product Surfaces

All products must consume one backend contract:

- web;
- mobile;
- extension;
- Telegram bot;
- API dashboard.

No product should calculate its own verdict. Products only render:

- final verdict;
- score;
- confidence;
- evidence;
- graph;
- reputation;
- runtime wallet impact;
- AI explanation;
- recommended action.

## Immediate Next Engineering Task

Start with Phase 1.

Concrete first task:

1. Add `scamshield/intelligence/verdict_core.py`.
2. Move final URL/domain decision assembly into the internal verdict core.
3. Keep external APIs as `reference_evidence`.
4. Return `details.internal_verdict`.
5. Add fixtures for:
   - verified safe crypto domains;
   - known malicious domains;
   - soft Web3 noise;
   - database exact matches;
   - conflicting external evidence.
6. Run:
   - `python -m compileall main.py scamshield scripts tests`;
   - `python scripts/run_accuracy_100.py`;
   - `git diff --check`.

## Success Definition

Noytrix becomes top-level when:

- it can detect a new scam before external APIs do;
- it can explain why a verdict happened;
- it can avoid false critical verdicts on legitimate sites;
- it can connect one indicator to a broader scam network;
- it can show what the user may lose before signing;
- it learns from every scan, report, and verified outcome;
- all products render the same backend truth.
