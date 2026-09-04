<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NEmpty } from 'naive-ui'
import { api } from '../api'
import type { StatsOverview } from '../api'
import type { EChartsCoreOption } from 'echarts/core'
import { CHART_FONT, STATUSES } from '../types'
import VChart from '../components/VChart.vue'

const data = ref<StatsOverview | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    data.value = await api.statsOverview()
  } finally {
    loading.value = false
  }
})

const FUNNEL_COLORS = ['#6366f1', '#8b5cf6', '#f59e0b', '#10b981', '#14b8a6']

// ---- 漏斗图 ----
const funnelOption = computed<EChartsCoreOption>(() => {
  const funnel = data.value?.funnel ?? []
  return {
    textStyle: { fontFamily: CHART_FONT },
    tooltip: { trigger: 'item', formatter: '{b}：{c} 家' },
    series: [
      {
        type: 'funnel',
        left: '4%',
        right: '4%',
        top: 12,
        bottom: 8,
        minSize: '18%',
        sort: 'none',
        gap: 6,
        label: {
          show: true,
          position: 'inside',
          formatter: (p: { name: string; value: number }) => `${p.name}  ${p.value}`,
          fontSize: 12,
          color: '#fff',
          fontWeight: 600,
        },
        itemStyle: { borderRadius: 6, borderWidth: 0 },
        color: FUNNEL_COLORS,
        data: funnel.map((f) => ({ name: f.label, value: f.count })),
      },
    ],
  }
})

// ---- 环节转化率 ----
const conversions = computed(() => {
  const funnel = data.value?.funnel ?? []
  const rates: { from: string; to: string; rate: number | null }[] = []
  for (let i = 1; i < funnel.length; i++) {
    const prev = funnel[i - 1].count
    const cur = funnel[i].count
    rates.push({
      from: funnel[i - 1].label,
      to: funnel[i].label,
      rate: prev > 0 ? Math.round((cur / prev) * 100) : null,
    })
  }
  return rates
})

// ---- 状态分布饼图 ----
const pieOption = computed<EChartsCoreOption>(() => {
  const byStatus = data.value?.by_status ?? {}
  const rows = STATUSES.map((s) => ({
    name: s.label,
    value: byStatus[s.key] ?? 0,
    itemStyle: { color: s.color },
  })).filter((r) => r.value > 0)
  return {
    textStyle: { fontFamily: CHART_FONT },
    tooltip: { trigger: 'item', formatter: '{b}：{c} 家 ({d}%)' },
    legend: {
      bottom: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      itemGap: 12,
      textStyle: { fontSize: 11, color: '#71717a' },
    },
    series: [
      {
        type: 'pie',
        radius: ['42%', '66%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        label: { show: false },
        emphasis: { label: { show: false } },
        data: rows,
      },
    ],
  }
})

// ---- 周活跃柱状图 ----
const weeklyOption = computed<EChartsCoreOption>(() => {
  const weekly = data.value?.weekly ?? []
  return {
    textStyle: { fontFamily: CHART_FONT },
    tooltip: { trigger: 'axis' },
    legend: {
      top: 0,
      right: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { fontSize: 11, color: '#71717a' },
    },
    grid: { left: 8, right: 8, top: 30, bottom: 0, containLabel: true },
    xAxis: {
      type: 'category',
      data: weekly.map((w) => w.week),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e4e4e7' } },
      axisLabel: { color: '#71717a', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: '#f4f4f5' } },
      axisLabel: { color: '#71717a', fontSize: 11 },
    },
    series: [
      {
        name: '投递',
        type: 'bar',
        data: weekly.map((w) => w.applied),
        itemStyle: { color: '#6366f1', borderRadius: [4, 4, 0, 0] },
        barMaxWidth: 18,
      },
      {
        name: '面试',
        type: 'bar',
        data: weekly.map((w) => w.interviews),
        itemStyle: { color: '#8b5cf6', borderRadius: [4, 4, 0, 0] },
        barMaxWidth: 18,
      },
    ],
  }
})

// ---- 渠道效果 ----
function pct(part: number, total: number): string {
  if (!total) return '—'
  return Math.round((part / total) * 100) + '%'
}
</script>

<template>
  <div class="flex h-full flex-col">
    <header class="fade-up flex items-end justify-between px-7 pb-4 pt-6">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">统计漏斗</h1>
        <p class="mt-1 text-[13px] text-zinc-400">
          求职转化全景：投递 → 面试 → 终面 → Offer → 接受
        </p>
      </div>
    </header>

    <div v-if="loading" class="grid flex-1 place-items-center text-sm text-zinc-400">
      正在加载统计…
    </div>

    <div v-else-if="data" class="fade-up-d1 min-h-0 flex-1 overflow-y-auto pb-6">
      <div class="grid grid-cols-1 gap-3.5 px-7 xl:grid-cols-3">
        <!-- 漏斗 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 xl:col-span-2">
          <div class="mb-1 flex items-center justify-between">
            <h2 class="text-[14.5px] font-bold text-zinc-800">求职转化漏斗</h2>
            <span class="text-[11.5px] text-zinc-400">含已挂掉 / 归档的岗位</span>
          </div>
          <div class="h-[290px]">
            <VChart :option="funnelOption" />
          </div>
          <div class="mt-2 flex flex-wrap items-center justify-center gap-1.5">
            <template v-for="(c, i) in conversions" :key="i">
              <span
                v-if="i > 0"
                class="mx-0.5 text-[11px] text-zinc-300"
              >›</span>
              <span
                class="rounded-full border px-2.5 py-0.5 text-[11px] font-medium"
                :class="
                  c.rate == null
                    ? 'border-zinc-200 bg-zinc-50 text-zinc-400'
                    : 'border-indigo-100 bg-indigo-50/60 text-indigo-600'
                "
              >
                {{ c.from }}→{{ c.to }} {{ c.rate == null ? '—' : c.rate + '%' }}
              </span>
            </template>
          </div>
        </section>

        <!-- 状态分布 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5">
          <h2 class="mb-1 text-[14.5px] font-bold text-zinc-800">岗位状态分布</h2>
          <div class="h-[330px]">
            <VChart v-if="Object.keys(data.by_status).length" :option="pieOption" />
            <NEmpty v-else class="mt-16" description="还没有任何岗位" />
          </div>
        </section>

        <!-- 周活跃 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 xl:col-span-2">
          <div class="mb-2 flex items-center justify-between">
            <h2 class="text-[14.5px] font-bold text-zinc-800">近 8 周活跃</h2>
            <span class="text-[11.5px] text-zinc-400">按自然周统计投递与面试场次</span>
          </div>
          <div class="h-[240px]">
            <VChart :option="weeklyOption" />
          </div>
        </section>

        <!-- 渠道效果 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5">
          <h2 class="mb-3 text-[14.5px] font-bold text-zinc-800">渠道效果</h2>
          <div v-if="data.channels.length === 0" class="py-8 text-center text-[13px] text-zinc-400">
            暂无投递数据
          </div>
          <table v-else class="w-full text-[12.5px]">
            <thead>
              <tr class="text-left text-[11px] uppercase tracking-wide text-zinc-400">
                <th class="pb-2 font-semibold">渠道</th>
                <th class="pb-2 text-center font-semibold">投递</th>
                <th class="pb-2 text-center font-semibold">约面</th>
                <th class="pb-2 text-center font-semibold">约面率</th>
                <th class="pb-2 text-center font-semibold">Offer</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="ch in data.channels"
                :key="ch.channel"
                class="border-t border-zinc-100"
              >
                <td class="py-2.5 font-medium text-zinc-700">{{ ch.channel }}</td>
                <td class="py-2.5 text-center tabular-nums text-zinc-600">{{ ch.total }}</td>
                <td class="py-2.5 text-center tabular-nums text-zinc-600">{{ ch.interviewed }}</td>
                <td class="py-2.5 text-center">
                  <span
                    class="rounded-md px-1.5 py-0.5 text-[11.5px] font-semibold tabular-nums"
                    :class="ch.interviewed === 0 ? 'bg-zinc-50 text-zinc-400' : 'bg-emerald-50 text-emerald-600'"
                  >
                    {{ pct(ch.interviewed, ch.total) }}
                  </span>
                </td>
                <td class="py-2.5 text-center tabular-nums text-zinc-600">{{ ch.offers || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </div>
  </div>
</template>
