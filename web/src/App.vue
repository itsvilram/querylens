<script setup lang="ts">
import { provide, ref } from 'vue'

import AskForm from '@/components/AskForm.vue'
import ChatThread from '@/components/ChatThread.vue'
import SchemaPanel from '@/components/SchemaPanel.vue'
import { askKey, useAskStream } from '@/composables/useAskStream'
import { useChatStore } from '@/stores/chat'
import { useThemeStore } from '@/stores/theme'

const chat = useChatStore()
const theme = useThemeStore()
provide(askKey, useAskStream()) // one stream for the whole page; components use useAsk()

const THEME_NAMES = { system: 'System', light: 'Light', dark: 'Dark' } as const

const form = ref<InstanceType<typeof AskForm> | null>(null)
function newChat() {
  chat.newChat()
  form.value?.focus()
}

// On small screens the schema opens in a dialog: <dialog> gives focus
// trapping and Escape-to-close for free.
const schemaDialog = ref<HTMLDialogElement | null>(null)
const schemaOpen = ref(false)
function openSchema() {
  schemaOpen.value = true
  schemaDialog.value?.showModal()
}
function closeSchema() {
  schemaDialog.value?.close()
}
</script>

<template>
  <div
    class="flex min-h-dvh flex-col bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100"
  >
    <a
      href="#question"
      class="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-10 focus:rounded focus:bg-white focus:px-3 focus:py-2 dark:focus:bg-slate-900"
    >
      Skip to the question box
    </a>

    <header class="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
      <div class="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3">
        <div>
          <h1 class="text-2xl font-bold">QueryLens</h1>
          <p class="text-sm text-slate-600 dark:text-slate-400">
            Ask a database questions in plain English. See the SQL, a table and a chart.
          </p>
        </div>
        <div class="flex gap-2 text-sm">
          <button
            type="button"
            class="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
            :disabled="!chat.turns.length || chat.busy"
            @click="newChat"
          >
            New chat
          </button>
          <button
            type="button"
            class="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-100 lg:hidden dark:border-slate-700 dark:hover:bg-slate-800"
            aria-haspopup="dialog"
            @click="openSchema"
          >
            Schema
          </button>
          <button
            type="button"
            class="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
            :aria-label="`Theme: ${THEME_NAMES[theme.choice]}. Change theme`"
            @click="theme.cycle()"
          >
            Theme: {{ THEME_NAMES[theme.choice] }}
          </button>
        </div>
      </div>
    </header>

    <div class="mx-auto flex w-full max-w-7xl flex-1">
      <main class="flex min-w-0 flex-1 flex-col">
        <div class="flex-1">
          <ChatThread />
        </div>
        <AskForm ref="form" />
      </main>

      <aside
        class="hidden w-80 shrink-0 border-l border-slate-200 p-4 lg:block dark:border-slate-800"
        aria-label="Database schema"
      >
        <div class="sticky top-4 max-h-[calc(100dvh-2rem)] overflow-y-auto">
          <SchemaPanel />
        </div>
      </aside>
    </div>

    <dialog
      ref="schemaDialog"
      aria-label="Database schema"
      class="m-0 ml-auto h-dvh max-h-dvh w-full max-w-sm bg-slate-50 p-4 text-slate-900 backdrop:bg-black/40 dark:bg-slate-950 dark:text-slate-100"
      @close="schemaOpen = false"
      @click.self="closeSchema"
    >
      <div class="mb-3 flex justify-end">
        <button
          type="button"
          class="rounded-md border border-slate-300 px-3 py-1 text-sm dark:border-slate-700"
          @click="closeSchema"
        >
          Close
        </button>
      </div>
      <SchemaPanel v-if="schemaOpen" />
    </dialog>
  </div>
</template>
