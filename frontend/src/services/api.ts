// Tiny fetch wrapper for the FastAPI backend.
// Base URL: VITE_API_BASE_URL (see .env.example), default http://localhost:8000.
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function detailToMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{ loc: [...], msg: '...' }]
    return detail.map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d))).join('; ')
  }
  return fallback
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, `Can’t reach the backend at ${BASE_URL}. Is it running?`)
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const data = await response.json()
      message = detailToMessage(data?.detail, message)
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, message)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  delete: <T = void>(path: string) => request<T>('DELETE', path),
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : 'Something went wrong'
}
