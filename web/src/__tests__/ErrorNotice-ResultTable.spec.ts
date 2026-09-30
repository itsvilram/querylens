import { render, screen } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Cell } from '@/api/types'
import ErrorNotice from '@/components/ErrorNotice.vue'
import ResultTable from '@/components/ResultTable.vue'

describe('ErrorNotice', () => {
  afterEach(() => vi.useRealTimers())

  it('is announced, and offers to try again', async () => {
    const user = userEvent.setup()
    const { emitted } = render(ErrorNotice, {
      props: { error: { code: 'query_failed', message: 'The database could not run it.' } },
    })

    expect(screen.getByRole('alert').textContent).toContain('The query failed')
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(emitted().retry).toHaveLength(1)
  })

  it('counts down Retry-After before a rate-limited question can be tried again', async () => {
    vi.useFakeTimers()
    render(ErrorNotice, {
      props: {
        error: { code: 'rate_limited', message: 'Too many.', request_id: 'abc', retry_after_s: 3 },
      },
    })
    const button = screen.getByRole('button')

    expect(button.textContent?.trim()).toBe('Try again in 3 s')
    expect(button).toHaveProperty('disabled', true)
    await vi.advanceTimersByTimeAsync(3000)

    expect(button.textContent?.trim()).toBe('Try again')
    expect(button).toHaveProperty('disabled', false)
    expect(screen.getByText('abc')).toBeTruthy() // the reference to report
  })
})

describe('ResultTable', () => {
  const columns = [
    { name: 'customer_id', type: 'int4' },
    { name: 'total', type: 'numeric' },
  ]
  const rows: Cell[][] = Array.from({ length: 60 }, (_, i) => [i + 1001, i % 2 ? 10.5 : 7.25])

  it('pages through many rows, 25 at a time', async () => {
    const user = userEvent.setup()
    render(ResultTable, { props: { columns, rows } })
    const previous = screen.getByRole('button', { name: 'Previous' })

    expect(screen.getByText('Rows 1–25 of 60')).toBeTruthy()
    expect(screen.getAllByRole('row')).toHaveLength(26) // header + 25
    expect(previous).toHaveProperty('disabled', true)

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(screen.getByText('Rows 51–60 of 60')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Next' })).toHaveProperty('disabled', true)
  })

  it('formats cells: ids plain, amounts with the same decimals, NULL visible', () => {
    render(ResultTable, {
      props: {
        columns,
        rows: [
          [1523, 10.5],
          [1524, 7.25],
          [1525, null],
        ] as Cell[][],
      },
    })

    expect(screen.getByText('1523')).toBeTruthy()
    expect(screen.getByText('10.50')).toBeTruthy() // 7.25 in the same column needs 2 decimals
    expect(screen.getByText('NULL')).toBeTruthy()
    expect(screen.queryByRole('navigation')).toBeNull() // one page: no pager
  })
})
