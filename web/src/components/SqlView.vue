<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps<{ sql: string }>()

// Plain text first; the highlighted version replaces it once Shiki has loaded.
const html = ref<string | null>(null)
watch(
  () => props.sql,
  async (sql) => {
    html.value = null
    try {
      const { highlightSql } = await import('@/lib/highlight')
      const highlighted = await highlightSql(sql)
      if (sql === props.sql) html.value = highlighted
    } catch {
      // keep the plain text: still readable, just not coloured
    }
  },
  { immediate: true },
)

const copied = ref(false)
let resetTimer: ReturnType<typeof setTimeout> | undefined
async function copy() {
  try {
    await navigator.clipboard.writeText(props.sql)
    copied.value = true
    clearTimeout(resetTimer)
    resetTimer = setTimeout(() => (copied.value = false), 2000)
  } catch {
    copied.value = false // clipboard blocked (e.g. not https): the text can still be selected
  }
}
onBeforeUnmount(() => clearTimeout(resetTimer))
</script>

<template>
  <div
    class="relative overflow-hidden rounded-lg border border-slate-200 text-[13px] leading-relaxed dark:border-slate-800"
  >
    <!-- Shiki's output: the SQL text inside it is escaped, so this is safe to insert. -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div v-if="html" class="overflow-x-auto [&_pre]:p-3 [&_pre]:pr-20" v-html="html" />
    <pre
      v-else
      class="overflow-x-auto bg-white p-3 pr-20 dark:bg-slate-900"
    ><code>{{ sql }}</code></pre>
    <button
      type="button"
      class="absolute top-2 right-2 rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
      @click="copy"
    >
      {{ copied ? 'Copied' : 'Copy' }}
    </button>
    <span class="sr-only" aria-live="polite">{{
      copied ? 'SQL copied to the clipboard' : ''
    }}</span>
  </div>
</template>
