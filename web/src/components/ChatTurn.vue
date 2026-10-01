<script setup lang="ts">
import { computed } from 'vue'

import { useAsk } from '@/composables/useAskStream'
import { useHealth } from '@/composables/useHealth'
import type { Turn } from '@/stores/chat'
import { useModelStore } from '@/stores/model'

import AnswerCard from './AnswerCard.vue'
import ErrorNotice from './ErrorNotice.vue'
import StageProgress from './StageProgress.vue'

const props = defineProps<{ turn: Turn }>()
const { ask } = useAsk()
const health = useHealth()
const models = useModelStore()

// Errors another model can get around: its quota or its service, not the question.
const MODEL_ERRORS = new Set(['daily_budget_used', 'llm_busy', 'llm_unavailable'])
const alternative = computed(() => {
  if (!props.turn.error || !MODEL_ERRORS.has(props.turn.error.code)) return null
  const used = props.turn.model ?? health.data.value?.default_model
  return health.data.value?.models.find((m) => m.id !== used) ?? null
})

function retryWith(model: string) {
  models.choice = model // also used for the next questions
  void ask(props.turn.question)
}
</script>

<template>
  <article class="space-y-3" :aria-labelledby="`question-${turn.id}`">
    <p
      :id="`question-${turn.id}`"
      class="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2 text-white"
    >
      {{ turn.question }}
    </p>
    <StageProgress v-if="turn.status === 'running'" :stages="turn.stages" />
    <ErrorNotice
      v-else-if="turn.status === 'error' && turn.error"
      :error="turn.error"
      :alternative="alternative"
      @retry="ask(turn.question)"
      @retry-with="retryWith"
    />
    <p v-else-if="turn.status === 'cancelled'" class="text-sm text-slate-600 dark:text-slate-400">
      Stopped.
    </p>
    <AnswerCard v-else-if="turn.answer" :answer="turn.answer" />
  </article>
</template>
