import React, { useMemo } from 'react';
import GlassCard from '../../common/GlassCard';
import Skeleton from '../../common/Skeleton';
import { ErrorBoundary } from '../../common/ErrorBoundary';

export type UMAPPoint = { id: string; x: number; y: number; label?: string; score?: number };

export interface SaliencyDriftViewerProps {
  points?: UMAPPoint[];
  loading?: boolean;
  onSelect?: (id: string) => void;
}

const CanvasScatter: React.FC<{ points: UMAPPoint[]; onSelect?: (id: string) => void }> = ({ points, onSelect }) => {
  const minX = Math.min(...points.map(p => p.x), 0);
  const minY = Math.min(...points.map(p => p.y), 0);
  const maxX = Math.max(...points.map(p => p.x), 1);
  const maxY = Math.max(...points.map(p => p.y), 1);

  const view = useMemo(() => ({ minX, minY, maxX, maxY }), [minX, minY, maxX, maxY]);

  return (
    <svg className="w-full h-64" viewBox="0 0 1000 600" preserveAspectRatio="xMidYMid meet" role="img">
      <rect width="100%" height="100%" fill="transparent" />
      {points.map(p => {
        const cx = ((p.x - view.minX) / (view.maxX - view.minX)) * 980 + 10;
        const cy = ((p.y - view.minY) / (view.maxY - view.minY)) * 580 + 10;
        const r = 4 + (p.score ?? 0) * 6;
        return (
          <circle
            key={p.id}
            cx={cx}
            cy={cy}
            r={r}
            fill={p.score && p.score > 0.7 ? '#FF6B6B' : '#00E6A8'}
            opacity={0.9}
            onClick={() => onSelect && onSelect(p.id)}
            aria-label={`point-${p.id}`}
          />
        );
      })}
    </svg>
  );
};

const TextHeatmap: React.FC<{ text?: string }> = ({ text }) => {
  if (!text) return null;
  return (
    <div className="absolute inset-0 pointer-events-none flex items-end">
      <div className="w-full text-xs text-text-primary p-3 bg-gradient-to-t from-surface-primary/70 via-transparent to-transparent opacity-80">
        <pre className="whitespace-pre-wrap break-words">{text}</pre>
      </div>
    </div>
  );
};

const SaliencyDriftViewer: React.FC<SaliencyDriftViewerProps> = ({ points = [], loading, onSelect }) => {
  if (loading) return <Skeleton className="w-full h-64" />;

  return (
    <ErrorBoundary>
      <GlassCard className="relative">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm text-text-primary">Saliency / Drift Viewer</h3>
        </div>
        <div className="relative">
          <CanvasScatter points={points} onSelect={onSelect} />
          <TextHeatmap text={points.slice(0, 1)[0]?.label} />
        </div>
      </GlassCard>
    </ErrorBoundary>
  );
};

export default React.memo(SaliencyDriftViewer);
