<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { NButton, NEmpty, useDialog, useMessage } from 'naive-ui'
import { AddOutline, PencilOutline, RemoveOutline, TrophyOutline } from '@vicons/ionicons5'
import { api } from '../api'
import type { OfferInfo } from '../api'
import type { EChartsCoreOption } from 'echarts/core'
import type { Opportunity } from '../types'
import {
  CHART_FONT,
  DEFAULT_OFFER_WEIGHTS,
  OFFER_DIMS,
  avatarGradient,
} from '../types'
import type { OfferDimKey } from '../types'
import VChart from '../components/VChart.vue'
import OfferModal from '../components/OfferModal.vue'

const message = useMessage()
const dialog = useDialog()

const opportunities = ref<Opportunity[]>([])
const offers = ref<OfferInfo[]>([])
const loading = ref(true)

const modalShow = ref(false)
const editingOpp = ref<Opportunity | null>(null)
const editingExisting = ref<OfferInfo | null>(null)

// ---- 权重（存浏览器本地）----
const WEIGHTS_KEY = 'interview-go:offer-weights'
const weights = reactive<Record<OfferDimKey, number>>({ ...DEFAULT_OFFER_WEIGHTS })

function loadWeights() {
  try {
    const raw = localStorage.getItem(WEIGHTS_KEY)
    if (raw) Object.assign(weights, JSON.parse(raw))
  } catch {
    /* 忽略损坏的本地数据 */
  }
}
function saveWeights() {
  localStorage.setItem(WEIGHTS_KEY, JSON.stringify(weights))
}
function resetWeights() {
  Object.assign(weights, DEFAULT_OFFER_WEIGHTS)
  saveWeights()
}
function bumpWeight(dim: OfferDimKey, delta: number) {
  const next = Math.min(5, Math.max(0, Math.round((weights[dim] + delta) * 2) / 2))
  if (next === weights[dim]) return
  weights[dim] = next
  saveWeights()
}

onMounted(async () => {
  loadWeights()
  try {
    const [oppData, offerData] = await Promise.all([api.listOpportunities(), api.listOffers()])
    opportunities.value = oppData.items
    offers.value = offerData.items
  } catch (e) {
    message.error((e as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
})

const OFFER_STAGE = ['offer', 'accepted']

const offerOpps = computed(() =>
  opportunities.value
    .filter((o) => OFFER_STAGE.includes(o.status))
    .sort((a, b) => (a.status === 'accepted' ? 1 : 0) - (b.status === 'accepted' ? 1 : 0)),
)

const offerByOppId = computed(() => {
  const map = new Map<number, OfferInfo>()
  for (const o of offers.value) map.set(o.opportunity_id, o)
  return map
})

/** 已有 Offer 记录的（用于对比表与雷达图） */
const withOffers = computed(() =>
  offerOpps.value
    .map((opp) => ({ opp, offer: offerByOppId.value.get(opp.id) }))
    .filter((x): x is { opp: Opportunity; offer: OfferInfo } => !!x.offer),
)

/** 还没录入 Offer 的 */
const missingOffers = computed(() =>
  offerOpps.value.filter((opp) => !offerByOppId.value.has(opp.id)),
)

// ---- 加权总分 ----
function weightedScore(offer: OfferInfo): number {
  let sum = 0
  let totalW = 0
  for (const dim of OFFER_DIMS) {
    const w = weights[dim.key] ?? 0
    totalW += w
    sum += w * (offer[dim.key] ?? 3)
  }
  return totalW > 0 ? sum / totalW : 0
}

function annualWan(offer: OfferInfo): number | null {
  if (!offer.monthly_salary || !offer.months) return null
  return (offer.monthly_salary * offer.months) / 10
}
function formatNum(v: number): string {
  return (Math.round(v * 10) / 10).toString()
}
function annualText(offer: OfferInfo): string {
  const wan = annualWan(offer)
  return wan === null ? '—' : `${formatNum(wan)} 万`
}
function annualDetail(offer: OfferInfo): string {
  if (!offer.monthly_salary || !offer.months) return ''
  return `（${formatNum(offer.monthly_salary)}K × ${offer.months}）`
}

// ---- 综合排名（决策台与表格共用的顺序）----
const ranked = computed(() =>
  withOffers.value
    .map((x) => ({ opp: x.opp, offer: x.offer, score: weightedScore(x.offer), annual: annualWan(x.offer) }))
    .sort((a, b) => b.score - a.score),
)

const best = computed(() => ranked.value[0] ?? null)
const scoreGap = computed(() =>
  ranked.value.length >= 2 ? ranked.value[0].score - ranked.value[1].score : null,
)

const maxAnnual = computed(() => {
  const vals = ranked.value.map((r) => r.annual).filter((v): v is number => v !== null)
  return vals.length ? Math.max(...vals) : 0
})

/** 某维度在所有 Offer 中的最高/最低分（表格高亮用） */
function dimExtremes(key: OfferDimKey) {
  const vals = ranked.value.map((r) => r.offer[key])
  return { max: Math.max(...vals), min: Math.min(...vals) }
}
function dimClass(key: OfferDimKey, val: number): string {
  if (ranked.value.length < 2) return 'text-zinc-700'
  const { max, min } = dimExtremes(key)
  if (val === max) return 'font-bold text-emerald-600'
  if (val === min && min !== max) return 'text-zinc-400'
  return 'font-medium text-zinc-700'
}

const totalWeight = computed(() =>
  OFFER_DIMS.reduce((acc, d) => acc + (weights[d.key] ?? 0), 0),
)

// ---- 雷达图 ----
const RADAR_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']

const radarOption = computed<EChartsCoreOption>(() => {
  return {
    textStyle: { fontFamily: CHART_FONT },
    color: RADAR_COLORS,
    legend: {
      bottom: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { fontSize: 11, color: '#71717a' },
    },
    tooltip: {},
    radar: {
      indicator: OFFER_DIMS.map((d) => ({ name: d.label, max: 5 })),
      radius: '58%',
      center: ['50%', '44%'],
      splitNumber: 5,
      axisName: { color: '#71717a', fontSize: 11 },
      splitLine: { lineStyle: { color: '#e4e4e7' } },
      splitArea: { areaStyle: { color: ['#fafafa', '#fff'] } },
      axisLine: { lineStyle: { color: '#e4e4e7' } },
    },
    series: [
      {
        type: 'radar',
        symbolSize: 3,
        data: ranked.value.map(({ offer }) => ({
          name: offer.company,
          value: OFFER_DIMS.map((d) => offer[d.key]),
          areaStyle: { opacity: 0.12 },
          lineStyle: { width: 2 },
        })),
      },
    ],
  }
})

function openCreate(opp: Opportunity) {
  editingOpp.value = opp
  editingExisting.value = offerByOppId.value.get(opp.id) ?? null
  modalShow.value = true
}

function onSaved(offer: OfferInfo) {
  const idx = offers.value.findIndex((o) => o.opportunity_id === offer.opportunity_id)
  if (idx >= 0) offers.value.splice(idx, 1, offer)
  else offers.value.push(offer)
}

function statusLabelOf(status: string | null) {
  return status === 'accepted' ? '已接受' : '已拿 Offer'
}
</script>

<template>
  <div class="flex h-full flex-col">
    <header class="fade-up flex items-end justify-between px-7 pb-4 pt-6 max-md:px-4 max-md:pt-4">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">Offer 对比</h1>
        <p class="mt-1 text-[13px] text-zinc-400">
          把手上的 Offer 放上天平：按你在意的维度调权重，综合分与差距一目了然
        </p>
      </div>
    </header>

    <div v-if="loading" class="grid flex-1 place-items-center text-sm text-zinc-400">
      正在加载…
    </div>

    <NEmpty
      v-else-if="offerOpps.length === 0"
      class="flex-1"
      size="large"
      description="还没有到 Offer 阶段的岗位 · 先去「岗位跟踪」推进面试吧"
    />

    <div v-else class="fade-up-d1 min-h-0 flex-1 overflow-y-auto pb-6">
      <!-- 待录入 -->
      <div v-if="missingOffers.length" class="px-7 pb-3.5 max-md:px-4">
        <div class="rounded-2xl border border-dashed border-amber-300/70 bg-amber-50/50 p-4">
          <div class="mb-2.5 text-[12.5px] font-semibold text-amber-600">
            以下岗位已到 Offer 阶段，录入信息后参与对比
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="opp in missingOffers"
              :key="opp.id"
              class="flex items-center gap-2 rounded-full border border-amber-300/80 bg-white py-1.5 pl-1.5 pr-3.5 transition-all hover:border-amber-400 hover:shadow-sm"
              @click="openCreate(opp)"
            >
              <span
                class="grid h-6 w-6 place-items-center rounded-full text-[10.5px] font-bold text-white"
                :style="{ background: avatarGradient(opp.company) }"
              >
                {{ opp.company.slice(0, 1) }}
              </span>
              <span class="text-[12.5px] font-medium text-zinc-700">{{ opp.company }}</span>
              <n-icon :component="AddOutline" :size="13" class="text-amber-500" />
            </button>
          </div>
        </div>
      </div>

      <template v-if="withOffers.length">
        <!-- 决策台：推荐卡 + 其余排名 -->
        <div class="grid grid-cols-1 gap-3.5 px-7 pb-3.5 max-md:px-4 xl:grid-cols-5">
          <!-- 综合推荐 -->
          <section
            v-if="best"
            class="group cursor-pointer rounded-2xl border border-emerald-200/70 bg-gradient-to-br from-emerald-50/80 via-white to-white p-5 transition-shadow hover:shadow-md max-md:p-4 xl:col-span-3"
            title="点击编辑这份 Offer"
            @click="openCreate(best.opp)"
          >
            <div class="flex items-center justify-between">
              <span class="inline-flex items-center gap-1.5 text-[12.5px] font-bold text-emerald-600">
                <n-icon :component="TrophyOutline" :size="15" />
                综合推荐
              </span>
              <span class="inline-flex items-center gap-2">
                <span
                  class="rounded-md px-1.5 py-0.5 text-[11px] font-semibold"
                  :class="
                    best.opp.status === 'accepted'
                      ? 'bg-teal-50 text-teal-600'
                      : 'bg-emerald-50 text-emerald-600'
                  "
                >
                  {{ statusLabelOf(best.opp.status) }}
                </span>
                <n-icon
                  :component="PencilOutline"
                  :size="13"
                  class="text-zinc-300 transition-colors group-hover:text-emerald-500 max-md:text-zinc-400"
                />
              </span>
            </div>

            <div class="mt-3 flex items-center gap-3">
              <span
                class="grid h-10 w-10 shrink-0 place-items-center rounded-xl text-[15px] font-bold text-white"
                :style="{ background: avatarGradient(best.opp.company) }"
              >
                {{ best.opp.company.slice(0, 1) }}
              </span>
              <div class="min-w-0">
                <div class="truncate text-[16px] font-bold text-zinc-900">{{ best.opp.company }}</div>
                <div class="truncate text-[12px] text-zinc-500">
                  {{ best.opp.position }}{{ best.opp.city ? ` · ${best.opp.city}` : '' }}
                </div>
              </div>
            </div>

            <div class="mt-4 flex flex-wrap gap-x-10 gap-y-3">
              <div>
                <div class="text-[11.5px] text-zinc-400">年薪估算</div>
                <div class="mt-1 flex items-baseline gap-1.5">
                  <span class="text-[26px] font-bold leading-none tabular-nums text-zinc-900">
                    {{ annualText(best.offer) }}
                  </span>
                  <span class="text-[11.5px] text-zinc-400">{{ annualDetail(best.offer) }}</span>
                </div>
              </div>
              <div>
                <div class="text-[11.5px] text-zinc-400">加权总分</div>
                <div class="mt-1 flex items-baseline gap-1.5">
                  <span class="text-[26px] font-bold leading-none tabular-nums text-emerald-600">
                    {{ best.score.toFixed(2) }}
                  </span>
                  <span class="text-[11.5px] text-zinc-400">
                    {{ scoreGap !== null ? `领先第 2 名 ${scoreGap.toFixed(2)} 分` : '目前唯一的 Offer' }}
                  </span>
                </div>
              </div>
            </div>

            <div class="mt-4 grid gap-1.5 sm:grid-cols-2 sm:gap-x-6">
              <div v-for="dim in OFFER_DIMS" :key="dim.key" class="flex items-center gap-2.5">
                <span class="w-[56px] shrink-0 text-[11.5px] text-zinc-500">{{ dim.label }}</span>
                <div class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-zinc-100">
                  <div
                    class="h-full rounded-full bg-gradient-to-r from-emerald-400 to-emerald-300"
                    :style="{ width: `${(best.offer[dim.key] / 5) * 100}%` }"
                  />
                </div>
                <span class="w-3 shrink-0 text-right text-[11.5px] font-semibold tabular-nums text-zinc-600">
                  {{ best.offer[dim.key] }}
                </span>
              </div>
            </div>
          </section>

          <!-- 其余 Offer 排名 -->
          <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 max-md:p-4 xl:col-span-2">
            <h2 class="text-[14.5px] font-bold text-zinc-800">其余 Offer</h2>
            <div
              v-if="ranked.length <= 1"
              class="mt-3 rounded-xl bg-zinc-50 px-3.5 py-4 text-[12.5px] leading-relaxed text-zinc-400"
            >
              目前只有一家到手的 Offer。继续推进其他流程，或调整左侧权重检验它是否真的达标。
            </div>
            <div v-else class="mt-1 flex flex-col">
              <button
                v-for="(r, i) in ranked.slice(1)"
                :key="r.opp.id"
                class="group flex items-center gap-3 rounded-xl px-2 py-2.5 text-left transition-colors hover:bg-zinc-50"
                :title="`点击编辑「${r.opp.company}」的 Offer`"
                @click="openCreate(r.opp)"
              >
                <span class="w-6 shrink-0 text-[12px] font-bold tabular-nums text-zinc-300">
                  #{{ i + 2 }}
                </span>
                <span
                  class="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-[11px] font-bold text-white"
                  :style="{ background: avatarGradient(r.opp.company) }"
                >
                  {{ r.opp.company.slice(0, 1) }}
                </span>
                <span class="min-w-0 flex-1">
                  <span class="flex items-center gap-1.5">
                    <span class="truncate text-[13px] font-semibold text-zinc-800">{{ r.opp.company }}</span>
                    <span
                      v-if="r.opp.status === 'accepted'"
                      class="shrink-0 rounded bg-teal-50 px-1 py-px text-[10px] font-semibold text-teal-600"
                    >
                      已接受
                    </span>
                  </span>
                  <span class="block truncate text-[11.5px] text-zinc-400">
                    {{ r.opp.position }}{{ r.annual !== null ? ` · 年薪 ${formatNum(r.annual)} 万` : '' }}
                  </span>
                </span>
                <span class="shrink-0 text-right">
                  <span class="block text-[13px] font-bold tabular-nums text-zinc-700">
                    {{ r.score.toFixed(2) }}
                  </span>
                  <span class="block text-[10.5px] tabular-nums text-zinc-400">
                    落后 {{ (ranked[0].score - r.score).toFixed(2) }}
                  </span>
                </span>
              </button>
            </div>
          </section>
        </div>

        <!-- 决策权重（紧凑步进条） -->
        <div class="px-7 pb-3.5 max-md:px-4">
          <div class="flex flex-wrap items-center gap-x-5 gap-y-2.5 rounded-2xl border border-zinc-200/70 bg-white px-4 py-3 max-md:px-3.5">
            <div class="flex items-baseline gap-2">
              <span class="text-[13px] font-bold text-zinc-800">决策权重</span>
              <span class="text-[11px] text-zinc-400">0–5 · 即时影响综合分</span>
            </div>
            <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
              <div v-for="dim in OFFER_DIMS" :key="dim.key" class="flex items-center gap-1.5">
                <span class="text-[12.5px] text-zinc-600">{{ dim.label }}</span>
                <button
                  class="grid h-6 w-6 place-items-center rounded-md border border-zinc-200 text-[13px] leading-none text-zinc-400 transition-colors hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-500"
                  :disabled="weights[dim.key] <= 0"
                  :class="{ 'cursor-not-allowed opacity-40': weights[dim.key] <= 0 }"
                  @click="bumpWeight(dim.key, -0.5)"
                >
                  <n-icon :component="RemoveOutline" :size="12" />
                </button>
                <span class="w-5 text-center text-[12.5px] font-semibold tabular-nums text-zinc-800">
                  {{ formatNum(weights[dim.key]) }}
                </span>
                <button
                  class="grid h-6 w-6 place-items-center rounded-md border border-zinc-200 text-[13px] leading-none text-zinc-400 transition-colors hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-500"
                  :disabled="weights[dim.key] >= 5"
                  :class="{ 'cursor-not-allowed opacity-40': weights[dim.key] >= 5 }"
                  @click="bumpWeight(dim.key, 0.5)"
                >
                  <n-icon :component="AddOutline" :size="12" />
                </button>
              </div>
            </div>
            <NButton quaternary size="tiny" class="ml-auto" @click="resetWeights">恢复默认</NButton>
          </div>
        </div>

        <!-- 雷达 + 对比表 -->
        <div class="grid grid-cols-1 gap-3.5 px-7 max-md:px-4 xl:grid-cols-5">
          <section class="flex flex-col rounded-2xl border border-zinc-200/70 bg-white p-5 max-md:p-4 xl:col-span-2">
            <h2 class="mb-1 text-[14.5px] font-bold text-zinc-800">五维评分画像</h2>
            <div class="min-h-[320px] flex-1">
              <VChart :option="radarOption" />
            </div>
          </section>

          <section class="min-w-0 rounded-2xl border border-zinc-200/70 bg-white p-5 max-md:p-4 xl:col-span-3">
            <div class="mb-3 flex items-center justify-between">
              <h2 class="text-[14.5px] font-bold text-zinc-800">Offer 明细对比</h2>
              <span class="text-[11.5px] text-zinc-400">点击列头公司名可编辑</span>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[560px] text-[12.5px]">
                <thead>
                  <tr class="border-b border-zinc-100">
                    <th class="sticky left-0 z-10 bg-white pb-2.5 pr-3 text-left text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
                      维度
                    </th>
                    <th v-for="r in ranked" :key="r.opp.id" class="pb-2.5 text-left">
                      <button
                        class="flex items-center gap-1.5 font-semibold text-zinc-700 hover:text-indigo-600"
                        @click="openCreate(r.opp)"
                      >
                        <span
                          class="grid h-5 w-5 place-items-center rounded-md text-[10px] font-bold text-white"
                          :style="{ background: avatarGradient(r.opp.company) }"
                        >
                          {{ r.opp.company.slice(0, 1) }}
                        </span>
                        {{ r.opp.company }}
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr class="border-b border-zinc-50">
                    <td class="sticky left-0 z-10 bg-white py-2 pr-3 text-zinc-400">状态</td>
                    <td v-for="r in ranked" :key="r.opp.id" class="py-2">
                      <span
                        class="rounded-md px-1.5 py-0.5 text-[11px] font-semibold"
                        :class="
                          r.opp.status === 'accepted'
                            ? 'bg-teal-50 text-teal-600'
                            : 'bg-emerald-50 text-emerald-600'
                        "
                      >
                        {{ statusLabelOf(r.opp.status) }}
                      </span>
                    </td>
                  </tr>
                  <tr class="border-b border-zinc-50">
                    <td class="sticky left-0 z-10 bg-white py-2 pr-3 text-zinc-400">年薪估算</td>
                    <td v-for="r in ranked" :key="r.opp.id" class="py-2 pr-4">
                      <div class="flex items-center gap-2">
                        <span
                          class="whitespace-nowrap font-semibold tabular-nums"
                          :class="r.annual !== null && r.annual === maxAnnual ? 'font-bold text-emerald-600' : 'text-zinc-800'"
                        >
                          {{ annualText(r.offer) }}
                        </span>
                        <div
                          v-if="r.annual !== null && maxAnnual > 0"
                          class="h-1 w-14 shrink-0 overflow-hidden rounded-full bg-zinc-100"
                        >
                          <div
                            class="h-full rounded-full bg-emerald-400/80"
                            :style="{ width: `${(r.annual / maxAnnual) * 100}%` }"
                          />
                        </div>
                      </div>
                    </td>
                  </tr>
                  <tr
                    v-for="row in [
                      ['签字费 / 奖金', 'signing_bonus'],
                      ['股票 / 期权', 'stock'],
                      ['公积金 / 福利', 'welfare'],
                      ['加班情况', 'overtime'],
                      ['通勤', 'commute'],
                    ] as const"
                    :key="row[1]"
                    class="border-b border-zinc-50"
                  >
                    <td class="sticky left-0 z-10 bg-white py-2 pr-3 align-top text-zinc-400">{{ row[0] }}</td>
                    <td
                      v-for="r in ranked"
                      :key="r.opp.id"
                      class="max-w-[180px] py-2 pr-4 align-top text-zinc-600"
                    >
                      {{ r.offer[row[1]] || '—' }}
                    </td>
                  </tr>
                  <tr class="border-b border-zinc-50">
                    <td class="sticky left-0 z-10 bg-white py-2 pr-3 align-top text-zinc-400">备注</td>
                    <td
                      v-for="r in ranked"
                      :key="r.opp.id"
                      class="max-w-[180px] py-2 pr-4 align-top text-zinc-500"
                      :title="r.offer.note || ''"
                    >
                      <span class="line-clamp-2">{{ r.offer.note || '—' }}</span>
                    </td>
                  </tr>
                  <tr
                    v-for="dim in OFFER_DIMS"
                    :key="dim.key"
                    class="border-b border-zinc-50"
                  >
                    <td class="sticky left-0 z-10 bg-white py-2 pr-3 text-zinc-400">{{ dim.label }}</td>
                    <td v-for="r in ranked" :key="r.opp.id" class="py-2">
                      <span class="text-[13px] tabular-nums" :class="dimClass(dim.key, r.offer[dim.key])">
                        {{ r.offer[dim.key] }}
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <td class="sticky left-0 z-10 bg-white py-3 pr-3 text-[13px] font-bold text-zinc-800">
                      加权总分
                    </td>
                    <td v-for="(r, i) in ranked" :key="r.opp.id" class="py-3">
                      <div class="flex items-center gap-1.5">
                        <span
                          class="text-[17px] font-bold tabular-nums"
                          :class="i === 0 ? 'text-emerald-600' : 'text-zinc-700'"
                        >
                          {{ r.score.toFixed(2) }}
                        </span>
                        <span
                          v-if="i === 0 && ranked.length > 1"
                          class="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10.5px] font-bold text-emerald-600 ring-1 ring-emerald-200"
                        >
                          推荐
                        </span>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div class="mt-2 text-[11px] text-zinc-400">
                加权总分 = Σ(维度评分 × 权重) ÷ Σ权重，当前权重合计 {{ totalWeight }}
              </div>
            </div>
          </section>
        </div>
      </template>
    </div>

    <OfferModal
      v-model:show="modalShow"
      :opportunity="editingOpp"
      :existing="editingExisting"
      @saved="onSaved"
    />
  </div>
</template>
