import { NextResponse } from 'next/server';

// Mock approved HITL decisions for admin view
export async function GET() {
  const approvedDecisions = [
    {
      id: 'hitl_001',
      type: 'Logo',
      riskLevel: 'High',
      sourceURL: 'https://marketplace.example.com/suspicious-logo',
      approvedAt: '2026-04-25T15:45:00Z',
      reviewer: 'reviewer@sentinelai.com',
      action: 'confirm',
      feedback: 'Clear trademark infringement - identical logo design',
      confidenceScore: 0.87,
    },
    {
      id: 'hitl_002',
      type: 'Artwork',
      riskLevel: 'Med',
      sourceURL: 'https://social.example.com/post/art-copy',
      approvedAt: '2026-04-25T14:22:00Z',
      reviewer: 'reviewer@sentinelai.com',
      action: 'overturn',
      feedback: 'Fair use - parody artwork with significant modifications',
      confidenceScore: 0.72,
    },
    {
      id: 'hitl_003',
      type: 'Counterfeit',
      riskLevel: 'High',
      sourceURL: 'https://ecommerce.example.com/product/fake',
      approvedAt: '2026-04-25T13:15:00Z',
      reviewer: 'reviewer@sentinelai.com',
      action: 'confirm',
      feedback: 'Confirmed counterfeit - exact product replica with fake branding',
      confidenceScore: 0.91,
    },
  ];

  return NextResponse.json({
    decisions: approvedDecisions,
    total: approvedDecisions.length,
  });
}