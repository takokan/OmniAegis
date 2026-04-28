'use client';

import React, { useState, useMemo } from 'react';
import { MainLayout } from '@/components/layout';
import {
  ConfidenceBadge,
  StatusChip,
  Button,
  DataTable,
  Input,
} from '@/components/ui';

interface AuditRecord {
  id: string;
  assetId: string;
  assetType: 'image' | 'video' | 'audio' | 'text';
  decision: 'approved' | 'rejected' | 'pending' | 'flagged' | 'anchored';
  confidence: number;
  policy: string;
  policyVersion: string;
  evidenceCount: number;
  annotatorId?: string;
  timestamp: string;
  riskScore: number;
}

const DEMO_AUDITS: AuditRecord[] = [
  {
    id: 'AUDIT-2024-0847',
    assetId: 'img_47f3a2b9',
    assetType: 'image',
    decision: 'approved',
    confidence: 0.92,
    policy: 'ContentV3',
    policyVersion: '3.2.1',
    evidenceCount: 3,
    annotatorId: 'user_001',
    timestamp: '2024-04-28 14:32:11',
    riskScore: 0.08,
  },
  {
    id: 'AUDIT-2024-0846',
    assetId: 'vid_56f4b3c1',
    assetType: 'video',
    decision: 'flagged',
    confidence: 0.34,
    policy: 'ContentV3',
    policyVersion: '3.2.1',
    evidenceCount: 7,
    timestamp: '2024-04-28 13:45:22',
    riskScore: 0.66,
  },
  {
    id: 'AUDIT-2024-0845',
    assetId: 'img_65f5c4d2',
    assetType: 'image',
    decision: 'pending',
    confidence: 0.51,
    policy: 'PolicyV2',
    policyVersion: '2.1.0',
    evidenceCount: 5,
    timestamp: '2024-04-28 12:18:05',
    riskScore: 0.49,
  },
  {
    id: 'AUDIT-2024-0844',
    assetId: 'aud_74g6d5e3',
    assetType: 'audio',
    decision: 'rejected',
    confidence: 0.18,
    policy: 'AudioV1',
    policyVersion: '1.0.0',
    evidenceCount: 2,
    annotatorId: 'user_003',
    timestamp: '2024-04-28 11:52:14',
    riskScore: 0.82,
  },
  {
    id: 'AUDIT-2024-0843',
    assetId: 'txt_83h7e6f4',
    assetType: 'text',
    decision: 'approved',
    confidence: 0.88,
    policy: 'NLPv2',
    policyVersion: '2.3.1',
    evidenceCount: 1,
    annotatorId: 'user_002',
    timestamp: '2024-04-28 10:25:33',
    riskScore: 0.12,
  },
  {
    id: 'AUDIT-2024-0842',
    assetId: 'img_92i8f7g5',
    assetType: 'image',
    decision: 'anchored',
    confidence: 0.73,
    policy: 'ContentV3',
    policyVersion: '3.2.1',
    evidenceCount: 4,
    timestamp: '2024-04-28 09:41:02',
    riskScore: 0.27,
  },
];

export default function AuditConsolePage() {
  const [selectedAudit, setSelectedAudit] = useState<AuditRecord | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterPolicy, setFilterPolicy] = useState<string | null>(null);
  const [filterDecision, setFilterDecision] = useState<string | null>(null);

  const filteredAudits = useMemo(() => {
    return DEMO_AUDITS.filter((audit) => {
      const matchesSearch =
        searchTerm === '' ||
        audit.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        audit.assetId.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesPolicy = !filterPolicy || audit.policy === filterPolicy;
      const matchesDecision = !filterDecision || audit.decision === filterDecision;

      return matchesSearch && matchesPolicy && matchesDecision;
    });
  }, [searchTerm, filterPolicy, filterDecision]);

  const policyOptions = [...new Set(DEMO_AUDITS.map((a) => a.policy))];
  const decisionOptions = [...new Set(DEMO_AUDITS.map((a) => a.decision))];

  return (
    <MainLayout
      breadcrumb={[
        { label: 'Audit Console' },
      ]}
      contextPanelTitle={selectedAudit ? `Audit ${selectedAudit.id}` : 'Audit Details'}
      contextPanelContent={
        selectedAudit && (
          <div className="space-y-6">
            {/* Core Audit Info */}
            <div className="space-y-3">
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Audit ID
                </p>
                <p className="text-sm font-mono text-accent">{selectedAudit.id}</p>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Asset
                </p>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-1 rounded text-xs font-semibold bg-surface-tertiary text-text-secondary">
                    {selectedAudit.assetType.toUpperCase()}
                  </span>
                  <code className="text-xs font-mono text-text-secondary">{selectedAudit.assetId}</code>
                </div>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                  Decision
                </p>
                <StatusChip status={selectedAudit.decision} />
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                  Confidence
                </p>
                <ConfidenceBadge value={selectedAudit.confidence} showTooltip />
              </div>
            </div>

            {/* Policy & Evidence */}
            <div className="border-t border-border-subtle pt-4 space-y-3">
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Policy
                </p>
                <p className="text-sm text-text-primary">{selectedAudit.policy}</p>
                <p className="text-xs text-text-tertiary mt-1">v{selectedAudit.policyVersion}</p>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Risk Score
                </p>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-2 bg-surface-tertiary rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        selectedAudit.riskScore >= 0.7
                          ? 'bg-danger'
                          : selectedAudit.riskScore >= 0.4
                            ? 'bg-warning'
                            : 'bg-success'
                      }`}
                      style={{ width: `${selectedAudit.riskScore * 100}%` }}
                    />
                  </div>
                  <span className="text-xs font-semibold text-text-secondary">
                    {(selectedAudit.riskScore * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Evidence
                </p>
                <p className="text-sm text-text-primary">{selectedAudit.evidenceCount} artifacts</p>
              </div>
            </div>

            {/* Metadata */}
            <div className="border-t border-border-subtle pt-4 space-y-3">
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Timestamp
                </p>
                <p className="text-xs text-text-secondary font-mono">{selectedAudit.timestamp}</p>
              </div>

              {selectedAudit.annotatorId && (
                <div>
                  <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                    Annotator
                  </p>
                  <p className="text-xs text-text-secondary">{selectedAudit.annotatorId}</p>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="border-t border-border-subtle pt-4 space-y-2">
              <Button size="sm" className="w-full">
                View Evidence
              </Button>
              <Button variant="secondary" size="sm" className="w-full">
                Export Record
              </Button>
            </div>
          </div>
        )
      }
      contextPanelActions={
        selectedAudit && (
          <Button variant="secondary" size="sm" onClick={() => setSelectedAudit(null)}>
            Close
          </Button>
        )
      }
      isContextPanelOpen={!!selectedAudit}
      onContextPanelClose={() => setSelectedAudit(null)}
    >
      {/* Main Content */}
      <div className="space-y-6">
        {/* Page Header */}
        <div className="space-y-2">
          <h1 className="text-4xl font-bold text-text-primary">Audit Console</h1>
          <p className="text-lg text-text-secondary">
            Review ML decision records, confidence scores, and policy compliance
          </p>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-4 rounded-lg bg-surface-secondary shadow-sm">
            <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
              Total Audits
            </p>
            <p className="text-3xl font-bold text-text-primary">{DEMO_AUDITS.length}</p>
            <p className="text-xs text-text-tertiary mt-2">24h period</p>
          </div>

          <div className="p-4 rounded-lg bg-surface-secondary shadow-sm">
            <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
              Approved
            </p>
            <p className="text-3xl font-bold text-success">
              {DEMO_AUDITS.filter((a) => a.decision === 'approved').length}
            </p>
            <p className="text-xs text-text-tertiary mt-2">High confidence</p>
          </div>

          <div className="p-4 rounded-lg bg-surface-secondary shadow-sm">
            <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
              Pending Review
            </p>
            <p className="text-3xl font-bold text-warning">
              {DEMO_AUDITS.filter((a) => a.decision === 'pending').length}
            </p>
            <p className="text-xs text-text-tertiary mt-2">Awaiting HITL</p>
          </div>

          <div className="p-4 rounded-lg bg-surface-secondary shadow-sm">
            <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
              Flagged
            </p>
            <p className="text-3xl font-bold text-danger">
              {DEMO_AUDITS.filter((a) => a.decision === 'flagged' || a.decision === 'rejected').length}
            </p>
            <p className="text-xs text-text-tertiary mt-2">Risk detected</p>
          </div>
        </div>

        {/* Filters */}
        <div className="p-4 bg-surface-secondary rounded-lg space-y-4 shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Input
              label="Search Audits"
              placeholder="Asset ID, Audit ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />

            <div>
              <label className="block text-xs font-semibold text-text-secondary uppercase letter-spacing-wide mb-2">
                Policy
              </label>
              <select
                value={filterPolicy || ''}
                onChange={(e) => setFilterPolicy(e.target.value || null)}
                className="w-full px-3 py-2 rounded-md border border-border-default bg-surface-primary text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent"
              >
                <option value="">All Policies</option>
                {policyOptions.map((policy) => (
                  <option key={policy} value={policy}>
                    {policy}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-secondary uppercase letter-spacing-wide mb-2">
                Decision
              </label>
              <select
                value={filterDecision || ''}
                onChange={(e) => setFilterDecision(e.target.value || null)}
                className="w-full px-3 py-2 rounded-md border border-border-default bg-surface-primary text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent"
              >
                <option value="">All Decisions</option>
                {decisionOptions.map((decision) => (
                  <option key={decision} value={decision}>
                    {decision.charAt(0).toUpperCase() + decision.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <p className="text-xs text-text-tertiary">
            {filteredAudits.length} of {DEMO_AUDITS.length} audits
          </p>
        </div>

        {/* Audit Table */}
        <DataTable<AuditRecord>
          columns={[
            {
              key: 'id',
              label: 'Audit ID',
              sortable: true,
              width: '160px',
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
              key: 'assetType',
              label: 'Type',
              sortable: true,
              width: '80px',
              render: (val) => (
                <span className="px-2 py-1 rounded text-xs font-semibold bg-surface-tertiary text-text-secondary">
                  {val.toUpperCase()}
                </span>
              ),
            },
            {
              key: 'confidence',
              label: 'Confidence',
              sortable: true,
              width: '140px',
              render: (val) => <ConfidenceBadge value={val} size="sm" />,
            },
            {
              key: 'decision',
              label: 'Decision',
              sortable: true,
              render: (val) => <StatusChip status={val as any} size="sm" />,
            },
            {
              key: 'policy',
              label: 'Policy',
              sortable: true,
              width: '100px',
              render: (val) => <span className="text-xs">{val}</span>,
            },
            {
              key: 'riskScore',
              label: 'Risk',
              sortable: true,
              width: '80px',
              render: (val) => (
                <span
                  className={`text-xs font-semibold ${
                    val >= 0.7 ? 'text-danger' : val >= 0.4 ? 'text-warning' : 'text-success'
                  }`}
                >
                  {(val * 100).toFixed(0)}%
                </span>
              ),
            },
            {
              key: 'timestamp',
              label: 'Timestamp',
              sortable: true,
              width: '180px',
              render: (val) => <span className="text-xs text-text-tertiary">{val}</span>,
            },
          ]}
          rows={filteredAudits}
          onRowClick={(row) => setSelectedAudit(row)}
        />
      </div>
    </MainLayout>
  );
}
