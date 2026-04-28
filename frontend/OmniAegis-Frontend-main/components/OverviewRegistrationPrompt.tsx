'use client';

import { useEffect, useState } from 'react';

import ContentRegistrationModal from '@/components/ContentRegistrationModal';
import { Button } from '@/components/ui';
import { useAuth } from '@/lib/auth-context';

const SESSION_KEY_PREFIX = 'sentinel-overview-onboarding-shown';
const LAST_ASSET_KEY = 'sentinel-last-registered-asset-id';
const LAST_GRAPH_KEY = 'sentinel-last-registered-graph';

export default function OverviewRegistrationPrompt() {
  const { user, loading } = useAuth();
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (loading || !user) {
      return;
    }

    const sessionKey = `${SESSION_KEY_PREFIX}:${user.id}`;
    if (sessionStorage.getItem(sessionKey) === 'true') {
      return;
    }

    sessionStorage.setItem(sessionKey, 'true');
    setIsOpen(true);
  }, [loading, user]);

  if (!user) {
    return null;
  }

  return (
    <>
      <div className="rounded-xl bg-surface-secondary p-4 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Protected content onboarding</p>
            <p className="mt-2 text-sm text-text-primary">
              Upload a licensed image, video, or audio asset to register it in Qdrant and build its Neo4j relationship graph.
            </p>
          </div>
          <Button onClick={() => setIsOpen(true)}>Register Content</Button>
        </div>
      </div>

      <ContentRegistrationModal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        userId={user.id}
        userName={user.name}
        onSuccess={(payload) => {
          const assetId = typeof payload?.asset_id === 'string' ? payload.asset_id : '';
          if (assetId) {
            localStorage.setItem(LAST_ASSET_KEY, assetId);
          }
          if (payload?.graph) {
            localStorage.setItem(LAST_GRAPH_KEY, JSON.stringify(payload.graph));
          }
        }}
      />
    </>
  );
}
