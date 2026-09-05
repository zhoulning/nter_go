<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NEmpty } from 'naive-ui'
import { api } from '../api'
import type { StatsOverview } from '../api'
import type { EChartsCoreOption } from 'echarts/core'
import { CHART_FONT, ROUND_LABEL, STATUSES } from '../types'
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

function pct(part: number, total: number): number | null {
  if (!total) return null
  return Math.round((part / total) * 100)
}

function pctFmt(v: number | null): string {
  return v == null ? '—' : `${v}%`
}

// ---- KPI 指标条 ----
const funnel = computed(() => data.value?.funnel ?? [])
const appliedCount = computed(() => funnel.value[0]?.count ?? 0)

interface Kpi {
  label: string
  value: string
  sub: string
}

const kpis = computed<Kpi[]>(() => {
  const c = data.value?.cycles
  const f = funnel.value
  const count = (key: string) => f.find((x) => x.key === key)?.count ?? 0
  const list: Kpi[] = [
    {
      label: '累计投递',
      value: String(appliedCount.value),
      sub: `其中接受 ${count('accepted')} 家`,
    },
    {
      label: '约面率',
      value: pctFmt(pct(count('interviewed'), appliedCount.value)),
      sub: `${count('interviewed')}/${appliedCount.value} 家进入面试`,
    },
    {
      label: 'Offer 率',
      value: pctFmt(pct(count('offer'), appliedCount.value)),
      sub: `${count('offer')}/${appliedCount.value} 拿到 Offer`,
    },
    {
      label: 'Offer 接受率',
      value: pctFmt(pct(count('accepted'), count('offer'))),
      sub: `${count('accepted')}/${count('offer')} 个 Offer 接受`,
    },
  ]
  if (c) {
    list.push({
      label: '响应率',
      value: pctFmt(c.response_rate),
      sub: `无回音 ${c.no_response} · 等待中 ${c.waiting}`,
    })
    list.push({
      label: '投递 → 首面',
      value: c.apply_to_interview_days != null ? `${c.apply_to_interview_days} 天` : '—',
      sub:
        c.apply_to_offer_days != null
          ? `投递 → Offer 平均 ${c.apply_to_offer_days} 天`
          : '暂无 Offer 周期数据',
    })
  }
  return list
})

// ---- 转化漏斗（自绘条形，含阶段转化与流失）----
interface FunnelRow {
  key: string
  label: string
  count: number
  color: string
  widthPct: number
  share: number | null
}

const funnelRows = computed<FunnelRow[]>(() => {
  const max = Math.max(1, appliedCount.value)
  return funnel.value.map((f, i) => ({
    ...f,
    color: FUNNEL_COLORS[i % FUNNEL_COLORS.length],
    widthPct: Math.max(f.count > 0 ? 8 : 2, (f.count / max) * 100),
    share: pct(f.count, appliedCount.value),
  }))
})

const stageFlows = computed(() => {
  const rates: { rate: number | null; lost: number }[] = []
  const f = funnel.value
  for (let i = 1; i < f.length; i++) {
    rates.push({
      rate: pct(f[i].count, f[i - 1].count),
      lost: Math.max(0, f[i - 1].count - f[i].count),
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

// ---- 近 12 周趋势 ----
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
        barMaxWidth: 14,
      },
      {
        name: '面试',
        type: 'bar',
        data: weekly.map((w) => w.interviews),
        itemStyle: { color: '#8b5cf6', borderRadius: [4, 4, 0, 0] },
        barMaxWidth: 14,
      },
    ],
  }
})

// ---- 面试轮次通过率 ----
const roundRows = computed(() =>
  (data.value?.rounds ?? [])
    .map((r) => ({
      ...r,
      label: ROUND_LABEL[r.round_type] ?? r.round_type,
      rateColor:
        r.pass_rate == null
          ? '#a1a1aa'
          : r.pass_rate >= 60
            ? '#10b981'
            : r.pass_rate >= 30
              ? '#f59e0b'
              : '#ef4444',
    }))
    .sort((a, b) => b.total - a.total),
)

// ---- 复盘得分趋势 ----
const reviewOption = computed<EChartsCoreOption>(() => {
  const trend = data.value?.review_trend ?? []
  return {
    textStyle: { fontFamily: CHART_FONT },
    tooltip: {
      trigger: 'axis',
      formatter: (params: { dataIndex: number }[]) => {
        const item = trend[params[0]?.dataIndex]
        if (!item) return ''
        return `${item.company ?? '未知公司'}<br/>${item.date} · 复盘 ${item.score} 分`
      },
    },
    grid: { left: 8, right: 12, top: 16, bottom: 0, containLabel: true },
    xAxis: {
      type: 'category',
      data: trend.map((t) => t.date),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e4e4e7' } },
      axisLabel: { color: '#71717a', fontSize: 11 },
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      splitLine: { lineStyle: { color: '#f4f4f5' } },
      axisLabel: { color: '#71717a', fontSize: 11 },
    },
    series: [
      {
        name: '复盘得分',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        data: trend.map((t) => t.score),
        lineStyle: { color: '#6366f1', width: 2.5 },
        itemStyle: { color: '#6366f1', borderColor: '#fff', borderWidth: 2 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(99,102,241,0.22)' },
              { offset: 1, color: 'rgba(99,102,241,0.02)' },
            ],
          },
        },
      },
    ],
  }
})
</script>

<template>
  <div class="flex h-full flex-col">
    <header class="fade-up flex items-end justify-between px-7 pb-4 pt-6 max-md:px-4 max-md:pt-4">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">数据洞察</h1>
        <p class="mt-1 text-[13px] text-zinc-400">
          求职转化与效率全景：投递 → 面试 → 终面 → Offer → 接受
        </p>
      </div>
    </header>

    <div v-if="loading" class="grid flex-1 place-items-center text-sm text-zinc-400">
      正在加载统计…
    </div>

    <div v-else-if="data" class="fade-up-d1 min-h-0 flex-1 overflow-y-auto pb-6">
      <div class="grid grid-cols-1 gap-3.5 px-7 max-md:px-4 xl:grid-cols-3">
        <!-- KPI 指标条 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-4 xl:col-span-3">
          <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <div v-for="kpi in kpis" :key="kpi.label" class="rounded-xl bg-zinc-50/70 px-4 py-3">
              <div class="text-[11.5px] font-medium text-zinc-400">{{ kpi.label }}</div>
              <div class="mt-1 text-[22px] font-bold leading-none tabular-nums text-zinc-900">
                {{ kpi.value }}
              </div>
              <div class="mt-1.5 truncate text-[10.5px] text-zinc-400" :title="kpi.sub">
                {{ kpi.sub }}
              </div>
            </div>
          </div>
        </section>

        <!-- 转化漏斗（自绘） -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 xl:col-span-2">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-[14.5px] font-bold text-zinc-800">求职转化漏斗</h2>
            <span class="text-[11.5px] text-zinc-400">含已挂掉 / 归档的岗位</span>
          </div>

          <div v-if="appliedCount === 0" class="py-14 text-center text-[13px] text-zinc-400">
            还没有投递记录，先去岗位跟踪添加并投递吧
          </div>

          <div v-else class="space-y-0.5">
            <template v-for="(row, i) in funnelRows" :key="row.key">
              <div class="flex items-center gap-3">
                <span class="w-[68px] shrink-0 text-right text-[12px] font-medium text-zinc-500">
                  {{ row.label }}
                </span>
                <div class="min-w-0 flex-1">
                  <div
                    class="flex h-9 items-center justify-between gap-2 whitespace-nowrap rounded-lg px-3 transition-all"
                    :style="{ width: row.widthPct + '%', minWidth: '128px', background: row.color }"
                  >
                    <span class="text-[12.5px] font-bold tabular-nums text-white">
                      {{ row.count }} 家
                    </span>
                    <span
                      v-if="row.share != null && i > 0"
                      class="overflow-hidden text-[11px] tabular-nums text-white/80 text-ellipsis"
                    >
                      占投递 {{ row.share }}%
                    </span>
                  </div>
                </div>
              </div>
              <!-- 阶段间转化 / 流失 -->
              <div v-if="i < funnelRows.length - 1" class="flex items-center gap-3 py-0.5 pl-[80px]">
                <span class="text-[11px] text-zinc-400">
                  <span class="font-semibold text-indigo-500">
                    {{ stageFlows[i]?.rate == null ? '—' : stageFlows[i].rate + '%' }}
                  </span>
                  转化至{{ funnelRows[i + 1].label }}
                  <span class="mx-1 text-zinc-300">·</span>
                  流失 {{ stageFlows[i]?.lost ?? 0 }} 家
                </span>
              </div>
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

        <!-- 近 12 周趋势 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 xl:col-span-2">
          <div class="mb-2 flex items-center justify-between">
            <h2 class="text-[14.5px] font-bold text-zinc-800">近 12 周趋势</h2>
            <span class="text-[11.5px] text-zinc-400">按自然周统计投递与面试场次</span>
          </div>
          <div class="h-[240px]">
            <VChart :option="weeklyOption" />
          </div>
        </section>

        <!-- 面试轮次通过率 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-[14.5px] font-bold text-zinc-800">轮次通过率</h2>
            <span class="text-[11.5px] text-zinc-400">哪一轮最容易挂</span>
          </div>

          <div v-if="roundRows.length === 0" class="py-10 text-center text-[13px] text-zinc-400">
            还没有出结果的面试场次
          </div>

          <div v-else class="space-y-3.5">
            <div v-for="r in roundRows" :key="r.round_type">
              <div class="mb-1 flex items-baseline justify-between">
                <span class="text-[12.5px] font-medium text-zinc-700">
                  {{ r.label }}
                  <span class="ml-1 text-[11px] tabular-nums text-zinc-400">
                    {{ r.passed }}/{{ r.total }}
                  </span>
                </span>
                <span class="text-[13px] font-bold tabular-nums" :style="{ color: r.rateColor }">
                  {{ r.pass_rate == null ? '—' : r.pass_rate + '%' }}
                </span>
              </div>
              <div class="h-2 overflow-hidden rounded-full bg-zinc-100">
                <div
                  class="h-full rounded-full"
                  :style="{ width: (r.pass_rate ?? 0) + '%', background: r.rateColor }"
                />
              </div>
              <div class="mt-1 text-[10.5px] tabular-nums text-zinc-400">
                通过 {{ r.passed }} · 挂了 {{ r.failed }}<template v-if="r.no_show">
                  · 未参加 {{ r.no_show }}</template>
              </div>
            </div>
          </div>
        </section>

        <!-- 渠道效果 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 xl:col-span-2">
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
              <tr v-for="ch in data.channels" :key="ch.channel" class="border-t border-zinc-100">
                <td class="py-2.5 font-medium text-zinc-700">{{ ch.channel }}</td>
                <td class="py-2.5 text-center tabular-nums text-zinc-600">{{ ch.total }}</td>
                <td class="py-2.5 text-center tabular-nums text-zinc-600">{{ ch.interviewed }}</td>
                <td class="py-2.5 text-center">
                  <span
                    class="rounded-md px-1.5 py-0.5 text-[11.5px] font-semibold tabular-nums"
                    :class="
                      ch.interviewed === 0 ? 'bg-zinc-50 text-zinc-400' : 'bg-emerald-50 text-emerald-600'
                    "
                  >
                    {{ pctFmt(pct(ch.interviewed, ch.total)) }}
                  </span>
                </td>
                <td class="py-2.5 text-center tabular-nums text-zinc-600">{{ ch.offers || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <!-- 复盘得分趋势 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5">
          <div class="mb-2 flex items-center justify-between">
            <h2 class="text-[14.5px] font-bold text-zinc-800">复盘得分趋势</h2>
            <span class="text-[11.5px] text-zinc-400">面试表现是否在变好</span>
          </div>
          <div
            v-if="(data.review_trend ?? []).length === 0"
            class="py-10 text-center text-[13px] text-zinc-400"
          >
            暂无复盘报告，去「面试复盘」生成一份
          </div>
          <div v-else class="h-[220px]">
            <VChart :option="reviewOption" />
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
