'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';

import { Button, Input } from '@/components/ui';

interface GraphNode {
  id: string;
  label: string;
  type: 'asset' | 'creator' | 'licensee' | string;
  is_query: boolean;
  metadata: Record<string, unknown>;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight: number;
}

interface GraphResponse {
  query_asset_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const LAST_ASSET_KEY = 'sentinel-last-registered-asset-id';
const LAST_GRAPH_KEY = 'sentinel-last-registered-graph';

function badgeClasses(type: string, isQuery: boolean) {
  if (isQuery) return 'bg-accent text-text-primary';
  if (type === 'creator') return 'bg-emerald-500/15 text-emerald-300';
  if (type === 'licensee') return 'bg-violet-500/15 text-violet-300';
  return 'bg-surface-tertiary text-text-secondary';
}

export default function XAIRelationshipExplorer() {
  const [assetId, setAssetId] = useState('');
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const selectedNode = useMemo(() => graph?.nodes.find((node) => node.is_query) ?? graph?.nodes[0] ?? null, [graph]);

  const loadGraph = async (requestedAssetId: string) => {
    const normalized = requestedAssetId.trim();
    if (!normalized) {
      setError('Enter an asset ID to load the Neo4j relationship graph.');
      return;
    }

    const token = localStorage.getItem('sentinel-access-token') || '';
    setLoading(true);
    setError('');

    try {
      const response = await fetch(`/api/xai/graph/${encodeURIComponent(normalized)}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || `Failed to load graph (${response.status})`);
      }

      const payload = (await response.json()) as GraphResponse;
      setGraph(payload);
      setAssetId(payload.query_asset_id);
      localStorage.setItem(LAST_ASSET_KEY, payload.query_asset_id);
      localStorage.setItem(LAST_GRAPH_KEY, JSON.stringify(payload));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load graph relationships.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const cachedAssetId = localStorage.getItem(LAST_ASSET_KEY) || '';
    const cachedGraph = localStorage.getItem(LAST_GRAPH_KEY);

    if (cachedAssetId) {
      setAssetId(cachedAssetId);
    }

    if (cachedGraph) {
      try {
        setGraph(JSON.parse(cachedGraph) as GraphResponse);
      } catch {
        localStorage.removeItem(LAST_GRAPH_KEY);
      }
    }
  }, []);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-4xl font-bold text-text-primary">XAI Relationship Graph</h1>
        <p className="text-lg text-text-secondary">
          Inspect the asset-centered relationship graph persisted in Neo4j after registration.
        </p>
      </div>

      <form
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          void loadGraph(assetId);
        }}
        className="grid gap-4 rounded-xl bg-surface-secondary p-4 shadow-sm lg:grid-cols-[minmax(0,1fr)_auto]"
      >
        <Input
          label="Asset ID"
          placeholder="Paste a registered asset ID"
          value={assetId}
          onChange={(event) => setAssetId(event.target.value)}
        />
        <div className="flex items-end">
          <Button className="w-full lg:w-auto" type="submit" isLoading={loading}>
            Load Graph
          </Button>
        </div>
      </form>

      {error && <div className="rounded-xl bg-danger-bg p-4 text-sm text-danger shadow-sm">{error}</div>}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_360px]">
        <div className="rounded-xl bg-surface-secondary p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Graph canvas</p>
              <p className="mt-2 text-sm text-text-primary">
                {graph
                  ? `${graph.nodes.length} nodes and ${graph.edges.length} relationships loaded from Neo4j.`
                  : 'Load an asset to visualize its related creator, licensee, and similar assets.'}
              </p>
            </div>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {(graph?.nodes ?? []).map((node) => (
              <div key={node.id} className="rounded-xl bg-surface-tertiary p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-text-primary">{node.label}</p>
                    <p className="mt-1 text-xs font-mono text-text-tertiary">{node.id}</p>
                  </div>
                  <span className={`rounded-full px-2 py-1 text-[11px] font-semibold uppercase ${badgeClasses(node.type, node.is_query)}`}>
                    {node.is_query ? 'query' : node.type}
                  </span>
                </div>
                <div className="mt-3 text-xs text-text-secondary">
                  {'modality' in node.metadata && typeof node.metadata.modality === 'string' ? (
                    <p>Modality: {node.metadata.modality}</p>
                  ) : (
                    <p>Node type: {node.type}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-xl bg-surface-secondary p-5 shadow-sm">
            <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Selected asset</p>
            {selectedNode ? (
              <div className="mt-3 space-y-2 text-sm text-text-secondary">
                <p className="font-semibold text-text-primary">{selectedNode.label}</p>
                <p className="font-mono text-xs">{selectedNode.id}</p>
                {'filename' in selectedNode.metadata && typeof selectedNode.metadata.filename === 'string' && (
                  <p>Filename: {selectedNode.metadata.filename}</p>
                )}
                {'license_file_name' in selectedNode.metadata && typeof selectedNode.metadata.license_file_name === 'string' && (
                  <p>License file: {selectedNode.metadata.license_file_name}</p>
                )}
                {'authorization_status' in selectedNode.metadata && typeof selectedNode.metadata.authorization_status === 'string' && (
                  <p>Status: {selectedNode.metadata.authorization_status}</p>
                )}
              </div>
            ) : (
              <p className="mt-3 text-sm text-text-secondary">No asset selected yet.</p>
            )}
          </div>

          <div className="rounded-xl bg-surface-secondary p-5 shadow-sm">
            <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Relationships</p>
            <div className="mt-3 space-y-3">
              {(graph?.edges ?? []).length > 0 ? (
                graph?.edges.map((edge, index) => (
                  <div key={`${edge.source}-${edge.target}-${edge.type}-${index}`} className="rounded-lg bg-surface-tertiary p-3 text-sm">
                    <p className="font-semibold text-text-primary">{edge.type}</p>
                    <p className="mt-1 text-xs text-text-secondary">
                      {edge.source} → {edge.target}
                    </p>
                    <p className="mt-1 text-xs text-text-tertiary">Weight: {edge.weight.toFixed(3)}</p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-text-secondary">No relationships loaded yet.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
