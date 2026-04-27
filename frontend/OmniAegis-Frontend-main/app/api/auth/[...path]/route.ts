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

async function proxyRequest(
  request: Request,
  params: { path?: string[] },
): Promise<Response> {
  const path = params.path?.join('/') ?? '';
  const targetUrl = new URL(
    `/auth/${path}`,
    `${normalizeBackendBaseUrl(BACKEND_API_BASE_URL)}/`,
  );
  targetUrl.search = new URL(request.url).search;

  const headers = new Headers(request.headers);
  headers.delete('host');
  headers.delete('content-length');

  const method = request.method.toUpperCase();
  const body = method === 'GET' || method === 'HEAD' ? undefined : await request.text();

  try {
    const upstream = await fetch(targetUrl, {
      method,
      headers,
      body,
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
        detail: 'Unable to reach the backend authentication service.',
      },
      { status: 503 },
    );
  }
}

export async function GET(request: Request, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context.params);
}

export async function POST(request: Request, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context.params);
}

export async function PUT(request: Request, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context.params);
}

export async function PATCH(request: Request, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context.params);
}

export async function DELETE(request: Request, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context.params);
}
