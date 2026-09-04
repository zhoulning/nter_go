<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { NButton, NEmpty, NSlider, useDialog, useMessage } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
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

const bestScoreId = computed(() => {
  if (withOffers.value.length < 2) return -1
  let best = -1
  let bestId = -1
  for (const { offer } of withOffers.value) {
    const s = weightedScore(offer)
    if (s > best) {
      best = s
      bestId = offer.id
    }
  }
  return bestId
})

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
      center: ['50%', '46%'],
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
        data: withOffers.value.map(({ offer }) => ({
          name: offer.company,
          value: OFFER_DIMS.map((d) => offer[d.key]),
          areaStyle: { opacity: 0.12 },
          lineStyle: { width: 2 },
        })),
      },
    ],
  }
})

// ---- 展示辅助 ----
function annualPackage(offer: OfferInfo): string {
  if (!offer.monthly_salary || !offer.months) return '—'
  const wan = (offer.monthly_salary * offer.months) / 10
  return `${wan.toFixed(0)} 万（${offer.monthly_salary}K × ${offer.months}）`
}

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
    <header class="fade-up flex items-end justify-between px-7 pb-4 pt-6">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">Offer 对比</h1>
        <p class="mt-1 text-[13px] text-zinc-400">
          录入各家的 Offer 信息与主观评分，调权重看加权总分，辅助最终决策
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
      <div v-if="missingOffers.length" class="px-7 pb-3.5">
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
        <!-- 权重配置 -->
        <div class="px-7 pb-3.5">
          <div class="rounded-2xl border border-zinc-200/70 bg-white p-4">
            <div class="mb-3 flex items-center justify-between">
              <h2 class="text-[13.5px] font-bold text-zinc-800">决策权重</h2>
              <NButton quaternary size="tiny" @click="resetWeights">恢复默认</NButton>
            </div>
            <div
              v-for="dim in OFFER_DIMS"
              :key="dim.key"
              class="flex items-center gap-3"
            >
              <span class="w-[64px] shrink-0 text-[12.5px] text-zinc-600">{{ dim.label }}</span>
              <NSlider
                v-model:value="weights[dim.key]"
                :min="0"
                :max="5"
                :step="0.5"
                :tooltip="false"
                @update:value="saveWeights"
              />
              <span class="w-8 shrink-0 text-right text-[12px] tabular-nums text-zinc-500">
                {{ weights[dim.key].toFixed(1).replace('.0', '') }}
              </span>
            </div>
          </div>
        </div>

        <!-- 雷达 + 对比表 -->
        <div class="grid grid-cols-1 gap-3.5 px-7 xl:grid-cols-5">
          <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 xl:col-span-2">
            <h2 class="mb-1 text-[14.5px] font-bold text-zinc-800">五维评分对比</h2>
            <div class="h-[360px]">
              <VChart :option="radarOption" />
            </div>
          </section>

          <section class="min-w-0 rounded-2xl border border-zinc-200/70 bg-white p-5 xl:col-span-3">
            <div class="mb-3 flex items-center justify-between">
              <h2 class="text-[14.5px] font-bold text-zinc-800">Offer 明细对比</h2>
              <span class="text-[11.5px] text-zinc-400">点击列头公司名可编辑</span>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[560px] text-[12.5px]">
                <thead>
                  <tr class="border-b border-zinc-100">
                    <th class="pb-2.5 pr-3 text-left text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
                      维度
                    </th>
                    <th
                      v-for="{ opp } in withOffers"
                      :key="opp.id"
                      class="pb-2.5 text-left"
                    >
                      <button
                        class="flex items-center gap-1.5 font-semibold text-zinc-700 hover:text-indigo-600"
                        @click="openCreate(opp)"
                      >
                        <span
                          class="grid h-5 w-5 place-items-center rounded-md text-[10px] font-bold text-white"
                          :style="{ background: avatarGradient(opp.company) }"
                        >
                          {{ opp.company.slice(0, 1) }}
                        </span>
                        {{ opp.company }}
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr class="border-b border-zinc-50">
                    <td class="py-2 pr-3 text-zinc-400">状态</td>
                    <td v-for="{ opp } in withOffers" :key="opp.id" class="py-2">
                      <span
                        class="rounded-md px-1.5 py-0.5 text-[11px] font-semibold"
                        :class="
                          opp.status === 'accepted'
                            ? 'bg-teal-50 text-teal-600'
                            : 'bg-emerald-50 text-emerald-600'
                        "
                      >
                        {{ statusLabelOf(opp.status) }}
                      </span>
                    </td>
                  </tr>
                  <tr class="border-b border-zinc-50">
                    <td class="py-2 pr-3 text-zinc-400">年薪估算</td>
                    <td v-for="{ offer } in withOffers" :key="offer.id" class="py-2 font-semibold tabular-nums text-zinc-800">
                      {{ annualPackage(offer) }}
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
                    <td class="py-2 pr-3 align-top text-zinc-400">{{ row[0] }}</td>
                    <td
                      v-for="{ offer } in withOffers"
                      :key="offer.id"
                      class="max-w-[180px] py-2 pr-4 align-top text-zinc-600"
                    >
                      {{ offer[row[1]] || '—' }}
                    </td>
                  </tr>
                  <tr
                    v-for="dim in OFFER_DIMS"
                    :key="dim.key"
                    class="border-b border-zinc-50"
                  >
                    <td class="py-2 pr-3 text-zinc-400">{{ dim.label }}</td>
                    <td v-for="{ offer } in withOffers" :key="offer.id" class="py-2">
                      <span class="inline-flex items-center gap-1.5">
                        <span class="font-semibold tabular-nums text-zinc-700">{{ offer[dim.key] }}</span>
                        <span class="flex gap-0.5">
                          <span
                            v-for="i in 5"
                            :key="i"
                            class="h-1.5 w-1.5 rounded-full"
                            :class="i <= offer[dim.key] ? 'bg-indigo-400' : 'bg-zinc-200'"
                          />
                        </span>
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <td class="py-3 pr-3 text-[13px] font-bold text-zinc-800">加权总分</td>
                    <td v-for="{ offer } in withOffers" :key="offer.id" class="py-3">
                      <span
                        class="inline-flex items-baseline gap-1 rounded-lg px-2 py-1"
                        :class="
                          offer.id === bestScoreId && withOffers.length > 1
                            ? 'bg-emerald-50 text-emerald-600 ring-1 ring-emerald-200'
                            : 'text-zinc-700'
                        "
                      >
                        <span class="text-[16px] font-bold tabular-nums">
                          {{ weightedScore(offer).toFixed(2) }}
                        </span>
                        <span
                          v-if="offer.id === bestScoreId && withOffers.length > 1"
                          class="text-[10.5px] font-semibold"
                        >
                          推荐
                        </span>
                      </span>
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
