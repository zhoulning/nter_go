<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  NButton,
  NDropdown,
  NInput,
  NSelect,
  NTag,
  useDialog,
  useMessage,
} from 'naive-ui'
import {
  AlertCircleOutline,
  ArrowBackOutline,
  BookOutline,
  BugOutline,
  CheckmarkCircleOutline,
  ChevronForwardOutline,
  DownloadOutline,
  MicOutline,
  RibbonOutline,
  SaveOutline,
  SparklesOutline,
  TimeOutline,
} from '@vicons/ionicons5'
import { api } from '../api'
import type { RecordingDetail, ReviewReportData, ReviewQuestion } from '../api'
import type { Resume } from '../types'
import { CHART_FONT, ROUND_LABEL } from '../types'
import VChart from '../components/VChart.vue'

const props = defineProps<{ id: number }>()
const emit = defineEmits<{ (e: 'back'): void; (e: 'changed'): void }>()

const message = useMessage()
const dialog = useDialog()

const rec = ref<RecordingDetail | null>(null)
const resumes = ref<Resume[]>([])
const rawDraft = ref('')
const cleanDraft = ref('')
const activeTranscript = ref<'raw' | 'clean'>('raw')
const activeDraft = computed({
  get: () => (activeTranscript.value === 'clean' ? cleanDraft.value : rawDraft.value),
  set: (v: string) => {
    if (activeTranscript.value === 'clean') cleanDraft.value = v
    else rawDraft.value = v
  },
})
const polishRunning = computed(() => rec.value?.polish_status === 'running')
const savingTranscript = ref(false)
const generating = ref(false)
const expandedQs = reactive(new Set<number>())
const bankSaving = reactive(new Set<number>())
const savedBank = reactive(new Set<number>())
const resumeId = ref<number | null>(null)
const activeTab = ref<'overview' | 'questions' | 'jd' | 'actions'>('overview')

let pollTimer: number | null = null
const prevStatus = ref<string | null>(null)
const prevPolish = ref<string | null>(null)
const prevReview = ref<string | null>(null)

function syncDrafts() {
  if (!rec.value) return
  rawDraft.value = rec.value.transcript ?? ''
  cleanDraft.value = rec.value.transcript_clean ?? ''
}

async function fetchRec(syncDrafts = false) {
  rec.value = await api.getRecording(props.id)
  if (syncDrafts) syncDrafts()
}

onMounted(async () => {
  try {
    const [recData, resumeData] = await Promise.all([api.getRecording(props.id), api.listResumes()])
    rec.value = recData
    syncDrafts()
    resumes.value = resumeData.items
    const def = resumeData.items.find((r) => r.is_default)
    if (def) resumeId.value = def.id
    prevStatus.value = rec.value.status
    prevPolish.value = rec.value.polish_status
    prevReview.value = rec.value.review_status
    startPolling()
  } catch (e) {
    message.error((e as Error).message || '加载失败')
  }
})

function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    if (!rec.value) return
    const busy =
      rec.value.status === 'transcribing' ||
      rec.value.review_status === 'running' ||
      rec.value.polish_status === 'running'
    if (!busy) return
    await fetchRec()
    if (!rec.value) return
    if (prevStatus.value === 'transcribing' && rec.value.status !== 'transcribing') syncDrafts()
    if (prevPolish.value === 'running' && rec.value.polish_status !== 'running') {
      cleanDraft.value = rec.value.transcript_clean ?? ''
      emit('changed')
      if (rec.value.polish_status === 'done') {
        message.success('AI 矫正稿已生成')
        activeTranscript.value = 'clean'
      }
    }
    if (prevReview.value === 'running' && rec.value.review_status !== 'running') {
      emit('changed')
      if (rec.value.review_status === 'done') message.success('复盘报告已生成')
    }
    prevStatus.value = rec.value.status
    prevPolish.value = rec.value.polish_status
    prevReview.value = rec.value.review_status
  }, 2500)
}
function stopPolling() {
  if (pollTimer) window.clearInterval(pollTimer)
  pollTimer = null
}
onBeforeUnmount(stopPolling)

const hasReport = computed(() => !!rec.value?.review)
const isBusy = computed(
  () => rec.value?.status === 'transcribing' || rec.value?.review_status === 'running',
)
const isText = computed(() => rec.value?.kind === 'text')
const fileUrl = computed(() => api.recordingFileUrl(props.id))

// ---- 操作 ----
function doTranscribe(engine: 'local' | 'cloud') {
  api
    .transcribeRecording(props.id, engine)
    .then(async () => {
      message.success(engine === 'local' ? '已启动本地转写' : '已启动云端转写')
      await fetchRec()
      if (rec.value) prevStatus.value = rec.value.status
      startPolling()
    })
    .catch((e) => message.error((e as Error).message, { duration: 6000 }))
}

const transcribeOptions = [
  { label: '本地转写 · 免费，CPU 较慢', key: 'local' },
  { label: '云端转写 · 快，按量计费', key: 'cloud' },
]

function onTranscribeSelect(key: string | number) {
  doTranscribe(key as 'local' | 'cloud')
}

async function saveActiveTranscript() {
  savingTranscript.value = true
  try {
    await api.saveTranscript(props.id, activeDraft.value, activeTranscript.value)
    message.success(activeTranscript.value === 'clean' ? '矫正稿已保存' : '文字稿已保存')
    await fetchRec(true)
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    savingTranscript.value = false
  }
}

function polishTranscript() {
  dialog.info({
    title: 'AI 矫正文字稿',
    content:
      'AI 将修正错别字与技术名词拼写、去除口语化内容，并标注「面试官 / 我」角色。原始稿会完整保留，可随时切换查看。',
    positiveText: '开始矫正',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.polishRecording(props.id)
        await fetchRec()
        if (rec.value) prevPolish.value = rec.value.polish_status
        startPolling()
      } catch (e) {
        message.error((e as Error).message, { duration: 6000 })
      }
    },
  })
}

function generateReview() {
  dialog.info({
    title: '生成复盘报告',
    content: `AI 将结合岗位 JD、关联简历与文字稿逐题分析。通常需要 30~90 秒，确定开始？`,
    positiveText: '开始生成',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        generating.value = true
        await api.generateReview(props.id, resumeId.value)
        await fetchRec()
        if (rec.value) {
          prevReview.value = rec.value.review_status
          prevPolish.value = rec.value.polish_status
          prevStatus.value = rec.value.status
        }
        startPolling()
        activeTab.value = 'overview'
      } catch (e) {
        message.error((e as Error).message, { duration: 6000 })
      } finally {
        generating.value = false
      }
    },
  })
}

// ---- 报告展示辅助 ----
const report = computed<ReviewReportData | null>(() => rec.value?.review?.report ?? null)

const DIMS = [
  { key: 'structure', label: '结构' },
  { key: 'depth', label: '深度' },
  { key: 'clarity', label: '表达' },
] as const

const avgScores = computed(() => {
  const qs = report.value?.questions ?? []
  if (!qs.length) return null
  const result: Record<string, number> = {}
  for (const k of DIMS) {
    result[k.key] = +(qs.reduce((a, q) => a + (q.scores[k] ?? 3), 0) / qs.length).toFixed(1)
  }
  return result
})

function questionAvg(q: ReviewQuestion): number {
  return +(((q.scores.structure ?? 3) + (q.scores.depth ?? 3) + (q.scores.clarity ?? 3)) / 3).toFixed(1)
}

const bestQuestion = computed(() => {
  const qs = report.value?.questions ?? []
  if (qs.length < 2) return null
  return qs.reduce((a, b) => (questionAvg(b) > questionAvg(a) ? b : a))
})

const worstQuestion = computed(() => {
  const qs = report.value?.questions ?? []
  if (qs.length < 2) return null
  return qs.reduce((a, b) => (questionAvg(b) < questionAvg(a) ? b : a))
})

const avgRadarOption = computed(() => {
  const avg = avgScores.value
  if (!avg) return {}
  return {
    textStyle: { fontFamily: CHART_FONT },
    radar: {
      indicator: DIMS.map((d) => ({ name: `${d.label} ${avg[d.key]}`, max: 5 })),
      radius: '68%',
      splitNumber: 4,
      axisName: { color: '#52525b', fontSize: 12, fontWeight: 600 },
      splitLine: { lineStyle: { color: '#e4e4e7' } },
      splitArea: { areaStyle: { color: ['#fafafa', '#f4f4f5'] } },
      axisLine: { lineStyle: { color: '#e4e4e7' } },
    },
    series: [
      {
        type: 'radar',
        data: [
          { value: DIMS.map((d) => avg[d.key]), name: '平均分' },
        ],
        areaStyle: { opacity: 0.18, color: '#6366f1' },
        lineStyle: { color: '#6366f1', width: 2 },
        itemStyle: { color: '#6366f1' },
        symbolSize: 5,
      },
    ],
  }
})

function scoreColor(score: number): string {
  if (score >= 4) return '#6366f1'
  if (score >= 3) return '#a5b4fc'
  return '#c7d2fe'
}

function scoreChipClass(score: number): string {
  if (score >= 4) return 'bg-indigo-50 text-indigo-600'
  if (score >= 3) return 'bg-zinc-100 text-zinc-600'
  return 'bg-zinc-100 text-zinc-400'
}

function fmtDuration(sec: number | null): string {
  if (sec == null) return '—'
  const s = Math.round(sec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
    : `${m}:${String(ss).padStart(2, '0')}`
}

function fmtSize(bytes: number): string {
  if (bytes > 1024 * 1024) return (bytes / 1024 ** 2).toFixed(1) + ' MB'
  return Math.max(1, Math.round(bytes / 1024)) + ' KB'
}

// ---- 题库入库 ----
async function addToBank(idx: number, q: ReviewQuestion) {
  if (!rec.value) return
  bankSaving.add(idx)
  try {
    // 复盘的 improved 示范回答遵循题库同一标准：直接带入；旧报告没有时入库后走统一入口生成
    const answer = q.improved?.trim() || null
    const saved = await api.createQuestion({
      content: q.question,
      dimension: q.topic || '其他',
      difficulty: 'medium',
      source: 'real',
      opportunity_id: rec.value.opportunity_id,
      sources: [
        {
          opportunity_id: rec.value.opportunity_id,
          round_id: rec.value.round_id ?? null,
        },
      ],
      my_answer: q.my_answer || null,
      answer_key: q.reference || null,
      answer_spoken: answer,
      self_rating: Math.round((q.scores.structure + q.scores.depth + q.scores.clarity) / 3),
      mastery: 'unknown',
    })
    if (!answer) await api.generateAnswer({ question_id: saved.id })
    savedBank.add(idx)
    message.success(answer ? '已存入题库，示范回答已一并带入' : '已存入题库，AI 答案已生成')
  } catch (e) {
    message.error((e as Error).message || '存入失败')
  } finally {
    bankSaving.delete(idx)
  }
}

// ---- 导出 Markdown ----
function exportMarkdown() {
  const r = report.value
  if (!r || !rec.value) return
  const lines: string[] = []
  lines.push(`# 面试复盘 · ${rec.value.company} ${ROUND_LABEL[rec.value.round_type ?? ''] ?? ''}`)
  lines.push('')
  lines.push(`- 总评：**${r.overall.score}/100**`)
  lines.push(`- 题目数：${r.questions.length}`)
  lines.push(`- 生成模型：${rec.value.review?.model ?? ''}`)
  lines.push(`- 生成时间：${rec.value.review?.created_at?.slice(0, 19).replace('T', ' ') ?? ''}`)
  lines.push('')
  lines.push('## 总体评价')
  lines.push(r.overall.summary)
  lines.push('')
  lines.push('### 亮点')
  r.overall.highlights.forEach((h) => lines.push(`- ${h}`))
  lines.push('')
  lines.push('### 不足')
  r.overall.weaknesses.forEach((w) => lines.push(`- ${w}`))
  lines.push('')
  lines.push('## 逐题复盘')
  r.questions.forEach((q, i) => {
    lines.push('')
    lines.push(`### ${i + 1}. ${q.question}`)
    lines.push(`> 维度：${q.topic} · 结构 ${q.scores.structure}/5 · 深度 ${q.scores.depth}/5 · 表达 ${q.scores.clarity}/5`)
    lines.push('')
    lines.push(`**我的回答**：${q.my_answer}`)
    if (q.good.length) {
      lines.push('')
      lines.push('亮点：')
      q.good.forEach((g) => lines.push(`- ✅ ${g}`))
    }
    if (q.bad.length) {
      lines.push('')
      lines.push('问题：')
      q.bad.forEach((b) => lines.push(`- ⚠️ ${b}`))
    }
    if (q.reference) {
      lines.push('')
      lines.push(`**参考要点**：${q.reference}`)
    }
    if (q.improved) {
      lines.push('')
      lines.push(`**更好的回答示范**：${q.improved}`)
    }
  })
  lines.push('')
  lines.push('## JD 对照')
  lines.push('')
  lines.push('已展示：')
  r.jd_match.demonstrated.forEach((d) => lines.push(`- ✅ ${d}`))
  lines.push('')
  lines.push('差距：')
  r.jd_match.gaps.forEach((g) => lines.push(`- ⚠️ ${g}`))
  lines.push('')
  lines.push('## 面试官关注点')
  lines.push(r.interviewer_focus)
  lines.push('')
  lines.push('## 行动清单')
  r.action_items.forEach((a) => lines.push(`- [ ] ${a}`))

  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `面试复盘-${rec.value.company}-${new Date().toISOString().slice(0, 10)}.md`
  a.click()
  URL.revokeObjectURL(a.href)
}

function setTab(key: string) {
  activeTab.value = key as typeof activeTab.value
}

function toggleQuestion(idx: number) {
  if (expandedQs.has(idx)) expandedQs.delete(idx)
  else expandedQs.add(idx)
}

const tabs = computed(() => [
  { key: 'overview', label: '总览' },
  { key: 'questions', label: `逐题复盘`, count: report.value?.questions.length ?? 0 },
  { key: 'jd', label: 'JD 对照' },
  { key: 'actions', label: '行动与沉淀' },
])
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- 顶栏 -->
    <header
      v-if="rec"
      class="flex items-center justify-between gap-3 border-b border-zinc-200/70 bg-white px-6 py-3.5 max-md:flex-wrap max-md:px-4"
    >
      <div class="flex min-w-0 items-center gap-3">
        <n-button quaternary size="small" @click="emit('back')">
          <n-icon :component="ArrowBackOutline" :size="16" />
          返回
        </n-button>
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h1 class="truncate text-[15.5px] font-bold text-zinc-900">
              {{ rec.company }} · 面试复盘
            </h1>
            <span
              v-if="rec.round_type"
              class="shrink-0 rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10.5px] font-medium text-zinc-500"
            >
              {{ ROUND_LABEL[rec.round_type] ?? '面试' }}
            </span>
          </div>
          <div class="truncate text-[11.5px] text-zinc-400">
            <template v-if="isText">
              {{ rec.filename }} · 文字稿 {{ (rec.transcript || '').length }} 字
            </template>
            <template v-else>
              {{ rec.filename }} · {{ fmtDuration(rec.duration_sec) }} · {{ fmtSize(rec.size) }}
            </template>
          </div>
        </div>
      </div>

      <div class="flex shrink-0 items-center gap-2.5 max-md:w-full max-md:flex-wrap">
        <n-select
          v-model:value="resumeId"
          size="small"
          clearable
          placeholder="简历：跟随岗位关联"
          class="!w-[190px] max-md:!w-full max-md:!flex-1"
          :options="resumes.map((r) => ({ label: r.name, value: r.id }))"
        />
        <a
          v-if="!isText"
          :href="fileUrl"
          :download="rec.filename"
          class="flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border border-zinc-200 px-3 py-1.5 text-[12.5px] font-medium text-zinc-600 transition-colors hover:border-indigo-200 hover:text-indigo-600"
          title="下载原始录音"
        >
          <n-icon :component="DownloadOutline" :size="14" />
          录音
        </a>
        <n-dropdown
          v-if="!isText && rec.status !== 'transcribed' && rec.status !== 'transcribing'"
          trigger="click"
          :options="transcribeOptions"
          @select="onTranscribeSelect"
        >
          <n-button size="small" secondary class="shrink-0 whitespace-nowrap">
            <n-icon :component="MicOutline" :size="15" class="mr-1" />
            转写
          </n-button>
        </n-dropdown>
        <n-button
          v-if="hasReport"
          size="small"
          secondary
          class="shrink-0 whitespace-nowrap"
          @click="exportMarkdown"
        >
          <n-icon :component="DownloadOutline" :size="15" class="mr-1" />
          导出报告
        </n-button>
        <n-button
          v-if="rec.status === 'transcribed' && rec.review_status !== 'running'"
          size="small"
          type="primary"
          :loading="generating"
          class="shrink-0 whitespace-nowrap"
          @click="generateReview"
        >
          <n-icon :component="SparklesOutline" :size="15" class="mr-1" />
          {{ hasReport ? '重新生成' : '生成复盘报告' }}
        </n-button>
      </div>
    </header>

    <div v-if="!rec" class="grid flex-1 place-items-center text-sm text-zinc-400">正在加载…</div>

    <div v-else class="grid min-h-0 flex-1 gap-3.5 overflow-hidden p-5 max-md:overflow-y-auto max-md:p-4 xl:grid-cols-5">
      <!-- 左列：状态 + 录音文件 + 文字稿 -->
      <div class="flex min-h-0 flex-col gap-3.5 xl:col-span-2">
        <div class="rounded-2xl border border-zinc-200/70 bg-white p-4">
          <h2 class="mb-3 text-[13.5px] font-bold text-zinc-800">处理状态</h2>
          <div class="flex flex-col gap-2.5 text-[12.5px]">
            <div v-if="!isText" class="flex items-center justify-between">
              <span class="text-zinc-500">转写状态</span>
              <span v-if="rec.status === 'transcribing'" class="flex items-center gap-2 text-indigo-600">
                转写中
                <span class="h-1.5 w-24 overflow-hidden rounded-full bg-indigo-100">
                  <span
                    class="block h-full rounded-full bg-indigo-500 transition-all"
                    :style="{ width: rec.progress + '%' }"
                  />
                </span>
                {{ rec.progress }}%
              </span>
              <n-tag v-else :bordered="false" size="small" :type="rec.status === 'transcribed' ? 'success' : rec.status === 'failed' ? 'error' : 'default'">
                {{ rec.status === 'transcribed' ? '已转写' : rec.status === 'failed' ? '转写失败' : '未转写' }}
              </n-tag>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-zinc-500">AI 矫正</span>
              <n-tag v-if="rec.polish_status === 'running'" :bordered="false" size="small">
                <span class="flex items-center gap-1.5 text-violet-600">
                  <span class="h-2 w-2 animate-ping rounded-full bg-violet-500" /> 矫正中
                </span>
              </n-tag>
              <n-tag v-else :bordered="false" size="small" :type="rec.polish_status === 'done' ? 'success' : rec.polish_status === 'failed' ? 'error' : 'default'">
                {{ rec.polish_status === 'done' ? '已矫正' : rec.polish_status === 'failed' ? '矫正失败' : '未矫正' }}
              </n-tag>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-zinc-500">复盘状态</span>
              <span v-if="rec.review_status === 'running'" class="flex items-center gap-1.5 text-violet-600">
                <span class="h-2 w-2 animate-ping rounded-full bg-violet-500" /> 生成中
              </span>
              <n-tag v-else :bordered="false" size="small" :type="rec.review_status === 'done' ? 'success' : rec.review_status === 'failed' ? 'error' : 'default'">
                {{ rec.review_status === 'done' ? '已生成' : rec.review_status === 'failed' ? '生成失败' : '未生成' }}
              </n-tag>
            </div>
            <div v-if="!isText && rec.transcript_engine" class="flex items-center justify-between">
              <span class="text-zinc-500">转写引擎</span>
              <span class="text-zinc-600">{{ rec.transcript_engine }}</span>
            </div>
            <div v-if="!isText" class="flex items-center justify-between">
              <span class="text-zinc-500">录音文件</span>
              <a
                :href="fileUrl"
                :download="rec.filename"
                class="flex items-center gap-1 text-indigo-500 hover:text-indigo-600"
              >
                <n-icon :component="DownloadOutline" :size="13" />
                下载保存
              </a>
            </div>
          </div>
          <div
            v-if="rec.error"
            class="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-[11.5px] leading-relaxed text-rose-600"
          >
            {{ rec.error }}
          </div>
          <div
            v-if="rec.review_error"
            class="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-[11.5px] leading-relaxed text-rose-600"
          >
            复盘失败：{{ rec.review_error }}
          </div>
          <div
            v-if="rec.polish_error"
            class="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-[11.5px] leading-relaxed text-rose-600"
          >
            矫正失败：{{ rec.polish_error }}
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col rounded-2xl border border-zinc-200/70 bg-white p-4">
          <div class="mb-2.5 flex items-center justify-between gap-2">
            <div class="flex items-center gap-0.5 rounded-lg bg-zinc-100/80 p-0.5">
              <button
                class="rounded-md px-2.5 py-1 text-[11.5px] font-medium transition-all"
                :class="activeTranscript === 'raw' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500'"
                @click="activeTranscript = 'raw'"
              >
                原始稿
              </button>
              <button
                class="flex items-center gap-1 rounded-md px-2.5 py-1 text-[11.5px] font-medium transition-all"
                :class="activeTranscript === 'clean' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500'"
                @click="activeTranscript = 'clean'"
              >
                AI 矫正稿
                <span
                  v-if="rec.polish_status === 'running'"
                  class="h-1.5 w-1.5 animate-ping rounded-full bg-violet-500"
                />
              </button>
            </div>
            <span class="text-[11px] text-zinc-400">{{ activeDraft.length }} 字 · 可编辑</span>
          </div>
          <n-input
            v-model:value="activeDraft"
            type="textarea"
            :placeholder="
              activeTranscript === 'clean'
                ? '尚无 AI 矫正稿 · 点击下方「AI 矫正」生成'
                : '粘贴或编辑转写文字稿（建议带 [MM:SS] 时间戳与说话人标记）。也可以用飞书妙记等工具转好后粘贴。'
            "
            :autosize="{ minRows: 10, maxRows: 26 }"
          />
          <div class="mt-2.5 flex items-center justify-between gap-2">
            <template v-if="activeTranscript === 'raw'">
              <n-button
                size="small"
                secondary
                type="primary"
                :disabled="!rawDraft || polishRunning || isBusy"
                :loading="polishRunning"
                @click="polishTranscript"
              >
                <n-icon :component="SparklesOutline" :size="14" class="mr-1" />
                AI 矫正
              </n-button>
              <span class="text-[10.5px] leading-tight text-zinc-400">
                修正错别字与技术名词、去口语化、标注「面试官 / 我」
              </span>
            </template>
            <template v-else>
              <span class="text-[10.5px] leading-tight text-zinc-400">
                {{
                  rec.polish_status === 'failed'
                    ? '矫正失败，可重试'
                    : rec.polished_at
                      ? '矫正于 ' + rec.polished_at.slice(0, 16).replace('T', ' ')
                      : ''
                }}
              </span>
            </template>
            <n-button size="small" tertiary :loading="savingTranscript" @click="saveActiveTranscript">
              <n-icon :component="SaveOutline" :size="14" class="mr-1" />
              保存当前稿
            </n-button>
          </div>
        </div>
      </div>

      <!-- 右列：报告（标签导航） -->
      <div class="flex min-h-0 flex-col xl:col-span-3">
        <!-- 无报告 -->
        <div
          v-if="!hasReport && rec.review_status !== 'running'"
          class="grid h-full place-items-center rounded-2xl border border-dashed border-zinc-200 bg-white/60 p-10"
        >
          <div class="max-w-sm text-center">
            <div
              class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-[0_6px_20px_rgba(99,102,241,0.4)]"
            >
              <n-icon :component="SparklesOutline" :size="26" />
            </div>
            <h3 class="text-[15px] font-bold text-zinc-800">AI 复盘报告</h3>
            <p class="mt-2 text-[12.5px] leading-relaxed text-zinc-400">
              {{
                rec.status !== 'transcribed'
                  ? '请先完成转写（或在左侧粘贴文字稿），然后点击右上角「生成复盘报告」'
                  : '点击右上角「生成复盘报告」，AI 会结合岗位 JD 与简历，逐题分析你的回答'
              }}
            </p>
          </div>
        </div>

        <!-- 生成中 -->
        <div
          v-else-if="rec.review_status === 'running'"
          class="grid h-full place-items-center rounded-2xl border border-indigo-200 bg-gradient-to-b from-indigo-50/60 to-white p-10"
        >
          <div class="text-center">
            <div class="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-[3px] border-indigo-200 border-t-indigo-500" />
            <h3 class="text-[15px] font-bold text-zinc-800">AI 正在逐题分析你的回答…</h3>
            <p class="mt-2 text-[12.5px] text-zinc-400">
              切题 → 逐题点评 → JD 对照 → 行动清单，通常需要 30~90 秒
            </p>
          </div>
        </div>

        <!-- 报告正文：标签导航 -->
        <template v-else-if="report">
          <div class="mb-3.5 flex items-center gap-1 rounded-xl bg-zinc-100/80 p-1 max-md:overflow-x-auto">
            <button
              v-for="t in tabs"
              :key="t.key"
              class="flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-[12.5px] font-medium transition-all"
              :class="activeTab === t.key ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'"
              @click="setTab(t.key)"
            >
              {{ t.label }}
              <span
                v-if="t.count"
                class="rounded-full px-1.5 text-[10.5px] font-semibold"
                :class="activeTab === t.key ? 'bg-indigo-50 text-indigo-600' : 'bg-zinc-200/80 text-zinc-500'"
              >
                {{ t.count }}
              </span>
            </button>
          </div>

          <div class="min-h-0 flex-1 overflow-y-auto pb-4 pr-0.5">
            <!-- ============ 总览 ============ -->
            <div v-show="activeTab === 'overview'" class="flex flex-col gap-3.5">
              <!-- 总评 -->
              <section class="rounded-2xl border border-zinc-200/70 bg-white p-5">
                <div class="flex items-center gap-6">
                  <div class="text-center">
                    <div class="text-[44px] font-bold leading-none tabular-nums text-indigo-600">
                      {{ report.overall.score }}
                    </div>
                    <div class="mt-1 text-[11px] text-zinc-400">综合评分 / 100</div>
                  </div>
                  <div class="w-px self-stretch bg-zinc-100" />
                  <div class="min-w-0 flex-1">
                    <div class="mb-1.5 flex items-center gap-2 text-[11px] text-zinc-400">
                      <n-icon :component="RibbonOutline" :size="13" />
                      共 {{ report.questions.length }} 个问题
                      <span class="rounded-full bg-zinc-100 px-2 py-0.5">{{ rec.review?.model }}</span>
                      <span class="rounded-full bg-zinc-100 px-2 py-0.5">
                        {{ rec.review?.created_at?.slice(0, 10) }}
                      </span>
                    </div>
                    <p class="text-[13px] leading-relaxed text-zinc-600">{{ report.overall.summary }}</p>
                  </div>
                </div>
                <div class="mt-4 grid grid-cols-2 gap-3">
                  <div class="rounded-xl bg-emerald-50/60 px-3.5 py-3">
                    <div class="mb-1.5 flex items-center gap-1.5 text-[11.5px] font-semibold text-emerald-600">
                      <n-icon :component="CheckmarkCircleOutline" :size="13" /> 做得好的
                    </div>
                    <ul class="space-y-1 text-[12px] leading-relaxed text-zinc-600">
                      <li v-for="(h, i) in report.overall.highlights" :key="i">· {{ h }}</li>
                    </ul>
                  </div>
                  <div class="rounded-xl bg-amber-50/70 px-3.5 py-3">
                    <div class="mb-1.5 flex items-center gap-1.5 text-[11.5px] font-semibold text-amber-600">
                      <n-icon :component="AlertCircleOutline" :size="13" /> 待改进
                    </div>
                    <ul class="space-y-1 text-[12px] leading-relaxed text-zinc-600">
                      <li v-for="(w, i) in report.overall.weaknesses" :key="i">· {{ w }}</li>
                    </ul>
                  </div>
                </div>
              </section>

              <!-- 答题能力分析（加大版） -->
              <section class="rounded-2xl border border-zinc-200/70 bg-white p-5">
                <div class="mb-3 flex items-center justify-between">
                  <h2 class="text-[14px] font-bold text-zinc-800">答题能力分析</h2>
                  <span class="text-[11px] text-zinc-400">基于全部 {{ report.questions.length }} 题的三维评分</span>
                </div>
                <div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
                  <div class="h-[300px]">
                    <VChart :option="avgRadarOption" />
                  </div>
                  <div class="flex flex-col justify-center gap-4">
                    <div v-for="dim in DIMS" :key="dim.key">
                      <div class="mb-1.5 flex items-center justify-between">
                        <span class="text-[12px] font-semibold text-zinc-600">{{ dim.label }}</span>
                        <span class="text-[13px] font-bold tabular-nums text-indigo-600">
                          {{ avgScores?.[dim.key] }}
                          <span class="text-[10.5px] font-normal text-zinc-400">/ 5</span>
                        </span>
                      </div>
                      <div class="flex items-center gap-1.5">
                        <div
                          v-for="(q, qi) in report.questions"
                          :key="qi"
                          class="group/dot relative flex-1"
                          :title="`第 ${qi + 1} 题：${q.scores[dim.key]} 分`"
                        >
                          <div class="h-2 rounded-full" :style="{ background: scoreColor(q.scores[dim.key]) }" />
                        </div>
                      </div>
                    </div>
                    <p class="text-[10.5px] leading-relaxed text-zinc-400">
                      每格代表一道题，颜色越深得分越高（4-5 分靛蓝 / 3 分浅蓝 / ≤2 分最浅）
                    </p>
                  </div>
                </div>
                <div v-if="bestQuestion || worstQuestion" class="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
                  <div
                    v-if="bestQuestion"
                    class="rounded-xl border border-emerald-100 bg-emerald-50/50 px-3.5 py-3"
                  >
                    <div class="mb-1 flex items-center gap-1.5 text-[11px] font-semibold text-emerald-600">
                      <n-icon :component="CheckmarkCircleOutline" :size="13" />
                      表现最佳 · {{ questionAvg(bestQuestion) }} 分
                    </div>
                    <p class="text-[12px] leading-relaxed text-zinc-600">{{ bestQuestion.question }}</p>
                  </div>
                  <div
                    v-if="worstQuestion"
                    class="rounded-xl border border-amber-100 bg-amber-50/60 px-3.5 py-3"
                  >
                    <div class="mb-1 flex items-center gap-1.5 text-[11px] font-semibold text-amber-600">
                      <n-icon :component="AlertCircleOutline" :size="13" />
                      最需加强 · {{ questionAvg(worstQuestion) }} 分
                    </div>
                    <p class="text-[12px] leading-relaxed text-zinc-600">{{ worstQuestion.question }}</p>
                  </div>
                </div>
              </section>

              <!-- 面试官关注点 -->
              <section class="rounded-2xl border border-zinc-200/70 bg-white p-5">
                <h2 class="mb-2.5 flex items-center gap-1.5 text-[14px] font-bold text-zinc-800">
                  <n-icon :component="TimeOutline" :size="15" class="text-indigo-500" />
                  面试官关注点
                </h2>
                <p
                  class="rounded-xl border-l-4 border-indigo-300 bg-indigo-50/40 px-4 py-3 text-[13px] leading-relaxed text-zinc-600"
                >
                  {{ report.interviewer_focus || '—' }}
                </p>
              </section>
            </div>

            <!-- ============ 逐题复盘 ============ -->
            <div v-show="activeTab === 'questions'">
              <div class="flex flex-col gap-2.5">
                <div
                  v-for="(q, i) in report.questions"
                  :key="i"
                  class="overflow-hidden rounded-2xl border border-zinc-200/70 bg-white"
                >
                  <button
                    class="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-zinc-50"
                    @click="toggleQuestion(i)"
                  >
                    <span class="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-indigo-50 text-[12.5px] font-bold text-indigo-600">
                      {{ i + 1 }}
                    </span>
                    <span class="min-w-0 flex-1">
                      <span class="block truncate text-[13.5px] font-semibold text-zinc-800">
                        {{ q.question }}
                      </span>
                      <span class="mt-0.5 block text-[11px] text-zinc-400">
                        {{ q.topic || '综合考察' }} · 我的回答 {{ q.my_answer.length }} 字 · 均分
                        {{ questionAvg(q) }}
                      </span>
                    </span>
                    <span class="flex shrink-0 items-center gap-1">
                      <span
                        v-for="k in ['structure', 'depth', 'clarity']"
                        :key="k"
                        class="rounded px-1.5 py-0.5 text-[10.5px] font-semibold"
                        :class="scoreChipClass(q.scores[k])"
                      >
                        {{ { structure: '结构', depth: '深度', clarity: '表达' }[k] }} {{ q.scores[k] }}
                      </span>
                    </span>
                    <n-icon
                      :component="ChevronForwardOutline"
                      :size="14"
                      class="shrink-0 text-zinc-300 transition-transform"
                      :class="expandedQs.has(i) ? 'rotate-90' : ''"
                    />
                  </button>

                  <div v-if="expandedQs.has(i)" class="border-t border-zinc-100 bg-zinc-50/50 px-4 py-4">
                    <div class="mb-3 grid grid-cols-3 gap-3">
                      <div
                        v-for="k in ['structure', 'depth', 'clarity']"
                        :key="k"
                        class="rounded-xl bg-white px-3 py-2.5 ring-1 ring-zinc-100"
                      >
                        <div class="text-[10.5px] text-zinc-400">
                          {{ { structure: '结构', depth: '深度', clarity: '表达' }[k] }}
                        </div>
                        <div class="mt-0.5 flex items-baseline gap-1">
                          <span class="text-[18px] font-bold tabular-nums text-zinc-800">{{ q.scores[k] }}</span>
                          <span class="text-[10.5px] text-zinc-400">/ 5</span>
                        </div>
                        <div class="mt-1.5 flex gap-0.5">
                          <span
                            v-for="dot in 5"
                            :key="dot"
                            class="h-1.5 flex-1 rounded-full"
                            :style="{ background: dot <= q.scores[k] ? '#6366f1' : '#e4e4e7' }"
                          />
                        </div>
                      </div>
                    </div>
                    <div class="rounded-xl bg-white px-4 py-3 text-[12.5px] leading-relaxed text-zinc-600 ring-1 ring-zinc-100">
                      <span class="font-semibold text-zinc-800">我的回答要点：</span>{{ q.my_answer }}
                    </div>
                    <div v-if="q.good.length" class="mt-2.5 space-y-1.5">
                      <div v-for="(g, gi) in q.good" :key="'g' + gi" class="flex items-start gap-2 text-[12.5px] text-zinc-600">
                        <n-icon :component="CheckmarkCircleOutline" :size="14" class="mt-0.5 shrink-0 text-emerald-500" />{{ g }}
                      </div>
                    </div>
                    <div v-if="q.bad.length" class="mt-2 space-y-1.5">
                      <div v-for="(b, bi) in q.bad" :key="'b' + bi" class="flex items-start gap-2 text-[12.5px] text-zinc-600">
                        <n-icon :component="BugOutline" :size="14" class="mt-0.5 shrink-0 text-amber-500" />{{ b }}
                      </div>
                    </div>
                    <div v-if="q.reference" class="mt-3 rounded-xl border border-zinc-100 bg-white px-4 py-3">
                      <div class="mb-1 flex items-center gap-1.5 text-[11.5px] font-bold text-zinc-700">
                        <n-icon :component="BookOutline" :size="13" /> 参考答题要点
                      </div>
                      <p class="whitespace-pre-wrap text-[12.5px] leading-relaxed text-zinc-600">{{ q.reference }}</p>
                    </div>
                    <div v-if="q.improved" class="mt-2.5 rounded-xl border border-indigo-100 bg-indigo-50/50 px-4 py-3">
                      <div class="mb-1 flex items-center gap-1.5 text-[11.5px] font-bold text-indigo-600">
                        <n-icon :component="SparklesOutline" :size="13" /> 更好的回答示范
                      </div>
                      <p class="whitespace-pre-wrap text-[12.5px] leading-relaxed text-zinc-600">{{ q.improved }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- ============ JD 对照 ============ -->
            <div v-show="activeTab === 'jd'" class="grid grid-cols-1 gap-3.5 md:grid-cols-2">
              <section class="rounded-2xl border border-zinc-200/70 bg-white p-5">
                <h2 class="mb-3 flex items-center gap-1.5 text-[14px] font-bold text-zinc-800">
                  <n-icon :component="CheckmarkCircleOutline" :size="15" class="text-emerald-500" />
                  已展示的要求
                  <span class="ml-auto rounded-full bg-emerald-50 px-2 text-[11px] text-emerald-600">
                    {{ report.jd_match.demonstrated.length }}
                  </span>
                </h2>
                <div class="space-y-2">
                  <div
                    v-for="(d, i) in report.jd_match.demonstrated"
                    :key="i"
                    class="rounded-xl bg-emerald-50/60 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-zinc-600"
                  >
                    {{ d }}
                  </div>
                  <div v-if="!report.jd_match.demonstrated.length" class="text-[12px] text-zinc-400">—</div>
                </div>
              </section>
              <section class="rounded-2xl border border-zinc-200/70 bg-white p-5">
                <h2 class="mb-3 flex items-center gap-1.5 text-[14px] font-bold text-zinc-800">
                  <n-icon :component="AlertCircleOutline" :size="15" class="text-amber-500" />
                  尚未覆盖 / 答弱的差距
                  <span class="ml-auto rounded-full bg-amber-50 px-2 text-[11px] text-amber-600">
                    {{ report.jd_match.gaps.length }}
                  </span>
                </h2>
                <div class="space-y-2">
                  <div
                    v-for="(g, i) in report.jd_match.gaps"
                    :key="i"
                    class="rounded-xl bg-amber-50/70 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-zinc-600"
                  >
                    {{ g }}
                  </div>
                  <div v-if="!report.jd_match.gaps.length" class="text-[12px] text-zinc-400">—</div>
                </div>
              </section>
            </div>

            <!-- ============ 行动与沉淀 ============ -->
            <div v-show="activeTab === 'actions'" class="flex flex-col gap-3.5">
              <section class="rounded-2xl border border-zinc-200/70 bg-white p-5">
                <h2 class="mb-3 text-[14px] font-bold text-zinc-800">下一步行动清单</h2>
                <div class="space-y-2">
                  <div
                    v-for="(a, i) in report.action_items"
                    :key="i"
                    class="flex items-start gap-3 rounded-xl bg-zinc-50 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-zinc-600"
                  >
                    <span class="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md bg-white text-[10px] font-bold text-indigo-500 ring-1 ring-zinc-200">
                      {{ i + 1 }}
                    </span>
                    {{ a }}
                  </div>
                  <div v-if="!report.action_items.length" class="text-[12px] text-zinc-400">—</div>
                </div>
              </section>

              <section
                v-if="report.questions_for_bank.length"
                class="rounded-2xl border border-zinc-200/70 bg-white p-5"
              >
                <h2 class="mb-1 text-[14px] font-bold text-zinc-800">真题沉淀</h2>
                <p class="mb-3 text-[11.5px] text-zinc-400">
                  存入题库后会标记为「真实面试」来源，后续 AI 预测题目时会参考你的薄弱维度
                </p>
                <div class="flex flex-col gap-2">
                  <div
                    v-for="(q, i) in report.questions_for_bank"
                    :key="i"
                    class="flex items-center gap-3 rounded-xl bg-zinc-50 px-3.5 py-2.5"
                  >
                    <span class="min-w-0 flex-1 truncate text-[12.5px] text-zinc-700">{{ q.content }}</span>
                    <span class="shrink-0 rounded-md bg-white px-1.5 py-0.5 text-[10.5px] text-zinc-500 ring-1 ring-zinc-200">
                      {{ q.dimension }}
                    </span>
                    <span class="shrink-0 rounded-md bg-white px-1.5 py-0.5 text-[10.5px] text-zinc-500 ring-1 ring-zinc-200">
                      {{ q.difficulty }}
                    </span>
                    <n-button
                      size="tiny"
                      :type="savedBank.has(i) ? 'default' : 'primary'"
                      :disabled="savedBank.has(i)"
                      :loading="bankSaving.has(i)"
                      secondary
                      @click="addToBank(i, q)"
                    >
                      {{ savedBank.has(i) ? '已入题库' : '存入题库' }}
                    </n-button>
                  </div>
                </div>
              </section>

              <div class="pb-2 text-center text-[11px] text-zinc-300">
                报告由 AI 生成（{{ rec.review?.model }}），仅供参考 ·
                {{ rec.review?.created_at?.slice(0, 19).replace('T', ' ') }}
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
