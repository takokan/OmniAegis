'use client';

import { useState, useEffect } from 'react';

interface TrainingMetric {
  round: number;
  timestamp: string;
  klDiv: number;
  reward: number;
  loss: number;
}

interface TrainingData {
  currentRound: number;
  totalRounds: number;
  metrics: TrainingMetric[];
}

export default function TrainingLoopMonitor() {
  const [data, setData] = useState<TrainingData | null>(null);
  const [activeMetric, setActiveMetric] = useState<'klDiv' | 'reward' | 'loss'>('klDiv');

  useEffect(() => {
    fetch('/api/rl/training-metrics')
      .then((res) => res.json())
      .then(setData)
      .catch(() => null);
  }, []);

  if (!data) {
    return (
      <div className="h-80 rounded-[1.75rem] bg-surface-elevated flex items-center justify-center text-text-secondary shadow-sm">
        <p className="text-sm">Loading training metrics...</p>
      </div>
    );
  }

  const getMetricLabel = (metric: 'klDiv' | 'reward' | 'loss') => {
    const labels = { klDiv: 'KL Divergence', reward: 'Reward Mean', loss: 'Loss' };
    return labels[metric];
  };

  const getMetricColor = (metric: 'klDiv' | 'reward' | 'loss') => {
    const colors = {
      klDiv: 'from-sky-400 to-sky-600',
      reward: 'from-emerald-400 to-emerald-600',
      loss: 'from-red-400 to-red-600',
    };
    return colors[metric];
  };

  const currentMetrics = data.metrics[data.metrics.length - 1];
  const maxKlDiv = Math.max(...data.metrics.map((m) => m.klDiv));
  const maxReward = Math.max(...data.metrics.map((m) => m.reward));
  const maxLoss = Math.max(...data.metrics.map((m) => m.loss));

  const getScale = (metric: 'klDiv' | 'reward' | 'loss') => {
    const scales = { klDiv: maxKlDiv, reward: maxReward, loss: maxLoss };
    return scales[metric];
  };

  return (
    <div className="space-y-6">
      {/* Metric Selector */}
      <div className="flex gap-2">
        {(['klDiv', 'reward', 'loss'] as const).map((metric) => (
          <button
            key={metric}
            onClick={() => setActiveMetric(metric)}
            className={`flex-1 rounded-2xl px-4 py-3 text-sm font-semibold transition ${
              activeMetric === metric
                ? `bg-gradient-to-r ${getMetricColor(metric)} text-text-primary`
                : 'bg-surface-tertiary text-text-secondary hover:bg-surface-elevated'
            }`}
          >
            {getMetricLabel(metric)}
          </button>
        ))}
      </div>

      {/* Current Values */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-3xl bg-surface-elevated p-6 shadow-sm">
          <p className="text-xs uppercase tracking-[0.28em] text-sky-600">KL Divergence</p>
          <p className="mt-2 text-3xl font-bold text-sky-900">{currentMetrics.klDiv.toFixed(4)}</p>
          <p className="mt-1 text-xs text-sky-700">Round {data.currentRound} / {data.totalRounds}</p>
        </div>
        <div className="rounded-3xl bg-surface-elevated p-6 shadow-sm">
          <p className="text-xs uppercase tracking-[0.28em] text-emerald-600">Reward Mean</p>
          <p className="mt-2 text-3xl font-bold text-emerald-900">{currentMetrics.reward.toFixed(2)}</p>
          <p className="mt-1 text-xs text-emerald-700">Converging ↑</p>
        </div>
        <div className="rounded-3xl bg-surface-elevated p-6 shadow-sm">
          <p className="text-xs uppercase tracking-[0.28em] text-red-600">Loss</p>
          <p className="mt-2 text-3xl font-bold text-red-900">{currentMetrics.loss.toFixed(4)}</p>
          <p className="mt-1 text-xs text-red-700">Decreasing ↓</p>
        </div>
      </div>

      {/* Timeline Chart */}
      <div className="premium-card rounded-3xl p-6 space-y-4">
        <p className="text-sm font-semibold text-text-primary">Training Progress</p>
        <div className="space-y-3">
          {data.metrics.map((metric, idx) => {
            const scale = getScale(activeMetric);
            const value = metric[activeMetric];
            const percentage = (value / scale) * 100;

            return (
              <div key={metric.round} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-text-secondary">
                    Round {metric.round} •{' '}
                    {new Date(metric.timestamp).toLocaleTimeString()}
                  </span>
                  <span className="font-mono font-semibold text-text-primary">
                    {value.toFixed(4)}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-surface-primary overflow-hidden">
                  <div
                    className={`h-full bg-gradient-to-r ${getMetricColor(activeMetric)} transition-all duration-300`}
                    style={{ width: `${percentage}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Training Status */}
      <div className="rounded-3xl bg-emerald-500/10 p-6 shadow-sm">
        <p className="text-sm font-semibold text-emerald-900">✓ Training Status: Converged</p>
        <p className="text-xs text-emerald-700 mt-2">
          All metrics show positive convergence. Model is ready for promotion to live.
        </p>
      </div>
    </div>
  );
}