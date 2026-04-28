'use client';

import DashboardShell from '@/components/DashboardShell';
import BlockchainAuditLedger from '@/components/Governance/BlockchainAuditLedger';
import PrivacyBudgetDashboard from '@/components/Governance/PrivacyBudgetDashboard';
import VersionRegistry from '@/components/Governance/VersionRegistry';

export default function GovernancePage() {
  return (
    <DashboardShell>
      <div className="space-y-8">
        <div className="space-y-3">
          <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Accountability</p>
          <h1 className="text-4xl font-bold tracking-tight text-text-primary">System Governance & Audit</h1>
          <p className="text-base leading-8 text-text-secondary">
            Track accountability, security, and model governance across your enforcement systems with complete audit trails and privacy guarantees.
          </p>
        </div>

        {/* Blockchain Audit Ledger */}
        <section className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
          <div className="mb-6">
            <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Audit Trail</p>
            <h2 className="mt-2 text-2xl font-bold text-text-primary">Blockchain Ledger</h2>
            <p className="text-sm text-text-secondary mt-2">Immutable record of all enforcement actions with cryptographic proofs</p>
          </div>
          <BlockchainAuditLedger />
        </section>

        {/* Privacy Budget Dashboard */}
        <section className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
          <div className="mb-6">
            <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Federated Learning</p>
            <h2 className="mt-2 text-2xl font-bold text-text-primary">Privacy Budget Tracking</h2>
            <p className="text-sm text-text-secondary mt-2">Monitor epsilon consumption across federated learning rounds</p>
          </div>
          <PrivacyBudgetDashboard />
        </section>

        {/* Version Registry */}
        <section className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
          <div className="mb-6">
            <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Model Management</p>
            <h2 className="mt-2 text-2xl font-bold text-text-primary">Version Registry</h2>
            <p className="text-sm text-text-secondary mt-2">View deployment history and manage model rollbacks</p>
          </div>
          <VersionRegistry />
        </section>
      </div>
    </DashboardShell>
  );
}