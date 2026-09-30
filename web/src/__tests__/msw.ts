// Mock Service Worker for tests: fetch() calls to /api/* are answered here, so
// components and composables run their real network code without a server.
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

import type { Answer, Schema } from '@/api/types'

export const SCHEMA: Schema = {
  database: 'Pagila',
  tables: [
    {
      name: 'film',
      description: 'The film catalogue: title, rental_rate, rating.',
      columns: [
        { name: 'film_id', type: 'integer', primary_key: true, references: null },
        { name: 'title', type: 'text', primary_key: false, references: null },
        { name: 'rental_rate', type: 'numeric(4,2)', primary_key: false, references: null },
        {
          name: 'language_id',
          type: 'smallint',
          primary_key: false,
          references: 'language.language_id',
        },
      ],
    },
    {
      name: 'language',
      description: 'Film languages.',
      columns: [
        { name: 'language_id', type: 'integer', primary_key: true, references: null },
        { name: 'name', type: 'character(20)', primary_key: false, references: null },
      ],
    },
  ],
}

export const ANSWER: Answer = {
  question: 'How many films are there?',
  standalone_question: 'How many films are there?',
  sql: 'SELECT\n  COUNT(*) AS films\nFROM film\nLIMIT 1001',
  explanation: 'Counts all films.',
  chart: 'number',
  chart_options: ['number', 'table'],
  columns: [{ name: 'films', type: 'int8' }],
  rows: [[1000]],
  truncated: false,
  model: 'fake',
  retries: 0,
  db_ms: 3.2,
  cache: 'miss',
  tokens: 900,
  elapsed_ms: 120,
}

export const server = setupServer(
  http.get('*/api/health', () => HttpResponse.json({ status: 'ok', llm_mode: 'real' })),
  http.get('*/api/schema', () => HttpResponse.json(SCHEMA)),
)

/** One server-sent event, as the API writes it. */
export function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

/** A text/event-stream response. `open: true` never ends it (for cancel tests). */
export function streamed(parts: string[], options: { open?: boolean } = {}): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const part of parts) controller.enqueue(encoder.encode(part))
      if (!options.open) controller.close()
    },
  })
  return new HttpResponse(body, { headers: { 'Content-Type': 'text/event-stream' } })
}
