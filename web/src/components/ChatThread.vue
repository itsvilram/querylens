<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { nextTick, ref, watch } from 'vue'

import { fetchHealth } from '@/api/client'
import { useAsk } from '@/composables/useAskStream'
import { useChatStore } from '@/stores/chat'

import ChatTurn from './ChatTurn.vue'

const EXAMPLES = [
  'Which film categories made the most money in 2024?',
  'How many rentals were there each month in 2024?',
  'Which 10 customers spent the most?',
  'How many films are there?',
]

const chat = useChatStore()
const { ask } = useAsk()
const health = useQuery({
  queryKey: ['health'],
  queryFn: ({ signal }) => fetchHealth(signal),
  staleTime: Infinity,
})

// Bring each new question into view (instantly if the user prefers less motion).
const list = ref<HTMLOListElement | null>(null)
watch(
  () => chat.turns.length,
  async (count, before) => {
    if (count <= before) return
    await nextTick()
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    list.value?.lastElementChild?.scrollIntoView({
      behavior: reduce ? 'auto' : 'smooth',
      block: 'start',
    })
  },
)
</script>

<template>
  <section aria-label="Conversation" class="mx-auto w-full max-w-4xl px-4 py-6">
    <div v-if="!chat.turns.length" class="space-y-4 py-8">
      <h2 class="text-xl font-semibold">Ask about the Pagila DVD-rental database</h2>
      <p class="text-slate-700 dark:text-slate-300">
        Films, actors, customers, rentals and payments from 2022 to 2026. QueryLens writes the SQL,
        checks it is safe, runs it read-only and shows the result. Try one of these:
      </p>
      <ul class="grid gap-2 sm:grid-cols-2">
        <li v-for="example in EXAMPLES" :key="example">
          <button
            type="button"
            class="h-full w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-left text-sm hover:border-indigo-400 hover:bg-indigo-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-indigo-500 dark:hover:bg-slate-800"
            @click="ask(example)"
          >
            {{ example }}
          </button>
        </li>
      </ul>
      <p class="text-sm text-slate-600 dark:text-slate-400">
        Then ask a follow-up, like <q>Only for store 2</q>.
      </p>
      <p
        v-if="health.data.value?.llm_mode === 'fake'"
        class="rounded-lg border border-sky-300 bg-sky-50 p-3 text-sm text-sky-950 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100"
      >
        Demo mode: this server has no AI key, so only the example questions above (and the store 2
        follow-up) have answers.
      </p>
    </div>

    <ol v-else ref="list" class="space-y-8">
      <li v-for="turn in chat.turns" :key="turn.id" class="scroll-mt-4">
        <ChatTurn :turn="turn" />
      </li>
    </ol>
  </section>
</template>
