<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import {
  AddOutline,
  ArrowBackOutline,
  CreateOutline,
  DocumentTextOutline,
  SparklesOutline,
} from '@vicons/ionicons5'
import { api } from '../api'
import type {
  MatchReportInfo,
  OfferInfo,
  Opportunity,
  RecordingInfo,
  ResearchNote,
  Resume,
  RoundEvent,
  RoundInfo,
} from '../types'
import {
  CHART_FONT,
  MATCH_DIMENSIONS,
  MATCH_VERDICT_ICON,
  MATCH_VERDICT_META,
  MATCH_WEIGHT_LABEL,
  NOTE_TYPE_META,
  ROUND_LABEL,
  ROUND_RESULT_META,
  STATUSES,
  avatarGradient,
} from '../types'
import { daysSince, eventLabel } from '../utils'
import MarkdownView from '../components/MarkdownView.vue'
import MockInterviewPanel from '../components/MockInterviewPanel.vue'
import OfferModal from '../components/OfferModal.vue'
import OpportunityModal from '../components/OpportunityModal.vue'
import PredictionPanel from '../components/PredictionPanel.vue'
import RoundModal from '../components/RoundModal.vue'
import VChart from '../components/VChart.vue'
import type { EChartsCoreOption } from 'echarts/core'

const props = defineProps<{ oppId: number | null }>()
const emit = defineEmits<{ (e: 'back'): void }>()

const message = useMessage()
const dialog = useDialog()

const activeTab = ref('overview')
const loading = ref(true)
const opp = ref<Opportunity | null>(null)
const resumes = ref<Resume[]>([])
const notes = ref<ResearchNote[]>([])
const matchReport = ref<MatchReportInfo | null>(null)
const recordings = ref<RecordingInfo[]>([])
const offer = ref<OfferInfo | null>(null)

// ---- 调研笔记 ----
const activeNoteType = ref('company')
const noteEditing = ref(false)
const noteDraft = ref('')
const noteSaving = ref(false)
const outlining = ref<string | null>(null)

// ---- 匹配度 ----
const matchResumeId = ref<number | null>(null)
const generating = ref(false)

// ---- 弹窗 ----
const editShow = ref(false)
const roundShow = ref(false)
const editingRound = ref<RoundEvent | null>(null)
const offerShow = ref(false)

async function load() {
  if (!props.oppId) return
  loading.value = true
  try {
    const [opps, resumeData] = await Promise.all([api.listOpportunities(), api.listResumes()])
    resumes.value = resumeData.items
    const found = opps.items.find((o) => o.id === props.oppId)
    if (!found) {
      message.error('该岗位不存在（可能已被删除）')
      emit('back')
      return
    }
    opp.value = found
    matchResumeId.value = found.resume_id
    const [noteData, matchData, recData, offerData] = await Promise.all([
      api.listNotes(found.id),
      api.getMatchReport(found.id),
      api.listRecordings(),
      api.listOffers(),
    ])
    notes.value = noteData.items
    matchReport.value = matchData.report
    recordings.value = recData.items.filter((r) => r.opportunity_id === found.id)
    offer.value = offerData.items.find((o) => o.opportunity_id === found.id) ?? null
  } catch (e) {
    message.error((e as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.oppId, load)

const statusMeta = computed(() => STATUSES.find((s) => s.key === opp.value?.status))

const sortedRounds = computed(() => {
  const rounds = [...(opp.value?.rounds ?? [])]
  rounds.sort((a, b) => (a.scheduled_at ?? '').localeCompare(b.scheduled_at ?? ''))
  return rounds
})

const metaItems = computed(() => {
  const o = opp.value
  if (!o) return []
  return [
    { label: '部门 / 业务线', value: o.department },
    { label: '城市', value: o.city },
    { label: '工作地址', value: o.address },
    { label: '薪资范围', value: o.salary_range },
    { label: '渠道', value: o.channel },
    { label: '投递时间', value: o.applied_at ? new Date(o.applied_at).toLocaleDateString() : '未投递' },
    { label: '关联简历', value: o.resume?.name ?? null },
  ]
})

// ---- 调研笔记 ----

const noteByType = computed<Record<string, ResearchNote | undefined>>(() => {
  const map: Record<string, ResearchNote | undefined> = {}
  for (const n of notes.value) map[n.note_type] = n
  return map
})
const currentNote = computed(() => noteByType.value[activeNoteType.value])
const currentNoteMeta = computed(() => NOTE_TYPE_META.find((n) => n.key === activeNoteType.value))

function switchNoteType(key: string) {
  activeNoteType.value = key
  noteEditing.value = false
}

function startEditNote() {
  noteDraft.value = currentNote.value?.content ?? ''
  noteEditing.value = true
}

async function saveNote() {
  if (!opp.value) return
  noteSaving.value = true
  try {
    const saved = await api.saveNote(opp.value.id, activeNoteType.value, {
      content: noteDraft.value,
      ai_generated: currentNote.value?.ai_generated ?? false,
    })
    const idx = notes.value.findIndex((n) => n.note_type === activeNoteType.value)
    if (idx >= 0) notes.value[idx] = saved
    else notes.value.push(saved)
    noteEditing.value = false
    message.success('已保存')
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    noteSaving.value = false
  }
}

function generateOutline() {
  if (!opp.value) return
  const noteType = activeNoteType.value
  const run = (overwrite: boolean) => {
    outlining.value = noteType
    api
      .generateOutline(opp.value!.id, noteType, overwrite)
      .then((saved) => {
        const idx = notes.value.findIndex((n) => n.note_type === noteType)
        if (idx >= 0) notes.value[idx] = saved
        else notes.value.push(saved)
        noteEditing.value = false
        message.success('AI 提纲已生成，记得补充核实内容')
      })
      .catch((e) => message.error((e as Error).message || '生成失败', { duration: 6000 }))
      .finally(() => (outlining.value = null))
  }
  if (currentNote.value?.content?.trim()) {
    dialog.warning({
      title: '覆盖现有内容？',
      content: '该笔记已有内容，AI 重新生成会覆盖它。建议先复制备份现有内容。',
      positiveText: '覆盖生成',
      negativeText: '取消',
      onPositiveClick: () => run(true),
    })
  } else {
    run(false)
  }
}

// ---- 匹配度 ----

async function generateMatch() {
  if (!opp.value) return
  generating.value = true
  try {
    matchReport.value = await api.generateMatchReport(opp.value.id, matchResumeId.value)
    message.success('匹配度报告已生成')
  } catch (e) {
    message.error((e as Error).message || '生成失败', { duration: 8000 })
  } finally {
    generating.value = false
  }
}

function deleteMatch() {
  if (!opp.value || !matchReport.value) return
  dialog.warning({
    title: '删除匹配度报告',
    content: '报告删除后不可恢复（可随时重新生成）。',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteMatchReport(opp.value!.id)
        matchReport.value = null
        message.success('已删除')
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}

function scoreGrade(score: number): { label: string; class: string } {
  if (score >= 85) return { label: '高度匹配', class: 'text-emerald-600' }
  if (score >= 70) return { label: '主体匹配', class: 'text-lime-600' }
  if (score >= 55) return { label: '有一定差距', class: 'text-amber-600' }
  return { label: '差距较大', class: 'text-rose-600' }
}

const radarOption = computed<EChartsCoreOption>(() => {
  const report = matchReport.value?.report
  const dims = MATCH_DIMENSIONS.map((d) => ({
    name: report?.dimension_labels?.[d.key] ?? d.label,
    max: 100,
  }))
  const values = MATCH_DIMENSIONS.map((d) => report?.dimensions?.[d.key] ?? 0)
  return {
    textStyle: { fontFamily: CHART_FONT },
    radar: {
      indicator: dims,
      radius: '65%',
      splitNumber: 4,
      axisName: { color: '#71717a', fontSize: 11 },
    },
    series: [
      {
        type: 'radar',
        areaStyle: { color: 'rgba(99,102,241,0.18)' },
        lineStyle: { color: '#6366f1', width: 2 },
        itemStyle: { color: '#6366f1' },
        data: [{ value: values, name: '匹配度' }],
      },
    ],
  }
})

const profileGroups = computed(() => {
  const p = matchReport.value?.report.job_profile
  if (!p) return []
  return (
    [
      ['硬性要求', p.hard, 'text-rose-600 bg-rose-50 border-rose-100'],
      ['技术栈', p.stack, 'text-indigo-600 bg-indigo-50 border-indigo-100'],
      ['软性要求', p.soft, 'text-sky-600 bg-sky-50 border-sky-100'],
      ['加分项', p.bonus, 'text-emerald-600 bg-emerald-50 border-emerald-100'],
    ] as const
  ).filter(([, arr]) => arr.length)
})

function exportMatchMd() {
  const report = matchReport.value
  if (!report || !opp.value) return
  const d = report.report
  const lines: string[] = []
  lines.push(`# 匹配度报告：${opp.value.company} · ${opp.value.position}`)
  lines.push('')
  lines.push(`- 匹配总分：**${d.total_score} / 100**`)
  lines.push(`- 评估简历：${report.resume_name ?? '未关联'}`)
  lines.push(`- 生成模型：${report.model}`)
  lines.push(`- 生成时间：${new Date(report.created_at).toLocaleString()}`)
  lines.push('')
  lines.push('## 五维匹配')
  for (const dim of MATCH_DIMENSIONS) {
    const label = d.dimension_labels?.[dim.key] ?? dim.label
    lines.push(`- ${label}：${d.dimensions?.[dim.key] ?? 0}`)
  }
  lines.push('')
  lines.push('## 岗位画像')
  const groups: [string, string[]][] = [
    ['硬性要求', d.job_profile.hard],
    ['技术栈', d.job_profile.stack],
    ['软性要求', d.job_profile.soft],
    ['加分项', d.job_profile.bonus],
  ]
  for (const [name, arr] of groups) {
    if (arr.length) {
      lines.push(`### ${name}`)
      for (const x of arr) lines.push(`- ${x}`)
      lines.push('')
    }
  }
  lines.push('## 逐条匹配')
  for (const item of d.items) {
    const v = MATCH_VERDICT_META[item.verdict]
    lines.push(`### ${MATCH_VERDICT_ICON[item.verdict] ?? ''} ${item.requirement}`)
    lines.push(
      `- 权重：${MATCH_WEIGHT_LABEL[item.weight] ?? item.weight}｜判定：${v?.label ?? item.verdict}`,
    )
    if (item.evidence) lines.push(`- 证据：${item.evidence}`)
    if (item.advice) lines.push(`- 建议：${item.advice}`)
    lines.push('')
  }
  if (d.focus.length) {
    lines.push('## 准备重点')
    for (const x of d.focus) lines.push(`- ${x}`)
    lines.push('')
  }
  if (d.resume_risks.length) {
    lines.push('## 简历追问风险')
    for (const x of d.resume_risks) lines.push(`- ${x}`)
    lines.push('')
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `匹配度报告-${opp.value.company}-${opp.value.position}.md`
  a.click()
  URL.revokeObjectURL(a.href)
}

// ---- 轮次与录音 ----

function editRound(round: RoundInfo | null) {
  if (round && opp.value) {
    // 轮次列表里的 RoundInfo 补上岗位信息构成 RoundModal 需要的 RoundEvent
    editingRound.value = {
      ...round,
      opportunity_id: opp.value.id,
      company: opp.value.company,
      position: opp.value.position,
    }
  } else {
    editingRound.value = null
  }
  roundShow.value = true
}

async function onRoundSaved() {
  await load()
}

async function onOfferSaved() {
  await load()
}

function deleteRound(round: RoundEvent) {
  dialog.warning({
    title: '删除轮次',
    content: `确定删除「${ROUND_LABEL[round.round_type] ?? '面试'}」这场轮次吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteRound(round.id)
        message.success('已删除')
        await load()
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}

const REC_STATUS: Record<string, { label: string; class: string }> = {
  uploaded: { label: '待转写', class: 'bg-zinc-100 text-zinc-500' },
  transcribing: { label: '转写中', class: 'bg-blue-50 text-blue-600' },
  transcribed: { label: '已转写', class: 'bg-emerald-50 text-emerald-600' },
  failed: { label: '转写失败', class: 'bg-rose-50 text-rose-600' },
}

function fmtDuration(sec: number | null): string {
  if (!sec) return '—'
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

// ---- Offer ----

async function deleteOffer() {
  if (!opp.value) return
  dialog.warning({
    title: '删除 Offer',
    content: '确定删除该岗位的 Offer 记录吗？',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteOffer(opp.value!.id)
        offer.value = null
        message.success('已删除')
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}

// ---- 编辑 / 删除岗位 ----

async function onEdited() {
  await load()
}

function deleteOpportunity() {
  if (!opp.value) return
  dialog.warning({
    title: '删除岗位',
    content: `确定删除「${opp.value.company} · ${opp.value.position}」吗？其轮次、录音、笔记等数据将一并删除，不可恢复。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteOpportunity(opp.value!.id)
        message.success('已删除')
        emit('back')
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-zinc-50/60">
    <!-- 顶栏 -->
    <div class="flex shrink-0 items-center gap-3 border-b border-zinc-200/70 bg-white px-5 py-3">
      <button
        class="flex items-center gap-1 rounded-lg px-2 py-1.5 text-[13px] text-zinc-500 transition-colors hover:bg-zinc-100"
        @click="emit('back')"
      >
        <n-icon :component="ArrowBackOutline" :size="15" />
        返回看板
      </button>
      <template v-if="opp">
        <div class="mx-1 h-5 w-px bg-zinc-200" />
        <div
          class="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-[15px] font-bold text-white shadow-sm"
          :style="{ background: avatarGradient(opp.company) }"
        >
          {{ opp.company.slice(0, 1) }}
        </div>
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="truncate text-[15px] font-bold text-zinc-900">{{ opp.company }}</span>
            <span
              class="shrink-0 rounded-md border px-1.5 text-[10.5px] font-bold leading-[18px]"
              :class="{
                'border-rose-200 bg-rose-50 text-rose-600': opp.priority === 'S',
                'border-amber-200 bg-amber-50 text-amber-600': opp.priority === 'A',
                'border-zinc-200 bg-zinc-50 text-zinc-500': opp.priority === 'B',
              }"
            >
              {{ opp.priority }}
            </span>
          </div>
          <div class="mt-0.5 flex items-center gap-1.5 text-[12px] text-zinc-500">
            <span
              class="inline-block h-1.5 w-1.5 rounded-full"
              :style="{ background: statusMeta?.color ?? '#94a3b8' }"
            />
            {{ statusMeta?.label ?? opp.status }}
            <span class="text-zinc-300">·</span>
            <span class="truncate">{{ opp.position }}</span>
            <span class="text-zinc-300">·</span>
            停留 {{ daysSince(opp.status_changed_at) }} 天
          </div>
        </div>
        <div class="ml-auto flex shrink-0 gap-2">
          <n-button size="small" @click="editShow = true">
            <template #icon><n-icon :component="CreateOutline" :size="14" /></template>
            编辑
          </n-button>
          <n-button size="small" type="error" secondary @click="deleteOpportunity">删除</n-button>
        </div>
      </template>
    </div>

    <div v-if="loading && !opp" class="grid flex-1 place-items-center text-[13px] text-zinc-400">
      加载中…
    </div>

    <!-- 内容区 -->
    <template v-else-if="opp">
      <n-tabs v-model:value="activeTab" type="line" class="min-h-0 flex-1 px-5">
        <!-- 概览 -->
        <n-tab-pane name="overview" tab="概览">
          <div class="max-h-[calc(100vh-180px)] overflow-y-auto pb-8">
            <div class="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
              <div v-for="item in metaItems" :key="item.label" class="rounded-xl bg-white px-3.5 py-2.5 shadow-sm">
                <div class="text-[11px] text-zinc-400">{{ item.label }}</div>
                <div class="mt-0.5 truncate text-[13px] font-medium text-zinc-700" :title="item.value ?? ''">
                  {{ item.value ?? '—' }}
                </div>
              </div>
            </div>

            <div class="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
              <div>
                <div class="mb-2 flex items-center justify-between">
                  <h3 class="text-[13.5px] font-semibold text-zinc-800">工作描述</h3>
                  <span v-if="opp.jd_text" class="text-[11px] text-zinc-400">{{ opp.jd_text.length }} 字</span>
                </div>
                <p
                  v-if="opp.jd_text"
                  class="max-h-[420px] overflow-y-auto whitespace-pre-wrap rounded-2xl border border-zinc-100 bg-white px-4 py-3 text-[13px] leading-relaxed text-zinc-700"
                >{{ opp.jd_text }}</p>
                <div
                  v-else
                  class="rounded-2xl border border-dashed border-zinc-200 px-4 py-8 text-center text-[12.5px] text-zinc-400"
                >
                  暂无工作描述 · 点右上角「编辑」补充，或新增时用 AI 提取
                </div>
              </div>
              <div>
                <h3 class="mb-2 text-[13.5px] font-semibold text-zinc-800">备注</h3>
                <p
                  v-if="opp.note"
                  class="whitespace-pre-wrap rounded-2xl border border-amber-100 bg-amber-50/70 px-4 py-3 text-[12.5px] leading-relaxed text-zinc-600"
                >{{ opp.note }}</p>
                <div v-else class="rounded-2xl border border-dashed border-zinc-200 px-4 py-8 text-center text-[12.5px] text-zinc-400">
                  暂无备注
                </div>
              </div>
            </div>
          </div>
        </n-tab-pane>

        <!-- 调研笔记 -->
        <n-tab-pane name="research" tab="调研笔记">
          <div class="flex h-[calc(100vh-190px)] gap-4">
            <!-- 左：类型列表 -->
            <div class="flex w-[190px] shrink-0 flex-col gap-1.5 overflow-y-auto">
              <button
                v-for="meta in NOTE_TYPE_META"
                :key="meta.key"
                class="rounded-xl border px-3 py-2.5 text-left transition-colors"
                :class="
                  activeNoteType === meta.key
                    ? 'border-indigo-200 bg-indigo-50/80'
                    : 'border-transparent bg-white hover:border-zinc-200'
                "
                @click="switchNoteType(meta.key)"
              >
                <div class="flex items-center justify-between">
                  <span
                    class="text-[13px] font-semibold"
                    :class="activeNoteType === meta.key ? 'text-indigo-600' : 'text-zinc-700'"
                  >{{ meta.label }}</span>
                  <span
                    v-if="noteByType[meta.key]?.content"
                    class="h-1.5 w-1.5 rounded-full bg-emerald-400"
                    title="已有内容"
                  />
                </div>
                <div class="mt-0.5 text-[11px] leading-snug text-zinc-400">{{ meta.hint }}</div>
              </button>
            </div>

            <!-- 右：编辑/查看 -->
            <div class="flex min-w-0 flex-1 flex-col rounded-2xl border border-zinc-100 bg-white p-4">
              <div class="mb-2 flex shrink-0 items-center gap-2">
                <h3 class="text-[14px] font-semibold text-zinc-800">{{ currentNoteMeta?.label }}</h3>
                <span
                  v-if="currentNote?.ai_generated"
                  class="rounded-md bg-violet-50 px-1.5 py-0.5 text-[10.5px] font-medium text-violet-600"
                >AI 提纲</span>
                <span v-if="currentNote?.updated_at" class="text-[11px] text-zinc-400">
                  更新于 {{ new Date(currentNote.updated_at).toLocaleString() }}
                </span>
                <div class="ml-auto flex gap-2">
                  <n-button
                    size="small"
                    type="primary"
                    secondary
                    :loading="outlining === activeNoteType"
                    @click="generateOutline"
                  >
                    <template #icon><n-icon :component="SparklesOutline" :size="14" /></template>
                    AI 生成提纲
                  </n-button>
                  <template v-if="noteEditing">
                    <n-button size="small" @click="noteEditing = false">取消</n-button>
                    <n-button size="small" type="primary" :loading="noteSaving" @click="saveNote">保存</n-button>
                  </template>
                  <n-button v-else size="small" @click="startEditNote">
                    {{ currentNote?.content ? '编辑' : '手动编写' }}
                  </n-button>
                </div>
              </div>

              <n-input
                v-if="noteEditing"
                v-model:value="noteDraft"
                type="textarea"
                placeholder="支持 Markdown：## 小节、- 列表、**加粗**"
                class="min-h-0 flex-1"
                :input-props="{ spellcheck: false }"
              />
              <template v-else-if="currentNote?.content">
                <div class="min-h-0 flex-1 overflow-y-auto pr-1">
                  <MarkdownView :source="currentNote.content" />
                </div>
              </template>
              <div v-else class="grid flex-1 place-items-center">
                <div class="text-center">
                  <p class="text-[12.5px] leading-relaxed text-zinc-400">
                    还没有「{{ currentNoteMeta?.label }}」内容<br />
                    用 AI 生成调研提纲，再逐条补充核实
                  </p>
                </div>
              </div>
            </div>
          </div>
        </n-tab-pane>

        <!-- 匹配度 -->
        <n-tab-pane name="match" tab="匹配度">
          <div class="max-h-[calc(100vh-180px)] overflow-y-auto pb-8">
            <!-- 生成中 -->
            <div v-if="generating" class="grid place-items-center rounded-2xl border border-dashed border-indigo-200 bg-white py-16">
              <div class="text-center">
                <n-spin size="28" />
                <div class="mt-3 text-[14px] font-semibold text-zinc-700">正在生成匹配度报告…</div>
                <p class="mt-1 text-[12.5px] text-zinc-400">AI 正在逐条对照 JD 与简历，大约需要几十秒</p>
              </div>
            </div>

            <!-- 无报告 -->
            <div v-else-if="!matchReport" class="grid place-items-center rounded-2xl border border-dashed border-zinc-200 bg-white py-16">
              <div class="w-[400px] text-center">
                <div class="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-500">
                  <n-icon :component="DocumentTextOutline" :size="24" />
                </div>
                <div class="mt-3 text-[14px] font-semibold text-zinc-700">岗位匹配度评估</div>
                <p class="mt-1 text-[12.5px] leading-relaxed text-zinc-400">
                  基于 JD 与简历生成匹配度报告：岗位画像、逐条匹配、五维评分、准备重点
                </p>
                <div v-if="!opp.jd_text?.trim()" class="mt-4 rounded-xl bg-amber-50 px-3 py-2 text-[12px] text-amber-600">
                  该岗位还没有工作描述，请先在「编辑」中补充 JD
                </div>
                <div v-else-if="!resumes.length" class="mt-4 rounded-xl bg-amber-50 px-3 py-2 text-[12px] text-amber-600">
                  请先到「简历库」上传简历
                </div>
                <template v-else>
                  <n-select
                    v-model:value="matchResumeId"
                    clearable
                    filterable
                    size="small"
                    class="mt-4 text-left"
                    :options="resumes.map((r) => ({ label: r.is_default ? `★ ${r.name}（默认）` : r.name, value: r.id }))"
                    placeholder="选择用于评估的简历（默认用投递关联的简历）"
                  />
                  <n-button type="primary" class="mt-3 !px-6" @click="generateMatch">生成匹配度报告</n-button>
                </template>
              </div>
            </div>

            <!-- 有报告 -->
            <template v-else>
              <div class="grid grid-cols-1 gap-4 xl:grid-cols-[320px_1fr]">
                <!-- 左：总分 + 雷达图 -->
                <div class="rounded-2xl border border-zinc-100 bg-white p-4">
                  <div class="flex items-baseline justify-center gap-2">
                    <span class="text-[40px] font-bold leading-none" :class="scoreGrade(matchReport.report.total_score).class">
                      {{ matchReport.report.total_score }}
                    </span>
                    <span class="text-[13px] text-zinc-400">/ 100</span>
                  </div>
                  <div class="mt-1 text-center text-[13px] font-semibold" :class="scoreGrade(matchReport.report.total_score).class">
                    {{ scoreGrade(matchReport.report.total_score).label }}
                  </div>
                  <div class="h-[240px]">
                    <VChart :option="radarOption" />
                  </div>
                  <div class="mt-1 border-t border-zinc-100 pt-2 text-[11px] leading-relaxed text-zinc-400">
                    简历：{{ matchReport.resume_name ?? '未关联' }} · {{ matchReport.model }}<br />
                    生成于 {{ new Date(matchReport.created_at).toLocaleString() }}
                  </div>
                </div>

                <!-- 右：岗位画像 -->
                <div class="rounded-2xl border border-zinc-100 bg-white p-4">
                  <h3 class="mb-3 text-[13.5px] font-semibold text-zinc-800">岗位画像</h3>
                  <div class="flex flex-col gap-3">
                    <div v-for="[name, arr, cls] in profileGroups" :key="name">
                      <div class="mb-1.5 text-[11.5px] font-medium text-zinc-400">{{ name }}</div>
                      <div class="flex flex-wrap gap-1.5">
                        <span
                          v-for="(tag, i) in arr"
                          :key="i"
                          class="rounded-lg border px-2 py-1 text-[12px]"
                          :class="cls"
                        >{{ tag }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 逐条匹配 -->
              <div class="mt-4 rounded-2xl border border-zinc-100 bg-white p-4">
                <h3 class="mb-3 text-[13.5px] font-semibold text-zinc-800">逐条匹配（{{ matchReport.report.items.length }}）</h3>
                <div class="flex flex-col gap-2.5">
                  <div
                    v-for="(item, i) in matchReport.report.items"
                    :key="i"
                    class="rounded-xl border border-zinc-100 px-3.5 py-2.5"
                  >
                    <div class="flex flex-wrap items-center gap-2">
                      <span>{{ MATCH_VERDICT_ICON[item.verdict] }}</span>
                      <span class="min-w-0 flex-1 text-[13px] font-medium text-zinc-800">{{ item.requirement }}</span>
                      <span
                        class="rounded-md border px-1.5 py-0.5 text-[10.5px] font-medium"
                        :class="MATCH_VERDICT_META[item.verdict]?.class"
                      >{{ MATCH_VERDICT_META[item.verdict]?.label ?? item.verdict }}</span>
                      <span class="rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10.5px] text-zinc-500">
                        {{ MATCH_WEIGHT_LABEL[item.weight] ?? item.weight }}
                      </span>
                    </div>
                    <div v-if="item.evidence" class="mt-1.5 text-[12.5px] leading-relaxed text-zinc-500">
                      <span class="text-zinc-400">证据：</span>{{ item.evidence }}
                    </div>
                    <div v-if="item.advice" class="mt-1 rounded-lg bg-indigo-50/60 px-2.5 py-1.5 text-[12.5px] leading-relaxed text-indigo-700">
                      {{ item.advice }}
                    </div>
                  </div>
                </div>
              </div>

              <!-- 准备重点 / 追问风险 -->
              <div class="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
                <div class="rounded-2xl border border-indigo-100 bg-indigo-50/50 p-4">
                  <h3 class="mb-2 text-[13.5px] font-semibold text-indigo-800">准备重点</h3>
                  <ol class="flex flex-col gap-1.5">
                    <li v-for="(f, i) in matchReport.report.focus" :key="i" class="flex gap-2 text-[12.5px] leading-relaxed text-zinc-700">
                      <span class="shrink-0 font-semibold text-indigo-500">{{ i + 1 }}.</span>
                      {{ f }}
                    </li>
                  </ol>
                </div>
                <div class="rounded-2xl border border-amber-100 bg-amber-50/50 p-4">
                  <h3 class="mb-2 text-[13.5px] font-semibold text-amber-700">简历追问风险</h3>
                  <ul class="flex flex-col gap-1.5">
                    <li v-for="(r, i) in matchReport.report.resume_risks" :key="i" class="flex gap-2 text-[12.5px] leading-relaxed text-zinc-700">
                      <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                      {{ r }}
                    </li>
                  </ul>
                </div>
              </div>

              <!-- 操作 -->
              <div class="mt-4 flex items-center gap-2.5">
                <n-select
                  v-model:value="matchResumeId"
                  clearable
                  filterable
                  size="small"
                  class="w-[280px]"
                  :options="resumes.map((r) => ({ label: r.is_default ? `★ ${r.name}（默认）` : r.name, value: r.id }))"
                  placeholder="换一份简历重新评估"
                />
                <n-button size="small" type="primary" secondary :disabled="!matchResumeId" @click="generateMatch">
                  用所选简历重新生成
                </n-button>
                <n-button size="small" @click="exportMatchMd">导出 Markdown</n-button>
                <n-button size="small" type="error" quaternary class="ml-auto" @click="deleteMatch">删除报告</n-button>
              </div>
            </template>
          </div>
        </n-tab-pane>

        <!-- 题目预测 -->
        <n-tab-pane name="predict" tab="题目预测">
          <PredictionPanel :opportunity="opp" />
        </n-tab-pane>

        <!-- 模拟面试 -->
        <n-tab-pane name="mock" tab="模拟面试">
          <MockInterviewPanel :opportunity="opp" />
        </n-tab-pane>

        <!-- 轮次与录音 -->
        <n-tab-pane name="rounds" tab="轮次与录音">
          <div class="grid max-h-[calc(100vh-180px)] grid-cols-1 gap-4 overflow-y-auto pb-8 xl:grid-cols-2">
            <div class="rounded-2xl border border-zinc-100 bg-white p-4">
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-[13.5px] font-semibold text-zinc-800">面试轮次（{{ sortedRounds.length }}）</h3>
                <n-button size="tiny" type="primary" secondary @click="editRound(null)">
                  <template #icon><n-icon :component="AddOutline" :size="13" /></template>
                  添加轮次
                </n-button>
              </div>
              <div v-if="sortedRounds.length" class="flex flex-col gap-2">
                <div
                  v-for="r in sortedRounds"
                  :key="r.id"
                  class="group rounded-xl border border-zinc-100 px-3.5 py-2.5"
                >
                  <div class="flex items-center gap-2.5">
                    <span class="w-12 shrink-0 text-[12.5px] font-semibold text-zinc-700">
                      {{ ROUND_LABEL[r.round_type] ?? '面试' }}
                    </span>
                    <span class="min-w-0 flex-1 truncate text-[12px] text-zinc-500">
                      {{ r.scheduled_at ? eventLabel(r.scheduled_at) : '未排期' }}
                    </span>
                    <span
                      class="shrink-0 rounded-md px-1.5 py-0.5 text-[10.5px] font-medium"
                      :style="{
                        background: (ROUND_RESULT_META[r.result] ?? ROUND_RESULT_META.pending).color + '14',
                        color: (ROUND_RESULT_META[r.result] ?? ROUND_RESULT_META.pending).color,
                      }"
                    >
                      {{ (ROUND_RESULT_META[r.result] ?? ROUND_RESULT_META.pending).label }}
                    </span>
                    <span class="hidden shrink-0 gap-1 group-hover:flex">
                      <n-button size="tiny" quaternary @click="editRound(r)">编辑</n-button>
                      <n-button size="tiny" quaternary type="error" @click="deleteRound(r)">删除</n-button>
                    </span>
                  </div>
                  <p v-if="r.note" class="mt-1 whitespace-pre-wrap pl-[58px] text-[12px] leading-relaxed text-zinc-500">{{ r.note }}</p>
                </div>
              </div>
              <div v-else class="rounded-xl border border-dashed border-zinc-200 px-4 py-8 text-center text-[12.5px] text-zinc-400">
                暂无面试安排 · 点击「添加轮次」排期
              </div>
            </div>

            <div class="rounded-2xl border border-zinc-100 bg-white p-4">
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-[13.5px] font-semibold text-zinc-800">面试录音（{{ recordings.length }}）</h3>
                <span class="text-[11px] text-zinc-400">上传与复盘请到「录音复盘」页面</span>
              </div>
              <div v-if="recordings.length" class="flex flex-col gap-2">
                <div
                  v-for="rec in recordings"
                  :key="rec.id"
                  class="flex items-center gap-2.5 rounded-xl border border-zinc-100 px-3.5 py-2.5"
                >
                  <n-icon :component="DocumentTextOutline" :size="15" class="shrink-0 text-zinc-300" />
                  <span class="min-w-0 flex-1 truncate text-[12.5px] text-zinc-700">{{ rec.filename }}</span>
                  <span class="shrink-0 text-[11px] text-zinc-400">{{ fmtDuration(rec.duration_sec) }}</span>
                  <span class="shrink-0 rounded-md px-1.5 py-0.5 text-[10.5px] font-medium" :class="REC_STATUS[rec.status]?.class">
                    {{ REC_STATUS[rec.status]?.label ?? rec.status }}
                  </span>
                </div>
              </div>
              <div v-else class="rounded-xl border border-dashed border-zinc-200 px-4 py-8 text-center text-[12.5px] text-zinc-400">
                该岗位还没有录音
              </div>
            </div>
          </div>
        </n-tab-pane>

        <!-- Offer -->
        <n-tab-pane name="offer" tab="Offer">
          <div class="max-h-[calc(100vh-180px)] overflow-y-auto pb-8">
            <div v-if="offer" class="rounded-2xl border border-zinc-100 bg-white p-4">
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-[13.5px] font-semibold text-zinc-800">Offer 信息</h3>
                <div class="flex gap-2">
                  <n-button size="small" @click="offerShow = true">编辑</n-button>
                  <n-button size="small" type="error" quaternary @click="deleteOffer">删除</n-button>
                </div>
              </div>
              <div class="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
                <div class="rounded-xl bg-zinc-50 px-3 py-2">
                  <div class="text-[11px] text-zinc-400">月薪</div>
                  <div class="mt-0.5 text-[13px] font-medium text-zinc-700">
                    {{ offer.monthly_salary != null ? `${offer.monthly_salary}K` : '—' }}
                    <span v-if="offer.months" class="text-zinc-400"> × {{ offer.months }} 薪</span>
                  </div>
                </div>
                <div v-for="f in [
                    ['签字费 / 奖金', offer.signing_bonus],
                    ['股票 / 期权', offer.stock],
                    ['公积金 / 福利', offer.welfare],
                    ['加班情况', offer.overtime],
                    ['通勤', offer.commute],
                  ] as const" :key="f[0]" class="rounded-xl bg-zinc-50 px-3 py-2">
                  <div class="text-[11px] text-zinc-400">{{ f[0] }}</div>
                  <div class="mt-0.5 truncate text-[13px] font-medium text-zinc-700">{{ f[1] || '—' }}</div>
                </div>
              </div>
              <div v-if="offer.note" class="mt-3 whitespace-pre-wrap rounded-xl bg-amber-50/70 px-3.5 py-2.5 text-[12.5px] text-zinc-600">
                {{ offer.note }}
              </div>
            </div>
            <div v-else class="grid place-items-center rounded-2xl border border-dashed border-zinc-200 bg-white py-14">
              <div class="text-center">
                <div class="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-emerald-50 text-emerald-500">
                  <n-icon :component="SparklesOutline" :size="24" />
                </div>
                <div class="mt-3 text-[14px] font-semibold text-zinc-700">还没有 Offer 记录</div>
                <p class="mt-1 text-[12.5px] text-zinc-400">拿到 Offer 后录入薪资结构与主观评分，可在「Offer 对比」页多Offer 横向对比</p>
                <n-button type="primary" class="mt-4 !px-6" @click="offerShow = true">录入 Offer</n-button>
              </div>
            </div>
          </div>
        </n-tab-pane>
      </n-tabs>
    </template>

    <!-- 弹窗 -->
    <OpportunityModal v-model:show="editShow" :opportunity="opp" :resumes="resumes" @saved="onEdited" />
    <RoundModal
      v-model:show="roundShow"
      :round="editingRound"
      :opportunities="opp ? [opp] : []"
      :default-date="null"
      @saved="onRoundSaved"
    />
    <OfferModal v-model:show="offerShow" :opportunity="opp" :existing="offer" @saved="onOfferSaved" />
  </div>
</template>
