import { useQuery } from '@tanstack/vue-query'

import { fetchHealth } from '@/api/client'

/** How the server runs (fake model? public demo?). Fetched once; Vue Query shares it. */
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => fetchHealth(signal),
    staleTime: Infinity,
  })
}
