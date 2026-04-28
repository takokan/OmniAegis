import React from 'react';
import GlassCard from '../../common/GlassCard';
import { ErrorBoundary } from '../../common/ErrorBoundary';

export type NodeStatus = 'idle' | 'syncing' | 'training' | 'offline';

export interface EdgeNode {
  id: string;
  label?: string;
  status: NodeStatus;
}

const StatusRing: React.FC<{ status: NodeStatus }> = ({ status }) => {
  const color = status === 'training' ? '#00E6A8' : status === 'syncing' ? '#60A5FA' : status === 'idle' ? '#94A3B8' : '#374151';
  const anim = status === 'training' ? 'animate-pulse' : status === 'syncing' ? 'animate-spin-slow' : '';
  return (
    <div className={`w-12 h-12 rounded-full flex items-center justify-center ${anim}`} style={{ border: `2px solid ${color}` }}>
      <div style={{ width: 24, height: 24, background: color, borderRadius: 12 }} />
    </div>
  );
};

const FLHealthMonitor: React.FC<{ nodes?: EdgeNode[] }> = ({ nodes = [] }) => {
  return (
    <ErrorBoundary>
      <GlassCard>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm text-text-primary">FL Health Monitor</h3>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {nodes.map(n => (
            <div key={n.id} className="flex items-center gap-3 p-2">
              <StatusRing status={n.status} />
              <div className="flex flex-col">
                <div className="text-sm text-text-primary">{n.label || n.id}</div>
                <div className="text-xs text-text-secondary">{n.status}</div>
              </div>
            </div>
          ))}
        </div>
      </GlassCard>
    </ErrorBoundary>
  );
};

export default React.memo(FLHealthMonitor);
