import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function GET() {
  const metric = await prisma.metric.findFirst();

  return NextResponse.json({
    totalAssets: metric?.totalAssets ?? 0,
    activeThreats: metric?.activeThreats ?? 0,
    protectionEfficiency: metric?.protectionEfficiency ?? 0,
  });
}