#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend/OmniAegis-Frontend-main"

cd "$ROOT_DIR"
npm --prefix "$FRONTEND_DIR" run dev
