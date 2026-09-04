<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NInput, useMessage } from 'naive-ui'
import {
  ArrowBackOutline,
  CloudUploadOutline,
  SparklesOutline,
} from '@vicons/ionicons5'
import { api } from '../api'
import type { Resume } from '../types'
import {
  parseResumeQuestions,
  parseResumeSuggestions,
} from '../types'

const props = defineProps<{ resumeId: number | null }>()
const emit = defineEmits<{ (e: 'back'): void }>()

const message = useMessage()

const resume = ref<Resume | null>(null)
const loading = ref(false)
const viewMode = ref<'structured' | 'raw'>('structured')
const activeTab = ref<'content' | 'review' | 'questions'>('content')
const busy = ref<'structure' | 'review' | 'questions' | null>(null)

// 背景信息说明（AI 体检与出题的重要依据）
const bgDraft = ref('')
const bgSaving = ref(false)
const bgDirty = computed(() => bgDraft.value !== (resume.value?.background ?? ''))

watch(resume, (r) => {
  if (r) bgDraft.value = r.background ?? ''
})

async function saveBackground() {
  if (!resume.value) return
  bgSaving.value = true
  try {
    resume.value = await api.updateResume(resume.value.id, {
      background: bgDraft.value.trim() || null,
    })
    message.success('背景信息已保存，AI 体检与出题会将其作为重要依据')
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    bgSaving.value = false
  }
}

async function load() {
  if (props.resumeId == null) return
  loading.value = true
  try {
    const data = await api.listResumes()
    resume.value = data.items.find((r) => r.id === props.resumeId) ?? null
    if (resume.value) {
      viewMode.value = resume.value.structured ? 'structured' : 'raw'
    }
  } catch (e) {
    message.error((e as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.resumeId, resume.value?.id],
  () => {
    if (resume.value?.id !== props.resumeId) load()
  },
  { immediate: true },
)

const suggestions = computed(() => parseResumeSuggestions(resume.value))
const predictedQuestions = computed(() => parseResumeQuestions(resume.value))

const scoreTone = computed(() => {
  const s = resume.value?.score
  if (s == null) return { color: '#a1a1aa', label: '' }
  if (s >= 85) return { color: '#10b981', label: '优秀' }
  if (s >= 70) return { color: '#6366f1', label: '良好' }
  if (s >= 60) return { color: '#f59e0b', label: '及格' }
  return { color: '#ef4444', label: '需优化' }
})
const ringStyle = computed(() => {
  const s = resume.value?.score ?? 0
  return {
    background: `conic-gradient(${scoreTone.value.color} ${s * 3.6}deg, #e4e4e7 ${s * 3.6}deg)`,
  }
})

const LEVEL_META: Record<string, { label: string; class: string }> = {
  high: { label: '硬伤', class: 'bg-rose-50 text-rose-600' },
  mid: { label: '加分', class: 'bg-amber-50 text-amber-600' },
  low: { label: '锦上添花', class: 'bg-zinc-100 text-zinc-500' },
}

/** 把 AI 整理出的 Markdown 拆成可渲染块：标题 / 条目（带层级）/ 段落 */
interface Block {
  t: 'h' | 'li' | 'p'
  text: string
  level: number
}

const blocks = computed<Block[]>(() => {
  const md = resume.value?.structured
  if (!md || viewMode.value !== 'structured') return []
  return md.split('\n').flatMap<Block>((raw) => {
    const indent = raw.length - raw.trimStart().length
    const line = raw.trim()
    if (!line) return []
    const level = Math.min(3, Math.floor(indent / 2))
    if (line.startsWith('## ')) return [{ t: 'h', text: line.slice(3).trim(), level: 0 }]
    if (line.startsWith('# ')) return [{ t: 'h', text: line.slice(2).trim(), level: 0 }]
    if (/^[-*•]\s+/.test(line))
      return [{ t: 'li', text: line.replace(/^[-*•]\s+/, ''), level }]
    return [{ t: 'p', text: line, level: 0 }]
  })
})

async function run(kind: 'structure' | 'review' | 'questions') {
  if (!resume.value) return
  busy.value = kind
  try {
    const saved =
      kind === 'structure'
        ? await api.structureResume(resume.value.id)
        : kind === 'review'
          ? await api.reviewResume(resume.value.id)
          : await api.predictResumeQuestions(resume.value.id)
    resume.value = saved
    if (kind === 'structure') {
      viewMode.value = 'structured'
      message.success('已按五大板块整理完成')
    } else if (kind === 'review') {
      message.success(`体检完成，得分 ${saved.score} 分`)
    } else {
      message.success(`已生成 ${parseResumeQuestions(saved).length} 道预测题`)
    }
  } catch (e) {
    message.error((e as Error).message || 'AI 调用失败', { duration: 6000 })
  } finally {
    busy.value = null
  }
}

async function setDefault() {
  if (!resume.value) return
  try {
    await api.setDefaultResume(resume.value.id)
    resume.value = { ...resume.value, is_default: true }
    message.success('已设为默认简历')
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  }
}

function fmtSize(size: number): string {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(size / 1024))} KB`
}

function fmtDate(dt: string): string {
  const d = new Date(dt)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}/${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
</script>

<template>
  <div class="flex h-full flex-col overflow-y-auto">
    <!-- 顶部：返回 + 简历身份 + 操作 + 页签 -->
    <header
      class="sticky top-0 z-10 border-b border-zinc-200/70 bg-[#f5f6f8]/95 px-7 pt-5 backdrop-blur"
    >
      <button
        class="mb-3 inline-flex items-center gap-1.5 text-[12.5px] text-zinc-400 transition-colors hover:text-indigo-500"
        @click="emit('back')"
      >
        <n-icon :component="ArrowBackOutline" :size="14" />
        返回简历管理
      </button>

      <div v-if="resume" class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex min-w-0 items-center gap-3.5">
          <div
            class="grid h-12 w-12 shrink-0 place-items-center rounded-2xl text-[13px] font-bold uppercase tracking-wide"
            :class="resume.ext === '.pdf' ? 'bg-rose-50 text-rose-500' : 'bg-sky-50 text-sky-600'"
          >
            {{ resume.ext.replace('.', '') }}
          </div>
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="truncate text-[20px] font-bold tracking-tight text-zinc-900">
                {{ resume.name }}
              </h1>
              <span
                v-if="resume.is_default"
                class="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[11px] font-medium text-indigo-600"
              >
                默认简历
              </span>
              <span
                v-if="resume.score != null"
                class="rounded-md px-1.5 py-0.5 text-[11px] font-semibold"
                :style="{ background: scoreTone.color + '18', color: scoreTone.color }"
              >
                体检 {{ resume.score }} 分 · {{ scoreTone.label }}
              </span>
            </div>
            <p class="mt-1 text-[12.5px] text-zinc-400">
              {{ resume.filename }} · {{ fmtSize(resume.size) }} · 上传于
              {{ fmtDate(resume.created_at) }}
              <template v-if="resume.text"> · 抽取 {{ resume.text.length }} 字</template>
            </p>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <n-button
            v-if="resume.text && !resume.structured"
            size="small"
            type="primary"
            secondary
            :loading="busy === 'structure'"
            @click="run('structure')"
          >
            <template #icon><n-icon :component="SparklesOutline" /></template>
            AI 整理格式
          </n-button>
          <n-button
            v-if="!resume.is_default"
            size="small"
            type="primary"
            secondary
            @click="setDefault"
          >
            设为默认简历
          </n-button>
          <a :href="api.resumeFileUrl(resume.id)" target="_blank">
            <n-button size="small">
              <template #icon><n-icon :component="CloudUploadOutline" /></template>
              下载原文
            </n-button>
          </a>
        </div>
      </div>

      <!-- 页签 -->
      <nav v-if="resume" class="detail-tabs mt-3">
        <button
          class="detail-tab"
          :class="activeTab === 'content' && 'active'"
          @click="activeTab = 'content'"
        >
          结构化简历
        </button>
        <button
          class="detail-tab"
          :class="activeTab === 'review' && 'active'"
          @click="activeTab = 'review'"
        >
          AI 简历体检
          <span
            v-if="resume.score != null"
            class="tab-chip"
            :style="{ background: scoreTone.color + '18', color: scoreTone.color }"
          >
            {{ resume.score }} 分
          </span>
        </button>
        <button
          class="detail-tab"
          :class="activeTab === 'questions' && 'active'"
          @click="activeTab = 'questions'"
        >
          预测面试题
          <span v-if="predictedQuestions.length" class="tab-chip bg-indigo-50 text-indigo-600">
            {{ predictedQuestions.length }} 道
          </span>
        </button>
      </nav>
    </header>

    <!-- 背景信息说明：体检 / 预测题页签共用 -->
    <div
      v-if="resume && (activeTab === 'review' || activeTab === 'questions')"
      class="mx-auto w-full max-w-[860px] px-7 pt-5"
    >
      <div class="rounded-2xl border border-zinc-200/80 bg-white p-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 class="text-[13.5px] font-semibold text-zinc-800">背景信息说明</h3>
            <p class="mt-0.5 text-[11.5px] text-zinc-400">
              目标方向、工作年限、期望、求职诉求、特殊情况（Gap / 转行）等——AI 体检与出题的重要依据
            </p>
          </div>
          <n-button
            v-if="bgDirty"
            size="tiny"
            type="primary"
            :loading="bgSaving"
            @click="saveBackground"
          >
            保存
          </n-button>
        </div>
        <n-input
          v-model:value="bgDraft"
          type="textarea"
          :rows="3"
          class="mt-2.5"
          placeholder="例：8 年 Java 后端经验，主投高级/专家岗，期望 25-35K；想去平台型中型公司；上家因业务收缩离职，目前在职看机会"
        />
      </div>
    </div>

    <!-- 主体 -->
    <div v-if="loading" class="grid flex-1 place-items-center text-sm text-zinc-400">
      正在加载…
    </div>
    <div v-else-if="!resume" class="grid flex-1 place-items-center">
      <div class="text-center">
        <p class="text-[13px] text-zinc-400">简历不存在或已被删除</p>
        <n-button quaternary class="mt-2" @click="emit('back')">返回简历管理</n-button>
      </div>
    </div>

    <!-- Tab：结构化简历 -->
    <div v-else-if="activeTab === 'content'" class="mx-auto w-full max-w-[920px] px-7 py-6">
      <div class="mb-4 flex items-center justify-between">
        <p class="text-[12.5px] text-zinc-400">
          AI 按五大板块整理，只调格式不改内容；可与原文对照检查
        </p>
        <div v-if="resume.structured" class="seg">
          <button :class="viewMode === 'structured' && 'active'" @click="viewMode = 'structured'">整理后</button>
          <button :class="viewMode === 'raw' && 'active'" @click="viewMode = 'raw'">原文</button>
        </div>
      </div>

      <div
        v-if="viewMode === 'structured' && !resume.structured"
        class="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-violet-200 bg-violet-50/40 px-6 py-14 text-center"
      >
        <n-icon :component="SparklesOutline" :size="28" class="text-violet-400" />
        <p class="text-[13px] text-zinc-500">
          还没有进行格式整理 · AI 会把简历内容按<br />
          <span class="font-medium text-zinc-700">个人信息 / 教育背景 / 专业技能 / 工作经历 / 项目经历</span><br />
          五大板块重排，只调格式不改内容
        </p>
        <n-button type="primary" :loading="busy === 'structure'" @click="run('structure')">
          AI 整理格式
        </n-button>
      </div>

      <div
        v-else-if="viewMode === 'structured' && blocks.length"
        class="rounded-2xl border border-zinc-200/80 bg-white px-5 py-4 shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
      >
        <template v-for="(b, i) in blocks" :key="i">
          <div v-if="b.t === 'h'" class="mb-2.5 mt-6 flex items-center gap-2 first:mt-1">
            <span class="h-4 w-1 rounded-full bg-indigo-500" />
            <span class="text-[14.5px] font-bold text-zinc-800">{{ b.text }}</span>
          </div>
          <div
            v-else-if="b.t === 'li'"
            class="flex gap-2 py-[4px]"
            :style="{ marginLeft: b.level * 20 + 'px' }"
          >
            <span
              v-if="b.level === 0"
              class="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-zinc-400"
            />
            <span v-else-if="b.level === 1" class="shrink-0 text-[12px] leading-[21px] text-zinc-300">▸</span>
            <span v-else class="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-zinc-200" />
            <span
              class="leading-relaxed"
              :class="[
                b.level === 0
                  ? 'text-[13.5px] font-medium text-zinc-800'
                  : b.level === 1
                    ? 'text-[13px] text-zinc-600'
                    : 'text-[12.5px] text-zinc-500',
              ]"
            >{{ b.text }}</span>
          </div>
          <p v-else class="py-[3px] text-[13px] leading-relaxed text-zinc-700">{{ b.text }}</p>
        </template>
      </div>

      <p
        v-else
        class="whitespace-pre-wrap rounded-2xl border border-zinc-200/80 bg-white px-5 py-4 text-[13px] leading-relaxed text-zinc-700 shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
      >{{ resume.text || '没有抽取到文本（该格式不支持自动抽取）' }}</p>
    </div>

    <!-- Tab：AI 简历体检 -->
    <div v-else-if="activeTab === 'review'" class="mx-auto w-full max-w-[860px] px-7 py-6">
      <div v-if="resume.score != null" class="space-y-4">
        <!-- 得分总览 -->
        <div class="flex items-center gap-6 rounded-2xl border border-zinc-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
          <div class="flex flex-col items-center gap-1.5">
            <div class="grid h-28 w-28 place-items-center rounded-full" :style="ringStyle">
              <div class="grid h-[88px] w-[88px] place-items-center rounded-full bg-white">
                <span class="text-[30px] font-bold tabular-nums" :style="{ color: scoreTone.color }">
                  {{ resume.score }}
                </span>
              </div>
            </div>
            <span class="text-[12px] font-semibold" :style="{ color: scoreTone.color }">
              {{ scoreTone.label }}
            </span>
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-[14px] font-semibold text-zinc-800">综合体检结论</div>
            <p class="mt-1.5 text-[12.5px] leading-relaxed text-zinc-500">
              从内容完整性、亮点与量化程度、经历说服力、表达简洁度、岗位匹配度五个维度综合评估，
              共给出 {{ suggestions.length }} 条优化建议
              （硬伤 {{ suggestions.filter((s) => s.level === 'high').length }} /
              加分 {{ suggestions.filter((s) => s.level === 'mid').length }} /
              锦上添花 {{ suggestions.filter((s) => s.level === 'low').length }}）。
            </p>
            <div class="mt-2.5 flex items-center gap-2">
              <n-button size="tiny" quaternary type="primary" :loading="busy === 'review'" @click="run('review')">
                重新体检
              </n-button>
              <span class="text-[11px] text-zinc-400">体检基于当前结构化内容，整理后建议重新体检</span>
            </div>
          </div>
        </div>

        <!-- 建议列表 -->
        <div
          v-for="(s, i) in suggestions"
          :key="i"
          class="rounded-2xl border border-zinc-200/80 bg-white p-4 shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
        >
          <div class="flex items-center gap-2">
            <span
              class="shrink-0 rounded px-1.5 py-0.5 text-[10.5px] font-semibold"
              :class="LEVEL_META[s.level]?.class ?? LEVEL_META.low.class"
            >
              {{ LEVEL_META[s.level]?.label ?? '建议' }}
            </span>
            <span class="text-[13.5px] font-semibold text-zinc-800">{{ i + 1 }}. {{ s.title }}</span>
          </div>
          <p class="mt-1.5 text-[12.5px] leading-relaxed text-zinc-500">{{ s.detail }}</p>
        </div>
      </div>

      <div v-else class="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-zinc-200 bg-white/70 px-6 py-20 text-center">
        <n-icon :component="SparklesOutline" :size="30" class="text-indigo-400" />
        <p class="text-[13.5px] font-medium text-zinc-600">还没有体检报告</p>
        <p class="text-[12.5px] leading-relaxed text-zinc-400">
          以面试官视角打分（0-100），<br />并给出 6-8 条具体到条目的优化建议
        </p>
        <n-button type="primary" :loading="busy === 'review'" @click="run('review')">
          生成体检报告
        </n-button>
      </div>
    </div>

    <!-- Tab：预测面试题 -->
    <div v-else-if="activeTab === 'questions'" class="mx-auto w-full max-w-[860px] px-7 py-6">
      <div v-if="predictedQuestions.length" class="space-y-4">
        <div class="flex items-center justify-between">
          <p class="text-[12.5px] text-zinc-400">
            基于简历真实内容预测的追问式问题，共 {{ predictedQuestions.length }} 道
          </p>
          <n-button size="tiny" quaternary type="primary" :loading="busy === 'questions'" @click="run('questions')">
            重新生成
          </n-button>
        </div>
        <div
          v-for="(item, i) in predictedQuestions"
          :key="i"
          class="rounded-2xl border border-zinc-200/80 bg-white p-4 shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
        >
          <div class="flex items-start gap-2.5">
            <span class="mt-px shrink-0 rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10.5px] font-medium text-indigo-600">
              {{ item.tag }}
            </span>
            <p class="text-[13.5px] font-semibold leading-relaxed text-zinc-800">
              Q{{ i + 1 }}. {{ item.q }}
            </p>
          </div>
          <details class="mt-2">
            <summary class="cursor-pointer select-none text-[11.5px] text-zinc-400 hover:text-zinc-600">
              参考答案要点
            </summary>
            <p class="mt-1.5 whitespace-pre-wrap rounded-xl bg-emerald-50/60 px-3 py-2.5 text-[12.5px] leading-relaxed text-zinc-600">
              {{ item.a }}
            </p>
          </details>
        </div>
      </div>

      <div v-else class="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-zinc-200 bg-white/70 px-6 py-20 text-center">
        <n-icon :component="SparklesOutline" :size="30" class="text-indigo-400" />
        <p class="text-[13.5px] font-medium text-zinc-600">还没有预测题</p>
        <p class="text-[12.5px] leading-relaxed text-zinc-400">
          基于简历中的项目与技能预测<br />面试官最可能追问的问题，附参考答案要点
        </p>
        <n-button type="primary" :loading="busy === 'questions'" @click="run('questions')">
          生成预测题
        </n-button>
      </div>
    </div>
  </div>
</template>
