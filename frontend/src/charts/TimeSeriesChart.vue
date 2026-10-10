<script setup lang="ts">
/**
 * Time-series chart with zoom, reference bands, maintenance markers and alarm periods (T019, UI-06/07).
 * Data arrives already downsampled by the server; ``zoom`` asks the parent for finer data.
 */
import { LineChart, ScatterChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Point, Range } from './merge'

echarts.use([
  LineChart,
  ScatterChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  CanvasRenderer,
])

export interface ChartLine {
  name: string
  points: Point[]
  kind?: 'line' | 'scatter'
  color?: string // CSS variable name, e.g. '--chart-1'
  dashed?: boolean
}
export interface ChartBand {
  name: string
  from: number
  to: number
  lower: number
  upper: number
}
export interface ChartMarker {
  ts: number
  label: string
}
export interface ChartPeriod {
  from: number
  to: number
  severity: 'WATCH' | 'WARNING' | 'CRITICAL'
  label: string
}

const props = withDefaults(
  defineProps<{
    lines: ChartLine[]
    unit?: string
    full?: Range | null
    bands?: ChartBand[]
    markers?: ChartMarker[]
    periods?: ChartPeriod[]
    height?: number
  }>(),
  { unit: '', full: null, bands: () => [], markers: () => [], periods: () => [], height: 360 },
)
const emit = defineEmits<{ zoom: [range: Range] }>()

const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: MutationObserver | null = null
let resize: ResizeObserver | null = null
let zoomTimer: ReturnType<typeof setTimeout> | undefined
const zoomState = ref<{ start: number; end: number }>({ start: 0, end: 100 })

const css = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()
const fmt = (ms: number) =>
  Number.isFinite(ms) ? new Date(ms).toISOString().slice(0, 16).replace('T', ' ') : ''

function option(): echarts.EChartsCoreOption {
  const ink = css('--ink-soft')
  const grid = css('--chart-grid')
  const palette = ['--chart-1', '--chart-2', '--chart-3', '--chart-4']
  const axis = {
    axisLine: { lineStyle: { color: grid } },
    axisLabel: { color: ink, fontSize: 11 },
    splitLine: { lineStyle: { color: grid } },
  }
  const sev = (s: ChartPeriod['severity']) => css(`--health-${s.toLowerCase()}-soft`)
  const first = {
    markArea: {
      silent: true,
      data: [
        ...props.periods.map((p) => [
          { xAxis: p.from, name: p.label, itemStyle: { color: sev(p.severity), opacity: 0.6 } },
          { xAxis: p.to },
        ]),
        ...props.bands.map((b) => [
          {
            xAxis: b.from,
            yAxis: b.lower,
            name: b.name,
            itemStyle: { color: css('--health-normal-soft'), opacity: 0.7 },
            label: { show: false },
          },
          { xAxis: b.to, yAxis: b.upper },
        ]),
      ],
    },
    markLine: {
      symbol: 'none',
      silent: true,
      lineStyle: { color: css('--ink-soft'), type: 'dashed' },
      label: { color: ink, fontSize: 10, formatter: '{b}' },
      data: props.markers.map((m) => ({ xAxis: m.ts, name: m.label })),
    },
  }
  return {
    animation: false,
    textStyle: { fontFamily: css('--font-ui') },
    grid: { left: 60, right: 24, top: 36, bottom: 72 },
    legend: { top: 0, textStyle: { color: ink }, icon: 'roundRect', itemHeight: 8 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line' },
      valueFormatter: (v: unknown) =>
        typeof v === 'number' ? `${v.toPrecision(5)} ${props.unit}` : '–',
    },
    xAxis: {
      type: 'time',
      min: props.full?.start,
      max: props.full?.end,
      ...axis,
      axisLabel: { ...axis.axisLabel, hideOverlap: true },
    },
    yAxis: { type: 'value', scale: true, name: props.unit, nameTextStyle: { color: ink }, ...axis },
    dataZoom: [
      { type: 'inside', filterMode: 'none', ...zoomState.value },
      {
        type: 'slider',
        filterMode: 'none',
        height: 22,
        bottom: 16,
        labelFormatter: (v: number) => fmt(v),
        textStyle: { color: ink, fontSize: 10 },
        ...zoomState.value,
      },
    ],
    series: props.lines.map((l, i) => ({
      name: l.name,
      type: l.kind ?? 'line',
      showSymbol: l.kind === 'scatter',
      symbolSize: 4,
      connectNulls: false,
      large: true,
      itemStyle: { color: css(l.color ?? palette[i % palette.length]!) },
      lineStyle: { width: 1.4, type: l.dashed ? 'dashed' : 'solid' },
      data: l.points,
      ...(i === 0 ? first : {}),
    })),
  }
}

function render() {
  chart?.setOption(option(), true)
}

function onDataZoom() {
  const opt = chart?.getOption() as { dataZoom?: { start: number; end: number }[] } | undefined
  const dz = opt?.dataZoom?.[0]
  if (!dz || !props.full) return
  zoomState.value = { start: dz.start, end: dz.end }
  clearTimeout(zoomTimer)
  zoomTimer = setTimeout(() => {
    const span = props.full!.end - props.full!.start
    emit('zoom', {
      start: props.full!.start + (span * dz.start) / 100,
      end: props.full!.start + (span * dz.end) / 100,
    })
  }, 200)
}

/** Programmatic zoom, as percentages of the full range (used by tests and range presets). */
function zoomTo(start: number, end: number) {
  chart?.dispatchAction({ type: 'dataZoom', start, end })
}
defineExpose({ zoomTo })

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value, undefined, { renderer: 'canvas' })
  render()
  chart.on('datazoom', onDataZoom)
  observer = new MutationObserver(render)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  resize = new ResizeObserver(() => chart?.resize())
  resize.observe(el.value)
})
onBeforeUnmount(() => {
  clearTimeout(zoomTimer)
  observer?.disconnect()
  resize?.disconnect()
  chart?.dispose()
})
watch(
  () => [props.lines, props.bands, props.markers, props.periods, props.full],
  () => render(),
  { deep: false },
)
watch(
  () => props.full,
  () => (zoomState.value = { start: 0, end: 100 }),
)
</script>

<template>
  <div
    ref="el"
    class="chart"
    :style="{ height: `${height}px` }"
    data-testid="ts-chart"
    :data-points="lines.reduce((n, l) => n + l.points.length, 0)"
  ></div>
</template>

<style scoped>
.chart {
  width: 100%;
}
</style>
