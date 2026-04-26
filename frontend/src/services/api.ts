/**
 * OmniAegis Backend API Client
 * Handles all communication with the Python FastAPI backend
 */

const getApiBaseUrl = (): string => {
  // Try environment variable first
  if (typeof import.meta !== 'undefined' && import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  // Default to relative path (works when frontend and backend on same origin)
  if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
    return 'http://localhost:8000';
  }

  // In production, assume same origin
  return '';
};

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface HealthCheckResponse {
  status: string;
  version: string;
  timestamp: number;
}

class OmniAegisApi {
  private baseUrl: string;
  private timeout: number = 30000; // 30 seconds

  constructor() {
    this.baseUrl = getApiBaseUrl();
  }

  /**
   * Health check endpoint
   */
  async healthCheck(): Promise<HealthCheckResponse> {
    return this.get<HealthCheckResponse>('/health');
  }

  /**
   * Fetch HITL item by ID
   */
  async getHITLItem(itemId: string): Promise<unknown> {
    return this.get(`/api/hitl/items/${itemId}`);
  }

  /**
   * Submit HITL review decision
   */
  async submitHITLReview(itemId: string, decision: unknown): Promise<unknown> {
    return this.post(`/api/hitl/items/${itemId}/review`, decision);
  }

  /**
   * Get XAI explanations
   */
  async getExplanations(assetId: string): Promise<unknown> {
    return this.get(`/api/xai/explanations/${assetId}`);
  }

  /**
   * Record decision in blockchain
   */
  async recordDecision(
    decisionId: string,
    policyId: number,
    riskScore: number,
    action: number,
    evidenceCid: string
  ): Promise<unknown> {
    return this.post('/api/sentinel/decisions', {
      decision_id: decisionId,
      policy_id: policyId,
      risk_score: riskScore,
      action,
      evidence_cid: evidenceCid,
    });
  }

  /**
   * Generic GET request
   */
  private async get<T = unknown>(endpoint: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'GET',
      headers: this.getHeaders(),
      signal: AbortSignal.timeout(this.timeout),
    });

    return this.handleResponse<T>(response);
  }

  /**
   * Generic POST request
   */
  private async post<T = unknown>(endpoint: string, data: unknown): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(this.timeout),
    });

    return this.handleResponse<T>(response);
  }

  /**
   * Generic PUT request
   */
  private async put<T = unknown>(endpoint: string, data: unknown): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'PUT',
      headers: this.getHeaders(),
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(this.timeout),
    });

    return this.handleResponse<T>(response);
  }

  /**
   * Handle API response
   */
  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      let errorMessage = `API Error: ${response.status} ${response.statusText}`;
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorData.error || errorMessage;
      } catch {
        // Couldn't parse error response
      }
      throw new Error(errorMessage);
    }

    try {
      return await response.json() as T;
    } catch {
      throw new Error('Failed to parse API response');
    }
  }

  /**
   * Get request headers
   */
  private getHeaders(): Record<string, string> {
    return {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
  }
}

// Singleton instance
export const apiClient = new OmniAegisApi();
export default apiClient;
