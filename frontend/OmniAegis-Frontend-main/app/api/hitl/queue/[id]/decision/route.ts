import { NextResponse } from 'next/server';

// Handle HITL decision submission
export async function POST(request: Request, { params }: { params: { id: string } }) {
  const body = await request.json();
  const { action, feedback } = body as { action: 'confirm' | 'overturn' | 'escalate'; feedback?: string };

  const result = {
    success: true,
    itemId: params.id,
    action,
    processedAt: new Date().toISOString(),
    auditId: 'aud_' + Math.random().toString(36).substr(2, 9),
    feedback: feedback || null,
  };

  return NextResponse.json(result);
}