// Environment variables for frontend
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export const API_TIMEOUT = import.meta.env.VITE_API_TIMEOUT || 30000;
export const ENVIRONMENT = import.meta.env.MODE || 'development';

export const API_ENDPOINTS = {
  // Health
  HEALTH: '/health',
  
  // HITL (Human-in-the-Loop)
  HITL_ITEMS: '/api/hitl/items',
  HITL_ITEM: (id: string) => `/api/hitl/items/${id}`,
  HITL_REVIEW: (id: string) => `/api/hitl/items/${id}/review`,
  HITL_QUEUE: '/api/hitl/queue',
  
  // XAI (Explainable AI)
  XAI_EXPLANATIONS: (assetId: string) => `/api/xai/explanations/${assetId}`,
  XAI_DRIFT: '/api/xai/drift/detect',
  XAI_PROJECTION: '/api/xai/projection/umap',
  
  // Sentinel (Audit)
  SENTINEL_DECISIONS: '/api/sentinel/decisions',
  SENTINEL_DECISION: (id: string) => `/api/sentinel/decisions/${id}`,
  
  // Batch (Blockchain)
  BATCH_MERKLE: '/api/batch/merkle',
  BATCH_PROOF: (decisionId: string) => `/api/batch/proof/${decisionId}`,
};
