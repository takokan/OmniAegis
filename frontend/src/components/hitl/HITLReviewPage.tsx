import { useEffect } from 'react';
import { useHITLReview } from '@/context/HITLReviewContext';
import { useHITLWebSocket } from '@/hooks/useHITLWebSocket';
import { apiClient } from '@/services/api';
import { AssetViewer } from './AssetViewer';
import { ContextGrid } from './ContextGrid';
import { DecisionPanel } from './DecisionPanel';
import { LockTimer } from './LockTimer';
import { GlassCard } from '@/components/common/GlassCard';

interface HITLReviewPageProps {
  itemId?: string;
  onDecisionSubmit?: (decision: unknown) => void | Promise<void>;
}

export function HITLReviewPage({ itemId, onDecisionSubmit }: HITLReviewPageProps) {
  const { state, setCurrentItem, setLockExpiry, setQueueDepth, setError, clearItem } = useHITLReview();

  const { isConnected } = useHITLWebSocket({
    onQueueDepthChange: (depth: number) => setQueueDepth(depth),
    onItemCompleted: (completedItemId: string) => {
      if (state.currentItem?.item_id === completedItemId) {
        clearItem();
      }
    },
    onAssignmentReady: (assignment: Record<string, unknown>) => {
      if (assignment.item_id && !state.currentItem) {
        setCurrentItem({
          item_id: String(assignment.item_id),
          asset_id: String(assignment.asset_id),
          priority_score: Number(assignment.priority_score),
          assigned_to: String(assignment.assigned_to),
          lock_ttl_seconds: Number(assignment.lock_ttl_seconds),
        });

        const expiresAt = Date.now() + Number(assignment.lock_ttl_seconds) * 1000;
        setLockExpiry(expiresAt);
      }
    },
  });

  useEffect(() => {
    if (!itemId || state.currentItem?.item_id === itemId) {
      return;
    }

    const fetchItem = async () => {
      try {
        const item = await apiClient.getHITLItem(itemId);
        setCurrentItem(item as any);
        const expiresAt = Date.now() + (item as any).lock_ttl_seconds * 1000;
        setLockExpiry(expiresAt);
      } catch (error) {
        setError(error instanceof Error ? error.message : 'Failed to load item');
      }
    };

    fetchItem();
  }, [itemId, state.currentItem, setCurrentItem, setLockExpiry, setError]);

  if (!state.currentItem) {
    return (
      <div className="w-full h-full flex items-center justify-center">
        <GlassCard className="p-8 text-center max-w-sm">
          <h2 className="text-lg font-semibold text-slate-300 mb-2">No Item to Review</h2>
          <p className="text-sm text-slate-400 mb-4">
            {isConnected
              ? 'Waiting for the next item to be assigned...'
              : 'Connecting to queue system...'}
          </p>
          <div className="flex items-center justify-center gap-2">
            <div
              className={`w-2 h-2 rounded-full transition-colors ${
                isConnected ? 'bg-emerald-400' : 'bg-slate-500'
              }`}
            />
            <span className="text-xs text-slate-400">
              {isConnected ? 'Connected' : 'Connecting'}
            </span>
          </div>
        </GlassCard>
      </div>
    );
  }

  return (
    <div className="w-full h-full flex flex-col gap-4 p-4 bg-gradient-to-br from-slate-950 to-slate-900">
      {state.error && (
        <div className="px-4 py-3 rounded-lg bg-rose-400/10 border border-rose-400/30 text-rose-300 text-sm">
          {state.error}
        </div>
      )}

      <LockTimer lockExpiresAt={state.lockExpiresAt} />

      <div className="grid grid-cols-[1fr_1fr_1fr] gap-4 flex-1 min-h-0">
        {/* Left: Primary Evidence (50%) */}
        <div className="col-span-2 flex flex-col h-full">
          <AssetViewer
            assetUrl={state.currentItem.metadata?.asset_url as string | undefined}
            assetType={state.currentItem.content_type}
            saliencyMapUrl={state.currentItem.metadata?.saliency_map_url as string | undefined}
          />
        </div>

        {/* Right Column: 50% split vertically */}
        <div className="flex flex-col gap-4 h-full">
          {/* Top Right: Context (25%) */}
          <ContextGrid
            assetId={state.currentItem.asset_id}
            confidence={state.currentItem.confidence}
            contentType={state.currentItem.content_type}
            priorityScore={state.currentItem.priority_score}
            rightsNodeIds={state.currentItem.rights_node_ids}
            metadata={state.currentItem.metadata}
          />

          {/* Bottom Right: Decision Panel (25%) */}
          <DecisionPanel onSubmit={onDecisionSubmit} isLoading={state.isLoading} />
        </div>
      </div>

      {/* Queue Status Footer */}
      <div className="flex justify-between items-center px-4 py-2 rounded-lg bg-slate-800/30 border border-white/10 text-xs text-slate-400">
        <span>Queue Depth: {state.queueDepth}</span>
        <span>
          Lock Remaining: {state.assignmentLockSecondsRemaining}s
        </span>
      </div>
    </div>
  );
}
