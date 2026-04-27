# OmniAegis - AI-Driven Sentinel System with Blockchain Audit Trails

OmniAegis is a comprehensive system that combines advanced AI/ML decision-making with blockchain-anchored audit trails. It provides a complete solution for:

- **Intelligent Decision Making**: Leveraging multiple fingerprinting modalities (audio, image, video, semantic)
- **Human-in-the-Loop Review**: Interactive review interface for high-stakes decisions
- **Explainable AI**: Full transparency into decision reasoning with XAI components
- **Blockchain Audit Trail**: Immutable recording of decisions on Polygon
- **Distributed Governance**: 2-of-3 multisig policy management
- **Batch Merkle Anchoring**: Gas-efficient on-chain verification

## System Architecture

### Components

1. **Smart Contracts** (Solidity)
   - `MerkleAnchor.sol`: Anchors batches of off-chain decision proofs
   - `PolicyRegistry.sol`: Manages governance-approved policies (2-of-3 multisig)
   - `SentinelAudit.sol`: Records high-stakes ML enforcement decisions

2. **Backend** (Python/FastAPI)
   - Fingerprinting services (audio, image, video, semantic embeddings)
   - Qdrant vector database for semantic search
   - Neo4j graph reasoning engine
   - PostgreSQL + Redis for state management
   - Batch coordinator for Merkle tree construction and blockchain anchoring
   - XAI components for decision explainability
   - HITL monitoring and queue management

3. **Frontend** (React/TypeScript/Vite)
   - Dashboard with KPI visualization
   - HITL review interface with real-time WebSocket updates
   - XAI explanation viewer
   - Policy management interface

## Quick Start

### Prerequisites

- Node.js 20+
- Python 3.11+
- Docker & Docker Compose (for containerized setup)
- Git

### Local Development Setup

#### 1. Clone and Install

```bash
# Clone the repository
git clone https://github.com/yourusername/omniaegis.git
cd omniaegis

# Install all dependencies
npm run setup

# This installs:
# - Root dependencies (Hardhat, etc.)
# - Frontend dependencies
# - Backend dependencies
```

#### 2. Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Copy frontend environment template
cp frontend/.env.example frontend/.env

# Edit .env with your configuration
# For local development, you can use defaults for most values
```

#### 3. Start Local Hardhat Node & Deploy Contracts

```bash
# Terminal 1: Start Hardhat local blockchain
npx hardhat node

# Terminal 2: Deploy contracts locally
npm run contracts:deploy:local

# This will output contract addresses - save them!
# Update .env with: MERKLE_ANCHOR_CONTRACT, POLICY_REGISTRY_CONTRACT, SENTINEL_AUDIT_CONTRACT
```

#### 4. Start Backend

```bash
# Terminal 3: Start FastAPI backend
npm run backend:dev

# Backend will be available at http://localhost:8000
# API docs at http://localhost:8000/docs
```

#### 5. Start Frontend

```bash
# Terminal 4: Start React frontend
npm run dev

# Frontend will be available at http://localhost:5173
```

### Docker Compose Setup (Recommended)

For a complete local environment with all services:

```bash
# Build and start all services
docker-compose up -d

# Services will be available at:
# - Frontend: http://localhost:5173
# - Backend: http://localhost:8000
# - PostgreSQL: localhost:5432
# - Redis: localhost:6379
# - Neo4j: http://localhost:7474
# - Qdrant: http://localhost:6333

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

## Contract Deployment

### Local (Hardhat)

```bash
# Deploy to local hardhat network
npm run contracts:deploy:local

# Run tests
npm run contracts:test

# Check gas usage
npm run contracts:coverage
```

### Testnet (Mumbai)

```bash
# Update .env with:
# POLYGON_PRIVATE_KEY=your_private_key
# POLYGONSCAN_API_KEY=your_polygonscan_key

# Deploy to Mumbai
npm run contracts:deploy:mumbai

# Verify on PolygonScan
npm run contracts:verify -- --network mumbai
```

### Mainnet (Polygon)

```bash
# Update .env with production credentials
# Deploy to Polygon
npm run contracts:deploy:polygon

# Verify on PolygonScan
npm run contracts:verify -- --network polygon
```

## API Documentation

### Health Check

```bash
curl http://localhost:8000/health
```

### HITL Review

```bash
# Get HITL item for review
curl http://localhost:8000/api/hitl/items/{itemId}

# Submit review decision
curl -X POST http://localhost:8000/api/hitl/items/{itemId}/review \
  -H "Content-Type: application/json" \
  -d '{"decision": "approved", "feedback": "..."}'
```

### XAI Explanations

```bash
# Get explanations for decision
curl http://localhost:8000/api/xai/explanations/{assetId}

# Get drift detection results
curl http://localhost:8000/api/xai/drift/detect

# Get UMAP projection
curl http://localhost:8000/api/xai/projection/umap
```

### Sentinel Audit

```bash
# Record decision on blockchain
curl -X POST http://localhost:8000/api/sentinel/decisions \
  -H "Content-Type: application/json" \
  -d '{
    "decision_id": "...",
    "policy_id": 1,
    "risk_score": 5000,
    "action": 1,
    "evidence_cid": "Qm..."
  }'
```

### Batch/Merkle

```bash
# Get Merkle proof for decision verification
curl http://localhost:8000/api/batch/proof/{decisionId}

# Get merkle batch status
curl http://localhost:8000/api/batch/merkle/{batchId}
```

## Smart Contract Interaction

### Using Ethers.js

```typescript
import { ethers } from 'ethers';
import MerkleAnchorABI from './artifacts/contracts/MerkleAnchor.sol/MerkleAnchor.json';

const provider = new ethers.JsonRpcProvider('http://localhost:8545');
const signer = new ethers.Wallet(PRIVATE_KEY, provider);

const merkleAnchor = new ethers.Contract(
  MERKLE_ANCHOR_ADDRESS,
  MerkleAnchorABI.abi,
  signer
);

// Authorize a gateway
await merkleAnchor.setGatewayAuthorisation(gatewayAddress, true);

// Anchor a batch
const tx = await merkleAnchor.anchorBatch(
  merkleRoot,
  startDecisionIndex,
  leafCount,
  manifestCid
);
```

## Development Workflows

### Adding a New API Endpoint

1. Create handler in `decision_layer/app/`
2. Add router to `app.main:app`
3. Document in API docstring
4. Update frontend API client in `frontend/src/services/api.ts`

### Modifying Smart Contracts

1. Edit contract in `contracts/`
2. Run tests: `npm run contracts:test`
3. Check gas: `npm run contracts:coverage`
4. Redeploy: `npm run contracts:deploy:local`

### Frontend Component Development

1. Create component in `frontend/src/components/`
2. Use context providers from `frontend/src/context/`
3. Use API client from `frontend/src/services/api.ts`
4. Test with mock data from `frontend/src/data/mockData.ts`

## Environment Variables

### Backend (.env)

```
# Blockchain
POLYGON_RPC_URL=http://127.0.0.1:8545
POLYGON_PRIVATE_KEY=...
MERKLE_ANCHOR_CONTRACT=0x...
POLICY_REGISTRY_CONTRACT=0x...
SENTINEL_AUDIT_CONTRACT=0x...

# Databases
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
NEO4J_URI=neo4j://...

# Vector DB
QDRANT_MODE=local
QDRANT_LOCAL_PATH=./.qdrant

# Storage
PINATA_API_KEY=...

# CORS
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# API
API_HOST=0.0.0.0
API_PORT=8000
```

### Frontend (.env)

```
VITE_API_URL=http://localhost:8000
VITE_API_TIMEOUT=30000
```

## Testing

### Unit Tests

```bash
# Backend (Python)
cd decision_layer
pytest

# Frontend (TypeScript)
cd frontend
npm run test
```

### Contract Tests

```bash
npm run contracts:test

# With coverage
npm run contracts:coverage
```

### Integration Tests

```bash
# Run full integration test suite
npm run test:integration
```

## Troubleshooting

### Backend Won't Start

```bash
# Check if port 8000 is in use
lsof -i :8000

# Check dependencies
pip install -r decision_layer/requirements.txt

# Check database connection
psql $DATABASE_URL -c "SELECT 1"
```

### Frontend API Errors

1. Ensure backend is running: `curl http://localhost:8000/health`
2. Check CORS configuration in `.env`
3. Check browser console for CORS errors
4. Verify `VITE_API_URL` in frontend `.env`

### Contract Deployment Fails

1. Ensure you have sufficient balance for gas
2. Check network configuration in `hardhat.config.ts`
3. Verify private key in `.env`
4. Check Hardhat node is running: `npx hardhat node`

### Docker Compose Issues

```bash
# Force rebuild
docker-compose down -v
docker-compose up --build

# Check service health
docker-compose ps

# View specific service logs
docker-compose logs -f backend
```

## Performance Optimization

### Backend

- Vector embeddings cached in Redis
- Neo4j query results cached
- Merkle trees computed in batches (10-min windows)
- Decision indexing via PostgreSQL + Qdrant

### Frontend

- Code splitting by route (Vite)
- Lazy loading of components
- WebSocket for real-time HITL updates
- Memoization of expensive computations

### Smart Contracts

- Merkle trees for batch anchoring (gas-efficient)
- Compact storage packing in structs
- Nonce-based replay protection (no signature storage)
- Single-use events for off-chain indexing

## Security Considerations

1. **Private Keys**: Never commit `.env` file - use environment management
2. **CORS**: Restrict origins in production
3. **Rate Limiting**: Add API rate limiting before production
4. **Database**: Use encrypted connections (PostgreSQL SSL, Redis TLS)
5. **Blockchain**: Use hardware wallets for production keys
6. **Policy Guardians**: Use separate addresses for 2-of-3 multisig
7. **Audit Logging**: All decisions recorded immutably on-chain

## License

MIT

## Support

For issues, questions, or contributions, please create a GitHub issue or contact the development team.

---

**Last Updated**: April 2026
**Version**: 1.0.0
