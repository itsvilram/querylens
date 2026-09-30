<script setup lang="ts">
import {
  createPaginatedRowModel,
  rowPaginationFeature,
  tableFeatures,
  useTable,
} from '@tanstack/vue-table'
import { computed } from 'vue'

import type { Cell, Column } from '@/api/types'
import { columnDecimals, formatCell, NUMBER_TYPES } from '@/lib/format'

const props = defineProps<{ columns: Column[]; rows: Cell[][] }>()

const PAGE_SIZE = 25

// TanStack Table is headless: it pages the rows, the markup below is ours.
const features = tableFeatures({
  rowPaginationFeature,
  paginatedRowModel: createPaginatedRowModel(),
})
// Rows are arrays, so each column reads its value by position. Column names
// can repeat (two "id" columns), so the position is also the column id.
const columns = props.columns.map((column, index) => ({
  id: String(index),
  header: column.name,
  accessorFn: (row: Cell[]) => row[index] ?? null,
}))
const data = computed(() => props.rows)
const table = useTable({
  features,
  columns,
  data,
  initialState: { pagination: { pageIndex: 0, pageSize: PAGE_SIZE } },
})

const page = computed(() => table.atoms.pagination.get())
const firstRow = computed(() => page.value.pageIndex * page.value.pageSize + 1)
const lastRow = computed(() =>
  Math.min(props.rows.length, (page.value.pageIndex + 1) * page.value.pageSize),
)
const pageSummary = computed(
  () => `Query result, rows ${firstRow.value} to ${lastRow.value} of ${props.rows.length}`,
)

// Same number of decimals down each column, worked out once over all rows (not just this page).
const decimals = computed(() =>
  props.columns.map((_, index) => columnDecimals(props.rows.map((row) => row[index] ?? null))),
)

function column(id: string): Column {
  return props.columns[Number(id)]!
}
function isNumber(id: string): boolean {
  return NUMBER_TYPES.has(column(id).type)
}
function show(value: unknown, id: string): string {
  return formatCell(value as Cell, column(id).name, decimals.value[Number(id)])
}
</script>

<template>
  <div>
    <div
      class="max-h-[28rem] overflow-auto rounded-lg border border-slate-200 dark:border-slate-800"
    >
      <table class="w-full border-collapse text-sm">
        <caption class="sr-only">
          {{
            pageSummary
          }}
        </caption>
        <thead class="sticky top-0 bg-slate-100 dark:bg-slate-900">
          <tr>
            <th
              v-for="header in table.getHeaderGroups()[0]?.headers ?? []"
              :key="header.id"
              scope="col"
              class="px-3 py-2 font-semibold whitespace-nowrap"
              :class="isNumber(header.column.id) ? 'text-right' : 'text-left'"
            >
              {{ column(header.column.id).name }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in table.getRowModel().rows"
            :key="row.id"
            class="border-t border-slate-200 odd:bg-white even:bg-slate-50 dark:border-slate-800 dark:odd:bg-slate-950 dark:even:bg-slate-900/50"
          >
            <td
              v-for="cell in row.getAllCells()"
              :key="cell.id"
              class="px-3 py-1.5 whitespace-nowrap"
              :class="[
                isNumber(cell.column.id) ? 'text-right tabular-nums' : 'text-left',
                cell.getValue() === null ? 'text-slate-500 italic dark:text-slate-400' : '',
              ]"
            >
              {{ show(cell.getValue(), cell.column.id) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <nav
      v-if="table.getPageCount() > 1"
      class="mt-2 flex items-center justify-between gap-2 text-sm"
      aria-label="Result pages"
    >
      <span class="text-slate-600 dark:text-slate-400">
        Rows {{ firstRow }}–{{ lastRow }} of {{ rows.length }}
      </span>
      <span class="flex gap-2">
        <button
          type="button"
          class="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-50 dark:border-slate-700"
          :disabled="!table.getCanPreviousPage()"
          @click="table.previousPage()"
        >
          Previous
        </button>
        <button
          type="button"
          class="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-50 dark:border-slate-700"
          :disabled="!table.getCanNextPage()"
          @click="table.nextPage()"
        >
          Next
        </button>
      </span>
    </nav>
  </div>
</template>
