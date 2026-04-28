'use client';

import { useState, useEffect } from 'react';

interface ApprovedDecision {
  id: string;
  type: string;
  riskLevel: string;
  sourceURL: string;
  approvedAt: string;
  reviewer: string;
  action: string;
  feedback: string;
  confidenceScore: number;
}

export default function HITLApprovalSummary() {
  const [decisions, setDecisions] = useState<ApprovedDecision[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/hitl/approved')
      .then(res => res.json())
      .then(data => {
        setDecisions(data.decisions);
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to fetch approved decisions:', err);
        setLoading(false);
      });
  }, []);

  const getActionColor = (action: string) => {
    switch (action) {
      case 'confirm': return 'bg-red-100 text-red-700';
      case 'overturn': return 'bg-emerald-100 text-emerald-700';
      case 'escalate': return 'bg-sky-100 text-sky-700';
      default: return 'bg-surface-elevated text-text-secondary';
    }
  };

  const getRiskColor = (riskLevel: string) => {
    switch (riskLevel.toLowerCase()) {
      case 'high': return 'bg-red-100 text-red-700';
      case 'medium': return 'bg-yellow-100 text-yellow-700';
      case 'low': return 'bg-emerald-100 text-emerald-700';
      default: return 'bg-surface-elevated text-text-secondary';
    }
  };

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map(i => (
          <div key={i} className="rounded-3xl bg-surface-tertiary p-4 animate-pulse shadow-sm">
            <div className="h-3 bg-surface-elevated rounded mb-2"></div>
            <div className="h-2 bg-surface-elevated rounded w-3/4"></div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {decisions.map((decision) => (
        <div
          key={decision.id}
          className="rounded-3xl bg-surface-tertiary p-4 text-sm shadow-sm"
        >
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-surface-elevated px-2 py-1 text-xs font-semibold text-text-secondary">
                {decision.type}
              </span>
              <span className={`rounded-full px-2 py-1 text-xs font-semibold ${getRiskColor(decision.riskLevel)}`}>
                {decision.riskLevel}
              </span>
              <span className={`rounded-full px-2 py-1 text-xs font-semibold ${getActionColor(decision.action)}`}>
                {decision.action === 'confirm' ? 'Confirmed' : decision.action === 'overturn' ? 'Overturned' : 'Escalated'}
              </span>
            </div>
            <span className="text-xs text-text-tertiary">
              {new Date(decision.approvedAt).toLocaleString()}
            </span>
          </div>
          <p className="text-text-primary font-medium mb-1">
            {new URL(decision.sourceURL).hostname}
          </p>
          <p className="text-text-secondary text-xs mb-2">{decision.feedback}</p>
          <div className="flex items-center justify-between text-xs text-text-tertiary">
            <span>By {decision.reviewer.split('@')[0]}</span>
            <span>{Math.round(decision.confidenceScore * 100)}% confidence</span>
          </div>
        </div>
      ))}
    </div>
  );
}