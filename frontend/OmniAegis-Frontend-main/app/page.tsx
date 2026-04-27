'use client';

import DashboardShell from '@/components/DashboardShell';
import OverviewMetrics from '@/components/OverviewMetrics';
import OverviewCards from '@/components/OverviewCards';
import LiveActivityFeed from '@/components/LiveActivityFeed';
import ThreatQueue from '@/components/ThreatQueue';
import HITLApprovalSummary from '@/components/HITLApprovalSummary';
import { useAuth } from '@/lib/auth-context';

export default function ExecutiveCommandCenter() {
  const { user } = useAuth();

  return (
    <DashboardShell>
      <div className="grid gap-8 xl:grid-cols-[1.3fr_0.7fr]">
        <section className="space-y-8">
          <OverviewMetrics />
          <OverviewCards />
          <LiveActivityFeed />
        </section>
        <section className="space-y-8">
          <ThreatQueue />
          {/* Admin-only: Approved HITL Decisions */}
          {user?.role === 'admin' && (
            <div className="rounded-[2rem] border border-slate-200/70 bg-white/90 p-8 shadow-sm backdrop-blur-sm">
              <div className="mb-6">
                <p className="text-sm uppercase tracking-[0.28em] text-slate-400">HITL Approvals</p>
                <h2 className="mt-2 text-2xl font-bold text-slate-950">Recent Decisions</h2>
                <p className="text-sm text-slate-600 mt-2">Approved piracy threat authentications from reviewers</p>
              </div>
              <HITLApprovalSummary />
            </div>
          )}
        </section>
      </div>
    </DashboardShell>
  );
}