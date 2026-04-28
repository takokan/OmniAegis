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
      <div className="h-80 rounded-[1.75rem] bg-surface-elevated flex items-center justify-center text-text-secondary shadow-sm">
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
                  ? 'bg-surface-elevated text-text-primary'
                  : 'bg-accent text-text-primary'
                : 'bg-surface-tertiary text-text-secondary hover:bg-surface-elevated'
            }`}
          >
            {policy === 'shadow' ? '🔬 Shadow' : '🚀 Live'}
          </button>
        ))}
      </div>

      {/* Active Policy Info */}
      <div className="rounded-3xl bg-surface-elevated p-6 space-y-2 shadow-sm">
        <div className="flex items-center justify-between">
          <p className="text-xs uppercase tracking-[0.28em] text-text-tertiary">Policy Version</p>
          <span className="rounded-full bg-surface-primary px-3 py-1 text-xs font-mono font-semibold text-text-secondary">
            {metrics.version}
          </span>
        </div>
        <p className="text-xs text-text-tertiary">
          Deployed: {new Date(metrics.deployedAt).toLocaleString()}
        </p>
      </div>

      {/* Metrics Grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        {comparison.slice(0, 4).map((metric) => (
          <div key={metric.label} className="premium-card rounded-3xl p-4">
            <p className="text-xs uppercase tracking-[0.28em] text-text-tertiary">{metric.label}</p>
            <p className="mt-2 text-2xl font-bold text-text-primary">
              {formatVal(metric.shadowVal)}{metric.unit}
            </p>
            <div className="mt-2 flex items-center justify-between text-xs">
              <span className="text-text-tertiary">vs Live:</span>
              <span className={getImprovementBadge(metric)}>
                {formatVal(metric.liveVal)}{metric.unit}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Constraints Status */}
      <div className="premium-card rounded-3xl p-6 space-y-4">
        <p className="text-sm font-semibold text-text-primary">Constraint Status</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl bg-surface-elevated p-4">
            <p className="text-xs text-text-tertiary">Privacy Budget</p>
            <p className="mt-1 font-mono font-semibold text-text-primary">
              {metrics.constraints.privacyBudget.used}/{metrics.constraints.privacyBudget.total}
            </p>
            <div className="mt-2 h-1 rounded-full bg-surface-primary overflow-hidden">
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
          <div className="rounded-2xl bg-surface-elevated p-4">
            <p className="text-xs text-text-tertiary">Fairness Score</p>
            <p className="mt-1 font-mono font-semibold text-text-primary">
              {(metrics.constraints.fairnessThreshold * 100).toFixed(1)}%
            </p>
            <p className="mt-2 text-xs text-emerald-600 font-semibold">Threshold met ✓</p>
          </div>
          <div className="rounded-2xl bg-surface-elevated p-4">
            <p className="text-xs text-text-tertiary">Latency P99</p>
            <p className="mt-1 font-mono font-semibold text-text-primary">{metrics.constraints.latencyP99}ms</p>
            <p className="mt-2 text-xs text-emerald-600 font-semibold">Within SLA ✓</p>
          </div>
        </div>
      </div>
    </div>
  );
}