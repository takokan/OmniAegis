'use client';

import React from 'react';

type StatusType = 'approved' | 'rejected' | 'pending' | 'flagged' | 'anchored' | 'reviewing';

interface StatusChipProps {
  status: StatusType;
  size?: 'sm' | 'md';
  className?: string;
}

const statusConfig: Record<
  StatusType,
  { label: string; colorVar: string; bgColorVar: string }
> = {
  approved: {
    label: 'APPROVED',
    colorVar: 'var(--color-success)',
    bgColorVar: 'var(--color-success-bg)',
  },
  rejected: {
    label: 'REJECTED',
    colorVar: 'var(--color-danger)',
    bgColorVar: 'var(--color-danger-bg)',
  },
  pending: {
    label: 'PENDING',
    colorVar: 'var(--color-warning)',
    bgColorVar: 'var(--color-warning-bg)',
  },
  flagged: {
    label: 'FLAGGED',
    colorVar: 'var(--color-danger)',
    bgColorVar: 'var(--color-danger-bg)',
  },
  anchored: {
    label: 'ANCHORED',
    colorVar: 'var(--color-accent)',
    bgColorVar: 'var(--color-accent-muted)',
  },
  reviewing: {
    label: 'REVIEWING',
    colorVar: 'var(--color-neutral)',
    bgColorVar: 'var(--color-neutral-bg)',
  },
};

function StatusIcon({ status }: { status: StatusType }) {
  switch (status) {
    case 'approved':
      return (
        <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="m3.5 8.5 2.5 2.5 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case 'rejected':
      return (
        <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M4 4l8 8M12 4 4 12" strokeLinecap="round" />
        </svg>
      );
    case 'pending':
      return (
        <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <circle cx="8" cy="8" r="5.5" />
          <path d="M8 5.2v3.2l2 1.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case 'flagged':
      return (
        <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M5 13V3" strokeLinecap="round" />
          <path d="M5 3h6l-1.6 2L11 7H5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case 'anchored':
      return (
        <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M8 2.5v8" strokeLinecap="round" />
          <path d="M4 5.5h8" strokeLinecap="round" />
          <path d="M3.5 10.5a4.5 4.5 0 0 0 9 0" strokeLinecap="round" />
        </svg>
      );
    case 'reviewing':
      return (
        <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <circle cx="8" cy="8" r="5.5" strokeDasharray="2 2" />
        </svg>
      );
  }
}

/**
 * StatusChip - Sentry-inspired badge for decision states
 * 
 * - Always uses icon + text (never color-only)
 * - Uppercase label with 0.06em letter-spacing
 * - Semantic colors mapped to status type
 */
export function StatusChip({
  status,
  size = 'md',
  className = '',
}: StatusChipProps) {
  const config = statusConfig[status];

  const sizeClasses = {
    sm: 'px-2 py-1 text-2xs gap-1',
    md: 'px-2 py-1 text-xs gap-1.5',
  };

  return (
    <div
      className={`inline-flex items-center font-semibold rounded-sm ${sizeClasses[size]} ${className}`}
      style={{
        backgroundColor: config.bgColorVar,
        color: config.colorVar,
        letterSpacing: '0.06em',
      }}
    >
      <span className="leading-none">
        <StatusIcon status={status} />
      </span>
      <span className="uppercase font-semibold leading-tight">{config.label}</span>
    </div>
  );
}

export default StatusChip;
