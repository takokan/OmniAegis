'use client';

import { useEffect, useState } from 'react';

interface MetricsData {
  totalAssets: number;
  activeThreats: number;
  protectionEfficiency: number;
}

export default function OverviewMetrics() {
  const [metrics, setMetrics] = useState<MetricsData | null>(null);

  useEffect(() => {
    fetch('/api/dashboard/metrics')
      .then((res) => res.json())
      .then(setMetrics)
      .catch(() => null);
  }, []);

  return (
    <section id="overview" className="grid gap-6 sm:grid-cols-3">
      {[
        { label: 'Total assets protected', value: metrics?.totalAssets ?? '—' },
        { label: 'Active threats', value: metrics?.activeThreats ?? '—' },
        { label: 'Protection efficiency', value: metrics?.protectionEfficiency ? `${metrics.protectionEfficiency}%` : '—' },
      ].map((item) => (
        <div key={item.label} className="rounded-3xl border border-slate-200/70 bg-white/90 p-8 shadow-sm backdrop-blur-sm flex flex-col items-center justify-center text-center">
          <p className="text-sm uppercase tracking-[0.3em] text-slate-600">{item.label}</p>
          <p className="mt-4 text-4xl font-semibold text-slate-950">{item.value}</p>
        </div>
      ))}
    </section>
  );
}