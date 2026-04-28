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
      <div className="rounded-[1.75rem] bg-surface-elevated p-6 h-48 flex items-center justify-center shadow-sm">
        <div className="text-center space-y-2">
          <p className="text-sm font-semibold text-text-primary">Pixel Saliency Map</p>
          <p className="text-xs text-text-tertiary">Visual importance heatmap showing why this content was flagged</p>
          <div className="mt-3 inline-block w-32 h-24 rounded bg-gradient-to-br from-blue-300 via-purple-300 to-red-300 opacity-60" />
        </div>
      </div>

      {/* Node-Link Graph */}
      <div className="rounded-[1.75rem] bg-surface-elevated p-6 h-48 flex items-center justify-center shadow-sm">
        <div className="text-center space-y-2">
          <p className="text-sm font-semibold text-text-primary">Relationship Graph</p>
          <p className="text-xs text-text-tertiary">Network showing asset connections and historical patterns</p>
          <div className="mt-3 space-y-1 text-xs">
            <div className="text-text-secondary">• Source linked to 3 other accounts</div>
            <div className="text-text-secondary">• Pattern matches 12 previous violations</div>
            <div className="text-text-secondary">• 87% similarity to known counterfeit</div>
          </div>
        </div>
      </div>

      {/* Context Data */}
      <div className="premium-card rounded-3xl p-4 space-y-3">
        <p className="text-xs uppercase tracking-[0.28em] text-text-tertiary font-semibold">Context Data</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl bg-surface-elevated p-3">
            <p className="text-xs text-text-tertiary mb-1">Confidence Score</p>
            <p className="text-2xl font-bold text-text-primary">{(item.confidenceScore * 100).toFixed(0)}%</p>
          </div>
          <div className="rounded-2xl bg-surface-elevated p-3">
            <p className="text-xs text-text-tertiary mb-1">Reason Code</p>
            <p className="text-sm font-mono font-semibold text-text-primary">{item.reasonCode}</p>
          </div>
          <div className="rounded-2xl bg-surface-elevated p-3">
            <p className="text-xs text-text-tertiary mb-1">Seller Reputation</p>
            <p className="text-sm font-semibold text-text-primary">{item.context.previousActions} prior actions</p>
          </div>
        </div>
      </div>
    </div>
  );
}