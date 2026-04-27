# Phase 6 Prompt 3: XAI Dashboard & Analytics Backend

## Components Implemented

### 1. Explainability Storage Service
**File**: [decision_layer/services/xai_storage.py](decision_layer/services/xai_storage.py)

Logs (Explanation Vector, Outcome) pairs to PostgreSQL time-series table with:
- 512-dimensional explanation vectors (JSON)
- SHAP feature importance values (JSONB)
- Saliency map overlays (JSONB)
- Asset and decision IDs
- Timestamp-based indexing for range queries

**Key Methods**:
- `log_explanation()` - Insert single explanation record
- `fetch_explanations_by_date_range()` - Query by time window and filters
- `get_shap_values_for_period()` - Extract SHAP distributions for drift analysis

**Schema**:
```sql
CREATE TABLE xai_explanations (
  id BIGSERIAL PRIMARY KEY,
  asset_id VARCHAR(255) NOT NULL,
  decision_id VARCHAR(255) NOT NULL,
  outcome SMALLINT NOT NULL,
  explanation_vector TEXT,
  shap_values JSONB,
  saliency_map JSONB,
  metadata JSONB,
  timestamp_ms BIGINT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_xai_asset_timestamp ON xai_explanations(asset_id, timestamp_ms DESC);
CREATE INDEX idx_xai_outcome_timestamp ON xai_explanations(outcome, timestamp_ms DESC);
CREATE INDEX idx_xai_timestamp ON xai_explanations(timestamp_ms DESC);
```

---

### 2. Drift Detection Service
**File**: [decision_layer/services/xai_drift.py](decision_layer/services/xai_drift.py)

Kolmogorov-Smirnov (KS) test implementation for feature distribution drift:
- Compares current period SHAP values against 30-day reference
- Flags features where p-value < 0.05 (configurable)
- Computes mean/std deltas for root cause analysis

**Key Methods**:
- `detect_drift()` - Single feature KS test
- `detect_drift_batch()` - Parallel KS test on multiple features
- `filter_drifted_features()` - Extract flagged features only

**Output**: `DriftDetectionResult` with:
- Feature name, KS statistic, p-value
- Current/reference mean and std
- `is_drifted` boolean flag
- Notes on mean shift magnitude

---

### 3. UMAP Projection Service
**File**: [decision_layer/services/xai_umap.py](decision_layer/services/xai_umap.py)

Dimensionality reduction from 512D embeddings to 2D for visualization:
- UMAP algorithm with configurable hyperparameters
- Redis caching keyed by content hash (TTL 24h default)
- Returns `[x, y]` coordinates per embedding

**Configuration**:
- `n_neighbors`: 15 (local neighborhood size)
- `min_dist`: 0.1 (minimum cluster distance)
- `metric`: euclidean
- Cache TTL: 86400 seconds

**Output**: `projected_2d` list of [x, y] pairs with metadata

---

### 4. Population Saliency Aggregation Worker
**File**: [decision_layer/services/xai_saliency.py](decision_layer/services/xai_saliency.py)

Aggregates saliency maps by content category to produce representative heatmaps:
- Normalizes individual maps (0-1 range)
- Resizes to canonical shape (224x224)
- Computes mean and std heatmaps
- Groups by content_type, modality, or custom field

**Key Methods**:
- `aggregate_saliency_maps()` - Single category aggregation
- `aggregate_batch_by_category()` - Multi-category grouping

**Output**: Per-category heatmap with:
- Average intensity values
- Standard deviation (confidence)
- Count of maps aggregated
- Min/max/mean statistics

---

### 5. XAI API Endpoints
**File**: [decision_layer/app/xai_api.py](decision_layer/app/xai_api.py)

FastAPI routes for XAI operations:

#### Explanation Logging
```
POST /xai/explanations/log
Body: { asset_id, decision_id, outcome, explanation_vector, shap_values?, saliency_map?, metadata? }
Response: { id, timestamp_ms }
```

#### Drift Detection
```
POST /xai/drift/detect
Body: { current_period_start_ms, current_period_end_ms, reference_period_start_ms, reference_period_end_ms, outcome? }
Response: { total_features, drifted_features, results: [{ feature_name, ks_statistic, p_value, is_drifted, ... }] }
```

#### UMAP Projection
```
POST /xai/projection/umap
Body: { embeddings: [[...], ...], cache_key? }
Response: { projected_2d: [[x, y], ...], count, dimensions: 2, cached }
```

#### Health Checks
```
GET /xai/health/drift
GET /xai/health/umap
```

---

## Integration with FastAPI Lifespan

Services are initialized in app lifespan:
- `ExplainabilityStorage` via `app.state.xai_storage`
- `UMAPProjector` via `app.state.umap_projector`
- Clean shutdown with `.close()` on all connections

Router registered as `app.include_router(xai_router)`

---

## Environment Variables

```bash
# Explainability Storage
POSTGRES_DSN=postgresql://user:pass@localhost/omniaegis
XAI_EXPLANATIONS_TABLE=xai_explanations
XAI_MAX_CONNECTIONS=16

# UMAP Projection
REDIS_URL=redis://localhost:6379/0
UMAP_CACHE_TTL_SECONDS=86400
UMAP_N_NEIGHBORS=15
UMAP_MIN_DIST=0.1
UMAP_METRIC=euclidean
UMAP_RANDOM_STATE=42
```

---

## Usage Examples

### Log Explanation
```python
import httpx

async with httpx.AsyncClient() as client:
    await client.post(
        "http://localhost:8000/xai/explanations/log",
        json={
            "asset_id": "img_12345",
            "decision_id": "dec_abc",
            "outcome": 1,
            "explanation_vector": [0.1, -0.05, ...],  # 512-D
            "shap_values": {"feature_1": 0.23, "feature_2": -0.15},
            "metadata": {"model_version": "2.1"}
        }
    )
```

### Detect Drift
```python
# Query SHAP value distributions from last 7 days vs. last 30 days
now_ms = int(time.time() * 1000)
week_ago = now_ms - 7 * 24 * 60 * 60 * 1000
month_ago = now_ms - 30 * 24 * 60 * 60 * 1000

await client.post(
    "http://localhost:8000/xai/drift/detect",
    json={
        "current_period_start_ms": week_ago,
        "current_period_end_ms": now_ms,
        "reference_period_start_ms": month_ago,
        "reference_period_end_ms": week_ago,
        "outcome": 1  # positive class only
    }
)
```

### Project Embeddings
```python
embeddings = [
    [0.1, 0.2, ..., 0.01],  # 512-D
    [0.15, 0.18, ..., 0.02],
    ...
]

response = await client.post(
    "http://localhost:8000/xai/projection/umap",
    json={"embeddings": embeddings}
)
# { "projected_2d": [[0.5, 0.3], [0.6, 0.25], ...], "cached": false }
```

---

## Architecture Highlights

✅ **Time-Series Database**: PostgreSQL with indexed columns for range queries  
✅ **Drift Detection**: Scipy KS test with configurable significance threshold  
✅ **Caching**: Redis with content-hash keys for UMAP projections  
✅ **Aggregation**: Asynchronous worker pattern for batch heatmap processing  
✅ **Type Safety**: Full TypeScript/Pydantic validation for all I/O  
✅ **Error Handling**: Custom exception classes and defensive API responses  
✅ **Scalability**: Connection pooling for both PostgreSQL and Redis  
✅ **Modularity**: Services decoupled from endpoints via dependency injection
