'use client';

import { useEffect, useMemo, useState } from 'react';

interface Threat {
  id: string;
  type: string;
  riskLevel: string;
  status: string;
  sourceURL: string;
  discoveredAt: string;
}

const actionOptions = [
  { label: 'Whitelist', tone: 'text-slate-700 bg-slate-100 hover:bg-slate-200' },
  { label: 'Takedown', tone: 'text-white bg-accent hover:bg-accent/90' },
  { label: 'Escalate', tone: 'text-slate-700 bg-slate-100 hover:bg-slate-200' },
];

function formatDate(date: string) {
  return new Date(date).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function statusBadge(status: string) {
  const mapping: Record<string, string> = {
    Pending: 'bg-amber-100 text-amber-700',
    Whitelisted: 'bg-emerald-100 text-emerald-700',
    Takedown: 'bg-red-100 text-red-700',
    Escalated: 'bg-sky-100 text-sky-700',
  };

  return mapping[status] ?? 'bg-slate-100 text-slate-700';
}

export default function ThreatQueue() {
  const [threats, setThreats] = useState<Threat[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/threats')
      .then((res) => res.json())
      .then(setThreats)
      .catch(() => setThreats([]));
  }, []);

  const selectedThreat = useMemo(
    () => threats.find((item) => item.id === selectedId) ?? threats[0] ?? null,
    [selectedId, threats]
  );

  const handleAction = async (action: string) => {
    if (!selectedThreat) return;
    setLoadingId(selectedThreat.id);

    const response = await fetch(`/api/threats/${selectedThreat.id}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    });

    if (!response.ok) {
      setLoadingId(null);
      return;
    }

    const updated = await response.json();
    setThreats((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    setLoadingId(null);
  };

  return (
    <section className="rounded-[2rem] border border-slate-200/70 bg-white/90 p-8 shadow-sm backdrop-blur-sm">
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.28em] text-slate-400">Threat monitoring</p>
            <h2 className="mt-2 text-2xl font-bold text-slate-950">Risk queue</h2>
          </div>
          <p className="text-sm text-slate-600">Select a threat to review and respond.</p>
        </div>
        <div className="space-y-4">
          {threats.map((threat) => (
            <button
              key={threat.id}
              type="button"
              onClick={() => setSelectedId(threat.id)}
              className={`w-full rounded-3xl border p-5 text-left transition ${
                selectedId === threat.id ? 'border-accent/30 bg-accent/5' : 'border-slate-200/70 bg-slate-50/70 hover:border-slate-300'
              }`}>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
                    <span className="rounded-full bg-slate-100 px-3 py-1 font-semibold text-slate-700">{threat.type}</span>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">{threat.riskLevel}</span>
                  </div>
                  <p className="max-w-xl text-base font-semibold text-slate-950">{new URL(threat.sourceURL).hostname} · {formatDate(threat.discoveredAt)}</p>
                </div>
                <span className={`rounded-full px-4 py-2 text-xs font-semibold ${statusBadge(threat.status)}`}>{threat.status}</span>
              </div>
            </button>
          ))}
        </div>
        {selectedThreat ? (
          <div className="rounded-[2rem] border border-slate-200/70 bg-slate-50/75 p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm uppercase tracking-[0.28em] text-slate-400">Selected threat</p>
                <h3 className="mt-2 text-xl font-semibold text-slate-950">{selectedThreat.type} detected</h3>
              </div>
              <p className="text-sm text-slate-600">Risk: {selectedThreat.riskLevel}</p>
            </div>
            <p className="mt-4 text-sm leading-7 text-slate-600">{selectedThreat.sourceURL}</p>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
              {actionOptions.map((option) => (
                <button
                  key={option.label}
                  type="button"
                  onClick={() => handleAction(option.label)}
                  disabled={loadingId === selectedThreat.id}
                  className={`rounded-3xl px-5 py-3 text-sm font-semibold transition ${option.tone} ${option.label === 'Takedown' ? 'shadow-lg shadow-accent/10' : ''}`}
                >
                  {loadingId === selectedThreat.id && option.label === 'Takedown' ? 'Applying...' : option.label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <p className="rounded-3xl border border-slate-200/70 bg-slate-50/75 p-6 text-slate-600">No threat selected yet.</p>
        )}
      </div>
    </section>
  );
}