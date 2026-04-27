'use client';

export default function OverviewCards() {
  return (
    <section className="space-y-6" id="monitoring">
      <div className="rounded-[2rem] border border-slate-200/70 bg-white/85 p-8 shadow-sm backdrop-blur-sm">
        <div className="flex items-center justify-between gap-6">
          <div>
            <p className="text-sm uppercase tracking-[0.28em] text-slate-400">Threat Insights</p>
            <h2 className="mt-3 text-2xl font-bold text-slate-950">Threat trend horizon</h2>
          </div>
          <span className="rounded-full bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-700">
            Last 30 days
          </span>
        </div>
        <div className="mt-8 h-72 rounded-[1.75rem] border border-slate-200/80 bg-slate-50/80 p-6 text-slate-500">
          <div className="flex h-full items-center justify-center text-center text-sm">Placeholder for trend visualization</div>
        </div>
      </div>
      <div className="rounded-[2rem] border border-slate-200/70 bg-white/85 p-8 shadow-sm backdrop-blur-sm">
        <div className="flex items-center justify-between gap-6">
          <div>
            <p className="text-sm uppercase tracking-[0.28em] text-slate-400">Regional scan</p>
            <h2 className="mt-3 text-2xl font-bold text-slate-950">Global threat map</h2>
          </div>
          <span className="rounded-full bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-700">
            Real-time feed
          </span>
        </div>
        <div className="mt-8 h-72 rounded-[1.75rem] border border-slate-200/80 bg-slate-50/80 p-6 text-slate-500">
          <div className="flex h-full items-center justify-center text-center text-sm">Placeholder for map panel</div>
        </div>
      </div>
    </section>
  );
}