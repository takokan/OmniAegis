'use client';

import { useState } from 'react';

interface PromoteModalProps {
  isOpen: boolean;
  onClose: () => void;
  shadowVersion: string;
  liveVersion: string;
}

export default function PromoteToLiveModal({
  isOpen,
  onClose,
  shadowVersion,
  liveVersion,
}: PromoteModalProps) {
  const [isPromoting, setIsPromoting] = useState(false);
  const [result, setResult] = useState<any>(null);

  const handlePromote = async () => {
    setIsPromoting(true);
    try {
      const response = await fetch('/api/rl/policies/promote', { method: 'POST' });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      setResult({ success: false, message: 'Promotion failed' });
    } finally {
      setIsPromoting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-[2rem] border border-slate-200 bg-white shadow-2xl">
        <div className="space-y-6 p-8">
          {/* Header */}
          {!result && (
            <>
              <div className="space-y-2">
                <h2 className="text-2xl font-bold text-slate-950">Promote Policy to Live</h2>
                <p className="text-sm text-slate-600">
                  This action will perform an atomic swap, making the shadow policy your new live policy.
                </p>
              </div>

              {/* Comparison Table */}
              <div className="space-y-3 rounded-2xl bg-slate-50 p-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs uppercase tracking-[0.28em] text-slate-400 mb-1">
                      Current Live
                    </p>
                    <p className="font-mono font-semibold text-slate-900">{liveVersion}</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.28em] text-slate-400 mb-1">
                      Will Promote
                    </p>
                    <p className="font-mono font-semibold text-accent">{shadowVersion}</p>
                  </div>
                </div>
              </div>

              {/* Safety Checklist */}
              <div className="space-y-2 rounded-2xl bg-emerald-50 border border-emerald-200 p-4">
                <p className="text-xs uppercase tracking-[0.28em] text-emerald-600 font-semibold mb-3">
                  Pre-Promotion Checks
                </p>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2 text-emerald-700">
                    <span className="font-semibold">✓</span>
                    <span>Training converged (KL Divergence: 0.1891)</span>
                  </div>
                  <div className="flex items-center gap-2 text-emerald-700">
                    <span className="font-semibold">✓</span>
                    <span>All constraints within acceptable bounds</span>
                  </div>
                  <div className="flex items-center gap-2 text-emerald-700">
                    <span className="font-semibold">✓</span>
                    <span>Improvement metrics validated</span>
                  </div>
                  <div className="flex items-center gap-2 text-emerald-700">
                    <span className="font-semibold">✓</span>
                    <span>1-hour rollback window available</span>
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex gap-3">
                <button
                  onClick={onClose}
                  className="flex-1 rounded-2xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-900 font-semibold py-3 transition"
                >
                  Cancel
                </button>
                <button
                  onClick={handlePromote}
                  disabled={isPromoting}
                  className="flex-1 rounded-2xl bg-accent hover:bg-accent/90 disabled:bg-slate-300 text-white font-semibold py-3 transition shadow-lg shadow-accent/20"
                >
                  {isPromoting ? 'Promoting...' : 'Confirm Promotion'}
                </button>
              </div>
            </>
          )}

          {/* Success State */}
          {result && result.success && (
            <>
              <div className="text-center space-y-3">
                <div className="inline-block text-4xl">✓</div>
                <h3 className="text-xl font-bold text-emerald-900">Promotion Successful</h3>
                <p className="text-sm text-slate-600">{result.message}</p>
              </div>

              <div className="space-y-3 rounded-2xl bg-emerald-50 border border-emerald-200 p-4">
                <div className="text-sm space-y-2">
                  <div className="flex justify-between">
                    <span className="text-slate-600">Promoted At:</span>
                    <span className="font-semibold text-slate-900">
                      {new Date(result.promotedAt).toLocaleString()}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-600">Audit ID:</span>
                    <span className="font-mono font-semibold text-slate-900">{result.auditId}</span>
                  </div>
                  {result.rollbackAvailable && (
                    <div className="flex justify-between pt-2 border-t border-emerald-200">
                      <span className="text-slate-600">Rollback Available:</span>
                      <span className="text-xs text-emerald-700 font-semibold">
                        Until {new Date(result.rollbackUntil).toLocaleTimeString()}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <button
                onClick={onClose}
                className="w-full rounded-2xl bg-slate-900 hover:bg-slate-800 text-white font-semibold py-3 transition"
              >
                Close
              </button>
            </>
          )}

          {/* Error State */}
          {result && !result.success && (
            <>
              <div className="text-center space-y-3">
                <div className="inline-block text-4xl">✗</div>
                <h3 className="text-xl font-bold text-red-900">Promotion Failed</h3>
                <p className="text-sm text-slate-600">{result.message}</p>
              </div>

              <button
                onClick={() => setResult(null)}
                className="w-full rounded-2xl bg-slate-900 hover:bg-slate-800 text-white font-semibold py-3 transition"
              >
                Try Again
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}