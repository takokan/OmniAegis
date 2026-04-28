'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { MainLayout } from '@/components/layout';
import { Button, Input } from '@/components/ui';

type BlockchainLog = {
  id: string;
  action: string;
  actor: string;
  timestamp: string;
  txHash: string;
  blockNumber: number;
  details: string;
};

type GovernanceAuditResponse = {
  entries?: Array<{
    id?: string;
    action?: string;
    timestamp?: string;
    admin?: string;
    reasoningHash?: string;
    details?: string;
  }>;
};

function randomHash(seed: string) {
  const safeSeed = seed.replace(/[^a-zA-Z0-9]/g, '').slice(0, 32).toLowerCase();
  return `0x${safeSeed.padEnd(64, '0').slice(0, 64)}`;
}

export default function BlockchainLogsPage() {
  const [logs, setLogs] = useState<BlockchainLog[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [newAction, setNewAction] = useState('');
  const [newActor, setNewActor] = useState('');
  const [newDetails, setNewDetails] = useState('');
  const [syncError, setSyncError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function syncFromAudit() {
      try {
        const res = await fetch('/api/governance/audit', { cache: 'no-store' });
        const data = (await res.json()) as GovernanceAuditResponse;
        const mapped: BlockchainLog[] = (data.entries || []).map((entry, idx) => ({
          id: (entry.id || `log-${idx + 1}`).toString(),
          action: (entry.action || 'Unknown action').toString(),
          actor: (entry.admin || 'system').toString(),
          timestamp: (entry.timestamp || new Date().toISOString()).toString(),
          txHash: randomHash(entry.reasoningHash || `tx-${idx + 1}`),
          blockNumber: 91000 + idx,
          details: (entry.details || 'No details provided.').toString(),
        }));
        if (!cancelled) {
          setLogs(mapped);
          setSyncError(null);
        }
      } catch {
        if (!cancelled) setSyncError('Live governance stream unavailable');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    syncFromAudit();
    const interval = window.setInterval(syncFromAudit, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const filteredLogs = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return logs;
    return logs.filter(
      (log) =>
        log.id.toLowerCase().includes(term) ||
        log.action.toLowerCase().includes(term) ||
        log.actor.toLowerCase().includes(term) ||
        log.txHash.toLowerCase().includes(term),
    );
  }, [logs, searchTerm]);

  const handleAddLog = async () => {
    if (!newAction.trim() || !newActor.trim()) return;
    const now = new Date().toISOString();
    const record: BlockchainLog = {
      id: `BLK-${Date.now()}`,
      action: newAction.trim(),
      actor: newActor.trim(),
      timestamp: now,
      txHash: randomHash(`${newAction}-${newActor}-${now}`),
      blockNumber: (logs[0]?.blockNumber || 91000) + 1,
      details: newDetails.trim() || 'Manual blockchain log entry.',
    };
    setLogs((prev) => [record, ...prev]);
    setNewAction('');
    setNewActor('');
    setNewDetails('');
    try {
      await fetch('/api/governance/audit', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          id: record.id,
          action: record.action,
          admin: record.actor,
          timestamp: record.timestamp,
          reasoningHash: record.txHash,
          details: record.details,
          policyVersion: 'manual-v1',
        }),
      });
      setSyncError(null);
    } catch {
      setSyncError('Saved locally; failed to publish to governance stream');
    }
  };

  return (
    <MainLayout breadcrumb={[{ label: 'Blockchain Logs' }]}>
      <div className="space-y-6">
        <div>
          <h1 className="text-4xl font-bold text-text-primary">Blockchain Logs</h1>
          <p className="text-lg text-text-secondary mt-1">
            Immutable-style ledger view for moderation and governance events
          </p>
          <p className="text-sm text-text-tertiary mt-2">
            {loading ? 'Syncing stream...' : syncError || 'Live stream active'}
          </p>
        </div>

        <div className="rounded-2xl bg-surface-secondary border border-border-subtle p-4 grid grid-cols-1 md:grid-cols-3 gap-3">
          <Input
            label="Action"
            placeholder="e.g. Escalate to legal"
            value={newAction}
            onChange={(e) => setNewAction(e.target.value)}
          />
          <Input
            label="Actor"
            placeholder="e.g. admin@omniaegis.ai"
            value={newActor}
            onChange={(e) => setNewActor(e.target.value)}
          />
          <Input
            label="Details"
            placeholder="Optional note"
            value={newDetails}
            onChange={(e) => setNewDetails(e.target.value)}
          />
          <div className="md:col-span-3">
            <Button onClick={handleAddLog}>Store blockchain log</Button>
          </div>
        </div>

        <div className="rounded-2xl bg-surface-secondary border border-border-subtle p-4">
          <Input
            label="Search Logs"
            placeholder="Search by ID, action, actor, or hash..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="rounded-2xl bg-surface-primary border border-border-subtle overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface-tertiary">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold text-text-secondary">ID</th>
                  <th className="px-4 py-3 text-left font-semibold text-text-secondary">Action</th>
                  <th className="px-4 py-3 text-left font-semibold text-text-secondary">Actor</th>
                  <th className="px-4 py-3 text-left font-semibold text-text-secondary">Timestamp</th>
                  <th className="px-4 py-3 text-left font-semibold text-text-secondary">Block</th>
                  <th className="px-4 py-3 text-left font-semibold text-text-secondary">Transaction Hash</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td className="px-4 py-4 text-text-tertiary" colSpan={6}>
                      Loading blockchain logs...
                    </td>
                  </tr>
                ) : filteredLogs.length === 0 ? (
                  <tr>
                    <td className="px-4 py-4 text-text-tertiary" colSpan={6}>
                      No logs found.
                    </td>
                  </tr>
                ) : (
                  filteredLogs.map((log) => (
                    <tr key={log.id} className="border-t border-border-subtle">
                      <td className="px-4 py-3 font-mono text-xs text-accent">{log.id}</td>
                      <td className="px-4 py-3 text-text-primary">{log.action}</td>
                      <td className="px-4 py-3 text-text-secondary">{log.actor}</td>
                      <td className="px-4 py-3 text-text-secondary">
                        {new Date(log.timestamp).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-text-secondary">{log.blockNumber}</td>
                      <td className="px-4 py-3 font-mono text-xs text-text-secondary">{log.txHash}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </MainLayout>
  );
}
