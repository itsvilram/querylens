import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { render, screen } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import SchemaPanel from '@/components/SchemaPanel.vue'
import SqlView from '@/components/SqlView.vue'

import { server } from './msw'

vi.mock('@/lib/highlight', () => ({
  highlightSql: async (sql: string) => `<pre class="shiki"><code>${sql}</code></pre>`,
}))

function renderPanel() {
  // A fresh cache per test, and no retry delays when the server fails.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(SchemaPanel, { global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
  return userEvent.setup()
}

describe('SchemaPanel', () => {
  it('lists the tables with their columns and keys', async () => {
    const user = renderPanel()

    await user.click(await screen.findByText('film'))

    expect(screen.getByText(/Pagila, 2 tables/)).toBeTruthy()
    expect(screen.getByText('rental_rate')).toBeTruthy()
    expect(screen.getByText('→ language.language_id')).toBeTruthy()
  })

  it('filters by table or column name', async () => {
    const user = renderPanel()
    await screen.findByText('film')

    await user.type(screen.getByRole('searchbox'), 'rental_rate')
    expect(screen.queryByText('language')).toBeNull()
    expect(screen.getByText('film')).toBeTruthy()

    await user.clear(screen.getByRole('searchbox'))
    await user.type(screen.getByRole('searchbox'), 'nothing like this')
    expect(screen.getByText(/No table or column matches/)).toBeTruthy()
  })

  it('says when the schema could not be loaded, and can try again', async () => {
    server.use(http.get('*/api/schema', () => HttpResponse.error(), { once: true }))
    const user = renderPanel()

    await user.click(await screen.findByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('film')).toBeTruthy()
  })
})

describe('SqlView', () => {
  it('copies the SQL to the clipboard and says so', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    render(SqlView, { props: { sql: 'SELECT 1' } })

    await user.click(screen.getByRole('button', { name: 'Copy' }))

    expect(writeText).toHaveBeenCalledWith('SELECT 1')
    expect(screen.getByRole('button', { name: 'Copied' })).toBeTruthy()
    expect(screen.getByText('SQL copied to the clipboard')).toBeTruthy()
  })
})
