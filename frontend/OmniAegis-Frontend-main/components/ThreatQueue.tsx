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
  { label: 'Whitelist', tone: 'text-text-primary bg-surface-elevated hover:bg-accent/10' },
  { label: 'Takedown', tone: 'text-text-primary bg-accent hover:bg-accent/90' },
  { label: 'Escalate', tone: 'text-text-primary bg-surface-elevated hover:bg-accent/10' },
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

  return mapping[status] ?? 'bg-surface-elevated text-text-secondary';
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
      <section className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Threat monitoring</p>
            <h2 className="mt-2 text-2xl font-bold text-text-primary">Risk queue</h2>
          </div>
          <p className="text-sm text-text-secondary">Select a threat to review and respond.</p>
        </div>
        <div className="space-y-4">
          {threats.map((threat) => (
            <button
              key={threat.id}
              type="button"
              onClick={() => setSelectedId(threat.id)}
              className={`w-full rounded-3xl p-5 text-left transition shadow-sm ${
                selectedId === threat.id ? 'bg-surface-elevated shadow-[0_0_0_1px_rgba(108,99,255,0.22)]' : 'bg-surface-tertiary hover:bg-surface-elevated'
              }`}>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2 text-sm text-text-secondary">
                    <span className="rounded-full bg-surface-elevated px-3 py-1 font-semibold text-text-primary">{threat.type}</span>
                    <span className="rounded-full bg-surface-elevated px-3 py-1 text-text-secondary">{threat.riskLevel}</span>
                  </div>
                  <p className="max-w-xl text-base font-semibold text-text-primary">{new URL(threat.sourceURL).hostname} · {formatDate(threat.discoveredAt)}</p>
                </div>
                <span className={`rounded-full px-4 py-2 text-xs font-semibold ${statusBadge(threat.status)}`}>{threat.status}</span>
              </div>
            </button>
          ))}
        </div>
        {selectedThreat ? (
          <div className="premium-card rounded-[2rem] p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Selected threat</p>
                <h3 className="mt-2 text-xl font-semibold text-text-primary">{selectedThreat.type} detected</h3>
              </div>
              <p className="text-sm text-text-secondary">Risk: {selectedThreat.riskLevel}</p>
            </div>
            <p className="mt-4 text-sm leading-7 text-text-secondary">{selectedThreat.sourceURL}</p>
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
          <p className="premium-card rounded-3xl p-6 text-text-secondary">No threat selected yet.</p>
        )}
      </div>
    </section>
  );
}