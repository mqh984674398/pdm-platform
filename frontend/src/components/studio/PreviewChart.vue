<script setup lang="ts">
/** ECharts preview for studio data. Data passed in is already converted to display units. */
import { BarChart, LineChart, ScatterChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ChartKind } from '@/api/contracts'

echarts.use([
  LineChart,
  ScatterChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
])

export interface ChartSeries {
  name: string
  unit: string
  /** [epoch ms, value], sorted by time */
  points: [number, number][]
  /** epoch ms of rows flagged by the quality check */
  flagged?: [number, number][]
}

const props = withDefaults(
  defineProps<{
    series: ChartSeries[]
    kind?: ChartKind
    height?: number
    flaggedLabel?: string
  }>(),
  { kind: 'LINE', height: 280, flaggedLabel: '' },
)

const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: MutationObserver | null = null
let resize: ResizeObserver | null = null

function css(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}
const utcTime = (ms: number) => new Date(ms).toISOString().slice(11, 19)

function histogram(values: number[], bins = 24): [string, number][] {
  if (!values.length) return []
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const w = (hi - lo) / bins || 1
  const counts = new Array<number>(bins).fill(0)
  for (const v of values) counts[Math.min(bins - 1, Math.floor((v - lo) / w))]!++
  return counts.map((c, i) => [(lo + w * (i + 0.5)).toPrecision(4), c])
}

function option(): echarts.EChartsCoreOption {
  const palette = ['--chart-1', '--chart-2', '--chart-3', '--chart-4'].map(css)
  const ink = css('--ink-soft')
  const grid = css('--chart-grid')
  const axis = {
    axisLine: { lineStyle: { color: grid } },
    axisLabel: { color: ink, fontSize: 11 },
    splitLine: { lineStyle: { color: grid } },
  }
  const base = {
    color: palette,
    animation: false,
    textStyle: { fontFamily: css('--font-ui') },
    grid: { left: 56, right: 56, top: 36, bottom: 28 },
    legend: { top: 0, textStyle: { color: ink }, icon: 'roundRect', itemHeight: 8 },
    tooltip: { trigger: props.kind === 'HISTOGRAM' ? 'axis' : 'item' },
  }
  const units = [...new Set(props.series.map((s) => s.unit))]
  const yAxes = units.slice(0, 2).map((u, i) => ({
    type: 'value',
    name: u,
    nameTextStyle: { color: ink },
    scale: true,
    position: i ? 'right' : 'left',
    ...axis,
    splitLine: { show: i === 0, lineStyle: { color: grid } },
  }))
  const yIndex = (s: ChartSeries) => Math.min(1, units.indexOf(s.unit))

  if (props.kind === 'HISTOGRAM') {
    return {
      ...base,
      xAxis: { type: 'category', name: units.join(' / '), ...axis },
      yAxis: { type: 'value', minInterval: 1, ...axis },
      series: props.series.map((s) => ({
        name: s.name,
        type: 'bar',
        barGap: '10%',
        data: histogram(s.points.map((p) => p[1])),
      })),
    }
  }
  if (props.kind === 'CYCLE_DURATION') {
    return {
      ...base,
      xAxis: { type: 'value', minInterval: 1, ...axis },
      yAxis: yAxes,
      series: props.series.map((s) => ({
        name: s.name,
        type: 'line',
        symbolSize: 4,
        yAxisIndex: yIndex(s),
        data: s.points.map((p, i) => [i + 1, p[1]]),
      })),
    }
  }
  if (props.kind === 'SCATTER' && props.series.length >= 2) {
    const [a, b] = props.series as [ChartSeries, ChartSeries]
    const bv = new Map(b.points)
    return {
      ...base,
      xAxis: { type: 'value', name: `${a.name} (${a.unit})`, scale: true, ...axis },
      yAxis: { type: 'value', name: `${b.name} (${b.unit})`, scale: true, ...axis },
      series: [
        {
          name: `${a.name} / ${b.name}`,
          type: 'scatter',
          symbolSize: 4,
          data: a.points.filter((p) => bv.has(p[0])).map((p) => [p[1], bv.get(p[0])]),
        },
      ],
    }
  }
  const flagged = props.series.flatMap((s) => (s.flagged?.length ? [s] : []))
  return {
    ...base,
    xAxis: {
      type: 'value',
      scale: true,
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: utcTime },
    },
    yAxis: yAxes,
    series: [
      ...props.series.map((s) => ({
        name: s.name,
        type: props.kind === 'SCATTER' ? 'scatter' : 'line',
        showSymbol: false,
        symbolSize: 4,
        lineStyle: { width: 1.5 },
        yAxisIndex: yIndex(s),
        data: s.points,
      })),
      ...flagged.map((s) => ({
        name: props.flaggedLabel,
        type: 'scatter',
        symbol: 'diamond',
        symbolSize: 8,
        itemStyle: { color: css('--health-warning') },
        yAxisIndex: yIndex(s),
        data: s.flagged,
        z: 5,
      })),
    ],
  }
}

function render() {
  chart?.setOption(option(), true)
}

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value, undefined, { renderer: 'canvas' })
  render()
  observer = new MutationObserver(render)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  resize = new ResizeObserver(() => chart?.resize())
  resize.observe(el.value)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  resize?.disconnect()
  chart?.dispose()
})
watch(() => [props.series, props.kind], render, { deep: true })
</script>

<template>
  <div ref="el" class="chart" :style="{ height: `${height}px` }" data-testid="preview-chart"></div>
</template>

<style scoped>
.chart {
  width: 100%;
}
</style>
