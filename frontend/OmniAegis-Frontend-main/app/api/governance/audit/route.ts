import { NextResponse } from 'next/server';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export async function GET() {
  try {
    const res = await fetch(`${BASE}/governance/audit?limit=150`, { cache: 'no-store' });
    const text = await res.text();
    if (!res.ok) {
      return NextResponse.json({ entries: [], total: 0, error: text }, { status: 502 });
    }
    const data = JSON.parse(text) as { entries?: unknown[]; total?: number };
    return NextResponse.json({
      entries: Array.isArray(data.entries) ? data.entries : [],
      total: typeof data.total === 'number' ? data.total : 0,
    });
  } catch (error) {
    return NextResponse.json(
      { entries: [], total: 0, error: error instanceof Error ? error.message : 'Failed to fetch governance audit logs' },
      { status: 502 },
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const res = await fetch(`${BASE}/governance/audit`, {
      method: 'POST',
      cache: 'no-store',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    if (!res.ok) {
      return NextResponse.json({ ok: false, error: text }, { status: 502 });
    }
    return NextResponse.json(JSON.parse(text));
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : 'Failed to append governance audit log' },
      { status: 502 },
    );
  }
}
