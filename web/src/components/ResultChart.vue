<script setup lang="ts">
// Loaded only when an answer has a chart (see AnswerCard), so Chart.js stays
// out of the first page load. Chart.js was picked over ECharts on measured
// size: 61 KB vs 200 KB gzipped for line + bar charts.
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { Answer } from '@/api/types'
import { chartData, describeChart } from '@/lib/chart'
import { useThemeStore } from '@/stores/theme'

Chart.register(
  BarController,
  BarElement,
  CategoryScale,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
)

const props = defineProps<{ answer: Answer; kind: 'line' | 'bar' }>()
const theme = useThemeStore()
const canvas = ref<HTMLCanvasElement | null>(null)

const data = computed(() => chartData(props.answer))
const description = computed(() => describeChart(props.kind, data.value))

// Colours that keep their contrast on both backgrounds.
const SERIES_COLOURS = ['#6366f1', '#f59e0b', '#10b981', '#ec4899', '#0ea5e9', '#84cc16']

let chart: Chart | null = null

function draw() {
  chart?.destroy()
  if (!canvas.value) return
  const text = theme.dark ? '#cbd5e1' : '#334155'
  const grid = theme.dark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(100, 116, 139, 0.2)'
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  chart = new Chart(canvas.value, {
    type: props.kind,
    data: {
      labels: data.value.labels,
      datasets: data.value.series.map((series, i) => {
        const colour = SERIES_COLOURS[i % SERIES_COLOURS.length]!
        return {
          label: series.label,
          data: series.values,
          backgroundColor: colour,
          borderColor: colour,
          borderWidth: props.kind === 'line' ? 2 : 0,
          pointRadius: data.value.labels.length > 60 ? 0 : 2,
        }
      }),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: reduceMotion ? false : undefined,
      plugins: {
        legend: { display: data.value.series.length > 1, labels: { color: text } },
      },
      scales: {
        x: { ticks: { color: text }, grid: { color: grid } },
        y: { ticks: { color: text }, grid: { color: grid }, beginAtZero: props.kind === 'bar' },
      },
    },
  })
}

onMounted(draw)
watch([() => props.kind, () => theme.dark, () => props.answer], draw)
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div class="relative h-72 w-full">
    <canvas ref="canvas" role="img" :aria-label="description" />
  </div>
</template>
