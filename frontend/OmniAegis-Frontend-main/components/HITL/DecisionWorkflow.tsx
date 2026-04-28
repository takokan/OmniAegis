'use client';

import { useState } from 'react';

interface DecisionWorkflowProps {
  itemId: string;
  onDecisionMade: (action: string) => void;
}

function ActionIcon({ type }: { type: 'confirm' | 'overturn' | 'escalate' }) {
  if (type === 'confirm') {
    return (
      <svg className="h-5 w-5" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M6 6l8 8M14 6l-8 8" strokeLinecap="round" />
        <circle cx="10" cy="10" r="7" />
      </svg>
    );
  }

  if (type === 'overturn') {
    return (
      <svg className="h-5 w-5" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="m5 10 3 3 7-7" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  return (
    <svg className="h-5 w-5" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M10 3.5 4.5 6.2v4.3c0 3.2 2.3 5.8 5.5 6.5 3.2-.7 5.5-3.3 5.5-6.5V6.2L10 3.5Z" />
      <path d="M7.4 10h5.2" strokeLinecap="round" />
    </svg>
  );
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
      <div className="rounded-3xl bg-emerald-500/10 p-6 text-center space-y-4 shadow-sm">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-700">
          <ActionIcon type="overturn" />
        </div>
        <h3 className="text-lg font-bold text-emerald-900">Decision Recorded</h3>
        <p className="text-sm text-emerald-700">
          Action: <span className="font-semibold uppercase">{result.action}</span>
        </p>
        <p className="text-xs text-emerald-300">
          Audit ID: <span className="font-mono">{result.auditId}</span>
        </p>
        {feedback && (
          <p className="text-xs text-emerald-300 pt-2">
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
          { key: 'confirm', label: 'Confirm Infringement', color: 'bg-red-100 hover:bg-red-200 text-red-900' },
          { key: 'overturn', label: 'Overturn / Whitelist', color: 'bg-emerald-100 hover:bg-emerald-200 text-emerald-900' },
          { key: 'escalate', label: 'Escalate to Legal', color: 'bg-sky-100 hover:bg-sky-200 text-sky-900' },
        ].map((action) => (
          <button
            key={action.key}
            onClick={() => setSelectedAction(action.key as any)}
            className={`rounded-2xl px-4 py-3 text-sm font-semibold transition ${action.color} ${
              selectedAction === action.key ? 'ring-2 ring-offset-2 ring-border-strong' : ''
            }`}
          >
            <div className="mb-2 flex justify-center">
              <ActionIcon type={action.key as 'confirm' | 'overturn' | 'escalate'} />
            </div>
            {action.label}
          </button>
        ))}
      </div>

      {/* Feedback Field */}
      {selectedAction === 'overturn' && (
        <div className="premium-card rounded-3xl p-5 space-y-3">
          <p className="text-sm font-semibold text-text-primary">Why are you overturning this?</p>
          <p className="text-xs text-text-secondary">
            Your feedback helps improve our federated learning model for better accuracy
          </p>
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            className="w-full rounded-2xl border border-border-default bg-surface-primary px-4 py-3 text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition text-sm"
            placeholder="e.g., This is a legitimate parody / fair use artwork..."
            rows={3}
          />
        </div>
      )}

      {/* Submit Button */}
      <button
        onClick={handleSubmit}
        disabled={!selectedAction || isSubmitting}
        className="w-full rounded-2xl bg-accent hover:bg-accent/90 disabled:bg-surface-elevated text-text-primary font-semibold py-3 transition shadow-lg shadow-accent/20"
      >
        {isSubmitting ? 'Submitting...' : selectedAction ? `Submit ${selectedAction.charAt(0).toUpperCase() + selectedAction.slice(1)} Decision` : 'Select an action'}
      </button>
    </div>
  );
}