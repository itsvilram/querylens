import type { Answer } from '@/api/types'

import { formatCell, NUMBER_TYPES } from './format'

export interface Series {
  label: string
  values: Array<number | null>
}

export interface ChartData {
  xLabel: string
  labels: string[]
  series: Series[]
}

/** The first column labels the x axis; every number column after it is one series. */
export function chartData(answer: Pick<Answer, 'columns' | 'rows'>): ChartData {
  const [first, ...rest] = answer.columns
  const measures = rest
    .map((column, i) => ({ column, index: i + 1 }))
    .filter(({ column }) => NUMBER_TYPES.has(column.type))
  return {
    xLabel: first?.name ?? '',
    labels: answer.rows.map((row) => formatCell(row[0] ?? null, first?.name)),
    series: measures.map(({ column, index }) => ({
      label: column.name,
      values: answer.rows.map((row) => {
        const value = row[index]
        return typeof value === 'number' ? value : null
      }),
    })),
  }
}

/** One or two sentences for screen readers: a canvas chart is only pixels. */
export function describeChart(kind: 'line' | 'bar', data: ChartData): string {
  const main = data.series[0]
  if (!main) return 'There is nothing to chart.'
  const count = data.labels.length
  let text =
    `${kind === 'line' ? 'Line' : 'Bar'} chart of ${main.label} by ${data.xLabel}, ` +
    `${count} ${kind === 'line' ? 'points' : 'bars'}.`

  const points = main.values.flatMap((value, i) => (value === null ? [] : [{ value, i }]))
  if (points.length > 1) {
    const highest = points.reduce((a, b) => (b.value > a.value ? b : a))
    const lowest = points.reduce((a, b) => (b.value < a.value ? b : a))
    const show = (p: { value: number; i: number }) =>
      `${data.labels[p.i]} (${formatCell(p.value, main.label)})`
    text += ` Highest: ${show(highest)}. Lowest: ${show(lowest)}.`
  }
  if (data.series.length > 1) {
    text += ` Also shows ${data.series
      .slice(1)
      .map((s) => s.label)
      .join(', ')}.`
  }
  return text
}
