'use client';

import { useState, useEffect } from 'react';

interface ModelVersion {
  id: string;
  type: string;
  version: string;
  status: 'Active' | 'Shadow' | 'Live' | 'Previous';
  deployedAt: string;
  performanceMetrics: Record<string, number>;
}

interface VersionData {
  versions: ModelVersion[];
  total: number;
}

export default function VersionRegistry() {
  const [data, setData] = useState<VersionData | null>(null);
  const [rollingBack, setRollingBack] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/governance/versions')
      .then((res) => res.json())
      .then(setData)
      .catch(() => null);
  }, []);

  const handleRollback = async (versionId: string) => {
    setRollingBack(versionId);
    try {
      const response = await fetch('/api/governance/versions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ versionId }),
      });
      const result = await response.json();
      alert(`Rollback initiated: ${result.rollbackId}`);
    } catch (error) {
      alert('Rollback failed');
    } finally {
      setRollingBack(null);
    }
  };

  if (!data) {
    return (
      <div className="h-80 rounded-[1.75rem] border border-slate-200/80 bg-slate-50/80 flex items-center justify-center text-slate-500">
        <p className="text-sm">Loading version registry...</p>
      </div>
    );
  }

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      Active: 'bg-emerald-100 text-emerald-700',
      Shadow: 'bg-sky-100 text-sky-700',
      Live: 'bg-accent/10 text-accent',
      Previous: 'bg-slate-100 text-slate-700',
    };
    return colors[status] || 'bg-slate-100 text-slate-700';
  };

  return (
    <div className="space-y-4">
      {data.versions.map((version) => (
        <div
          key={version.id}
          className="rounded-3xl border border-slate-200/70 bg-white/85 p-6 hover:shadow-md transition"
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex-1 space-y-2">
              <div className="flex items-center gap-3">
                <h3 className="text-lg font-bold text-slate-950">
                  {version.type} <span className="font-mono text-sm text-slate-600">{version.version}</span>
                </h3>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${getStatusBadge(version.status)}`}>
                  {version.status}
                </span>
              </div>
              <p className="text-sm text-slate-600">
                Deployed: {new Date(version.deployedAt).toLocaleString()}
              </p>

              {/* Performance Metrics */}
              <div className="flex flex-wrap gap-2 pt-2">
                {Object.entries(version.performanceMetrics).map(([key, value]) => (
                  <span key={key} className="rounded-full bg-slate-50 px-3 py-1 text-xs text-slate-600">
                    <span className="font-semibold">{key}:</span> {typeof value === 'number' && value < 1 ? value.toFixed(3) : value}
                  </span>
                ))}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex-shrink-0 flex gap-2">
              {version.status === 'Previous' && (
                <button
                  onClick={() => handleRollback(version.id)}
                  disabled={rollingBack === version.id}
                  className="rounded-2xl border border-slate-200 bg-white hover:bg-slate-50 disabled:bg-slate-100 text-slate-900 font-semibold py-2 px-4 text-sm transition"
                >
                  {rollingBack === version.id ? 'Rolling back...' : 'Rollback'}
                </button>
              )}
              {version.status === 'Shadow' && (
                <button className="rounded-2xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-900 font-semibold py-2 px-4 text-sm transition">
                  Compare
                </button>
              )}
              <button className="rounded-2xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-900 font-semibold py-2 px-4 text-sm transition">
                View Logs
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}