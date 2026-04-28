'use client';

import DashboardShell from '@/components/DashboardShell';
import PolicyComparisonTool from '@/components/RLOptimizer/PolicyComparisonTool';
import TrainingLoopMonitor from '@/components/RLOptimizer/TrainingLoopMonitor';
import ConstraintOverrideLog from '@/components/RLOptimizer/ConstraintOverrideLog';
import PromoteToLiveModal from '@/components/RLOptimizer/PromoteToLiveModal';
import { useState } from 'react';

export default function RLOptimizerPage() {
  const [isPromoteModalOpen, setIsPromoteModalOpen] = useState(false);

  return (
    <DashboardShell>
      <div className="space-y-8">
        <div className="space-y-3">
          <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Phase 4 Control</p>
          <h1 className="text-4xl font-bold tracking-tight text-text-primary">RL Policy Optimizer</h1>
          <p className="text-base leading-8 text-text-secondary">
            Transparent view into the RL black box. Monitor policy training, compare shadow vs. live policies, and manage constraint overrides with safety-first atomic promotions.
          </p>
        </div>

        {/* Policy Comparison Tool */}
        <section className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
          <div className="mb-6">
            <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Policy Management</p>
            <h2 className="mt-2 text-2xl font-bold text-text-primary">Policy Comparison</h2>
          </div>
          <PolicyComparisonTool />
        </section>

        {/* Training Loop Monitor */}
        <section className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
          <div className="mb-6">
            <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Training Loop</p>
            <h2 className="mt-2 text-2xl font-bold text-text-primary">KL Divergence & Reward Mean</h2>
          </div>
          <TrainingLoopMonitor />
        </section>

        {/* Constraint Override Log */}
        <section className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
          <div className="mb-6">
            <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Safety Guardrails</p>
            <h2 className="mt-2 text-2xl font-bold text-text-primary">Constraint Override Log</h2>
            <p className="text-sm text-text-secondary mt-2">
              Feed of safety constraints intercepting RL decisions to prevent harmful policies
            </p>
          </div>
          <ConstraintOverrideLog />
        </section>

        {/* Promote to Live */}
        <div className="flex gap-4">
          <button
            onClick={() => setIsPromoteModalOpen(true)}
            className="flex-1 rounded-2xl bg-accent hover:bg-accent/90 text-text-primary font-semibold py-4 transition shadow-lg shadow-accent/20"
          >
            Promote to Live
          </button>
          <button className="flex-1 rounded-2xl border border-border-default bg-surface-primary hover:bg-surface-elevated text-text-primary font-semibold py-4 transition">
            View History
          </button>
        </div>
      </div>

      <PromoteToLiveModal
        isOpen={isPromoteModalOpen}
        onClose={() => setIsPromoteModalOpen(false)}
        shadowVersion="v3.1.0-shadow"
        liveVersion="v3.0.8-live"
      />
    </DashboardShell>
  );
}