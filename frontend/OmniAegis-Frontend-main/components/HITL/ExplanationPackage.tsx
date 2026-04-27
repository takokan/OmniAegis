'use client';

interface ExplanationPanelProps {
  item: {
    id: string;
    type: string;
    reasonCode: string;
    confidenceScore: number;
    explanation: {
      saliencyMap: string;
      nodeLinks: string;
    };
    context: {
      previousActions: number;
      seller: string;
      region: string;
    };
  };
}

export default function ExplanationPackage({ item }: ExplanationPanelProps) {
  return (
    <div className="space-y-4">
      {/* Saliency Map */}
      <div className="rounded-[1.75rem] border border-slate-200/80 bg-slate-50/80 p-6 h-48 flex items-center justify-center">
        <div className="text-center space-y-2">
          <p className="text-sm font-semibold text-slate-700">Pixel Saliency Map</p>
          <p className="text-xs text-slate-500">Visual importance heatmap showing why this content was flagged</p>
          <div className="mt-3 inline-block w-32 h-24 rounded bg-gradient-to-br from-blue-300 via-purple-300 to-red-300 opacity-60" />
        </div>
      </div>

      {/* Node-Link Graph */}
      <div className="rounded-[1.75rem] border border-slate-200/80 bg-slate-50/80 p-6 h-48 flex items-center justify-center">
        <div className="text-center space-y-2">
          <p className="text-sm font-semibold text-slate-700">Relationship Graph</p>
          <p className="text-xs text-slate-500">Network showing asset connections and historical patterns</p>
          <div className="mt-3 space-y-1 text-xs">
            <div className="text-slate-600">• Source linked to 3 other accounts</div>
            <div className="text-slate-600">• Pattern matches 12 previous violations</div>
            <div className="text-slate-600">• 87% similarity to known counterfeit</div>
          </div>
        </div>
      </div>

      {/* Context Data */}
      <div className="rounded-3xl border border-slate-200/70 bg-white/85 p-4 space-y-3">
        <p className="text-xs uppercase tracking-[0.28em] text-slate-400 font-semibold">Context Data</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl bg-slate-50 p-3">
            <p className="text-xs text-slate-500 mb-1">Confidence Score</p>
            <p className="text-2xl font-bold text-slate-950">{(item.confidenceScore * 100).toFixed(0)}%</p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-3">
            <p className="text-xs text-slate-500 mb-1">Reason Code</p>
            <p className="text-sm font-mono font-semibold text-slate-900">{item.reasonCode}</p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-3">
            <p className="text-xs text-slate-500 mb-1">Seller Reputation</p>
            <p className="text-sm font-semibold text-slate-900">{item.context.previousActions} prior actions</p>
          </div>
        </div>
      </div>
    </div>
  );
}