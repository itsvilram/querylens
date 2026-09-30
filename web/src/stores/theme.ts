import { defineStore } from 'pinia'
import { computed, ref, watch, watchEffect } from 'vue'

export type ThemeChoice = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'querylens-theme' // also read by the small script in index.html

function saved(): ThemeChoice {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system' // storage can be blocked (private mode, strict settings)
  }
}

/** Light or dark: follows the system unless the user picked one. Puts `dark` on <html>. */
export const useThemeStore = defineStore('theme', () => {
  const choice = ref<ThemeChoice>(saved())
  const media =
    typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-color-scheme: dark)')
      : null
  const systemDark = ref(media?.matches ?? false)
  media?.addEventListener('change', (event) => (systemDark.value = event.matches))

  const dark = computed(
    () => choice.value === 'dark' || (choice.value === 'system' && systemDark.value),
  )
  watchEffect(() => document.documentElement.classList.toggle('dark', dark.value))
  watch(choice, (value) => {
    try {
      localStorage.setItem(STORAGE_KEY, value)
    } catch {
      // not saved; the choice still applies until the page is closed
    }
  })

  function cycle() {
    const order: ThemeChoice[] = ['system', 'light', 'dark']
    choice.value = order[(order.indexOf(choice.value) + 1) % order.length]!
  }

  return { choice, dark, cycle }
})
