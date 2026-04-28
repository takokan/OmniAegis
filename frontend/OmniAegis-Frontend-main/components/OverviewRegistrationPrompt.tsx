'use client';

import { useEffect, useState } from 'react';

import ContentRegistrationModal from '@/components/ContentRegistrationModal';
import { Button } from '@/components/ui';
import { LAST_LOGIN_EVENT_KEY, useAuth } from '@/lib/auth-context';

const LAST_ASSET_KEY = 'sentinel-last-registered-asset-id';
const LAST_GRAPH_KEY = 'sentinel-last-registered-graph';
const ONBOARDING_SHOWN_PREFIX = 'sentinel-overview-onboarding-shown';

export default function OverviewRegistrationPrompt() {
  const { user, loading } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const isEligibleRole = user?.role === 'reviewer';

  useEffect(() => {
    if (loading || !user || !isEligibleRole) {
      return;
    }

    const loginEvent = localStorage.getItem(LAST_LOGIN_EVENT_KEY) || '';
    if (!loginEvent) {
      return;
    }

    const shownKey = `${ONBOARDING_SHOWN_PREFIX}:${user.id}:${loginEvent}`;
    if (sessionStorage.getItem(shownKey) === 'true') {
      return;
    }

    sessionStorage.setItem(shownKey, 'true');
    setIsOpen(true);
  }, [isEligibleRole, loading, user]);

  if (!user || !isEligibleRole) {
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
