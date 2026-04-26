# OmniAegis Architecture

## System Overview

OmniAegis is a multi-tier system combining AI/ML decision-making with blockchain auditability:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React/Vite)                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │  Dashboard KPIs  │  │  HITL Interface  │  │  XAI Viewer  │   │
│  └──────────────────┘  └──────────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                ▲
                    HTTP + WebSocket (CORS-enabled)
                                │
┌─────────────────────────────────────────────────────────────────┐
│                    Backend (Python/FastAPI)                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Fingerprinting  │ Reasoning  │ HITL  │ Batch │ XAI      │   │
│  │  - Audio        │ - Neo4j    │ Queue │ Coord │ - SHAP   │   │
│  │  - Image        │ - GNN      │ Manager│ Merkle│ - Captum │   │
│  │  - Video        │ - Graph    │        │ Trees │ - UMAP   │   │
│  │  - Semantic     │  Building  │        │       │ - Drift  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
        ▲                          ▲                    ▲
        │                          │                    │
        ├─ PostgreSQL          ├─ Qdrant           ├─ Pinata IPFS
        ├─ Redis Cache         ├─ Vector Search    ├─ Evidence Storage
        └─ Monitoring          └─ Embeddings       └─ Decision Proofs
                                                      
        ▲
        │ (Web3.py)
        │
┌─────────────────────────────────────────────────────────────────┐
│                   Smart Contracts (Solidity)                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │  MerkleAnchor    │  │ PolicyRegistry   │  │ SentinelAudit│   │
│  │  - Batch anchors │  │ - 2-of-3 multisig│  │ - Decision  │   │
│  │  - Root storage  │  │ - Policy versions│  │   records   │   │
│  │  - Verification  │  │ - Governance     │  │ - CID links │   │
│  └──────────────────┘  └──────────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                ▲
                          Polygon RPC
                                │
                      ┌─────────────────┐
                      │ Polygon Network │
                      │ (Layer 2)       │
                      └─────────────────┘
```

## Component Details

### Frontend Layer

**Technology**: React 18 + TypeScript + Vite + Tailwind CSS

**Key Components**:
- **Dashboard**: Real-time KPI visualization with Recharts
- **HITL Review**: Asset viewer with saliency maps + decision panel
- **XAI Dashboard**: Explanation visualization and drift monitoring
- **WebSocket Hook**: Real-time updates for queue depth and assignments

**State Management**: React Context API
- `DashboardContext`: Global dashboard state
- `HITLReviewContext`: HITL-specific state

**API Integration**: Centralized `apiClient` in `services/api.ts`

### Backend Layer

**Technology**: Python 3.11 + FastAPI + Uvicorn

**Modules**:

1. **Fingerprinting Services**
   - `ImageFingerprinter`: CNN-based image hashing
   - `AudioFingerprinter`: Mel-spectrogram based audio fingerprinting
   - `VideoFingerprinter`: Frame sampling + aggregation
   - `SemanticEmbedder`: Transformer-based embeddings (512-dim)

2. **Reasoning Engine**
   - `GraphBuilder`: Neo4j relationship construction
   - `RightsGNN`: Graph neural network for decision inference
   - `GraphExplainer`: Path-based explainability
   - `Calibration`: ECE computation for model confidence

3. **HITL Management**
   - `HITLMonitorService`: Queue and assignment management
   - `LockTimer`: TTL-based assignment locking
   - `MaintenanceLoop`: Periodic queue clean-up

4. **Batch Coordination**
   - `BatchCoordinator`: Merkle tree construction
   - `DecisionLeaf`: Standardized leaf format
   - `MerkleBatch`: Batch metadata
   - 10-minute batching window with PostgreSQL persistence

5. **XAI Components**
   - `VisualExplainer`: Saliency map generation
   - `UMAPProjector`: Dimensionality reduction
   - `ExplainabilityStorage`: S3-based result caching
   - `XAIDriftDetector`: Model drift monitoring

6. **Audit & Storage**
   - `AuditService`: Decision logging
   - `BatchCoordinator`: IPFS coordination (Pinata)
   - `GraphDBService`: Neo4j driver management
   - `MetricsRegistry`: Prometheus metrics

### Smart Contract Layer

**Technology**: Solidity 0.8.20 + OpenZeppelin

**Contracts**:

1. **MerkleAnchor**
   - Stores Merkle root batches
   - Gateway allowlist pattern
   - Batch verification via `verifyDecisionInBatch()`
   - Gas-optimized storage packing
   - Events: `BatchAnchored`, `GatewayAuthorisationUpdated`

2. **PolicyRegistry**
   - Governance-approved policies
   - 2-of-3 multisig with ECDSA
   - Single-use nonce replay protection
   - Guardian rotation capability
   - Events: `PolicyUpserted`, `PolicyRevoked`, `GuardianUpdated`

3. **SentinelAudit**
   - Immutable decision records
   - CID hash storage (compact)
   - High-stakes decision marking
   - Batch recording for efficiency
   - Events: `DecisionRecorded`, `GatewayAuthorisationUpdated`

## Data Flow

### Decision Recording Flow

```
User/System
    │
    ▼
┌─────────────────────────────────┐
│ Fingerprint Generation          │
│ - Image/Audio/Video analysis    │
│ - Semantic embedding            │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Decision Inference              │
│ - Query Qdrant for similar      │
│ - Run Neo4j reasoning           │
│ - Compute confidence score      │
└─────────────────────────────────┘
    │
    ├─ High Confidence?
    │  │ YES ──────────────────┐
    │  │ NO ─────────┐         │
    │              ▼         ▼
    │         ┌─────────┐  ┌──────────────┐
    │         │ HITL Q  │  │ Direct       │
    │         │ (Redis) │  │ Recording    │
    │         └─────────┘  └──────────────┘
    │              │              │
    │              ▼              ▼
    │        ┌─────────────────────────┐
    │        │ PostgreSQL Log          │
    │        │ (Immediate persistence) │
    │        └─────────────────────────┘
    │              │
    └──────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Batch Collection (10 min window)│
│ - Aggregate decisions           │
│ - Build Merkle tree             │
│ - Upload to IPFS (Pinata)       │
│ - Create manifest CID           │
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Blockchain Anchoring            │
│ - Call MerkleAnchor.anchorBatch │
│ - Gas-optimized batch recording │
│ - Emit BatchAnchored event      │
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Audit Trail Complete            │
│ - Immutable on-chain record     │
│ - Off-chain proof verification  │
└─────────────────────────────────┘
```

### Human-in-the-Loop Flow

```
Decision Queue
     │
     ▼
┌───────────────────────────┐
│ Assignment                │
│ - Lock for 5 mins (Redis) │
│ - Assign to reviewer      │
│ - WebSocket notification  │
└───────────────────────────┘
     │
     ▼
┌───────────────────────────┐
│ HITL Review Interface     │
│ - Asset display           │
│ - Saliency maps (XAI)     │
│ - Decision recommendation │
└───────────────────────────┘
     │
     ▼
┌───────────────────────────┐
│ User Decision             │
│ - Approve/Reject/Escalate│
│ - Add feedback            │
└───────────────────────────┘
     │
     ▼
┌───────────────────────────┐
│ Record Final Decision     │
│ - Update PostgreSQL       │
│ - Call SentinelAudit      │
│ - Update Neo4j graph      │
└───────────────────────────┘
```

## Database Schema

### PostgreSQL

```sql
-- Decision logs
CREATE TABLE decisions (
    decision_id UUID PRIMARY KEY,
    asset_id UUID NOT NULL,
    model_confidence FLOAT,
    action INTEGER,
    created_at TIMESTAMP,
    INDEX (asset_id, created_at)
);

-- HITL queue
CREATE TABLE hitl_queue (
    item_id UUID PRIMARY KEY,
    decision_id UUID,
    assigned_to VARCHAR,
    locked_until TIMESTAMP,
    created_at TIMESTAMP
);

-- Merkle batches
CREATE TABLE merkle_batches (
    batch_id UUID PRIMARY KEY,
    window_start TIMESTAMP,
    window_end TIMESTAMP,
    merkle_root BYTEA,
    manifest_cid VARCHAR,
    created_at TIMESTAMP
);
```

### Neo4j

```cypher
-- Relationship graph for reasoning
CREATE (a:Asset {id: $assetId, ...})
CREATE (p:Policy {id: $policyId, ...})
CREATE (d:Decision {id: $decisionId, ...})
CREATE (a)-[:EVALUATED_BY]->(d)
CREATE (d)-[:GOVERNED_BY]->(p)
```

### Qdrant

```python
# Vector collections
collections = {
    "semantic_assets": {
        "vector_size": 512,
        "distance": "Cosine",
        "index": "HNSW",
        "m": 16,
        "ef_construct": 128
    }
}
```

### Redis

```
# Cache structure
decision:{decision_id} -> {confidence, action, timestamp}
hitl:queue -> {item_ids}
hitl:lock:{item_id} -> {assigned_to, expires_at}
calibration:batch -> {predictions[], targets[]}
```

## API Endpoints

### Core Endpoints

```
GET    /health                               Health check
GET    /docs                                 API documentation (Swagger UI)

GET    /api/hitl/items/{itemId}             Get HITL item
POST   /api/hitl/items/{itemId}/review      Submit review decision
GET    /api/hitl/queue                       Get queue status

GET    /api/xai/explanations/{assetId}      Get explanations
POST   /api/xai/drift/detect                Detect model drift
POST   /api/xai/projection/umap             UMAP projection

POST   /api/sentinel/decisions              Record decision
GET    /api/sentinel/decisions/{decisionId} Get decision record

POST   /api/batch/merkle                    Initiate Merkle batch
GET    /api/batch/proof/{decisionId}        Get Merkle proof
```

## Security Architecture

### Authentication
- API Key based (backend-to-blockchain)
- No user authentication (future: OAuth2)

### Authorization
- Gateway allowlist pattern (contracts)
- Guardian multisig (policy changes)
- Role-based access control (future)

### Data Protection
- IPFS for immutable evidence storage
- PostgreSQL encryption at rest
- Redis TLS for cache
- Blockchain as source of truth

### Compliance
- Immutable audit trail
- Decision explainability
- Policy governance
- Regulatory reporting ready

## Scalability Considerations

### Horizontal Scaling
- **Backend**: Load balancer + multiple instances
- **Database**: Connection pooling, read replicas
- **Vector DB**: Distributed Qdrant clusters
- **Cache**: Redis cluster mode

### Vertical Scaling
- **Batch size**: Configurable Merkle tree sizes
- **Vector dims**: Trade-off accuracy vs. speed
- **Model**: Switch to lighter models for edge

### Optimization
- Decision caching
- Batch query optimization
- Vector index tuning
- Neo4j query planning

## Monitoring & Observability

### Metrics
- API response times (Prometheus)
- Decision latency (histogram)
- Batch anchoring gas costs
- Cache hit rates
- Model confidence distribution

### Logging
- Structured JSON logs
- Centralized logging (DataDog/Grafana)
- Error rate tracking
- Decision audit logs

### Alerts
- High API latency (>1s)
- Database connection failures
- Blockchain transaction failures
- Cache memory pressure

---

For deployment details, see [DEPLOYMENT.md](./DEPLOYMENT.md)
For API details, see [README.md](./README.md)
