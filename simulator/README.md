# OmniAegis Simulator

This simulator generates synthetic multi-user activity that mimics core OmniAegis flows without depending on database writes.

It simulates:
- multiple signed-in users,
- synthetic content uploads across modalities (`image`, `video`, `audio`, `text`),
- decision stream events (`sentinel:decision:stream`),
- real-time HITL queue feed updates (`sentinel:hitl:queue` via consumer, or direct fallback),
- blockchain-style governance/audit logs (`sentinel:blockchain:audit:stream`).

## Why this works without DB

The simulator writes directly to Redis streams/ZSET keys used by the existing services.  
So even if PostgreSQL/Neo4j are inactive, the live queue/log UX still updates.

## Setup

From repo root:

```bash
python -m venv .venv-sim
source .venv-sim/bin/activate
pip install -r simulator/requirements.txt
```

Set Redis URL if needed:

```bash
export SIM_REDIS_URL="redis://127.0.0.1:6379/0"
```

If `.env` exists at repo root, the simulator will auto-load it and resolve Redis in this order:
1. `--redis-url`
2. `SIM_REDIS_URL`
3. `REDIS_URL` (unless it points to localhost and Upstash credentials are present)
4. derived Upstash Redis TLS URL from `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN`
5. `redis://127.0.0.1:6379/0`

## Run

One simulation round:

```bash
python simulator/simulator.py --users 10 --iterations 6 --fallback-hitl
```

Continuous load:

```bash
python simulator/simulator.py --users 15 --iterations 8 --continuous --fallback-hitl
```

## Backend/Frontend compatibility added

This repo now includes:
- backend endpoint `GET /governance/audit` to read audit log entries from Redis stream,
- backend endpoint `POST /governance/audit` to append audit log entries,
- frontend route `GET /api/governance/audit` proxying to backend,
- frontend blockchain logs page polling `/api/governance/audit` for real-time updates.

## Notes

- `--fallback-hitl` is recommended when `ENABLE_DECISION_STREAM_CONSUMER` is disabled.
- If the decision consumer is enabled, HITL queue is updated by normal project logic from the decision stream.
