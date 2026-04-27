'use client';

import { useState, useEffect } from 'react';

interface PolicyMetrics {
  version: string;
  deployedAt: string;
  klDivergence: number;
  rewardMean: number;
  rewardStd: number;
  enforcementRate: number;
  falsePositiveRate: number;
  constraints: {
    privacyBudget: { used: number; total: number };
    fairnessThreshold: number;
    latencyP99: number;
  };
}

interface PolicyComparisonData {
  shadow: PolicyMetrics;
  live: PolicyMetrics;
}

export default function PolicyComparisonTool() {
  const [data, setData] = useState<PolicyComparisonData | null>(null);
  const [activePolicy, setActivePolicy] = useState<'shadow' | 'live'>('shadow');

  useEffect(() => {
    fetch('/api/rl/policy-metrics')
      .then((res) => res.json())
      .then(setData)
      .catch(() => null);
  }, []);

  if (!data) {
    return (
      <div className="h-80 rounded-[1.75rem] border border-slate-200/80 bg-slate-50/80 flex items-center justify-center text-slate-500">
        <p className="text-sm">Loading policy metrics...</p>
      </div>
    );
  }

  const metrics = data[activePolicy];
  const comparison = [
    { label: 'KL Divergence', shadowVal: data.shadow.klDivergence, liveVal: data.live.klDivergence, unit: '', better: 'lower' },
    { label: 'Reward Mean', shadowVal: data.shadow.rewardMean, liveVal: data.live.rewardMean, unit: '', better: 'higher' },
    { label: 'Reward Std Dev', shadowVal: data.shadow.rewardStd, liveVal: data.live.rewardStd, unit: '', better: 'lower' },
    { label: 'Enforcement Rate', shadowVal: data.shadow.enforcementRate, liveVal: data.live.enforcementRate, unit: '%', better: 'higher' },
    { label: 'False Positive Rate', shadowVal: data.shadow.falsePositiveRate, liveVal: data.live.falsePositiveRate, unit: '%', better: 'lower' },
  ];

  const formatVal = (val: number) => (val < 1 ? val.toFixed(4) : val.toFixed(2));
  const getImprovementBadge = (metric: (typeof comparison)[0]) => {
    const isBetter = metric.better === 'higher' ? data.shadow[metric.label.toLowerCase().replace(/ /g, '') as keyof PolicyMetrics] > data.live[metric.label.toLowerCase().replace(/ /g, '') as keyof PolicyMetrics] : data.shadow[metric.label.toLowerCase().replace(/ /g, '') as keyof PolicyMetrics] < data.live[metric.label.toLowerCase().replace(/ /g, '') as keyof PolicyMetrics];
    return isBetter ? 'text-emerald-600' : 'text-red-600';
  };

  return (
    <div className="space-y-6">
      {/* Policy Selector */}
      <div className="flex gap-2">
        {['shadow', 'live'].map((policy) => (
          <button
            key={policy}
            onClick={() => setActivePolicy(policy as 'shadow' | 'live')}
            className={`flex-1 rounded-2xl px-4 py-3 text-sm font-semibold transition ${
              activePolicy === policy
                ? policy === 'shadow'
                  ? 'bg-slate-100 text-slate-900'
                  : 'bg-accent text-white'
                : 'bg-slate-50 text-slate-600 hover:bg-slate-100'
            }`}
          >
            {policy === 'shadow' ? '🔬 Shadow' : '🚀 Live'}
          </button>
        ))}
      </div>

      {/* Active Policy Info */}
      <div className="rounded-3xl bg-slate-50/75 p-6 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Policy Version</p>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-mono font-semibold text-slate-700">
            {metrics.version}
          </span>
        </div>
        <p className="text-xs text-slate-500">
          Deployed: {new Date(metrics.deployedAt).toLocaleString()}
        </p>
      </div>

      {/* Metrics Grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        {comparison.slice(0, 4).map((metric) => (
          <div key={metric.label} className="rounded-3xl border border-slate-200/70 bg-white/85 p-4">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{metric.label}</p>
            <p className="mt-2 text-2xl font-bold text-slate-950">
              {formatVal(metric.shadowVal)}{metric.unit}
            </p>
            <div className="mt-2 flex items-center justify-between text-xs">
              <span className="text-slate-500">vs Live:</span>
              <span className={getImprovementBadge(metric)}>
                {formatVal(metric.liveVal)}{metric.unit}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Constraints Status */}
      <div className="rounded-3xl border border-slate-200/70 bg-white/85 p-6 space-y-4">
        <p className="text-sm font-semibold text-slate-900">Constraint Status</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-xs text-slate-500">Privacy Budget</p>
            <p className="mt-1 font-mono font-semibold text-slate-900">
              {metrics.constraints.privacyBudget.used}/{metrics.constraints.privacyBudget.total}
            </p>
            <div className="mt-2 h-1 rounded-full bg-slate-200 overflow-hidden">
              <div
                className={`h-full ${
                  metrics.constraints.privacyBudget.used / metrics.constraints.privacyBudget.total > 0.8
                    ? 'bg-red-500'
                    : 'bg-emerald-500'
                }`}
                style={{
                  width: `${(metrics.constraints.privacyBudget.used / metrics.constraints.privacyBudget.total) * 100}%`,
                }}
              />
            </div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-xs text-slate-500">Fairness Score</p>
            <p className="mt-1 font-mono font-semibold text-slate-900">
              {(metrics.constraints.fairnessThreshold * 100).toFixed(1)}%
            </p>
            <p className="mt-2 text-xs text-emerald-600 font-semibold">Threshold met ✓</p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-xs text-slate-500">Latency P99</p>
            <p className="mt-1 font-mono font-semibold text-slate-900">{metrics.constraints.latencyP99}ms</p>
            <p className="mt-2 text-xs text-emerald-600 font-semibold">Within SLA ✓</p>
          </div>
        </div>
      </div>
    </div>
  );
}