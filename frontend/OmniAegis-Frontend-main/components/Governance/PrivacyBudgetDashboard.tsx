'use client';

import { useState, useEffect } from 'react';

interface PrivacyData {
  currentRound: number;
  totalRounds: number;
  budgetStatus: Array<{
    round: number;
    timestamp: string;
    epsilonUsed: number;
    epsilonBudget: number;
    percentageUsed: number;
  }>;
}

export default function PrivacyBudgetDashboard() {
  const [data, setData] = useState<PrivacyData | null>(null);

  useEffect(() => {
    fetch('/api/governance/privacy-budget')
      .then((res) => res.json())
      .then(setData)
      .catch(() => null);
  }, []);

  if (!data) {
    return (
      <div className="h-96 rounded-[1.75rem] border border-slate-200/80 bg-slate-50/80 flex items-center justify-center text-slate-500">
        <p className="text-sm">Loading privacy metrics...</p>
      </div>
    );
  }

  const current = data.budgetStatus[0];
  const remaining = current.epsilonBudget - current.epsilonUsed;
  const isWarning = current.percentageUsed > 70;
  const isDanger = current.percentageUsed > 90;

  const getStatusColor = () => {
    if (isDanger) return 'text-red-700 bg-red-50 border-red-200';
    if (isWarning) return 'text-yellow-700 bg-yellow-50 border-yellow-200';
    return 'text-emerald-700 bg-emerald-50 border-emerald-200';
  };

  return (
    <div className="space-y-6">
      {/* Current Status */}
      <div className={`rounded-3xl border p-6 ${getStatusColor()}`}>
        <p className="text-xs uppercase tracking-[0.28em] font-semibold mb-3">
          Current Round {data.currentRound} / {data.totalRounds}
        </p>
        <div className="grid gap-4 sm:grid-cols-4">
          <div>
            <p className="text-xs text-slate-600 mb-1">Budget Used</p>
            <p className="text-2xl font-bold">{current.epsilonUsed.toFixed(1)}</p>
          </div>
          <div>
            <p className="text-xs text-slate-600 mb-1">Budget Remaining</p>
            <p className="text-2xl font-bold">{remaining.toFixed(1)}</p>
          </div>
          <div>
            <p className="text-xs text-slate-600 mb-1">Total Budget</p>
            <p className="text-2xl font-bold">{current.epsilonBudget}</p>
          </div>
          <div>
            <p className="text-xs text-slate-600 mb-1">Usage %</p>
            <p className="text-2xl font-bold">{current.percentageUsed}%</p>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="mt-4 h-2 rounded-full bg-slate-300/50 overflow-hidden">
          <div
            className={`h-full transition-all ${
              isDanger ? 'bg-red-500' : isWarning ? 'bg-yellow-500' : 'bg-emerald-500'
            }`}
            style={{ width: `${current.percentageUsed}%` }}
          />
        </div>
      </div>

      {/* Historical Timeline */}
      <div className="rounded-3xl border border-slate-200/70 bg-white/85 p-6">
        <p className="text-sm font-semibold text-slate-900 mb-4">Privacy Budget Consumption Timeline</p>
        <div className="space-y-3">
          {data.budgetStatus.map((status, idx) => (
            <div key={status.round} className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-600">
                  Round {status.round} • {new Date(status.timestamp).toLocaleTimeString()}
                </span>
                <span className="font-mono font-semibold text-slate-900">
                  ε {status.epsilonUsed.toFixed(2)} ({status.percentageUsed}%)
                </span>
              </div>
              <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-sky-400 to-sky-600 transition-all"
                  style={{ width: `${status.percentageUsed}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* FL Retraining Status */}
      <div className="rounded-3xl border border-slate-200/70 bg-slate-50/75 p-6 space-y-3">
        <p className="text-sm font-semibold text-slate-900">Federated Learning Retraining</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-2xl bg-white p-3">
            <p className="text-xs text-slate-500 mb-1">Next FL Round</p>
            <p className="font-semibold text-slate-900">Round 13 in 45 minutes</p>
          </div>
          <div className="rounded-2xl bg-white p-3">
            <p className="text-xs text-slate-500 mb-1">Budget Refresh</p>
            <p className="font-semibold text-slate-900">10.0 ε → New Round</p>
          </div>
        </div>
      </div>
    </div>
  );
}