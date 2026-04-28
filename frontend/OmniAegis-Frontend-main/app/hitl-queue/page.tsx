'use client';

import DashboardShell from '@/components/DashboardShell';
import HITLQueueList from '@/components/HITL/HITLQueueList';
import ExplanationPackage from '@/components/HITL/ExplanationPackage';
import DecisionWorkflow from '@/components/HITL/DecisionWorkflow';
import { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

interface QueueItem {
  id: string;
  type: string;
  riskLevel: string;
  status: string;
  sourceURL: string;
  discoveredAt: string;
  confidenceScore: number;
  reasonCode: string;
  explanation: {
    saliencyMap: string;
    nodeLinks: string;
  };
  context: {
    previousActions: number;
    seller: string;
    region: string;
  };
}

export default function HITLQueuePage() {
  const { user } = useAuth();
  const router = useRouter();
  const [selectedItem, setSelectedItem] = useState<QueueItem | null>(null);
  const [decisionMade, setDecisionMade] = useState(false);

  useEffect(() => {
    if (user && user.role !== 'reviewer') {
      router.push('/');
    }
  }, [user, router]);

  if (!user || user.role !== 'reviewer') {
    return null;
  }

  return (
    <DashboardShell>
      <div className="space-y-8">
        <div className="space-y-3">
          <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Human-in-the-Loop</p>
          <h1 className="text-4xl font-bold tracking-tight text-text-primary">Operational Queue</h1>
          <p className="text-base leading-8 text-text-secondary">
            High-efficiency interface for final enforcement decisions. Review explanations, contextual data, and take action on pending cases.
          </p>
        </div>

        <div className="grid gap-8 lg:grid-cols-[0.6fr_1.4fr]">
          {/* Queue List */}
          <section className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
            <div className="mb-6">
              <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Queue</p>
              <h2 className="mt-2 text-2xl font-bold text-text-primary">Pending Decisions</h2>
            </div>
            <HITLQueueList
              onSelect={(item) => {
                setSelectedItem(item);
                setDecisionMade(false);
              }}
            />
          </section>

          {/* Details & Decision */}
          {selectedItem ? (
            <div className="space-y-6">
              {!decisionMade ? (
                <>
                  {/* Explanation Package */}
                  <section className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
                    <div className="mb-6">
                      <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Explainability</p>
                      <h2 className="mt-2 text-2xl font-bold text-text-primary">Explanation Package</h2>
                    </div>
                    <ExplanationPackage item={selectedItem} />
                  </section>

                  {/* Decision Workflow */}
                  <section className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
                    <div className="mb-6">
                      <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Decision</p>
                      <h2 className="mt-2 text-2xl font-bold text-text-primary">Take Action</h2>
                    </div>
                    <DecisionWorkflow
                      itemId={selectedItem.id}
                      onDecisionMade={() => setDecisionMade(true)}
                    />
                  </section>
                </>
              ) : (
                <div className="rounded-[2rem] bg-emerald-500/10 p-8 shadow-sm backdrop-blur-sm flex flex-col items-center justify-center min-h-96 text-center">
                  <div className="text-5xl mb-4">✓</div>
                  <h3 className="text-2xl font-bold text-emerald-900 mb-2">Decision Recorded</h3>
                  <p className="text-emerald-700 mb-6">Your action has been logged and will influence future model training.</p>
                  <button
                    onClick={() => setSelectedItem(null)}
                    className="rounded-2xl bg-emerald-600 hover:bg-emerald-700 text-text-primary font-semibold px-6 py-3 transition"
                  >
                    Next Item in Queue
                  </button>
                </div>
              )}
            </div>
          ) : (
            <section className="premium-card rounded-[2rem] p-8 flex items-center justify-center min-h-96 text-center">
              <div>
                <p className="text-text-secondary font-semibold">Select a case from the queue to begin review</p>
                <p className="text-sm text-text-tertiary mt-2">Each case includes visual explanations and contextual data</p>
              </div>
            </section>
          )}
        </div>
      </div>
    </DashboardShell>
  );
}