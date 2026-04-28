'use client';

import React, { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { MainLayout } from '@/components/layout';
import { Button } from '@/components/ui';

interface ModelVersion {
  id: string;
  version: string;
  releaseDate: string;
  accuracy: number;
  driftScore: number;
  status: 'active' | 'deprecated' | 'staging';
  inferencesPerDay: number;
  avgLatency: number;
}

const MODELS: ModelVersion[] = [
  {
    id: 'model_v3.2.1',
    version: '3.2.1',
    releaseDate: '2024-04-15',
    accuracy: 0.945,
    driftScore: 0.08,
    status: 'active',
    inferencesPerDay: 142000,
    avgLatency: 234,
  },
  {
    id: 'model_v3.2.0',
    version: '3.2.0',
    releaseDate: '2024-03-20',
    accuracy: 0.938,
    driftScore: 0.14,
    status: 'deprecated',
    inferencesPerDay: 8000,
    avgLatency: 241,
  },
  {
    id: 'model_v3.3.0-rc1',
    version: '3.3.0-rc1',
    releaseDate: '2024-04-25',
    accuracy: 0.952,
    driftScore: 0.05,
    status: 'staging',
    inferencesPerDay: 2100,
    avgLatency: 218,
  },
];

interface DriftTimeline {
  date: string;
  driftScore: number;
  dataPoints: number;
}

const DRIFT_TIMELINE: DriftTimeline[] = [
  { date: '2024-04-14', driftScore: 0.05, dataPoints: 18000 },
  { date: '2024-04-15', driftScore: 0.06, dataPoints: 22000 },
  { date: '2024-04-16', driftScore: 0.07, dataPoints: 19500 },
  { date: '2024-04-17', driftScore: 0.08, dataPoints: 21000 },
  { date: '2024-04-18', driftScore: 0.07, dataPoints: 20500 },
  { date: '2024-04-19', driftScore: 0.06, dataPoints: 23000 },
  { date: '2024-04-20', driftScore: 0.08, dataPoints: 19800 },
  { date: '2024-04-21', driftScore: 0.09, dataPoints: 21200 },
  { date: '2024-04-22', driftScore: 0.10, dataPoints: 22500 },
  { date: '2024-04-23', driftScore: 0.09, dataPoints: 20800 },
  { date: '2024-04-24', driftScore: 0.08, dataPoints: 23100 },
  { date: '2024-04-25', driftScore: 0.07, dataPoints: 18900 },
  { date: '2024-04-26', driftScore: 0.06, dataPoints: 21500 },
  { date: '2024-04-27', driftScore: 0.08, dataPoints: 20200 },
  { date: '2024-04-28', driftScore: 0.08, dataPoints: 22800 },
];

const getStatusColor = (status: string) => {
  switch (status) {
    case 'active':
      return 'bg-success bg-opacity-10 text-success border-success border-opacity-30';
    case 'staging':
      return 'bg-warning bg-opacity-10 text-warning border-warning border-opacity-30';
    case 'deprecated':
      return 'bg-border-subtle text-text-secondary border-border-default';
    default:
      return 'bg-border-subtle text-text-secondary border-border-default';
  }
};

export default function ModelMonitorPage() {
  const [selectedModel, setSelectedModel] = useState<ModelVersion>(MODELS[0]);
  const [timeRange, setTimeRange] = useState<'7d' | '30d' | '90d'>('30d');
  const [isContextPanelOpen, setIsContextPanelOpen] = useState(false);
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-accent border-r-transparent" />
      </div>
    );
  }

  if (user && user.role !== 'admin') {
    return (
      <div className="min-h-screen flex items-center justify-center p-8">
        <div className="max-w-lg w-full text-center p-8 rounded-lg bg-surface-secondary shadow-md">
          <h2 className="text-xl font-semibold text-text-primary">Not authorized</h2>
          <p className="text-sm text-text-secondary mt-2">You do not have permission to view the Model Monitor. Contact an administrator if you believe this is an error.</p>
          <div className="mt-4">
            <a href="/" className="inline-block px-4 py-2 rounded-md bg-accent text-text-primary">Return to Overview</a>
          </div>
        </div>
      </div>
    );
  }

  const getFilteredDriftTimeline = () => {
    const daysMap = { '7d': 7, '30d': 30, '90d': 90 };
    const days = daysMap[timeRange];
    return DRIFT_TIMELINE.slice(-days);
  };

  const filteredDrift = getFilteredDriftTimeline();
  const maxDrift = Math.max(...filteredDrift.map((d) => d.driftScore));
  const avgDrift = (
    filteredDrift.reduce((sum, d) => sum + d.driftScore, 0) / filteredDrift.length
  ).toFixed(3);

  return (
    <MainLayout
      breadcrumb={[{ label: 'Model Monitor' }]}
      contextPanelTitle={selectedModel ? `Model ${selectedModel.version}` : 'Model Details'}
      contextPanelContent={
        selectedModel && (
          <div className="space-y-6">
            {/* Model Identity */}
            <div className="space-y-3">
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Model ID
                </p>
                <p className="text-sm font-mono text-accent">{selectedModel.id}</p>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Version
                </p>
                <p className="text-sm text-text-primary font-semibold">{selectedModel.version}</p>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                  Status
                </p>
                <span className={`px-3 py-1 rounded text-xs font-semibold border ${getStatusColor(selectedModel.status)}`}>
                  {selectedModel.status.toUpperCase()}
                </span>
              </div>
            </div>

            {/* Performance Metrics */}
            <div className="border-t border-border-subtle pt-4 space-y-4">
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                  Accuracy
                </p>
                <div className="space-y-2">
                  <p className="text-2xl font-bold text-success">
                    {(selectedModel.accuracy * 100).toFixed(1)}%
                  </p>
                  <div className="w-full h-3 bg-surface-tertiary rounded-full overflow-hidden">
                    <div
                      className="h-full bg-success"
                      style={{ width: `${selectedModel.accuracy * 100}%` }}
                    />
                  </div>
                </div>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                  Drift Score
                </p>
                <div className="space-y-2">
                  <p
                    className={`text-2xl font-bold ${
                      selectedModel.driftScore >= 0.15
                        ? 'text-danger'
                        : selectedModel.driftScore >= 0.08
                          ? 'text-warning'
                          : 'text-success'
                    }`}
                  >
                    {selectedModel.driftScore.toFixed(3)}
                  </p>
                  <div className="w-full h-3 bg-surface-tertiary rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        selectedModel.driftScore >= 0.15
                          ? 'bg-danger'
                          : selectedModel.driftScore >= 0.08
                            ? 'bg-warning'
                            : 'bg-success'
                      }`}
                      style={{
                        width: `${Math.min(selectedModel.driftScore * 100, 100)}%`,
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Operational Metrics */}
            <div className="border-t border-border-subtle pt-4 space-y-3">
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Daily Inferences
                </p>
                <p className="text-lg font-bold text-text-primary">
                  {(selectedModel.inferencesPerDay / 1000).toFixed(0)}K
                </p>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Avg Latency
                </p>
                <p className="text-lg font-bold text-text-primary">
                  {selectedModel.avgLatency}ms
                </p>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Release Date
                </p>
                <p className="text-sm text-text-secondary">{selectedModel.releaseDate}</p>
              </div>
            </div>

            <div className="border-t border-border-subtle pt-4">
              <p className="text-xs text-text-tertiary">
                Version operations are disabled until the monitor page is connected to a deployment control API.
              </p>
            </div>
          </div>
        )
      }
      contextPanelActions={
        <Button variant="secondary" size="sm" onClick={() => setIsContextPanelOpen(false)}>
          Close
        </Button>
      }
      isContextPanelOpen={isContextPanelOpen}
      onContextPanelClose={() => setIsContextPanelOpen(false)}
    >
      {/* Main Content */}
      <div className="space-y-6">
        {/* Page Header */}
        <div className="space-y-2">
          <h1 className="text-4xl font-bold text-text-primary">Model Monitor</h1>
          <p className="text-lg text-text-secondary">
            Track model performance, drift detection, and production health
          </p>
        </div>

        {/* Active Model Summary */}
        <div className="p-6 rounded-lg bg-surface-secondary shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                Current Model
              </p>
              <p className="text-2xl font-bold text-text-primary">v{MODELS[0].version}</p>
            </div>

            <div>
              <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                Accuracy
              </p>
              <p className="text-2xl font-bold text-success">
                {(MODELS[0].accuracy * 100).toFixed(1)}%
              </p>
            </div>

            <div>
              <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                Drift Score
              </p>
              <p className="text-2xl font-bold text-warning">{MODELS[0].driftScore.toFixed(2)}</p>
            </div>

            <div>
              <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                Daily Load
              </p>
              <p className="text-2xl font-bold text-accent">
                {(MODELS[0].inferencesPerDay / 1000).toFixed(0)}K
              </p>
            </div>
          </div>
        </div>

        {/* Drift Timeline */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-text-primary">Drift Timeline</h2>
            <div className="flex gap-2">
              {(['7d', '30d', '90d'] as const).map((range) => (
                <Button
                  key={range}
                  variant={timeRange === range ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() => setTimeRange(range)}
                >
                  {range}
                </Button>
              ))}
            </div>
          </div>

          <div className="p-6 rounded-lg bg-surface-secondary shadow-sm">
            {/* Simple Bar Chart */}
            <div className="space-y-3">
              {filteredDrift.map((point) => (
                <div key={point.date} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-text-secondary">{point.date}</span>
                    <span
                      className={`font-semibold ${
                        point.driftScore >= 0.15
                          ? 'text-danger'
                          : point.driftScore >= 0.08
                            ? 'text-warning'
                            : 'text-success'
                      }`}
                    >
                      {point.driftScore.toFixed(3)}
                    </span>
                  </div>
                  <div className="w-full h-2 bg-surface-tertiary rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        point.driftScore >= 0.15
                          ? 'bg-danger'
                          : point.driftScore >= 0.08
                            ? 'bg-warning'
                            : 'bg-success'
                      }`}
                      style={{
                        width: `${Math.min((point.driftScore / maxDrift) * 100, 100)}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>

            {/* Stats */}
            <div className="mt-6 pt-6 border-t border-border-subtle grid grid-cols-3 gap-4">
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Avg Drift
                </p>
                <p className="text-lg font-bold text-text-primary">{avgDrift}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Max Drift
                </p>
                <p className="text-lg font-bold text-warning">{maxDrift.toFixed(3)}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Data Points
                </p>
                <p className="text-lg font-bold text-text-primary">
                  {(filteredDrift.reduce((sum, d) => sum + d.dataPoints, 0) / 1000).toFixed(0)}K
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Model Versions */}
        <div className="space-y-4">
          <h2 className="text-xl font-semibold text-text-primary">Model Versions</h2>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {MODELS.map((model) => (
              <div
                key={model.id}
                onClick={() => {
                  setSelectedModel(model);
                  setIsContextPanelOpen(true);
                }}
                className={`p-4 rounded-lg border cursor-pointer transition-colors duration-fast ${
                  selectedModel.id === model.id
                    ? 'bg-surface-elevated border-accent shadow-glow'
                    : 'bg-surface-secondary border-border-default hover:bg-surface-tertiary'
                }`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold">
                      Version
                    </p>
                    <p className="text-lg font-bold text-text-primary mt-1">v{model.version}</p>
                  </div>
                  <span
                    className={`px-3 py-1 rounded text-xs font-semibold border ${getStatusColor(model.status)}`}
                  >
                    {model.status.toUpperCase()}
                  </span>
                </div>

                <div className="space-y-3 border-t border-border-subtle pt-3">
                  <div>
                    <p className="text-xs text-text-secondary mb-1">Accuracy</p>
                    <p className="text-sm font-semibold text-success">
                      {(model.accuracy * 100).toFixed(1)}%
                    </p>
                  </div>

                  <div>
                    <p className="text-xs text-text-secondary mb-1">Drift Score</p>
                    <p
                      className={`text-sm font-semibold ${
                        model.driftScore >= 0.15
                          ? 'text-danger'
                          : model.driftScore >= 0.08
                            ? 'text-warning'
                            : 'text-success'
                      }`}
                    >
                      {model.driftScore.toFixed(3)}
                    </p>
                  </div>

                  <div className="text-xs text-text-tertiary">
                    Released {model.releaseDate}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </MainLayout>
  );
}
