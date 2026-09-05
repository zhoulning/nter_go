<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  NButton,
  NEmpty,
  NForm,
  NFormItem,
  NModal,
  NSelect,
  NUpload,
  useDialog,
  useMessage,
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { AddOutline, ArrowForwardOutline, DocumentTextOutline, DownloadOutline, MicOutline } from '@vicons/ionicons5'
import { api } from '../api'
import type { RecordingInfo } from '../api'
import type { Opportunity as Opp } from '../types'
import { ROUND_LABEL, avatarGradient } from '../types'
import RecordingDetailView from './RecordingDetailView.vue'

const message = useMessage()
const dialog = useDialog()

const recordings = ref<RecordingInfo[]>([])
const opportunities = ref<Opp[]>([])
const loading = ref(true)
// 详情 id 与 URL 同步（?page=recordings&id=3 刷新/直达均停留在该条复盘）
const detailId = ref<number | null>(initialIdFromUrl())

function initialIdFromUrl(): number | null {
  const raw = new URLSearchParams(location.search).get('id')
  return raw ? Number(raw) || null : null
}

function syncIdParam(id: number | null) {
  const params = new URLSearchParams(location.search)
  if (id == null) params.delete('id')
  else params.set('id', String(id))
  history.replaceState(null, '', `?${params.toString()}`)
}

function openDetail(id: number) {
  detailId.value = id
  syncIdParam(id)
}

function closeDetail() {
  detailId.value = null
  syncIdParam(null)
}

// 上传弹窗
const uploadShow = ref(false)
const uploading = ref(false)
const createType = ref<'recording' | 'text'>('recording')
const uploadOppId = ref<number | null>(null)
const uploadRoundId = ref<number | null>(null)
const uploadFile = ref<File | null>(null)
const textTitle = ref('')
const textTranscript = ref('')

const activeOppOptions = computed(() =>
  opportunities.value
    .filter((o) => !['rejected', 'no_response', 'give_up'].includes(o.status))
    .map((o) => ({ label: `${o.company} · ${o.position}`, value: o.id })),
)

const roundOptions = computed(() => {
  const opp = opportunities.value.find((o) => o.id === uploadOppId.value)
  if (!opp) return []
  return [
    ...opp.rounds.map((r) => {
      const d = r.scheduled_at ? new Date(r.scheduled_at) : null
      const date = d ? ` ${d.getMonth() + 1}/${d.getDate()}` : ''
      return { label: `${ROUND_LABEL[r.round_type] ?? '面试'}${date}`, value: r.id }
    }),
    { label: '不关联具体轮次', value: -1 },
  ]
})

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const [recData, oppData] = await Promise.all([api.listRecordings(), api.listOpportunities()])
    recordings.value = recData.items
    opportunities.value = oppData.items
  } catch (e) {
    if (!silent) message.error((e as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(() => load())

// 有进行中的任务时自动轮询刷新
const pollTimer = window.setInterval(() => {
  if (recordings.value.some((r) => r.status === 'transcribing' || r.review_status === 'running')) {
    load(true)
  }
}, 3000)
onBeforeUnmount(() => window.clearInterval(pollTimer))

// ---- 上传 ----
function openCreate() {
  createType.value = 'recording'
  uploadOppId.value = null
  uploadRoundId.value = null
  uploadFile.value = null
  textTitle.value = ''
  textTranscript.value = ''
  uploadShow.value = true
}

function onFileChange(options: { file: UploadFileInfo; fileList: UploadFileInfo[] }) {
  uploadFile.value = (options.file.file as File) ?? null
}

async function submitCreate() {
  if (!uploadOppId.value) return message.warning('请选择关联的岗位')
  uploading.value = true
  try {
    const roundId = uploadRoundId.value === -1 ? null : uploadRoundId.value
    let rec: RecordingInfo
    if (createType.value === 'text') {
      if (textTranscript.value.trim().length < 10) {
        message.warning('请填写面试文字稿（至少 10 个字）')
        uploading.value = false
        return
      }
      rec = await api.createTextRecording({
        opportunity_id: uploadOppId.value,
        round_id: roundId,
        title: textTitle.value.trim() || null,
        transcript: textTranscript.value,
      })
      message.success('文字复盘已创建')
    } else {
      if (!uploadFile.value) {
        message.warning('请选择录音文件')
        uploading.value = false
        return
      }
      rec = await api.uploadRecording(uploadFile.value, uploadOppId.value, roundId)
      message.success('录音已上传')
    }
    uploadShow.value = false
    await load(true)
    openDetail(rec.id)
  } catch (e) {
    message.error((e as Error).message || '创建失败')
  } finally {
    uploading.value = false
  }
}

// ---- 操作 ----
function doTranscribe(rec: RecordingInfo, engine: 'local' | 'cloud') {
  api
    .transcribeRecording(rec.id, engine)
    .then(() => {
      message.success(engine === 'local' ? '已启动本地转写' : '已启动云端转写')
      load(true)
    })
    .catch((e) => message.error((e as Error).message, { duration: 6000 }))
}

function confirmDelete(rec: RecordingInfo) {
  dialog.warning({
    title: '删除录音',
    content: `确定删除「${rec.company} · ${rec.filename}」吗？文字稿与复盘报告会一并删除。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteRecording(rec.id)
        message.success('已删除')
        await load(true)
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}

// ---- 展示辅助 ----
function fmtSize(bytes: number): string {
  if (bytes > 1024 * 1024 * 1024) return (bytes / 1024 ** 3).toFixed(1) + ' GB'
  if (bytes > 1024 * 1024) return (bytes / 1024 ** 2).toFixed(1) + ' MB'
  return Math.max(1, Math.round(bytes / 1024)) + ' KB'
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

function transcribeBadge(rec: RecordingInfo) {
  if (rec.status === 'transcribing') return { text: `转写中 ${rec.progress}%`, cls: 'bg-indigo-50 text-indigo-600' }
  if (rec.status === 'transcribed') return { text: '已转写', cls: 'bg-emerald-50 text-emerald-600' }
  if (rec.status === 'failed') return { text: '转写失败', cls: 'bg-rose-50 text-rose-600' }
  return { text: '未转写', cls: 'bg-zinc-100 text-zinc-500' }
}

function reviewBadge(rec: RecordingInfo) {
  if (rec.review_status === 'running') return { text: '报告生成中', cls: 'bg-violet-50 text-violet-600' }
  if (rec.review_status === 'done') return { text: `已复盘 ${rec.review_score ?? ''}`, cls: 'bg-emerald-50 text-emerald-600' }
  if (rec.review_status === 'failed') return { text: '复盘失败', cls: 'bg-rose-50 text-rose-600' }
  return { text: '未复盘', cls: 'bg-zinc-100 text-zinc-500' }
}
</script>

<template>
  <!-- 详情模式：全屏覆盖 -->
  <RecordingDetailView
    v-if="detailId !== null"
    :id="detailId"
    @back="closeDetail"
    @changed="load(true)"
  />

  <div v-else class="flex h-full flex-col">
    <header class="fade-up flex items-end justify-between px-7 pb-4 pt-6 max-md:px-4 max-md:pt-4">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">面试复盘</h1>
        <p class="mt-1 text-[13px] text-zinc-400">
          录音复盘与文字复盘两种方式，结合岗位 JD、简历生成逐题复盘报告
        </p>
      </div>
      <button class="btn-gradient shrink-0 whitespace-nowrap max-md:ml-3" @click="openCreate">
        <n-icon :component="AddOutline" :size="16" />
        新建复盘
      </button>
    </header>

    <div v-if="loading && !recordings.length" class="grid flex-1 place-items-center text-sm text-zinc-400">
      正在加载…
    </div>

    <NEmpty
      v-else-if="recordings.length === 0"
      class="flex-1"
      size="large"
      description="还没有录音 · 点右上角「上传录音」，或直接粘贴文字稿生成复盘报告"
    />

    <div v-else class="min-h-0 flex-1 overflow-y-auto px-7 pb-6 max-md:px-4">
      <div class="flex flex-col gap-3">
        <div
          v-for="rec in recordings"
          :key="rec.id"
          class="group flex items-stretch overflow-hidden rounded-2xl border border-zinc-200/70 bg-white shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition-all hover:-translate-y-px hover:border-indigo-200 hover:shadow-[0_10px_24px_-8px_rgba(16,24,40,0.15)]"
        >
          <button
            class="flex min-w-0 flex-1 items-center gap-4 p-4 text-left"
            @click="openDetail(rec.id)"
          >
          <span
            class="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-[16px] font-bold text-white"
            :style="{ background: avatarGradient(rec.company ?? '?') }"
          >
            {{ (rec.company ?? '?').slice(0, 1) }}
          </span>
          <span class="min-w-0 flex-1">
            <span class="flex items-center gap-2 max-md:flex-wrap">
              <span class="truncate text-[14px] font-semibold text-zinc-800">{{ rec.company }}</span>
              <span
                v-if="rec.round_type"
                class="shrink-0 rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10.5px] font-medium text-zinc-500"
              >
                {{ ROUND_LABEL[rec.round_type] ?? '面试' }}
              </span>
              <span
                class="shrink-0 rounded-md px-1.5 py-0.5 text-[10.5px] font-medium"
                :class="rec.kind === 'text' ? 'bg-violet-50 text-violet-600' : 'bg-sky-50 text-sky-600'"
              >
                {{ rec.kind === 'text' ? '文字复盘' : '录音复盘' }}
              </span>
              <span
                v-if="rec.kind !== 'text'"
                class="shrink-0 rounded-full px-2 py-0.5 text-[10.5px] font-semibold"
                :class="transcribeBadge(rec).cls"
              >
                {{ transcribeBadge(rec).text }}
              </span>
              <span
                class="shrink-0 rounded-full px-2 py-0.5 text-[10.5px] font-semibold"
                :class="reviewBadge(rec).cls"
              >
                {{ reviewBadge(rec).text }}
              </span>
            </span>
            <span class="mt-0.5 flex items-center gap-2 text-[11.5px] text-zinc-400 max-md:flex-wrap">
              <span class="truncate">{{ rec.position }}</span>
              <template v-if="rec.kind === 'text'">
                <span>·</span>
                <span class="shrink-0">{{ (rec.transcript || '').length }} 字</span>
              </template>
              <template v-else>
                <span>·</span>
                <span class="shrink-0">{{ fmtDuration(rec.duration_sec) }}</span>
                <span>·</span>
                <span class="shrink-0">{{ fmtSize(rec.size) }}</span>
              </template>
              <span>·</span>
              <span class="shrink-0">{{ new Date(rec.created_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }}</span>
            </span>
          </span>
            <n-icon
              :component="ArrowForwardOutline"
              :size="16"
              class="shrink-0 text-zinc-300 transition-colors group-hover:text-indigo-400"
            />
          </button>
          <div
            class="flex w-12 shrink-0 items-center justify-center border-l border-zinc-100 opacity-0 transition-opacity group-hover:opacity-100 max-md:opacity-100"
          >
            <a
              :href="api.recordingFileUrl(rec.id)"
              :download="rec.filename"
              title="下载录音"
              class="grid h-8 w-8 place-items-center rounded-lg text-zinc-400 hover:bg-indigo-50 hover:text-indigo-600"
              @click.stop
            >
              <n-icon :component="DownloadOutline" :size="15" />
            </a>
          </div>
        </div>
      </div>
    </div>

    <!-- 上传弹窗 -->
    <n-modal :show="uploadShow" transform-origin="center" @update:show="uploadShow = $event">
      <div class="modal-card">
        <div class="mb-4">
          <h2 class="text-[16px] font-bold text-zinc-900">新建面试复盘</h2>
          <p class="mt-0.5 text-[12px] text-zinc-400">
            有录音选「录音复盘」，现场面试没录音选「文字复盘」直接写文字稿
          </p>
        </div>
        <div class="mb-4 flex items-center gap-1 rounded-xl bg-zinc-100/80 p-1">
          <button
            class="flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-medium transition-all"
            :class="createType === 'recording' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500'"
            @click="createType = 'recording'"
          >
            <n-icon :component="MicOutline" :size="14" /> 录音复盘
          </button>
          <button
            class="flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-medium transition-all"
            :class="createType === 'text' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500'"
            @click="createType = 'text'"
          >
            <n-icon :component="DocumentTextOutline" :size="14" /> 文字复盘
          </button>
        </div>
        <n-form label-placement="top" size="small">
          <n-form-item label="关联岗位" required>
            <n-select
              v-model:value="uploadOppId"
              :options="activeOppOptions"
              filterable
              placeholder="选择这次面试所属的岗位"
            />
          </n-form-item>
          <n-form-item label="关联轮次">
            <n-select
              v-model:value="uploadRoundId"
              :options="roundOptions"
              :disabled="!uploadOppId"
              placeholder="选填：这场录音对应哪一轮"
            />
          </n-form-item>
          <template v-if="createType === 'recording'">
            <n-form-item label="录音文件" required>
              <n-upload
                :max="1"
                :default-upload="false"
                accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,.webm,.wma,audio/*"
                @change="onFileChange"
              >
                <n-button>
                  <n-icon :component="MicOutline" :size="15" class="mr-1.5" />
                  选择音频文件
                </n-button>
              </n-upload>
              <span class="ml-2 text-[11px] text-zinc-400">mp3 / wav / m4a 等，≤ 200MB</span>
            </n-form-item>
          </template>
          <template v-else>
            <n-form-item label="复盘标题">
              <n-input v-model:value="textTitle" placeholder="选填，默认「文字复盘 + 日期」" />
            </n-form-item>
            <n-form-item label="面试文字稿" required>
              <n-input
                v-model:value="textTranscript"
                type="textarea"
                :rows="6"
                placeholder="粘贴或撰写这场面试的问答记录 / 面经，建议标注「面试官 / 我」，生成报告后还可用 AI 矫正"
              />
            </n-form-item>
          </template>
        </n-form>
        <div class="mt-2 flex justify-end gap-2.5">
          <n-button quaternary @click="uploadShow = false">取消</n-button>
          <n-button type="primary" class="!px-5" :loading="uploading" @click="submitCreate">
            {{ createType === 'text' ? '创建' : '上传' }}
          </n-button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<style scoped>
.modal-card {
  width: 520px;
  max-width: calc(100vw - 48px);
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  box-shadow:
    0 20px 50px -12px rgba(16, 24, 40, 0.25),
    0 0 0 1px rgba(16, 24, 40, 0.04);
}
</style>
