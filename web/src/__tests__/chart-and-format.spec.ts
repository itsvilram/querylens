import { describe, expect, it } from 'vitest'

import { chartData, describeChart } from '../lib/chart'
import { columnDecimals, formatCell, formatMs } from '../lib/format'

const REVENUE = {
  columns: [
    { name: 'category', type: 'text' },
    { name: 'revenue', type: 'numeric' },
    { name: 'rentals', type: 'int8' },
  ],
  rows: [
    ['Sci-Fi', 4207.68, 1101],
    ['Music', 3071.52, 830],
    ['Drama', 3722.54, 998],
  ],
}

describe('chartData', () => {
  it('labels the x axis with the first column and makes a series of each number column', () => {
    const data = chartData(REVENUE)

    expect(data.xLabel).toBe('category')
    expect(data.labels).toEqual(['Sci-Fi', 'Music', 'Drama'])
    expect(data.series.map((s) => s.label)).toEqual(['revenue', 'rentals'])
    expect(data.series[0]?.values).toEqual([4207.68, 3071.52, 3722.54])
  })

  it('leaves out text columns after the first and turns missing numbers into gaps', () => {
    const data = chartData({
      columns: [
        { name: 'month', type: 'date' },
        { name: 'note', type: 'text' },
        { name: 'rentals', type: 'int8' },
      ],
      rows: [
        ['2024-01-01', 'x', 10],
        ['2024-02-01', 'y', null],
      ],
    })

    expect(data.series).toEqual([{ label: 'rentals', values: [10, null] }])
  })
})

describe('describeChart', () => {
  it('says what the chart shows, with its highest and lowest points', () => {
    expect(describeChart('bar', chartData(REVENUE))).toBe(
      'Bar chart of revenue by category, 3 bars. Highest: Sci-Fi (4,207.68). ' +
        'Lowest: Music (3,071.52). Also shows rentals.',
    )
  })
})

describe('formatCell', () => {
  it('formats numbers, but not ids and years', () => {
    expect(formatCell(1234567.891, 'revenue')).toBe('1,234,567.89')
    expect(formatCell(1523, 'customer_id')).toBe('1523')
    expect(formatCell(2024, 'year')).toBe('2024')
  })

  it('shows NULL, booleans, arrays and timestamps readably', () => {
    expect(formatCell(null)).toBe('NULL')
    expect(formatCell(true)).toBe('true')
    expect(formatCell(['a', 'b'])).toBe('{a, b}')
    expect(formatCell('2024-05-01T10:15:00+00:00')).toBe('2024-05-01 10:15')
    expect(formatCell('2024-05-01')).toBe('2024-05-01')
  })

  it('gives a column one number of decimals, so its numbers line up', () => {
    const decimals = columnDecimals([2159.14, 1837.7, 2000, null, 'n/a'])

    expect(decimals).toBe(2)
    expect(formatCell(1837.7, 'revenue', decimals)).toBe('1,837.70')
    expect(formatCell(2000, 'revenue', decimals)).toBe('2,000.00')
    expect(columnDecimals([1, 2, 3])).toBe(0)
    expect(columnDecimals([0.123456])).toBe(2) // never more than 2
  })

  it('formats durations', () => {
    expect(formatMs(4.9)).toBe('5 ms')
    expect(formatMs(1387)).toBe('1.4 s')
  })
})
