<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, ref, useId } from 'vue'

import { fetchSchema } from '@/api/client'

// Server state: Vue Query fetches the schema once, caches it, and gives us
// loading and error states. (The chat itself is client state, in Pinia.)
const schema = useQuery({
  queryKey: ['schema'],
  queryFn: ({ signal }) => fetchSchema(signal),
  staleTime: Infinity, // the schema doesn't change while the page is open
})

const filterId = useId()
const filter = ref('')
const tables = computed(() => {
  const all = schema.data.value?.tables ?? []
  const needle = filter.value.trim().toLowerCase()
  if (!needle) return all
  return all.filter(
    (table) =>
      table.name.includes(needle) || table.columns.some((column) => column.name.includes(needle)),
  )
})
</script>

<template>
  <div class="space-y-3">
    <div>
      <h2 class="text-lg font-semibold">Schema</h2>
      <p class="text-sm text-slate-600 dark:text-slate-400">
        The tables QueryLens can read<template v-if="schema.data.value">
          ({{ schema.data.value.database }}, {{ schema.data.value.tables.length }} tables)</template
        >.
      </p>
    </div>

    <div>
      <label :for="filterId" class="sr-only">Filter tables and columns</label>
      <input
        :id="filterId"
        v-model="filter"
        type="search"
        placeholder="Filter tables or columns"
        class="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
      />
    </div>

    <div v-if="schema.isPending.value" class="space-y-2" aria-hidden="true">
      <div
        v-for="n in 6"
        :key="n"
        class="h-8 rounded bg-slate-200 motion-safe:animate-pulse dark:bg-slate-800"
      />
    </div>

    <div v-else-if="schema.isError.value" role="alert" class="text-sm">
      <p>The schema could not be loaded.</p>
      <button type="button" class="mt-2 rounded-md border px-3 py-1" @click="schema.refetch()">
        Try again
      </button>
    </div>

    <p v-else-if="!tables.length" class="text-sm text-slate-600 dark:text-slate-400">
      No table or column matches “{{ filter }}”.
    </p>

    <ul v-else class="space-y-1">
      <li v-for="table in tables" :key="table.name">
        <details class="rounded-md border border-slate-200 dark:border-slate-800">
          <summary class="flex cursor-pointer justify-between px-3 py-1.5 font-mono text-sm">
            {{ table.name }}
            <span class="text-xs text-slate-500 dark:text-slate-400">{{
              table.columns.length
            }}</span>
          </summary>
          <div class="border-t border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
            <p class="mb-2 text-slate-700 dark:text-slate-300">{{ table.description }}</p>
            <ul class="space-y-0.5 font-mono text-xs">
              <li v-for="column in table.columns" :key="column.name" class="flex flex-wrap gap-x-2">
                <span class="font-semibold">{{ column.name }}</span>
                <span class="text-slate-500 dark:text-slate-400">{{ column.type }}</span>
                <span v-if="column.primary_key" class="text-amber-700 dark:text-amber-300">PK</span>
                <span v-if="column.references" class="text-indigo-700 dark:text-indigo-300">
                  → {{ column.references }}
                </span>
              </li>
            </ul>
          </div>
        </details>
      </li>
    </ul>
  </div>
</template>
