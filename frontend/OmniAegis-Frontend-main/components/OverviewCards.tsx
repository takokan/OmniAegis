'use client';

export default function OverviewCards() {
  return (
    <section className="space-y-6" id="monitoring">
      <div className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
        <div className="flex items-center justify-between gap-6">
          <div>
            <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Threat Insights</p>
            <h2 className="mt-3 text-2xl font-bold text-text-primary">Threat trend horizon</h2>
          </div>
          <span className="rounded-full bg-surface-elevated px-4 py-2 text-sm font-semibold text-text-secondary">
            Last 30 days
          </span>
        </div>
        <div className="mt-8 h-72 rounded-[1.75rem] bg-surface-elevated p-6 text-text-secondary shadow-sm">
          <div className="flex h-full items-center justify-center text-center text-sm">Placeholder for trend visualization</div>
        </div>
      </div>
      <div className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
        <div className="flex items-center justify-between gap-6">
          <div>
            <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Regional scan</p>
            <h2 className="mt-3 text-2xl font-bold text-text-primary">Global threat map</h2>
          </div>
          <span className="rounded-full bg-surface-elevated px-4 py-2 text-sm font-semibold text-text-secondary">
            Real-time feed
          </span>
        </div>
        <div className="mt-8 h-72 rounded-[1.75rem] bg-surface-elevated p-6 text-text-secondary shadow-sm">
          <div className="flex h-full items-center justify-center text-center text-sm">Placeholder for map panel</div>
        </div>
      </div>
    </section>
  );
}