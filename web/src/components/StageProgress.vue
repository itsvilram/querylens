<script setup lang="ts">
import { computed } from 'vue'

import type { Stage } from '@/api/types'
import { STAGE_LABELS } from '@/lib/format'

const props = defineProps<{ stages: Stage[] }>()

const current = computed(() => {
  const last = props.stages.at(-1)
  return last ? STAGE_LABELS[last] : 'Starting'
})
</script>

<template>
  <div class="space-y-3">
    <ol class="space-y-1 text-sm text-slate-700 dark:text-slate-300">
      <li v-for="(stage, i) in stages" :key="i" class="flex items-center gap-2">
        <svg
          v-if="i < stages.length - 1"
          class="size-4 text-emerald-600 dark:text-emerald-400"
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fill-rule="evenodd"
            d="M16.7 5.3a1 1 0 0 1 0 1.4l-8 8a1 1 0 0 1-1.4 0l-4-4a1 1 0 1 1 1.4-1.4L8 12.6l7.3-7.3a1 1 0 0 1 1.4 0Z"
            clip-rule="evenodd"
          />
        </svg>
        <span
          v-else
          class="size-4 rounded-full border-2 border-indigo-500 border-t-transparent motion-safe:animate-spin"
          aria-hidden="true"
        />
        {{ STAGE_LABELS[stage] }}
      </li>
      <li v-if="!stages.length" class="flex items-center gap-2">
        <span
          class="size-4 rounded-full border-2 border-indigo-500 border-t-transparent motion-safe:animate-spin"
          aria-hidden="true"
        />
        Starting
      </li>
    </ol>

    <!-- Loading skeleton: the rough shape of the answer that is coming. -->
    <div class="space-y-2" aria-hidden="true">
      <div class="h-4 w-3/4 rounded bg-slate-200 motion-safe:animate-pulse dark:bg-slate-800" />
      <div class="h-32 rounded bg-slate-200 motion-safe:animate-pulse dark:bg-slate-800" />
    </div>

    <!-- Screen readers hear each new stage once, without moving focus. -->
    <p class="sr-only" aria-live="polite">{{ current }}</p>
  </div>
</template>
