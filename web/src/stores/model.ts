import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'querylens-model'

function saved(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null // storage can be blocked (private mode, strict settings)
  }
}

/**
 * Which of the server's models the visitor picked (GET /api/health lists them).
 * null = the server's default. Remembered in this browser only.
 */
export const useModelStore = defineStore('model', () => {
  const choice = ref<string | null>(saved())
  watch(choice, (value) => {
    try {
      if (value) localStorage.setItem(STORAGE_KEY, value)
      else localStorage.removeItem(STORAGE_KEY)
    } catch {
      // not remembered; the choice still applies until the page is closed
    }
  })
  return { choice }
})
