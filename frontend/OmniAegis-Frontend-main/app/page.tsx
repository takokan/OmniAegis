'use client';

import React, { useState } from 'react';
import { MainLayout } from '@/components/layout';
import OverviewRegistrationPrompt from '@/components/OverviewRegistrationPrompt';
import {
  ConfidenceBadge,
  StatusChip,
  Button,
  DataTable,
  Modal,
} from '@/components/ui';

function OverviewMetricIcon({ type }: { type: 'ingest' | 'decision' | 'queue' | 'privacy' }) {
  switch (type) {
    case 'ingest':
      return (
        <svg className="h-7 w-7 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M12 4v9" strokeLinecap="round" />
          <path d="m8.5 9.5 3.5 3.5 3.5-3.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M5 18.5h14" strokeLinecap="round" />
        </svg>
      );
    case 'decision':
      return (
        <svg className="h-7 w-7 text-success" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="m6 12.5 4 4 8-9" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case 'queue':
      return (
        <svg className="h-7 w-7 text-sky-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="8" cy="9" r="2.5" />
          <circle cx="16" cy="9" r="2.5" />
          <path d="M4.5 18c.7-2.2 2-3.5 3.5-3.5S10.8 15.8 11.5 18" strokeLinecap="round" />
          <path d="M12.5 18c.7-2.2 2-3.5 3.5-3.5s2.8 1.3 3.5 3.5" strokeLinecap="round" />
        </svg>
      );
    case 'privacy':
      return (
        <svg className="h-7 w-7 text-warning" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <rect x="5" y="11" width="14" height="9" rx="2" />
          <path d="M8 11V8a4 4 0 1 1 8 0v3" strokeLinecap="round" />
        </svg>
      );
  }
}

interface AuditRow {
  id: string;
  assetId: string;
  decision: 'approved' | 'rejected' | 'pending';
  confidence: number;
  policy: string;
  timestamp: string;
}

const DEMO_AUDITS: AuditRow[] = [
  {
    id: 'AUDIT-001',
    assetId: 'img_47f3a2',
    decision: 'approved',
    confidence: 0.87,
    policy: 'ContentV3',
    timestamp: '2024-04-28 09:42',
  },
  {
    id: 'AUDIT-002',
    assetId: 'img_56f4b3',
    decision: 'rejected',
    confidence: 0.15,
    policy: 'ContentV3',
    timestamp: '2024-04-28 08:20',
  },
  {
    id: 'AUDIT-003',
    assetId: 'img_65f5c4',
    decision: 'pending',
    confidence: 0.52,
    policy: 'PolicyV2',
    timestamp: '2024-04-28 07:15',
  },
];

export default function OverviewPage() {
  const [selectedAudit, setSelectedAudit] = useState<AuditRow | null>(null);
  const [showModal, setShowModal] = useState(false);

  return (
    <MainLayout
      breadcrumb={[{ label: 'Overview' }]}
      contextPanelTitle={selectedAudit ? `Audit ${selectedAudit.id}` : 'Details'}
      contextPanelContent={
        selectedAudit && (
          <div className="space-y-4">
            <div>
              <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold">
                Asset ID
              </p>
              <p className="text-sm text-text-primary font-mono">{selectedAudit.assetId}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold">
                Confidence
              </p>
              <div className="mt-1">
                <ConfidenceBadge value={selectedAudit.confidence} />
              </div>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold">
                Policy
              </p>
              <p className="text-sm text-text-primary">{selectedAudit.policy}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold">
                Status
              </p>
              <div className="mt-2">
                <StatusChip status={selectedAudit.decision} />
              </div>
            </div>
          </div>
        )
      }
      contextPanelActions={
        selectedAudit && (
          <>
            <Button variant="secondary" size="sm" onClick={() => setSelectedAudit(null)}>
              Close
            </Button>
            <Button size="sm" onClick={() => setShowModal(true)}>
              View Details
            </Button>
          </>
        )
      }
      isContextPanelOpen={!!selectedAudit}
      onContextPanelClose={() => setSelectedAudit(null)}
    >
      {/* Main Content */}
      <div className="space-y-8">
        {/* Hero Section */}
        <div className="space-y-2">
          <h1 className="text-4xl font-bold text-text-primary">Overview</h1>
          <p className="text-lg text-text-secondary">
            Monitor ML model audits, decisions, and explainability metrics
          </p>
        </div>

        <OverviewRegistrationPrompt />

        {/* KPI Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Ingested Today', value: '14,302', icon: 'ingest' as const },
            { label: 'Decisions Made', value: '9,847', icon: 'decision' as const },
            { label: 'HITL Queue', value: '12', icon: 'queue' as const },
            { label: 'Privacy Budget', value: 'ε: 0.73', icon: 'privacy' as const },
          ].map((metric) => (
            <div
              key={metric.label}
              className="p-6 rounded-xl bg-surface-secondary hover:bg-surface-tertiary transition-colors duration-fast shadow-[0_12px_28px_rgba(16,24,40,0.08)]"
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm text-text-secondary uppercase font-semibold letter-spacing-wide">
                    {metric.label}
                  </p>
                  <p className="text-3xl font-bold text-text-primary mt-2">{metric.value}</p>
                </div>
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-surface-elevated shadow-sm">
                  <OverviewMetricIcon type={metric.icon} />
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Audit Table */}
        <div className="space-y-4">
          <h2 className="text-xl font-semibold text-text-primary">Recent Audits</h2>
          <DataTable<AuditRow>
            columns={[
              {
                key: 'id',
                label: 'ID',
                sortable: true,
                width: '140px',
                render: (val) => (
                  <code className="text-xs font-mono text-accent">{val}</code>
                ),
              },
              {
                key: 'assetId',
                label: 'Asset ID',
                sortable: true,
                render: (val) => (
                  <code className="text-xs font-mono text-text-secondary">{val}</code>
                ),
              },
              {
                key: 'confidence',
                label: 'Confidence',
                sortable: true,
                render: (val) => <ConfidenceBadge value={val} size="sm" />,
              },
              {
                key: 'decision',
                label: 'Decision',
                sortable: true,
                render: (val) => <StatusChip status={val} size="sm" />,
              },
              {
                key: 'policy',
                label: 'Policy',
                sortable: true,
              },
              {
                key: 'timestamp',
                label: 'Timestamp',
                sortable: true,
                render: (val) => (
                  <span className="text-xs text-text-secondary">{val}</span>
                ),
              },
            ]}
            rows={DEMO_AUDITS}
            onRowClick={(row) => setSelectedAudit(row)}
          />
        </div>
      </div>

      {/* Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Audit Details"
        size="md"
        actions={
          <>
            <Button variant="secondary" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button onClick={() => setShowModal(false)}>Confirm</Button>
          </>
        }
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            This is a modal dialog showing the details of the selected audit record.
          </p>
          <div className="p-4 bg-surface-tertiary rounded-lg shadow-sm">
            <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
              Audit Information
            </p>
            <div className="space-y-2 text-sm">
              <div>
                <span className="text-text-secondary">ID:</span>{' '}
                <code className="text-accent font-mono">AUDIT-001</code>
              </div>
              <div>
                <span className="text-text-secondary">Status:</span>{' '}
                <span>✓ APPROVED</span>
              </div>
              <div>
                <span className="text-text-secondary">Confidence:</span> 87%
              </div>
            </div>
          </div>
        </div>
      </Modal>
    </MainLayout>
  );
}
