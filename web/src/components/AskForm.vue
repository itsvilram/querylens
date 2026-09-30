<script setup lang="ts">
import { ref } from 'vue'

import { useAsk } from '@/composables/useAskStream'
import { useChatStore } from '@/stores/chat'

const MAX_LENGTH = 500 // the API's limit

const chat = useChatStore()
const { ask, cancel } = useAsk()
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
