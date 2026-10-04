/**
 * Thin fetch wrapper for the AgriSense API: JWT auth with one refresh on 401, JSON and multipart
 * bodies, and errors that carry the API's {detail, code}.
 */
import { getTokens, setTokens } from './tokens';
import type { ApiErrorBody } from './types';

export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://10.0.2.2:8000').replace(/\/$/, '') + '/api/v1';

// Sending a report also runs the AI check on the server (up to ~45 s while there is no background worker).
const TIMEOUT_MS = 60_000;
// Photo and audio uploads on rural mobile data can take well over 30 s.
const UPLOAD_TIMEOUT_MS = 120_000;

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ApiErrorBody | null,
    public cause?: string, // for status 0: why the request never got an answer (network error, timeout)
  ) {
    super(ApiError.describe(body) ?? cause ?? `Request failed (${status})`);
  }

  /** True when the request never got an answer (no network, timeout). */
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
  if (body instanceof FormData) return sendMultipart(path, method, body, headers);
  let payload: BodyInit | undefined;
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await fetch(API_URL + path, { method, headers, body: payload, signal: controller.signal });
  } catch (error) {
    const cause = controller.signal.aborted ? `No answer after ${TIMEOUT_MS / 1000} s` : String((error as Error)?.message ?? error);
    throw new ApiError(0, null, cause);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Multipart uploads go through XMLHttpRequest: Expo replaces the global fetch with expo/fetch, which
 * rejects React Native's {uri, name, type} file parts ("Unsupported FormData implementation").
 * React Native's XHR reads those files natively.
 */
function sendMultipart(path: string, method: string, body: FormData, headers: Record<string, string>): Promise<Response> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, API_URL + path);
    for (const [key, value] of Object.entries(headers)) xhr.setRequestHeader(key, value);
    xhr.timeout = UPLOAD_TIMEOUT_MS;
    xhr.onload = () => resolve(new Response(xhr.responseText || null, { status: xhr.status }));
    xhr.onerror = () => reject(new ApiError(0, null, 'Network request failed'));
    xhr.ontimeout = () => reject(new ApiError(0, null, `No answer after ${UPLOAD_TIMEOUT_MS / 1000} s`));
    xhr.send(body);
  });
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
