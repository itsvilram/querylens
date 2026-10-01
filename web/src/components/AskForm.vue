<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'

import { useAsk } from '@/composables/useAskStream'
import { useHealth } from '@/composables/useHealth'
import { useChatStore } from '@/stores/chat'
import { useModelStore } from '@/stores/model'

const MAX_LENGTH = 500 // the API's limit

const chat = useChatStore()
const { ask, cancel } = useAsk()
const health = useHealth()
const models = useModelStore()
const modelId = useId()

// The model switch: only when the server offers more than one (e.g. Gemini and Groq).
const options = computed(() => health.data.value?.models ?? [])
const selected = computed({
  get: () => models.choice ?? health.data.value?.default_model ?? '',
  set: (id: string) => {
    models.choice = id === health.data.value?.default_model ? null : id
  },
})
// A remembered choice this server doesn't offer (any more) falls back to its default.
watch(options, (list) => {
  if (models.choice && list.length && !list.some((m) => m.id === models.choice)) {
    models.choice = null
  }
})
const text = ref('')
const box = ref<HTMLTextAreaElement | null>(null)

function submit() {
  if (!text.value.trim() || chat.busy) return
  const question = text.value
  text.value = ''
  void ask(question)
}

function onKeydown(event: KeyboardEvent) {
  // Enter sends, Shift+Enter adds a line. isComposing: don't send while an
  // input method (e.g. for Hindi or Japanese) is still building a word.
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    submit()
  }
}

defineExpose({ focus: () => box.value?.focus() })
</script>

<template>
  <form
    class="sticky bottom-0 border-t border-slate-200 bg-slate-50/95 px-4 py-3 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95"
    @submit.prevent="submit"
  >
    <div class="mx-auto flex max-w-4xl items-end gap-2">
      <div class="flex-1">
        <div v-if="options.length > 1" class="mb-2 flex items-center gap-2 text-sm">
          <label :for="modelId" class="text-slate-600 dark:text-slate-400">Model</label>
          <select
            :id="modelId"
            v-model="selected"
            class="rounded-md border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
          >
            <option v-for="option in options" :key="option.id" :value="option.id">
              {{ option.label }}
            </option>
          </select>
        </div>
        <label for="question" class="sr-only">Your question</label>
        <textarea
          id="question"
          ref="box"
          v-model="text"
          rows="2"
          :maxlength="MAX_LENGTH"
          placeholder="Ask about films, rentals, customers or payments…"
          aria-describedby="question-help"
          class="block w-full resize-none rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 placeholder:text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-400"
          @keydown="onKeydown"
        />
        <p
          id="question-help"
          class="mt-1 flex justify-between text-xs text-slate-600 dark:text-slate-400"
        >
          <span>Enter to send, Shift+Enter for a new line.</span>
          <span>{{ text.length }}/{{ MAX_LENGTH }}</span>
        </p>
        <p v-if="health.data.value?.demo" class="text-xs text-slate-600 dark:text-slate-400">
          Questions go to Google&rsquo;s Gemini (free tier). Don&rsquo;t type private data.
        </p>
      </div>
      <button
        v-if="!chat.busy"
        type="submit"
        :disabled="!text.trim()"
        class="mb-6 rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Ask
      </button>
      <button
        v-else
        type="button"
        class="mb-6 rounded-lg border border-slate-300 px-4 py-2 font-medium hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
        @click="cancel"
      >
        Stop
      </button>
    </div>
  </form>
</template>
