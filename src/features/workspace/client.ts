import type { OperationRequest, SharedApiError } from './types';

// Only the public endpoint belongs in the client bundle. Credentials never do.
export const apiUrl = (process.env.EXPO_PUBLIC_API_URL ?? '').trim().replace(/\/$/, '');
export const sharedMode = apiUrl.length > 0;

interface StateWithToken {
  session: { accessToken: string | null };
}

export function workspaceError(error: unknown): string {
  if (typeof error === 'object' && error !== null) {
    if (
      'data' in error &&
      typeof error.data === 'object' &&
      error.data !== null &&
      'message' in error.data &&
      typeof error.data.message === 'string'
    )
      return error.data.message;
    if ('message' in error && typeof error.message === 'string') return error.message;
  }
  return 'The request could not be completed. Try again.';
}

export async function sharedFetch(path: string, token: string, body?: object): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25_000);
  try {
    return await fetch(`${apiUrl}${path}`, {
      method: body ? 'POST' : 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

export async function sharedOperation(
  request: object,
  state: unknown,
): Promise<{ data: unknown } | { error: SharedApiError }> {
  const token = (state as StateWithToken).session.accessToken;
  if (!sharedMode || !token)
    return { error: { status: 401, data: { message: 'Sign in to the shared service.' } } };
  try {
    const response = await sharedFetch('/api/operations', token, request);
    const data: unknown = await response.json();
    if (!response.ok)
      return { error: { status: response.status, data: { message: workspaceError(data) } } };
    return { data };
  } catch {
    return {
      error: {
        status: 503,
        data: { message: 'Cannot reach the shared service. Check your connection and retry.' },
      },
    };
  }
}

export async function exportReport(
  id: string,
  format: 'html' | 'csv',
  token: string,
): Promise<string> {
  const response = await sharedFetch(
    `/api/reports/${encodeURIComponent(id)}?format=${format}`,
    token,
  );
  if (!response.ok) throw new Error(workspaceError(await response.json()));
  return response.text();
}

export const operation = (name: string, input?: object): OperationRequest => ({
  operation: name,
  ...(input ? { input } : {}),
});
