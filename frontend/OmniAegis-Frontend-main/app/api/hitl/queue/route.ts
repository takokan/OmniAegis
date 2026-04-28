import { NextResponse } from 'next/server';

export async function GET() {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
  const res = await fetch(`${base}/hitl/queue/peek?limit=100`, { cache: 'no-store' });
  const text = await res.text();
  if (!res.ok) {
    return NextResponse.json({ items: [], total: 0, error: text }, { status: 502 });
  }
  try {
    const data = JSON.parse(text);
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ items: [], total: 0, error: 'invalid backend response' }, { status: 502 });
  }
}