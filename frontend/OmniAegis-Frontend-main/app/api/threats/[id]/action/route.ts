import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function POST(request: Request, { params }: { params: { id: string } }) {
  const body = await request.json();
  const { action } = body as { action?: string };

  const actionMap: Record<string, string> = {
    Whitelist: 'Whitelisted',
    Takedown: 'Takedown',
    Escalate: 'Escalated',
  };

  const newStatus = actionMap[action ?? ''];
  if (!newStatus) {
    return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
  }

  const threat = await prisma.threat.update({
    where: { id: params.id },
    data: { status: newStatus as any },
  });

  return NextResponse.json(threat);
}