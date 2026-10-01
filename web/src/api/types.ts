// The API's JSON shapes. Source of truth: api/app/api/ask.py, schema.py, stats.py.

export type Chart = 'line' | 'bar' | 'number' | 'table'

export type Stage = 'rewrite' | 'wait' | 'retrieve' | 'generate' | 'correct' | 'execute'

export type CacheStatus = 'hit' | 'miss' | 'coalesced' | 'off'

export type Scalar = string | number | boolean | null

/** One value in a result row: a Postgres array comes as a JSON array. */
export type Cell = Scalar | Scalar[]

export interface Column {
  name: string
  type: string // Postgres type, e.g. "int8", "numeric", "date", "text"
}

export interface Answer {
  question: string
  standalone_question: string // how a follow-up was understood
  sql: string // "" when the model declined to write SQL
  explanation: string
  chart: Chart
  chart_options: Chart[] // charts that fit these rows; always includes "table"
  columns: Column[]
  rows: Cell[][]
  truncated: boolean // more rows existed than the server's row cap
  model: string
  retries: number
  db_ms: number
  cache: CacheStatus
  tokens: number
  model_id: string // which of the server's models answered ("gemini", "groq", ...)
  elapsed_ms: number
}

export interface ApiErrorBody {
  code: string // e.g. "rate_limited", "unsafe_sql", "llm_busy"
  message: string // one safe sentence, fine to show as is
  request_id?: string
  retry_after_s?: number | null
}

export interface SchemaColumn {
  name: string
  type: string
  primary_key: boolean
  references: string | null // "language.language_id"
}

export interface SchemaTable {
  name: string
  description: string
  columns: SchemaColumn[]
}

export interface Schema {
  database: string
  tables: SchemaTable[]
}
