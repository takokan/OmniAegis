import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function GET(request: Request) {
  const url = new URL(request.url);
  const type = url.searchParams.get('type');
  const status = url.searchParams.get('status');

  const where: any = {};
  if (type) where.type = type;
  if (status) where.status = status;

  const threats = await prisma.threat.findMany({
    where,
    orderBy: { discoveredAt: 'desc' },
  });

  return NextResponse.json(threats);
}