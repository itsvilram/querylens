import type { ApiErrorBody, Schema } from './types'

/** An HTTP error from the API, already turned into a safe message. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiErrorBody,
  ) {
    super(body.message)
  }
}

const FALLBACK_MESSAGES: Record<number, string> = {
  422: 'The question could not be sent. It must be 1 to 500 characters.',
  429: 'Too many questions in a short time. Please wait a moment.',
}

/** Our API sends {"error": {code, message, request_id}}; anything else gets a plain message. */
export async function toApiError(response: Response): Promise<ApiError> {
  const retryAfter = Number(response.headers.get('Retry-After')) || null
  const requestId = response.headers.get('X-Request-ID') ?? undefined
  try {
    const body = (await response.json()) as { error?: ApiErrorBody }
    if (body.error?.code) {
      return new ApiError(response.status, { ...body.error, retry_after_s: retryAfter })
    }
  } catch {
    // not JSON (e.g. a proxy's HTML error page): use the fallback below
  }
  return new ApiError(response.status, {
    code: response.status === 429 ? 'rate_limited' : `http_${response.status}`,
    message: FALLBACK_MESSAGES[response.status] ?? 'The server could not answer. Please try again.',
    request_id: requestId,
    retry_after_s: retryAfter,
  })
}

export interface ModelInfo {
  id: string // what to send as "model" with a question
  label: string
}

export interface Health {
  status: 'ok'
  llm_mode: 'fake' | 'real' // fake: no AI key on the server, only the demo questions work
  demo: boolean // the public demo: tell visitors where their questions go
  models: ModelInfo[] // the models a visitor can pick, the default first
  default_model: string | null
}

export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch('/api/health', { signal })
  if (!response.ok) throw await toApiError(response)
  return (await response.json()) as Health
}

export async function fetchSchema(signal?: AbortSignal): Promise<Schema> {
  const response = await fetch('/api/schema', { signal })
  if (!response.ok) throw await toApiError(response)
  return (await response.json()) as Schema
}
