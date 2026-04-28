import React, { useMemo } from 'react';
import GlassCard from '../../common/GlassCard';
import Skeleton from '../../common/Skeleton';
import { ErrorBoundary } from '../../common/ErrorBoundary';
import useHITLWebSocket, { HITLMessage } from '../../../hooks/useHITLWebSocket';

interface HITLDecisionQueueProps {
  maxItems?: number;
}

const Row: React.FC<{ item: HITLMessage; onClick?: (id: string) => void }> = React.memo(({ item, onClick }) => {
  return (
    <div
      role="listitem"
      tabIndex={0}
      onClick={() => onClick && onClick(item.id)}
      className="flex items-center justify-between p-2 hover:bg-surface-elevated rounded"
    >
      <div className="flex items-center gap-3">
        <div className="w-3 h-3 rounded-full bg-emerald-400" />
        <div className="text-sm text-text-primary">{item.id}</div>
      </div>
      <div className="text-xs text-text-secondary">{new Date(item.timestamp).toLocaleTimeString()}</div>
    </div>
  );
});

Row.displayName = 'HITLDecisionQueueRow';

const HITLDecisionQueue: React.FC<HITLDecisionQueueProps> = ({ maxItems = 200 }) => {
  const { messages, connected } = useHITLWebSocket();

  const items = useMemo(() => messages.slice(0, maxItems), [messages, maxItems]);

  if (!connected && items.length === 0) return <Skeleton className="w-full h-64" />;

  return (
    <ErrorBoundary>
      <GlassCard>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm text-text-primary">HITL Decision Queue</h3>
          <div className="text-xs text-text-secondary">{connected ? 'Live' : 'Disconnected'}</div>
        </div>
        <div role="list" className="max-h-64 overflow-auto space-y-1">
          {items.map(it => (
            <Row key={it.id} item={it} />
          ))}
        </div>
      </GlassCard>
    </ErrorBoundary>
  );
};

export default HITLDecisionQueue;
