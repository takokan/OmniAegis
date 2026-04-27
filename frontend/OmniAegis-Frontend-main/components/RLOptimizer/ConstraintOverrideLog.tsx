'use client';

import { useState, useEffect } from 'react';

interface Constraint {
  id: string;
  timestamp: string;
  constraint: string;
  proposedDecision: string;
  override: 'ALLOWED' | 'BLOCKED';
  reason: string;
  policyVersion: string;
}

interface ConstraintData {
  constraints: Constraint[];
  total: number;
}

export default function ConstraintOverrideLog() {
  const [data, setData] = useState<ConstraintData | null>(null);
  const [filter, setFilter] = useState<'ALL' | 'ALLOWED' | 'BLOCKED'>('ALL');

  useEffect(() => {
    fetch('/api/rl/constraints')
      .then((res) => res.json())
      .then(setData)
      .catch(() => null);
  }, []);

  if (!data) {
    return (
      <div className="h-80 rounded-[1.75rem] border border-slate-200/80 bg-slate-50/80 flex items-center justify-center text-slate-500">
        <p className="text-sm">Loading constraint log...</p>
      </div>
    );
  }

  const filtered =
    filter === 'ALL' ? data.constraints : data.constraints.filter((c) => c.override === filter);

  const allowedCount = data.constraints.filter((c) => c.override === 'ALLOWED').length;
  const blockedCount = data.constraints.filter((c) => c.override === 'BLOCKED').length;

  const getOverrideBadge = (override: 'ALLOWED' | 'BLOCKED') => {
    return override === 'ALLOWED'
      ? 'bg-emerald-100 text-emerald-700'
      : 'bg-red-100 text-red-700';
  };

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-3xl bg-slate-50/75 p-4">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Total Intercepted</p>
          <p className="mt-2 text-3xl font-bold text-slate-950">{data.total}</p>
        </div>
        <div className="rounded-3xl bg-emerald-50 border border-emerald-200 p-4">
          <p className="text-xs uppercase tracking-[0.28em] text-emerald-600">Allowed Through</p>
          <p className="mt-2 text-3xl font-bold text-emerald-900">{allowedCount}</p>
        </div>
        <div className="rounded-3xl bg-red-50 border border-red-200 p-4">
          <p className="text-xs uppercase tracking-[0.28em] text-red-600">Blocked</p>
          <p className="mt-2 text-3xl font-bold text-red-900">{blockedCount}</p>
        </div>
      </div>

      {/* Filter Buttons */}
      <div className="flex gap-2">
        {(['ALL', 'ALLOWED', 'BLOCKED'] as const).map((status) => (
          <button
            key={status}
            onClick={() => setFilter(status)}
            className={`flex-1 rounded-2xl px-4 py-3 text-sm font-semibold transition ${
              filter === status
                ? status === 'ALLOWED'
                  ? 'bg-emerald-100 text-emerald-900'
                  : status === 'BLOCKED'
                    ? 'bg-red-100 text-red-900'
                    : 'bg-slate-900 text-white'
                : 'bg-slate-50 text-slate-600 hover:bg-slate-100'
            }`}
          >
            {status}
          </button>
        ))}
      </div>

      {/* Constraint Log */}
      <div className="space-y-3">
        {filtered.map((constraint) => (
          <div
            key={constraint.id}
            className="rounded-3xl border border-slate-200/70 bg-white/85 p-5 hover:shadow-md transition"
          >
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex-1 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                    {constraint.constraint}
                  </span>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${getOverrideBadge(
                      constraint.override
                    )}`}
                  >
                    {constraint.override}
                  </span>
                </div>
                <p className="text-sm font-semibold text-slate-900">
                  Decision: <span className="text-slate-600">{constraint.proposedDecision}</span>
                </p>
                <p className="text-sm text-slate-600">{constraint.reason}</p>
                <div className="flex items-center gap-2 text-xs text-slate-500 pt-1">
                  <span>{new Date(constraint.timestamp).toLocaleString()}</span>
                  <span>•</span>
                  <span className="font-mono">{constraint.policyVersion}</span>
                </div>
              </div>
              <div className="flex-shrink-0 rounded-2xl bg-slate-50 px-3 py-1 text-xs font-mono text-slate-600">
                {constraint.id}
              </div>
            </div>
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="rounded-3xl border border-slate-200/70 bg-slate-50/75 p-8 text-center">
          <p className="text-slate-600">No constraints found for this filter.</p>
        </div>
      )}
    </div>
  );
}