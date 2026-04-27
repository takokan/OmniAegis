'use client';

import { useState } from 'react';

interface DecisionWorkflowProps {
  itemId: string;
  onDecisionMade: (action: string) => void;
}

export default function DecisionWorkflow({ itemId, onDecisionMade }: DecisionWorkflowProps) {
  const [selectedAction, setSelectedAction] = useState<'confirm' | 'overturn' | 'escalate' | null>(null);
  const [feedback, setFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<any>(null);

  const handleSubmit = async () => {
    if (!selectedAction) return;
    setIsSubmitting(true);

    try {
      const response = await fetch(`/api/hitl/queue/${itemId}/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: selectedAction,
          feedback: feedback || null,
        }),
      });

      const data = await response.json();
      setResult(data);
      onDecisionMade(selectedAction);
    } catch (error) {
      setResult({ success: false, message: 'Decision submission failed' });
    } finally {
      setIsSubmitting(false);
    }
  };

  if (result?.success) {
    return (
      <div className="rounded-3xl border border-emerald-200 bg-emerald-50 p-6 text-center space-y-4">
        <p className="text-3xl">✓</p>
        <h3 className="text-lg font-bold text-emerald-900">Decision Recorded</h3>
        <p className="text-sm text-emerald-700">
          Action: <span className="font-semibold uppercase">{result.action}</span>
        </p>
        <p className="text-xs text-emerald-600">
          Audit ID: <span className="font-mono">{result.auditId}</span>
        </p>
        {feedback && (
          <p className="text-xs text-emerald-700 pt-2 border-t border-emerald-200">
            Feedback recorded for retraining
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Action Buttons */}
      <div className="grid gap-3 sm:grid-cols-3">
        {[
          { key: 'confirm', label: 'Confirm Infringement', color: 'bg-red-100 hover:bg-red-200 text-red-900', icon: '🚫' },
          { key: 'overturn', label: 'Overturn / Whitelist', color: 'bg-emerald-100 hover:bg-emerald-200 text-emerald-900', icon: '✓' },
          { key: 'escalate', label: 'Escalate to Legal', color: 'bg-sky-100 hover:bg-sky-200 text-sky-900', icon: '⚖️' },
        ].map((action) => (
          <button
            key={action.key}
            onClick={() => setSelectedAction(action.key as any)}
            className={`rounded-2xl px-4 py-3 text-sm font-semibold transition ${action.color} ${
              selectedAction === action.key ? 'ring-2 ring-offset-2 ring-slate-400' : ''
            }`}
          >
            <div className="text-lg mb-1">{action.icon}</div>
            {action.label}
          </button>
        ))}
      </div>

      {/* Feedback Field */}
      {selectedAction === 'overturn' && (
        <div className="rounded-3xl border border-slate-200/70 bg-slate-50/75 p-5 space-y-3">
          <p className="text-sm font-semibold text-slate-900">Why are you overturning this?</p>
          <p className="text-xs text-slate-600">
            Your feedback helps improve our federated learning model for better accuracy
          </p>
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition text-sm"
            placeholder="e.g., This is a legitimate parody / fair use artwork..."
            rows={3}
          />
        </div>
      )}

      {/* Submit Button */}
      <button
        onClick={handleSubmit}
        disabled={!selectedAction || isSubmitting}
        className="w-full rounded-2xl bg-accent hover:bg-accent/90 disabled:bg-slate-300 text-white font-semibold py-3 transition shadow-lg shadow-accent/20"
      >
        {isSubmitting ? 'Submitting...' : selectedAction ? `Submit ${selectedAction.charAt(0).toUpperCase() + selectedAction.slice(1)} Decision` : 'Select an action'}
      </button>
    </div>
  );
}