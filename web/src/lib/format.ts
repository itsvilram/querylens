import type { Cell, Stage } from '@/api/types'

export const STAGE_LABELS: Record<Stage, string> = {
  rewrite: 'Understanding your follow-up',
  wait: 'The same question is already running: waiting for its answer',
  retrieve: 'Finding the relevant tables',
  generate: 'Writing SQL',
  correct: 'The SQL failed, fixing it',
  execute: 'Running the query',
}

export const NUMBER_TYPES = new Set(['int2', 'int4', 'int8', 'numeric', 'float4', 'float8'])
export const TIME_TYPES = new Set(['date', 'timestamp', 'timestamptz'])

const MAX_DECIMALS = 2
const numberFormats = new Map<string, Intl.NumberFormat>()

function numberFormat(grouping: boolean, decimals: number): Intl.NumberFormat {
  const key = `${grouping}:${decimals}`
  let format = numberFormats.get(key)
  if (!format) {
    format = new Intl.NumberFormat('en', {
      useGrouping: grouping,
      minimumFractionDigits: decimals,
      maximumFractionDigits: Math.max(decimals, MAX_DECIMALS),
    })
    numberFormats.set(key, format)
  }
  return format
}

/** Ids and years read wrong with thousands separators ("customer 1,523", "2,024"). */
function isIdLike(columnName: string): boolean {
  const name = columnName.toLowerCase()
  return name === 'id' || name.endsWith('_id') || name === 'year' || name.endsWith('_year')
}

/**
 * How many decimals a column's numbers need (at most 2), so they line up:
 * 1,837.70 under 2,159.14, not 1,837.7.
 */
export function columnDecimals(values: Cell[]): number {
  let decimals = 0
  for (const value of values) {
    if (typeof value !== 'number' || Number.isInteger(value)) continue
    const fraction = String(value).split('.')[1] ?? ''
    decimals = Math.max(decimals, Math.min(fraction.length, MAX_DECIMALS))
  }
  return decimals
}

/** One table cell as text. `decimals`: a fixed number of decimals for numbers (see columnDecimals). */
export function formatCell(value: Cell, columnName = '', decimals = 0): string {
  if (value === null) return 'NULL'
  if (typeof value === 'number') return numberFormat(!isIdLike(columnName), decimals).format(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  // Nested arrays (multi-dimensional Postgres arrays) are shown the same way.
  if (Array.isArray(value)) return `{${value.map((item) => formatCell(item as Cell)).join(', ')}}`
  // ISO timestamps from the API: "2024-05-01T10:15:00+00:00" -> "2024-05-01 10:15"
  const timestamp = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(:\d{2}(\.\d+)?)?([+-]\d{2}:\d{2}|Z)?$/.exec(
    value,
  )
  return timestamp ? `${timestamp[1]} ${timestamp[2]}` : value
}

export function formatMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`
}
