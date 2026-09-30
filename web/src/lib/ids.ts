/**
 * A random id for a chat or a turn (matches the API's session_id rule: 16-64 of [A-Za-z0-9-]).
 *
 * crypto.randomUUID() only exists on secure pages (https, or localhost), so a
 * phone opening the dev server by LAN address gets the fallback.
 */
export function newId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}
