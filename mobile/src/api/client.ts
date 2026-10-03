/**
 * Thin fetch wrapper for the AgriSense API: JWT auth with one refresh on 401, JSON and multipart
 * bodies, and errors that carry the API's {detail, code}.
 */
import { getTokens, setTokens } from './tokens';
import type { ApiErrorBody } from './types';

export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://10.0.2.2:8000').replace(/\/$/, '') + '/api/v1';

const TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ApiErrorBody | null,
  ) {
    super(ApiError.describe(body) ?? `Request failed (${status})`);
  }

  /** True when the request never reached the server (no network, timeout). */
  get offline(): boolean {
    return this.status === 0;
  }

  get code(): string | undefined {
    return typeof this.body?.code === 'string' ? this.body.code : undefined;
  }

  private static describe(body: ApiErrorBody | null): string | undefined {
    if (!body) return undefined;
    if (typeof body.detail === 'string') return body.detail;
    // DRF field errors: {"field": ["message"]}
    for (const value of Object.values(body)) {
      if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
      if (typeof value === 'string') return value;
    }
    return undefined;
  }
}

let onSignedOut: (() => void) | null = null;
export function setSignedOutHandler(handler: () => void) {
  onSignedOut = handler;
}

type Body = Record<string, unknown> | FormData | undefined;

async function send(path: string, method: string, body: Body, access: string | null): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (access) headers.Authorization = `Bearer ${access}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await fetch(API_URL + path, { method, headers, body: payload, signal: controller.signal });
  } catch {
    throw new ApiError(0, null);
  } finally {
    clearTimeout(timer);
  }
}

async function refreshAccess(): Promise<string | null> {
  const tokens = await getTokens();
  if (!tokens) return null;
  const response = await send('/auth/token/refresh/', 'POST', { refresh: tokens.refresh }, null);
  if (!response.ok) {
    await setTokens(null);
    onSignedOut?.();
    return null;
  }
  const data = (await response.json()) as { access: string; refresh?: string };
  await setTokens({ access: data.access, refresh: data.refresh ?? tokens.refresh });
  return data.access;
}

export async function api<T>(path: string, options: { method?: string; body?: Body; auth?: boolean } = {}): Promise<T> {
  const { method = 'GET', body, auth = true } = options;
  let access = auth ? (await getTokens())?.access ?? null : null;
  let response = await send(path, method, body, access);
  if (response.status === 401 && auth) {
    access = await refreshAccess();
    if (access) response = await send(path, method, body, access);
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!response.ok) throw new ApiError(response.status, (data ?? null) as ApiErrorBody | null);
  return data as T;
}

/** A local file (photo, audio) as a multipart part. */
export function filePart(uri: string, name: string, type: string): Blob {
  // React Native's FormData accepts {uri, name, type}; the cast keeps TypeScript's DOM types happy.
  return { uri, name, type } as unknown as Blob;
}
