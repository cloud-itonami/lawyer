import { json, type RequestEvent } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

type Env = Record<string, unknown> & { AGENTGATEWAY_MCP_ROUTER_URL?: string; MCP_ROUTER_URL?: string };

function envOf(event: RequestEvent): Env { return ((event.platform as { env?: Env } | undefined)?.env ?? {}) as Env; }

function mcpRouterUrl(env: Env): string | null {
  const configured = typeof env.AGENTGATEWAY_MCP_ROUTER_URL === 'string' && env.AGENTGATEWAY_MCP_ROUTER_URL.trim()
    ? env.AGENTGATEWAY_MCP_ROUTER_URL
    : typeof env.MCP_ROUTER_URL === 'string' && env.MCP_ROUTER_URL.trim()
      ? env.MCP_ROUTER_URL
      : null;
  return configured?.replace(/\/+$/, '') ?? null;
}

function noStore(body: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers);
  headers.set('cache-control', 'no-store');
  return json(body, { ...init, headers });
}

/**
 * Forward one XRPC call to the MCP router as a `tools/call`.
 *
 * Shared by both handlers because the only thing that differs between a query
 * and a procedure is where the arguments come from: the query string for GET,
 * the JSON body for POST. Everything downstream — envelope, header stamping,
 * error unwrapping — is the same call.
 */
async function forward(event: RequestEvent, input: unknown): Promise<Response> {
  const nsid = event.params.path;
  if (!nsid) return noStore({ error: 'Missing XRPC method' }, { status: 400 });
  const routerUrl = mcpRouterUrl(envOf(event));
  if (!routerUrl) return noStore({ error: 'MCP router not configured' }, { status: 503 });
  const headers = new Headers(event.request.headers);
  headers.delete('host');
  headers.set('content-type', 'application/json');
  headers.set('x-gftd-bff', 'sveltekit-edge-bff');
  headers.set('x-gftd-xrpc-method', nsid);
  const upstream = await fetch(routerUrl, {
    method: 'POST',
    headers,
    body: JSON.stringify({ jsonrpc: '2.0', id: crypto.randomUUID(), method: 'tools/call', params: { name: nsid, arguments: input } })
  });
  const upstreamText = await upstream.text();
  let payload: unknown = upstreamText;
  try { payload = upstreamText ? JSON.parse(upstreamText) : null; } catch { /* Preserve text payload. */ }
  if (!upstream.ok) return noStore({ error: 'MCP router request failed', upstream: payload }, { status: upstream.status });
  if (payload && typeof payload === 'object' && 'error' in payload) {
    const error = (payload as { error?: { message?: string } }).error;
    return noStore({ error: error?.message ?? 'MCP router returned an error', upstream: payload }, { status: 502 });
  }
  const result = payload && typeof payload === 'object' && 'result' in payload ? (payload as { result?: unknown }).result : payload;
  const structured = result && typeof result === 'object' && 'structuredContent' in result ? (result as { structuredContent?: unknown }).structuredContent : result;
  return noStore(structured ?? {});
}

/**
 * XRPC queries. Every lexicon in `lexicons/lawyer/` whose `defs.main.type` is
 * `query` is called this way — GET with the parameters in the query string —
 * and the views do exactly that (`fetch(url)` with no options).
 *
 * Without this export SvelteKit answers 405 before any of the code above runs.
 * The views wrap their call in a `catch` that substitutes demo data, so the
 * page then renders fabricated matters and grants with nothing on screen to
 * say so. `test/xrpc_contract_test.cljs` pins the lexicon-type -> method
 * binding for that reason.
 */
export const GET: RequestHandler = async (event) =>
  forward(event, Object.fromEntries(event.url.searchParams));

/** XRPC procedures: arguments arrive as a JSON body. */
export const POST: RequestHandler = async (event) =>
  forward(event, await event.request.json().catch(() => ({})));

export const OPTIONS: RequestHandler = async () => new Response(null, {
  status: 204,
  headers: {
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
    'access-control-allow-headers': 'content-type,authorization',
    'access-control-max-age': '86400'
  }
});
