<script setup lang="ts">
import { useAsk } from '@/composables/useAskStream'
import type { Turn } from '@/stores/chat'

import AnswerCard from './AnswerCard.vue'
import ErrorNotice from './ErrorNotice.vue'
import StageProgress from './StageProgress.vue'

defineProps<{ turn: Turn }>()
const { ask } = useAsk()
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
      @retry="ask(turn.question)"
    />
    <p v-else-if="turn.status === 'cancelled'" class="text-sm text-slate-600 dark:text-slate-400">
      Stopped.
    </p>
    <AnswerCard v-else-if="turn.answer" :answer="turn.answer" />
  </article>
</template>
