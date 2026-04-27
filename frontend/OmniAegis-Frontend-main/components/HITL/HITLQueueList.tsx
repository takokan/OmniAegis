'use client';

import { useState, useEffect } from 'react';

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

interface QueueData {
  items: QueueItem[];
  total: number;
}

export default function HITLQueueList({ onSelect }: { onSelect: (item: QueueItem) => void }) {
  const [data, setData] = useState<QueueData | null>(null);

  useEffect(() => {
    fetch('/api/hitl/queue')
      .then((res) => res.json())
      .then(setData)
      .catch(() => null);
  }, []);

  if (!data) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 rounded-3xl bg-slate-100 animate-pulse" />
        ))}
      </div>
    );
  }

  const getRiskColor = (level: string) => {
    const colors: Record<string, string> = {
      High: 'bg-red-100 text-red-700',
      Med: 'bg-yellow-100 text-yellow-700',
      Low: 'bg-emerald-100 text-emerald-700',
    };
    return colors[level] || 'bg-slate-100 text-slate-700';
  };

  return (
    <div className="space-y-3">
      {data.items.map((item) => (
        <button
          key={item.id}
          onClick={() => onSelect(item)}
          className="w-full rounded-3xl border border-slate-200/70 bg-slate-50/70 p-5 text-left hover:border-slate-300 hover:bg-slate-50/90 transition"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex-1 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                  {item.type}
                </span>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${getRiskColor(item.riskLevel)}`}>
                  {item.riskLevel}
                </span>
              </div>
              <p className="max-w-lg text-base font-semibold text-slate-950">
                {new URL(item.sourceURL).hostname}
              </p>
              <p className="text-xs text-slate-500">
                {new Date(item.discoveredAt).toLocaleString()}
              </p>
            </div>
            <div className="flex flex-col items-end gap-2">
              <span className="rounded-full bg-amber-100 text-amber-700 px-3 py-1 text-xs font-semibold">
                {item.status}
              </span>
              <span className="text-xs font-semibold text-slate-600">
                {(item.confidenceScore * 100).toFixed(0)}% confidence
              </span>
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}