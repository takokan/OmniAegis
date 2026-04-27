'use client';

import { useState, useEffect } from 'react';

interface AuditEntry {
  id: string;
  action: string;
  timestamp: string;
  policyVersion: string;
  reasoningHash: string;
  admin: string;
  details: string;
}

interface AuditData {
  entries: AuditEntry[];
  total: number;
}

export default function BlockchainAuditLedger() {
  const [data, setData] = useState<AuditData | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    fetch('/api/governance/audit')
      .then((res) => res.json())
      .then(setData)
      .catch(() => null);
  }, []);

  if (!data) {
    return (
      <div className="h-96 rounded-[1.75rem] border border-slate-200/80 bg-slate-50/80 flex items-center justify-center text-slate-500">
        <p className="text-sm">Loading audit ledger...</p>
      </div>
    );
  }

  const filtered = data.entries.filter(
    (e) =>
      e.action.toLowerCase().includes(searchTerm.toLowerCase()) ||
      e.admin.toLowerCase().includes(searchTerm.toLowerCase()) ||
      e.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getActionBadgeColor = (action: string) => {
    if (action.includes('Takedown')) return 'bg-red-100 text-red-700';
    if (action.includes('Whitelist')) return 'bg-emerald-100 text-emerald-700';
    if (action.includes('Escalate')) return 'bg-sky-100 text-sky-700';
    if (action.includes('Auto')) return 'bg-purple-100 text-purple-700';
    return 'bg-slate-100 text-slate-700';
  };

  return (
    <div className="space-y-6">
      {/* Search Bar */}
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Search by action, admin, or audit ID..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent"
        />
        <button className="rounded-2xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-900 font-semibold px-4 py-2 text-sm transition">
          Export
        </button>
      </div>

      {/* Table */}
      <div className="rounded-3xl border border-slate-200/70 bg-white/85 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="px-6 py-4 text-left font-semibold text-slate-600">Action</th>
                <th className="px-6 py-4 text-left font-semibold text-slate-600">Timestamp</th>
                <th className="px-6 py-4 text-left font-semibold text-slate-600">Policy Version</th>
                <th className="px-6 py-4 text-left font-semibold text-slate-600">Admin</th>
                <th className="px-6 py-4 text-left font-semibold text-slate-600">Reasoning Hash</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry) => (
                <tr key={entry.id} className="border-b border-slate-200/50 hover:bg-slate-50/50 transition">
                  <td className="px-6 py-4">
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${getActionBadgeColor(entry.action)}`}>
                      {entry.action}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-slate-600">
                    {new Date(entry.timestamp).toLocaleString()}
                  </td>
                  <td className="px-6 py-4 text-slate-600 font-mono text-xs">{entry.policyVersion}</td>
                  <td className="px-6 py-4 text-slate-600 text-xs">{entry.admin}</td>
                  <td className="px-6 py-4 text-slate-600 font-mono text-xs">
                    <span title={entry.reasoningHash}>{entry.reasoningHash.slice(0, 12)}...</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Details Row */}
      {filtered.length > 0 && (
        <div className="rounded-3xl border border-slate-200/70 bg-slate-50/75 p-4">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400 mb-2">Latest Entry Details</p>
          <p className="text-sm text-slate-700">{filtered[0].details}</p>
        </div>
      )}
    </div>
  );
}