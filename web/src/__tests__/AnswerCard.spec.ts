import { render, screen } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'

import type { Answer } from '@/api/types'
import AnswerCard from '@/components/AnswerCard.vue'

import { ANSWER } from './msw'

// jsdom has no canvas, so stand in for the Chart.js component.
vi.mock('@/components/ResultChart.vue', () => ({
  __esModule: true, // so Vue's async-component loader takes `default`, as with a real .vue file
  default: defineComponent({
    props: { answer: Object, kind: String },
    setup: (props) => () => h('div', { 'data-testid': 'chart' }, `${props.kind} chart`),
  }),
}))
// Skip loading Shiki: the plain SQL is what matters here.
vi.mock('@/lib/highlight', () => ({
  highlightSql: async (sql: string) => `<pre class="shiki"><code>${sql}</code></pre>`,
}))

const REVENUE: Answer = {
  ...ANSWER,
  question: 'Only for store 2',
  standalone_question: 'Which film categories made the most money in 2024 at store 2?',
  sql: 'SELECT c.name AS category, SUM(p.amount) AS revenue FROM ...',
  explanation: 'Adds up 2024 payments per film category at store 2.',
  chart: 'bar',
  chart_options: ['bar', 'table'],
  columns: [
    { name: 'category', type: 'text' },
    { name: 'revenue', type: 'numeric' },
  ],
  rows: [
    ['Action', 2159.14],
    ['Foreign', 2079.08],
  ],
}

describe('AnswerCard', () => {
  it('shows how a follow-up was understood, the chart, the table and the SQL', async () => {
    render(AnswerCard, { props: { answer: REVENUE } })

    expect(screen.getByText(/Understood as/).textContent).toContain('at store 2?')
    expect(await screen.findByTestId('chart')).toHaveProperty('textContent', 'bar chart')
    expect(screen.getByRole('table')).toBeTruthy()
    expect(screen.getByText('2,159.14')).toBeTruthy()
    expect((await screen.findByText(/SELECT c.name/)).tagName).toBe('CODE')
  })

  it('does not repeat a question that needed no rewrite', () => {
    render(AnswerCard, { props: { answer: ANSWER } })

    expect(screen.queryByText(/Understood as/)).toBeNull()
  })

  it('switches between the charts that fit, and the table stays', async () => {
    const user = userEvent.setup()
    render(AnswerCard, { props: { answer: REVENUE } })
    const bar = screen.getByRole('button', { name: 'Bar' })
    const none = screen.getByRole('button', { name: 'No chart' })

    expect(bar.getAttribute('aria-pressed')).toBe('true')
    await user.click(none)

    expect(none.getAttribute('aria-pressed')).toBe('true')
    expect(screen.queryByTestId('chart')).toBeNull()
    expect(screen.getByRole('table')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Line' })).toBeNull() // doesn't fit these rows
  })

  it('shows a single value as a big number', () => {
    render(AnswerCard, { props: { answer: ANSWER } })

    expect(screen.getAllByText('1,000')[0]?.className).toContain('text-4xl')
  })

  it('says no SQL was run when the model declined', () => {
    const declined = { ...ANSWER, sql: '', columns: [], rows: [], chart: 'table' as const }
    render(AnswerCard, { props: { answer: { ...declined, chart_options: ['table' as const] } } })

    expect(screen.getByText('No SQL was run for this question.')).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('marks answers that came from the cache', () => {
    render(AnswerCard, { props: { answer: { ...ANSWER, cache: 'hit', tokens: 0 } } })

    expect(screen.getByText('From cache')).toBeTruthy()
    expect(screen.getByText('0 tokens')).toBeTruthy()
  })

  it('warns when the rows were cut off at the row cap', () => {
    render(AnswerCard, { props: { answer: { ...REVENUE, truncated: true } } })

    expect(screen.getByText(/Showing the first 2 rows only/)).toBeTruthy()
  })
})
