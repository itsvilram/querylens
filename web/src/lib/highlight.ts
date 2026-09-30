/**
 * SQL syntax highlighting with Shiki. Imported lazily (only when an answer
 * shows SQL), so it stays out of the first page load.
 *
 * Fine-grained build: only the SQL grammar and two themes, with the JavaScript
 * regex engine instead of the WebAssembly one (no extra download).
 */
import { createHighlighterCore, type HighlighterCore } from 'shiki/core'
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript'

let highlighter: Promise<HighlighterCore> | null = null

function getHighlighter(): Promise<HighlighterCore> {
  highlighter ??= createHighlighterCore({
    themes: [import('@shikijs/themes/github-light'), import('@shikijs/themes/github-dark')],
    langs: [import('@shikijs/langs/sql')],
    engine: createJavaScriptRegexEngine(),
  })
  return highlighter
}

/**
 * The SQL as HTML. Both themes' colors are set as CSS variables and main.css
 * picks one by the page's theme, so switching theme needs no re-highlighting.
 * Shiki escapes the code text, so the HTML is safe to insert.
 */
export async function highlightSql(sql: string): Promise<string> {
  return (await getHighlighter()).codeToHtml(sql, {
    lang: 'sql',
    themes: { light: 'github-light', dark: 'github-dark' },
    defaultColor: false,
  })
}
