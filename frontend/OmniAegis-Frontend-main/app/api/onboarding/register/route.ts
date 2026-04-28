import { NextResponse } from 'next/server';

const BACKEND_API_BASE_URL =
  process.env.API_BASE_URL ||
  process.env.VITE_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  'http://localhost:8000';

function normalizeBackendBaseUrl(baseUrl: string): string {
  try {
    const url = new URL(baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`);
    return url.toString().replace(/\/$/, '');
  } catch {
    return 'http://localhost:8000';
  }
}

export async function POST(request: Request): Promise<Response> {
  const targetUrl = new URL('/onboarding/register', `${normalizeBackendBaseUrl(BACKEND_API_BASE_URL)}/`);
  const headers = new Headers(request.headers);
  headers.delete('host');
  headers.delete('content-length');

  try {
    const upstream = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body: await request.arrayBuffer(),
      redirect: 'manual',
    });

    return new Response(await upstream.arrayBuffer(), {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: upstream.headers,
    });
  } catch {
    return NextResponse.json(
      {
        detail: 'Unable to reach the backend onboarding service.',
      },
      { status: 503 },
    );
  }
}
