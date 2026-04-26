# Deployment Guide

This guide covers deploying OmniAegis to production environments.

## Pre-Deployment Checklist

- [ ] All tests passing (`npm run contracts:test`, backend tests)
- [ ] Environment variables configured for target network
- [ ] Private keys stored securely
- [ ] CORS origins properly configured
- [ ] Database backups enabled
- [ ] Monitoring/alerting set up
- [ ] Contract audit completed (for mainnet)

## Contract Deployment

### 1. Deploy to Testnet (Mumbai)

```bash
# Update .env
export POLYGON_PRIVATE_KEY=your_mumbai_private_key
export POLYGONSCAN_API_KEY=your_polygonscan_key

# Dry run first
npx hardhat run scripts/deploy.ts --network mumbai

# Actual deployment
npm run contracts:deploy:mumbai

# Verify contracts
npm run contracts:verify -- --network mumbai
```

### 2. Deploy to Mainnet (Polygon)

```bash
# Review deployment script
cat scripts/deploy.ts

# Update .env with mainnet config
export POLYGON_RPC_URL=https://polygon-rpc.com
export POLYGON_CHAIN_ID=137
export POLYGON_PRIVATE_KEY=your_mainnet_private_key

# Dry run on forked mainnet
npx hardhat run scripts/deploy.ts --network localhost --no-compile

# Actual deployment to mainnet
npm run contracts:deploy:polygon

# Verify on PolygonScan
npm run contracts:verify -- --network polygon

# Save addresses
cat deployments/latest.json > contracts-deployed.json
```

### 3. Post-Deployment Setup

After contracts are deployed:

```bash
# 1. Update .env with deployed addresses
cat deployments/latest.json

# 2. Authorize gateways
npx hardhat run scripts/authorize-gateways.ts --network polygon

# 3. Set guardians for PolicyRegistry
npx hardhat run scripts/setup-guardians.ts --network polygon

# 4. Verify contracts are working
curl -X GET https://api.polygonscan.com/api?module=contract&action=getabi&address=0x... &apikey=YOUR_KEY
```

## Backend Deployment

### AWS ECS (Recommended)

1. **Create ECR Repository**
```bash
aws ecr create-repository --repository-name omniaegis-backend
```

2. **Build and Push Docker Image**
```bash
docker build -f Dockerfile.backend -t omniaegis-backend:latest .
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker tag omniaegis-backend:latest YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/omniaegis-backend:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/omniaegis-backend:latest
```

3. **Deploy to ECS**
```bash
# Create ECS task definition (task-definition.json)
aws ecs register-task-definition --cli-input-json file://task-definition.json

# Create ECS service
aws ecs create-service \
  --cluster omniaegis \
  --service-name backend \
  --task-definition omniaegis-backend:1 \
  --desired-count 2 \
  --load-balancers targetGroupArn=arn:aws:...,containerName=omniaegis-backend,containerPort=8000
```

### Google Cloud Run

```bash
# Build and push
gcloud builds submit --tag gcr.io/PROJECT_ID/omniaegis-backend:latest -f Dockerfile.backend

# Deploy
gcloud run deploy omniaegis-backend \
  --image gcr.io/PROJECT_ID/omniaegis-backend:latest \
  --platform managed \
  --region us-central1 \
  --set-env-vars DATABASE_URL=...,REDIS_URL=...,etc \
  --memory 2Gi \
  --cpu 2
```

### Heroku

```bash
heroku create omniaegis-backend
heroku buildpacks:add heroku/python
heroku config:set DATABASE_URL=... REDIS_URL=... etc
git push heroku main
```

## Frontend Deployment

### Vercel (Recommended)

1. **Connect GitHub Repository**
```bash
npm install -g vercel
vercel link
```

2. **Deploy**
```bash
# Set environment variables in Vercel dashboard
# VITE_API_URL=https://api.omniaegis.com

# Deploy
vercel deploy --prod
```

### Netlify

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Deploy
netlify deploy --prod --dir=frontend/dist \
  --site-name omniaegis-frontend \
  --env=production
```

### AWS S3 + CloudFront

```bash
# Build frontend
npm run build --prefix frontend

# Upload to S3
aws s3 sync frontend/dist s3://omniaegis-frontend-prod --delete

# Invalidate CloudFront cache
aws cloudfront create-invalidation --distribution-id E123ABC --paths "/*"
```

## Database Setup

### PostgreSQL

```bash
# Use managed service (AWS RDS, Google Cloud SQL, or Supabase)
# Or self-hosted:

docker run -d \
  -e POSTGRES_USER=omniaegis \
  -e POSTGRES_PASSWORD=strong_password \
  -e POSTGRES_DB=omniaegis \
  -p 5432:5432 \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:16-alpine

# Run migrations
psql $DATABASE_URL < database/migrations/001-init.sql
```

### Redis

```bash
# Use managed service (AWS ElastiCache, Upstash, or Redis Cloud)
# Or self-hosted:

docker run -d \
  -p 6379:6379 \
  -v redis_data:/data \
  redis:7-alpine redis-server --appendonly yes
```

### Neo4j

```bash
# Use managed service (Neo4j AuraDB)
# Or self-hosted:

docker run -d \
  -e NEO4J_AUTH=neo4j/strong_password \
  -p 7687:7687 \
  -p 7474:7474 \
  -v neo4j_data:/var/lib/neo4j/data \
  neo4j:5-community
```

### Qdrant

```bash
# Use managed service (Qdrant Cloud)
# Or self-hosted with persistent storage

docker run -d \
  -p 6333:6333 \
  -p 6334:6334 \
  -v qdrant_data:/qdrant/storage \
  qdrant/qdrant:latest
```

## Monitoring & Logging

### Setup Prometheus + Grafana

```bash
# Create prometheus.yml config
mkdir -p monitoring
cat > monitoring/prometheus.yml << EOF
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'omniaegis-backend'
    static_configs:
      - targets: ['localhost:8000']
EOF

# Run Prometheus
docker run -d -p 9090:9090 -v $(pwd)/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus

# Run Grafana
docker run -d -p 3000:3000 grafana/grafana

# Access Grafana at http://localhost:3000
```

### Setup Datadog

```bash
# Install Datadog agent on backend host
DD_AGENT_MAJOR_VERSION=7 DD_API_KEY=YOUR_API_KEY DD_SITE="datadoghq.com" bash -c "$(curl -L https://s3.amazonaws.com/dd-agent/scripts/install_agent.sh)"

# Configure logs
cat > /etc/datadog-agent/conf.d/fastapi.d/conf.yaml << EOF
logs:
  - type: file
    path: /app/logs/fastapi.log
    service: omniaegis
    source: fastapi
EOF
```

## Backup & Disaster Recovery

### Database Backup

```bash
# Automated daily backups to S3
aws s3 sync /var/lib/postgresql/data s3://omniaegis-backups/database/$(date +%Y-%m-%d)/ --sse AES256
```

### Contract Backup

```bash
# Keep contract ABIs and deployment info
git commit -m "Backup contracts deployment #$(date +%s)"
```

## Scaling

### Horizontal Scaling (Backend)

```bash
# Use load balancer (ALB, NGINX) in front of multiple backend instances
# Each instance connects to shared database/cache

# Monitor and auto-scale based on:
# - CPU usage > 70%
# - Memory usage > 80%
# - Request latency > 1s
```

### Database Scaling

- **PostgreSQL**: Read replicas, connection pooling
- **Redis**: Cluster mode, replication
- **Neo4j**: Graph database clustering
- **Qdrant**: Distributed mode

## Security Hardening

1. **Network Security**
   - Use VPC/private networking
   - Enable WAF (Web Application Firewall)
   - DDoS protection

2. **Secret Management**
   - Use AWS Secrets Manager / Google Secret Manager
   - Never commit secrets
   - Rotate keys regularly

3. **API Security**
   - Rate limiting
   - API key management
   - Request signing

4. **Blockchain Security**
   - Use hardware wallet for private keys
   - Enable 2FA on deployment tools
   - Multi-sig for critical operations

## Maintenance & Updates

```bash
# Update dependencies
npm update
pip list --outdated

# Security patches
npm audit fix
pip check

# Contract upgrades
# Use proxy pattern for upgradeable contracts
npx hardhat upgrade
```

## Troubleshooting Deployments

### Check Application Health

```bash
# Backend health
curl https://api.omniaegis.com/health

# Database connectivity
psql $DATABASE_URL -c "SELECT 1"

# Redis connectivity
redis-cli -u $REDIS_URL ping

# Neo4j connectivity
cypher-shell -u neo4j -p password "RETURN 1"
```

### View Logs

```bash
# AWS CloudWatch
aws logs tail /ecs/omniaegis-backend --follow

# Google Cloud Logging
gcloud logging read --filter="resource.type=cloud_run_revision" --limit 50

# Docker logs
docker logs -f omniaegis-backend
```

### Rollback Deployment

```bash
# ECS rollback
aws ecs update-service --cluster omniaegis --service backend --task-definition omniaegis-backend:PREVIOUS_VERSION

# Vercel rollback
vercel rollback

# GitHub rollback
git revert <commit-hash>
git push
```

---

For more information, see [README.md](./README.md)
