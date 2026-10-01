<script setup lang="ts">
import { computed, defineAsyncComponent, h, ref } from 'vue'

import type { Answer, Chart } from '@/api/types'
import { formatCell, formatMs } from '@/lib/format'

import ResultTable from './ResultTable.vue'
import SqlView from './SqlView.vue'

// Chart.js is only downloaded when a chart is shown.
// Until it has loaded, an empty box of the chart's exact height holds its place,
// so the page doesn't jump when the chart appears.
const ResultChart = defineAsyncComponent({
  loader: () => import('./ResultChart.vue'),
  loadingComponent: { render: () => h('div', { class: 'h-72 w-full', 'aria-hidden': 'true' }) },
  delay: 0,
})

const props = defineProps<{ answer: Answer }>()

const CHART_NAMES: Record<Chart, string> = {
  line: 'Line',
  bar: 'Bar',
  number: 'Number',
  table: 'No chart',
}

// The server picks a chart that fits the columns; the user can switch to any other that fits.
const chart = ref<Chart>(props.answer.chart)
const rewritten = computed(
  () =>
    props.answer.standalone_question.trim().toLowerCase() !==
    props.answer.question.trim().toLowerCase(),
)
const fromCache = computed(() => props.answer.cache === 'hit' || props.answer.cache === 'coalesced')
const rowCount = computed(() => props.answer.rows.length)
const bigNumber = computed(() =>
  formatCell(props.answer.rows[0]?.[0] ?? null, props.answer.columns[0]?.name),
)
</script>

<template>
  <div
    class="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900/40"
  >
    <p v-if="rewritten" class="text-sm text-slate-600 dark:text-slate-400">
      Understood as: <q class="italic">{{ answer.standalone_question }}</q>
    </p>
    <p>{{ answer.explanation }}</p>

    <template v-if="answer.sql">
      <div
        v-if="answer.chart_options.length > 1"
        role="group"
        aria-label="Show the result as"
        class="flex flex-wrap gap-1"
      >
        <button
          v-for="option in answer.chart_options"
          :key="option"
          type="button"
          :aria-pressed="chart === option"
          class="rounded-md border px-3 py-1 text-sm"
          :class="
            chart === option
              ? 'border-indigo-600 bg-indigo-600 text-white'
              : 'border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800'
          "
          @click="chart = option"
        >
          {{ CHART_NAMES[option] }}
        </button>
      </div>

      <div
        v-if="chart === 'number'"
        class="rounded-lg bg-slate-50 p-6 text-center dark:bg-slate-900"
      >
        <p class="text-4xl font-bold tabular-nums">{{ bigNumber }}</p>
        <p class="mt-1 text-sm text-slate-600 dark:text-slate-400">{{ answer.columns[0]?.name }}</p>
      </div>
      <ResultChart v-else-if="chart === 'line' || chart === 'bar'" :answer="answer" :kind="chart" />

      <ResultTable :columns="answer.columns" :rows="answer.rows" />
      <p v-if="answer.truncated" class="text-sm text-amber-700 dark:text-amber-300">
        Showing the first {{ rowCount.toLocaleString('en') }} rows only. Ask a narrower question to
        see the rest.
      </p>

      <details open>
        <summary class="cursor-pointer text-sm font-medium">SQL</summary>
        <div class="mt-2">
          <SqlView :sql="answer.sql" />
        </div>
      </details>
    </template>
    <p v-else class="text-sm text-slate-600 dark:text-slate-400">
      No SQL was run for this question.
    </p>

    <p class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-600 dark:text-slate-400">
      <span
        v-if="fromCache"
        class="rounded bg-emerald-100 px-1.5 font-medium text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200"
      >
        From cache
      </span>
      <span v-if="answer.sql">
        {{ rowCount.toLocaleString('en') }} {{ rowCount === 1 ? 'row' : 'rows' }}
      </span>
      <span>{{ formatMs(answer.elapsed_ms) }}</span>
      <span v-if="answer.sql && !fromCache">database {{ formatMs(answer.db_ms) }}</span>
      <span>{{ answer.tokens.toLocaleString('en') }} tokens</span>
      <span v-if="answer.retries"
        >fixed after {{ answer.retries }} failed {{ answer.retries === 1 ? 'try' : 'tries' }}</span
      >
      <span>{{ answer.model }}</span>
    </p>
  </div>
</template>
