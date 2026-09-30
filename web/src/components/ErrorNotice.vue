<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'

import type { ApiErrorBody } from '@/api/types'

const props = defineProps<{ error: ApiErrorBody }>()
const emit = defineEmits<{ retry: [] }>()

const TITLES: Record<string, string> = {
  rate_limited: 'Slow down a little',
  daily_budget_used: "Today's AI budget is used up",
  llm_busy: 'The AI service is busy',
  llm_unavailable: 'The AI service is not available',
  llm_bad_answer: 'The AI sent an unreadable answer',
  unsafe_sql: 'Blocked by a safety check',
  query_timeout: 'The query took too long',
  query_failed: 'The query failed',
  network_error: 'Connection problem',
  connection_lost: 'Connection problem',
}
const title = computed(() => TITLES[props.error.code] ?? 'Something went wrong')
const rateLimited = computed(() => props.error.code === 'rate_limited')

// Count down Retry-After, so "Try again" only works once the server will accept it.
const secondsLeft = ref(props.error.retry_after_s ?? 0)
const timer = secondsLeft.value > 0 ? setInterval(tick, 1000) : undefined
function tick() {
  secondsLeft.value = Math.max(0, secondsLeft.value - 1)
  if (secondsLeft.value === 0) clearInterval(timer)
}
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div
    role="alert"
    class="rounded-lg border p-4"
    :class="
      rateLimited
        ? 'border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100'
        : 'border-rose-300 bg-rose-50 text-rose-950 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-100'
    "
  >
    <p class="font-semibold">{{ title }}</p>
    <p class="mt-1 text-sm">{{ error.message }}</p>
    <div class="mt-3 flex flex-wrap items-center gap-3">
      <button
        type="button"
        :disabled="secondsLeft > 0"
        class="rounded-md border border-current px-3 py-1 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60"
        @click="emit('retry')"
      >
        {{ secondsLeft > 0 ? `Try again in ${secondsLeft} s` : 'Try again' }}
      </button>
      <span v-if="error.request_id" class="text-xs opacity-80">
        Reference: <code>{{ error.request_id }}</code>
      </span>
    </div>
  </div>
</template>
