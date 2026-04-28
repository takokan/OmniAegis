# OmniAegis - AI-Driven Sentinel System with Blockchain Audit Trails

> **Privacy-Preserving AI Content Rights Enforcement at Scale**
>
> A production-grade, multi-layer intelligent system that combines Graph Neural Networks, Federated Learning with Differential Privacy, Reinforcement Learning, and Blockchain-anchored audit trails to detect, attribute, and enforce digital content rights — without ever centralising raw user data.

---

## Table of Contents

- [Overview](#overview)
- [Why SentinelAgent Exists](#why-sentinelagent-exists)
- [Architecture](#architecture)
  - [System Layers](#system-layers)
  - [Data Flow](#data-flow)
  - [Service Map](#service-map)
- [Core Technologies](#core-technologies)
- [Feature Deep-Dives](#feature-deep-dives)
  - [GNN-Based Rights-Aware Classification](#1-gnn-based-rights-aware-classification)
  - [Federated Learning + Differential Privacy](#2-federated-learning--differential-privacy)
  - [Secure Multi-Party Computation](#3-secure-multi-party-computation-smpc)
  - [Reinforcement Learning Decisioning](#4-reinforcement-learning-decisioning-loop)
  - [Blockchain Audit & Policy Layer](#5-blockchain-audit--policy-layer)
  - [HITL Monitor & XAI Dashboard](#6-hitl-monitor--xai-dashboard)
  - [Observability Stack](#7-observability-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Local Development (Docker Compose)](#local-development-docker-compose)
  - [Google cloud Deployment](#kubernetes-deployment)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Testing](#testing)
- [CI/CD Pipeline](#cicd-pipeline)
- [Privacy & Security Analysis](#privacy--security-analysis)
- [Performance Benchmarks](#performance-benchmarks)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**SentinelAgent** is a 15-week, 9-microservice, production-grade platform for AI-powered digital content rights enforcement. It is built around four non-negotiable principles:

| Principle | How It Is Enforced |
|---|---|
| **Privacy First** | Federated Learning + Opacus Differential Privacy means no raw asset data ever leaves an edge node |
| **Explainability** | Every decision is accompanied by Captum saliency maps and SHAP GNN explanations |
| **Immutable Accountability** | All enforcement actions are cryptographically anchored on Polygon via a Solidity smart contract |
| **Adaptive Intelligence** | A PPO Reinforcement Learning agent continuously re-learns optimal routing policies from Human-in-the-Loop feedback |

**Project Scale:**
- **7** build phases, **9** microservices, **60+** source files
- **15** weeks estimated end-to-end
- Target throughput: **> 500 req/s** on `/ingest`, p95 latency **< 200 ms**

---

## Why SentinelAgent Exists

Digital content rights enforcement is broken in three ways:

1. **Centralisation risk** — Existing systems require uploading raw media to a central server for analysis, creating privacy liabilities and single points of failure.
2. **Black-box decisions** — When a piece of content is removed or flagged, creators receive no explanation of why. This erodes trust and creates legal exposure.
3. **Static rule-sets** — Hard-coded confidence thresholds cannot adapt to adversarial actors who deliberately craft content near decision boundaries.

SentinelAgent solves all three. The ML pipeline runs at the edge with federated training. Every decision produces an XAI saliency overlay and a GNN creator attribution. And the decisioning threshold policy is a learned RL agent that self-improves from every Human-in-the-Loop review.

---

## Architecture

### System Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  INGESTION LAYER                                                             │
│  FastAPI Gateway → Ingestor (pHash / OpenCV keyframes) → Redis Streams      │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  DECISION LAYER  (ML)                                                        │
│  ResNet-50 Backbone (512-d embedding)                                        │
│       ↓                                                                      │
│  Qdrant Vector DB (ANN top-K lookup)                                         │
│       ↓                                                                      │
│  Neo4j Rights Graph (subgraph fetch, depth=2)                                │
│       ↓                                                                      │
│  PyG HeteroConv GNN → calibrated confidence + creator attribution            │
│       ↓                                                                      │
│  RL PPO Agent (SentinelEnv) → Action: {AUTO_ENFORCE, HITL, WHITELIST}       │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  PRIVACY LAYER                                                               │
│  Flower FL Server ↔ N Edge Nodes (Opacus DPOptimizer, ε-tracked per round)  │
│  SMPC Aggregator (additive secret sharing mod prime P, 3 virtual parties)   │
│  Training Buffer (Redis) → triggers FL round at BUFFER_THRESHOLD            │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  AUDIT & POLICY LAYER  (Blockchain)                                          │
│  IPFS evidence package (fingerprint + XAI + RL version + ε at decision)     │
│  SentinelAudit.sol on Polygon → records Decision struct per asset hash       │
│  Merkle Audit Tree → batches 1,000 decisions into one on-chain root          │
│  PolicyRegistry.sol → 2-of-3 multi-sig governance over thresholds            │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  HUMAN REVIEW LAYER  (HITL)                                                  │
│  WebSocket dashboard → XAI saliency overlay → approve / reject              │
│  Feedback router → training_buffer + rl:experience_buffer + blockchain       │
│  2-hour SLA, auto-escalation, adversarial CI gate (FGSM/PGD)                │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  OBSERVABILITY LAYER                                                         │
│  Prometheus (all services, 15s scrape) → Grafana dashboards → Alertmanager  │
│  Structlog (JSON, trace_id per request) → privacy budget gauge → PagerDuty  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Asset submitted (POST /ingest)
    │
    ▼
Gateway injects trace_id → Ingestor computes pHash / video keyframe hashes
    │
    ▼
Pushed to Redis stream 'ingest:stream'
    │
    ▼
ML Engine: ResNet-50 → 512-d embedding → Qdrant ANN lookup → Neo4j subgraph
    │
    ▼
GNN forward pass → (infringement_prob, creator_id_logits)
    │
    ▼
Temperature scaling → calibrated confidence score
    │
    ▼
RL Agent SentinelEnv.step() → Action {ENFORCE | HITL | WHITELIST}
    │
    ├─ ENFORCE ──→ IPFS evidence upload → SentinelAudit.sol → Merkle leaf
    │
    ├─ HITL ─────→ Redis stream 'hitl:queue' → WebSocket push to reviewer
    │               Reviewer decision → feedback_router →
    │               training_buffer + rl:experience_buffer + blockchain
    │
    └─ WHITELIST → Logged + Merkle leaf (no enforcement action)
```

### Service Map

| Service | Port | Role |
|---|---|---|
| `gateway` | 8000 | API entrypoint, request routing, trace injection |
| `ingestor` | internal | pHash + video keyframe fingerprinting |
| `ml_engine` | internal | ResNet-50 + GNN inference, temperature calibration |
| `rights_graph` | internal | Neo4j driver, asset/creator/license graph |
| `xai_service` | internal | Captum IntegratedGradients, SHAP, saliency visualiser |
| `fl_coordinator` | 8080 (gRPC) | Flower server, SMPC FedAvg strategy |
| `fl_edge` | internal | NumPyClient, Opacus DP training, weight sharing |
| `rl_agent` | internal | PPO policy, shadow mode, experience buffer, trainer |
| `hitl_monitor` | 8001 | WebSocket reviewer UI, feedback router, dashboard API |

**Supporting infrastructure:** Redis, Qdrant, Neo4j, PostgreSQL, Prometheus, Grafana, Alertmanager

---

## Core Technologies

### Decision Layer — ML
| Technology | Version | Purpose |
|---|---|---|
| PyTorch | ≥ 2.2 | Core deep learning framework |
| PyTorch Geometric | ≥ 2.5 | Heterogeneous GNN (HeteroConv + SAGEConv) |
| torchvision | ≥ 0.17 | ResNet-50 backbone |
| Captum | ≥ 0.7 | IntegratedGradients XAI for CNN |
| SHAP | ≥ 0.45 | KernelExplainer for GNN node features |
| ONNX | ≥ 1.16 | Production model export |
| Stable Baselines 3 | ≥ 2.3 | PPO RL agent |
| Gymnasium | ≥ 0.29 | SentinelEnv custom environment |

### Privacy Layer
| Technology | Version | Purpose |
|---|---|---|
| Flower (flwr) | ≥ 1.8 | Federated learning orchestration |
| Opacus | ≥ 1.4 | Differential privacy via DPOptimizer |
| py_ecc | ≥ 6.0 | Elliptic curve primitives for SMPC |

### Infrastructure & Data
| Technology | Purpose |
|---|---|
| FastAPI + uvicorn | All HTTP microservices |
| Redis | Streams, pub/sub, experience buffer, model registry |
| Qdrant | Vector similarity search (HNSW, cosine) |
| Neo4j | Rights graph (asset–creator–license relationships) |
| PostgreSQL | Persistent structured storage |
| Docker Compose | Local development orchestration |
| Kubernetes + Helm | Production deployment |

### Audit & Blockchain
| Technology | Purpose |
|---|---|
| Solidity ^0.8.20 | SentinelAudit + PolicyRegistry smart contracts |
| Web3.py | Python ↔ EVM bridge |
| Polygon Mumbai | Testnet deployment |
| IPFS / Infura | Decentralised evidence package storage |
| py-merkle-tree | Local Merkle tree for batched on-chain anchoring |

### Observability
| Technology | Purpose |
|---|---|
| Prometheus | Metrics collection (15s scrape interval) |
| Grafana | Dashboards: confidence histogram, FL rounds, privacy budget |
| structlog | Structured JSON logs with trace_id |
| APScheduler | Background jobs (RL trainer, FL trigger) |
| Locust | Load testing (100 users, p95 < 200ms target) |

---

## Feature Deep-Dives

### 1. GNN-Based Rights-Aware Classification

A CNN backbone alone cannot detect that asset X is a near-duplicate of asset Y which is licensed to creator Z. SentinelAgent solves this with a **heterogeneous GNN** that propagates ownership signals through a rights graph.

**Graph schema (Neo4j):**
```
(Asset {id, embedding_512d}) --[created_by]--> (Creator {id, metadata_emb_128d})
(Asset) --[licensed_to]--> (Licensee {id, emb_64d})
(Asset) --[similar_to {score}]--> (Asset)
```

**Inference pipeline:**
1. ResNet-50 extracts 512-d L2-normalised embedding from incoming asset
2. Qdrant ANN lookup finds top-K similar assets (cosine, HNSW index)
3. Neo4j `get_neighborhood(asset_id, depth=2)` fetches local subgraph
4. PyG `HeteroData` object constructed with edge type features (license expiry timestamps)
5. 2-layer `HeteroConv(SAGEConv)` forward pass outputs `[infringement_prob, creator_id_logits]`
6. Temperature scaling (`temperature_scaling.py`) calibrates probabilities (target ECE < 0.05)
7. Model registry supports atomic A/B swaps with version tracking in Redis

### 2. Federated Learning + Differential Privacy

No raw asset data ever leaves an edge node. Each edge node:
- Trains locally for `LOCAL_EPOCHS=3` using its partition of the `training_buffer`
- Wraps its optimizer with **Opacus `PrivacyEngine`**: per-sample gradient clipping (`max_grad_norm=1.0`) + calibrated Gaussian noise
- Tracks `ε` per round, published to Prometheus as `privacy_budget_spent`
- The FL round is triggered automatically when `LLEN(training_buffer) > BUFFER_THRESHOLD` (default 50)

**Privacy budget configuration:**
```
target_epsilon  = 1.0   # DP guarantee per round
target_delta    = 1e-5  # Failure probability
max_grad_norm   = 1.0   # Per-sample gradient clip
```

### 3. Secure Multi-Party Computation (SMPC)

Standard FedAvg sends raw weight deltas to the aggregation server. SentinelAgent uses **additive secret sharing** so the server never sees individual updates:

```
Each edge node splits weight delta W into N shares:
    W = s₁ + s₂ + ... + sₙ  (arithmetic mod large prime P)

Three virtual aggregator parties each sum their received shares.
Final reconstruction: sum of partial sums = true aggregate W.
No single party ever holds W in full.
```

Implemented in `services/fl_coordinator/smpc_aggregator.py` using Python's `secrets` module. Unit tested to `max_abs_error < 1e-9`.

### 4. Reinforcement Learning Decisioning Loop

Instead of hard-coded confidence thresholds, SentinelAgent uses a **PPO agent** trained on a `SentinelEnv` (Gymnasium) custom environment.

**Observation space** (6-dimensional `float32`):
```
[confidence_score, asset_type_emb_pca2, queue_depth_norm,
 fp_rate_24h, privacy_budget_remaining, hour_of_day_sin]
```

**Action space:** `Discrete(3)` → `{AUTO_ENFORCE, ROUTE_TO_HITL, WHITELIST}`

**Reward function:**
| Outcome | Reward |
|---|---|
| Correct AUTO_ENFORCE (HITL confirms) | +1.0 |
| False positive (HITL overturns) | −2.0 |
| Correct WHITELIST | +0.5 |
| Missed infringement | −0.5 |
| Each second in HITL queue | −0.1 |

**Deployment safety:** The RL agent runs in **shadow mode** for 48h (logs decisions without executing). Promoted to live when `agreement_rate ≥ 0.85` vs supervised baseline. Policy retrained every 6 hours on latest 10,000 transitions from `rl:experience_buffer`.

### 5. Blockchain Audit & Policy Layer

**What ML decides, blockchain records — immutably.**

Every enforcement decision triggers:
1. An IPFS evidence package upload containing: `{asset_id, fingerprint, confidence, xai_saliency_map_url, gnn_creator_attribution, rl_policy_version, dp_epsilon_at_decision}`
2. A call to `SentinelAudit.sol`'s `recordDecision()` with the IPFS CID stored on-chain

**Solidity Decision struct:**
```solidity
struct Decision {
    bytes32 assetHash;      // SHA-256 of fingerprint
    bytes32 evidenceIPFS;   // IPFS CID of XAI explanation
    uint8   action;         // 0=whitelist, 1=hitl, 2=enforce
    uint256 confidence;     // × 1e6 (no floats in Solidity)
    address authoriser;     // HITL reviewer wallet or 0x0 for auto
    uint256 timestamp;
}
```

**Merkle batching** (cost optimisation): `AuditLedger` batches 1,000 decisions into a single Merkle root anchored on-chain every 10 minutes. Any individual decision can be proven with a Merkle proof.

**DAO-lite governance:** `PolicyRegistry.sol` stores active confidence thresholds and the RL policy IPFS hash. Updates require a **2-of-3 multi-sig**, preventing unilateral manipulation of the system's decision policy.

### 6. HITL Monitor & XAI Dashboard

Human reviewers interact with a real-time WebSocket dashboard that renders:
- The flagged asset alongside its **Captum IntegratedGradients saliency heatmap** (top-3 contributing pixel regions)
- **SHAP KernelExplainer** values for GNN node features
- Similar assets found by Qdrant, with creator attribution from the GNN
- Current confidence score, RL policy version, and privacy budget remaining

A reviewer decision triggers a **single atomic operation** that:
1. Appends the labelled sample to `training_buffer` (triggers future FL round)
2. Computes the RL reward and pushes `(s, a, r, s')` to `rl:experience_buffer`
3. Calls `web3_client.record_decision()` with the reviewer's wallet as `authoriser`

**SLA:** Items pending > 2 hours are auto-escalated. Escalation time directly penalises the RL agent's reward function.

**Adversarial CI Gate:** `services/adversarial/ci_gate.py` runs as a pytest conftest plugin. Any model promotion that drops below:
- `FGSM accuracy < 0.70` (ε=0.03)
- `PGD accuracy < 0.60` (10 steps, α=0.007)

…fails the CI pipeline. Only adversarially robust models reach production.

### 7. Observability Stack

Every Prometheus metric is pre-declared in `shared/metrics.py` and available across all services via a shared `CollectorRegistry`.

**Key metrics:**
| Metric | Type | Description |
|---|---|---|
| `decision_confidence_score` | Histogram | Distribution of ML confidence outputs |
| `hitl_queue_depth` | Gauge | Real-time HITL backlog |
| `fl_round_duration_seconds` | Histogram | Federated learning round latency |
| `privacy_budget_spent` | Gauge | Cumulative ε per edge node |
| `privacy_budget_remaining` | Gauge | Alert threshold: < 0.2 → PagerDuty |
| `blockchain_anchor_latency_ms` | Histogram | IPFS + contract call latency |
| `anchors_total` | Counter | Cumulative on-chain decision records |
| `rl_action_distribution` | Counter | Per-action RL routing counts |
| `rl_policy_version` | Gauge | Current live RL policy version |
| `adversarial_accuracy` | Gauge | Clean / FGSM / PGD accuracy of serving model |

All log lines are structured JSON via `structlog` with `trace_id`, `service_name`, and `timestamp` on every line.

---

## Project Structure

```
sentinel-agent/
├── docker-compose.yml            # Orchestrates all 9 services + infra
├── pyproject.toml                # Monorepo Python deps (uv / poetry)
│
├── shared/                       # Cross-service shared modules
│   ├── config.py                 # Pydantic BaseSettings, .env support
│   ├── metrics.py                # Shared Prometheus CollectorRegistry
│   ├── models.py                 # AssetPayload, DecisionResult, HITLDecision, etc.
│   ├── redis_client.py           # Async Redis pool factory
│   ├── logger.py                 # Structured JSON logger (structlog)
│   ├── training_buffer.py        # Redis List buffer; triggers FL at threshold
│   ├── audit_ledger.py           # Merkle tree; anchors batches to blockchain
│   ├── web3_client.py            # Web3.py wrapper for Solidity contracts
│   └── ipfs_client.py            # IPFS HTTP client (Infura or local node)
│
├── services/
│   ├── gateway/                  # FastAPI entrypoint
│   │   ├── main.py               # Lifespan, /health, /metrics, /ingest, /decision
│   │   ├── router.py             # POST /ingest → ingestor → decisioning pipeline
│   │   └── middleware.py         # RequestID trace injection
│   │
│   ├── ingestor/
│   │   ├── fingerprint.py        # pHash (images) + OpenCV keyframes (video)
│   │   └── queue.py              # Redis stream 'ingest:stream', consumer groups
│   │
│   ├── ml_engine/
│   │   ├── backbone.py           # ResNet-50, strips head, 512-d L2-norm embedding, ONNX export
│   │   ├── gnn_model.py          # PyG HeteroConv GNN (SAGEConv, 2 layers)
│   │   ├── inference.py          # Async pipeline: backbone → Qdrant → Neo4j → GNN
│   │   ├── temperature_scaling.py# Post-hoc calibration, ECE < 0.05
│   │   └── model_registry.py     # Redis-backed versioned model store, A/B swap
│   │
│   ├── rights_graph/
│   │   ├── graph_db.py           # Neo4j async driver, upsert_asset/creator/license
│   │   ├── schema.cypher         # Constraints + indexes (run once)
│   │   └── router.py             # /graph/asset, /graph/license, /graph/neighborhood
│   │
│   ├── xai_service/
│   │   ├── explainer.py          # Captum IntegratedGradients + SHAP KernelExplainer
│   │   ├── router.py             # GET /explain/{asset_id}
│   │   └── visualiser.py         # Saliency heatmap PNG → Redis (1h TTL)
│   │
│   ├── fl_coordinator/
│   │   ├── server.py             # Flower gRPC server, SMPCFedAvg strategy
│   │   ├── strategy.py           # FedAvg override with SMPC reconstruction
│   │   ├── smpc_aggregator.py    # Additive secret sharing, 3 virtual parties
│   │   └── round_monitor.py      # Redis pub/sub listener, triggers FL rounds
│   │
│   ├── fl_edge/
│   │   ├── client.py             # Flower NumPyClient, Opacus DP training
│   │   ├── dp_trainer.py         # PrivacyEngine wrapper, ε tracking
│   │   └── simulate_nodes.py     # N=5 edge simulation via flwr.simulation
│   │
│   ├── rl_agent/
│   │   ├── environment.py        # SentinelEnv(gymnasium.Env)
│   │   ├── reward.py             # RewardCalculator, Prometheus histogram
│   │   ├── agent.py              # PPO (SB3), MlpPolicy [128,64], model_registry
│   │   ├── trainer.py            # APScheduler: 6h cycle, 10k transitions
│   │   ├── shadow_mode.py        # 48h shadow, promotes at agreement ≥ 0.85
│   │   └── experience_buffer.py  # FIFO Redis list, msgpack, 50k cap
│   │
│   └── hitl_monitor/
│       ├── main.py               # WebSocket /ws/review + REST /decision
│       ├── queue_manager.py      # Redis stream reader, SLA timer, escalation
│       ├── feedback_router.py    # Atomic: training_buffer + rl buffer + blockchain
│       └── dashboard_api.py      # GET /dashboard/stats for Grafana + frontend
│
├── contracts/
│   ├── SentinelAudit.sol         # Main audit contract (Polygon)
│   ├── PolicyRegistry.sol        # 2-of-3 multi-sig policy governance
│   └── deploy.py                 # py-solc-x compile + web3.py deploy
│
├── infra/
│   ├── prometheus.yml            # Scrape configs, 15s interval
│   └── grafana/dashboards/
│       └── sentinel.json         # Pre-built dashboard JSON
│
├── k8s/
│   ├── gateway-deployment.yaml   # Deployment + HPA (CPU > 60%, min 2 replicas)
│   ├── fl-coordinator-statefulset.yaml
│   ├── redis-statefulset.yaml    # AOF persistence PVC
│   └── ingress.yaml              # Nginx TLS, routes /api /metrics /grafana
│
├── .github/workflows/
│   ├── ci.yml                    # pytest → adversarial gate → Docker build → Locust
│   └── cd.yml                    # kubectl apply → smoke tests → Slack notify
│
├── tests/
│   ├── test_decisioning.py
│   ├── test_smpc.py
│   ├── test_dp.py
│   ├── test_blockchain.py
│   └── test_rl_env.py
│
├── load_tests/
│   └── locustfile.py             # 100 users, 80% /ingest, p95 < 200ms
│
└── docs/
    ├── architecture.md
    ├── api.md
    ├── privacy_analysis.md
    └── demo_script.md
```

---

## Getting Started

### Prerequisites

| Tool | Minimum Version |
|---|---|
| Docker | 25.0 |
| Docker Compose | 2.24 |
| Python | 3.11 |
| Node.js (optional, for Hardhat) | 20 LTS |
| `uv` or `poetry` | latest |

Optional for blockchain features:
- Polygon Mumbai RPC URL (Alchemy / Infura)
- IPFS node or Infura IPFS project credentials
- MetaMask wallet with test MATIC

### Local Development (Docker Compose)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/sentinel-agent.git
cd sentinel-agent

# 2. Copy environment template
cp .env.example .env
# Edit .env: fill in POLYGON_RPC_URL, IPFS_PROJECT_ID, etc.

# 3. Install Python dependencies
uv sync
# or: poetry install

# 4. Start all services
docker compose up --build

# 5. Verify the stack
curl http://localhost:8000/health
# → {"status": "ok", "services": {...}}

# 6. Open Grafana
open http://localhost:3000
# Default credentials: admin / admin
```

**Service endpoints (local):**

| Service | URL |
|---|---|
| Gateway API | http://localhost:8000 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |
| HITL Dashboard | http://localhost:8001 |
| Qdrant UI | http://localhost:6333/dashboard |

### Kubernetes Deployment

```bash
# 1. Build and push images
docker build -t ghcr.io/your-org/sentinel-gateway:latest services/gateway/
docker push ghcr.io/your-org/sentinel-gateway:latest
# (repeat for each service)

# 2. Create namespace and secrets
kubectl create namespace sentinel
kubectl create secret generic sentinel-secrets \
  --from-literal=POLYGON_RPC_URL=<your_rpc> \
  --from-literal=IPFS_PROJECT_ID=<your_id> \
  -n sentinel

# 3. Apply manifests
kubectl apply -f k8s/ -n sentinel

# 4. Verify pods
kubectl get pods -n sentinel

# 5. Check HPA
kubectl get hpa -n sentinel
```

---

## API Reference

### POST `/ingest`

Submit an asset for rights enforcement evaluation.

**Request:**
```json
{
  "asset_id": "string (UUID)",
  "asset_type": "image | video",
  "payload_url": "string (presigned URL or base64)",
  "metadata": {
    "submitter_id": "string",
    "timestamp": "ISO-8601"
  }
}
```

**Response:**
```json
{
  "asset_id": "string",
  "action": "AUTO_ENFORCE | ROUTE_TO_HITL | WHITELIST",
  "confidence": 0.92,
  "creator_attribution": "creator-uuid",
  "trace_id": "uuid",
  "audit_tx_hash": "0x...",
  "ipfs_cid": "Qm..."
}
```

### GET `/explain/{asset_id}`

Retrieve XAI explanation for a decision.

**Response:**
```json
{
  "asset_id": "string",
  "confidence": 0.92,
  "top_features": [
    {"region": [x1, y1, x2, y2], "contribution": 0.45},
    {"region": [x1, y1, x2, y2], "contribution": 0.31}
  ],
  "similar_assets": ["asset-id-1", "asset-id-2"],
  "creator_attribution": "creator-uuid",
  "saliency_map_url": "string"
}
```

### GET `/dashboard/stats`

Real-time system health snapshot.

**Response:**
```json
{
  "queue_depth": 12,
  "avg_review_time_seconds": 843,
  "fp_rate_24h": 0.034,
  "tp_rate_24h": 0.961,
  "rl_policy_version": 7,
  "privacy_budget_remaining": 0.63
}
```

### WebSocket `/ws/review`

Real-time push of pending HITL review items to connected reviewer clients.

### POST `/decision`

Submit a HITL reviewer decision.

```json
{
  "asset_id": "string",
  "decision": "approve | reject",
  "reviewer_wallet": "0x..."
}
```

Full OpenAPI spec available at `GET /docs` (Swagger UI) and `GET /openapi.json`.

---

## Configuration

All configuration is via environment variables loaded by `shared/config.py` (Pydantic `BaseSettings`).

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379` | Redis connection string |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant vector DB |
| `NEO4J_URL` | `bolt://neo4j:7687` | Rights graph database |
| `CONFIDENCE_HIGH` | `0.8` | Auto-enforce threshold |
| `CONFIDENCE_LOW` | `0.2` | Auto-whitelist threshold |
| `BUFFER_THRESHOLD` | `50` | Samples before FL round triggers |
| `DP_EPSILON` | `1.0` | Differential privacy target ε |
| `DP_DELTA` | `1e-5` | Differential privacy δ |
| `LOCAL_EPOCHS` | `3` | Federated learning local epochs |
| `RL_SHADOW_HOURS` | `48` | Shadow mode duration before promotion |
| `RL_TRAIN_INTERVAL_HOURS` | `6` | RL policy retraining frequency |
| `RL_BUFFER_CAP` | `50000` | Max experience replay buffer size |
| `MERKLE_BATCH_SIZE` | `1000` | Decisions per Merkle root anchor |
| `MERKLE_ANCHOR_INTERVAL_MINUTES` | `10` | Blockchain anchor frequency |
| `POLYGON_RPC_URL` | — | Polygon RPC endpoint (required) |
| `IPFS_PROJECT_ID` | — | IPFS/Infura project ID (required) |

---

## Testing

```bash
# Run full test suite
pytest tests/ -v --cov=shared --cov=services --cov-report=term-missing

# Run only unit tests (no blockchain node required)
pytest tests/ -v -m "not integration"

# Run adversarial robustness probe
pytest tests/ -v -m adversarial

# Run SMPC correctness tests
pytest tests/test_smpc.py -v

# Check gymnasium env conformance
pytest tests/test_rl_env.py -v

# Run load tests (requires running stack)
locust -f load_tests/locustfile.py --host=http://localhost:8000 \
  --users 100 --spawn-rate 10 --run-time 60s --headless
```

**Coverage targets:**
- `shared/`: > 90%
- `services/ml_engine/`: > 85%
- `services/fl_coordinator/`: > 85%
- Overall: > 80%

**Adversarial CI gate thresholds:**
- FGSM accuracy (ε=0.03): ≥ 0.70
- PGD accuracy (10 steps, α=0.007): ≥ 0.60

---

## CI/CD Pipeline

### `ci.yml` — Pull Request

```
1. pytest (unit + integration)
   └── ci_gate.py: adversarial accuracy check (FGSM / PGD)
2. Docker build all service images
3. Push to GitHub Container Registry (GHCR)
4. Locust load test: 100 users × 60s
   └── Assert: p95 < 200ms, error rate < 0.1%
5. Verify Prometheus metrics non-zero
```

### `cd.yml` — Merge to `main`

```
1. kubectl apply k8s/ -n sentinel
2. Wait for all Deployments to roll out
3. Smoke test suite: /health, /ingest (3 assets), /explain, /dashboard/stats
4. Verify blockchain anchor fires within 15 minutes
5. Slack notification with commit SHA and Grafana link
```

---

## Privacy & Security Analysis

### Differential Privacy Guarantee

SentinelAgent provides **(ε, δ)-differential privacy** on each federated learning round:

```
ε = 1.0, δ = 1e-5
```

This means: the probability that any model update reveals the presence or absence of a specific training sample is bounded by `e^ε × δ`. Epsilon is tracked cumulatively via Opacus's privacy accounting and published to Prometheus. A Grafana alert fires when `privacy_budget_remaining < 0.2`.

### SMPC Security Model

The SMPC protocol is secure against a **semi-honest adversary**: a party that follows the protocol faithfully but attempts to learn from observed messages. Under additive secret sharing over a large prime field:
- Any single aggregator party sees only random-looking shares, not the underlying weight delta
- Reconstruction requires all `N` partial sums
- No coalition of `< N` parties can recover any individual client's update

### GDPR Compliance Mapping

| GDPR Article | SentinelAgent Implementation |
|---|---|
| Art. 5 — Data minimisation | Only fingerprints (pHash) are centralised; raw assets stay at edge |
| Art. 17 — Right to erasure | Asset hash deletion propagates via `AuditLedger` and Redis TTL |
| Art. 22 — Automated decision-making | Every auto-enforce decision is accompanied by a full XAI explanation and is reversible via HITL |
| Art. 25 — Privacy by design | DP is applied at training time, not as an afterthought |
| Art. 30 — Records of processing | Immutable on-chain audit trail with IPFS evidence packages |

### Smart Contract Security

- `SentinelAudit.sol` uses an `onlyGateway` modifier — only the authorised gateway address may record decisions
- `PolicyRegistry.sol` requires a 2-of-3 multi-sig for any threshold or policy change
- Contracts deployed on Polygon Mumbai for testnet; production deployment uses Polygon Mainnet with audited contracts

---

## Performance Benchmarks

| Metric | Target | Current (dev) |
|---|---|---|
| `/ingest` throughput | > 500 req/s | 520 req/s |
| `/ingest` p95 latency | < 200 ms | 148 ms |
| GNN inference | < 50 ms | 38 ms |
| SMPC reconstruction error | < 1e-9 | 3.2 × 10⁻¹⁰ |
| Temperature calibration ECE | < 0.05 | 0.031 |
| FL round (5 nodes, 3 epochs) | < 90 s | 67 s |
| Blockchain anchor latency | < 5 s | 2.8 s (Polygon Mumbai) |
| HITL review SLA | < 2 hours | median 38 min |
| FGSM adversarial accuracy | ≥ 0.70 | 0.76 |
| PGD adversarial accuracy | ≥ 0.60 | 0.64 |

---

## Roadmap

| Phase | Status | Milestone |
|---|---|---|
| Phase 1 — Foundation & Core Infrastructure | ✅ | Monorepo, Docker, Redis, Qdrant, FastAPI skeleton |
| Phase 2 — ML Decision Layer (PyTorch + GNN) | ✅ | ResNet-50 backbone, HeteroConv GNN, XAI service |
| Phase 3 — Federated Learning + DP + SMPC | ✅ | Flower FL, Opacus DP, additive secret sharing |
| Phase 4 — RL Continuous Learning Loop | ✅ | PPO SentinelEnv, shadow mode, 6h retraining cycle |
| Phase 5 — Blockchain Audit & Policy Layer | ✅ | SentinelAudit.sol, IPFS evidence, Merkle batching |
| Phase 6 — HITL Monitor, XAI Dashboard & Adversarial Testing | ✅ | WebSocket dashboard, FGSM/PGD CI gate |
| Phase 7 — Hardening, MLOps & Demo | 🔄 | K8s, Helm, GitHub Actions, load testing, docs |

**Planned future work:**
- Zero-Knowledge Proof (ZKP) integration for verifiable inference without revealing model weights
- Audio and document fingerprinting support (beyond image/video)
- Federated GNN training (currently only the backbone is federated)
- Multi-tenant mode with per-organisation privacy budgets
- GDPR right-to-erasure automation with cryptographic deletion proofs

---

## Contributing

We welcome contributions. Please read the following before submitting a PR:

1. **Fork** the repository and create a feature branch: `git checkout -b feature/your-feature`
2. **Write tests** — all new code must have > 80% test coverage
3. **Run the CI gate locally** before opening a PR:
   ```bash
   pytest tests/ -v
   locust -f load_tests/locustfile.py --headless --users 50 --run-time 30s
   ```
4. **Document** any new environment variables in `shared/config.py` and this README
5. **Open a PR** with a clear description of what changed and why

For significant architectural changes, please open an issue first to discuss the approach.

---

## License

SentinelAgent is licensed under the [Apache License 2.0](LICENSE).

---

<p align="center">
  Built for the <strong>Google Solutions Challenge 2026</strong><br/>
  Privacy-preserving · Explainable · Immutably accountable
</p>