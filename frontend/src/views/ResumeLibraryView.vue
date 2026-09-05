<script setup lang="ts">
import { computed, h, inject, onMounted, reactive, ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import type { UploadCustomRequestOptions } from 'naive-ui'
import { CloudUploadOutline } from '@vicons/ionicons5'
import { api } from '../api'
import type { Resume, ResumeUsage } from '../types'
import { OPEN_RESUME_DETAIL } from '../injectionKeys'

const message = useMessage()
const dialog = useDialog()

const resumes = ref<Resume[]>([])
const loading = ref(true)
const uploading = ref(false)

const editShow = ref(false)
const editing = ref<Resume | null>(null)
const editForm = reactive({ name: '', note: '', background: '' })
const editSaving = ref(false)

const structuringId = ref<number | null>(null)
const openResumeDetail = inject(OPEN_RESUME_DETAIL, null)

async function structureNow(r: Resume) {
  structuringId.value = r.id
  try {
    const saved = await api.structureResume(r.id)
    message.success(`「${saved.name}」已按五大板块整理完成`)
    await load()
  } catch (e) {
    message.error((e as Error).message || 'AI 整理失败', { duration: 6000 })
  } finally {
    structuringId.value = null
  }
}

async function setDefault(r: Resume) {
  try {
    await api.setDefaultResume(r.id)
    message.success(`已将「${r.name}」设为默认简历`)
    await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  }
}

async function load() {
  loading.value = true
  try {
    const data = await api.listResumes(true)
    resumes.value = data.items
  } catch (e) {
    message.error((e as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

const totalTextWords = computed(() =>
  resumes.value.reduce((sum, r) => sum + (r.text?.length ?? 0), 0),
)

function fmtSize(size: number): string {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(size / 1024))} KB`
}

function fmtDate(dt: string): string {
  const d = new Date(dt)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}/${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

async function customRequest({ file, onFinish, onError }: UploadCustomRequestOptions) {
  uploading.value = true
  try {
    const f = file.file as File
    const saved = await api.uploadResume(f)
    message.success(`已上传「${saved.name}」${saved.text ? `，抽取到 ${saved.text.length} 字简历文本` : '（该格式暂不支持自动抽取文本）'}`)
    await load()
    onFinish()
  } catch (e) {
    message.error((e as Error).message || '上传失败')
    onError()
  } finally {
    uploading.value = false
  }
}

function beforeUpload({ file }: { file: { file?: File | null } }) {
  const f = file.file
  if (!f) return false
  const ok = /\.(pdf|docx?|)$/i.test(f.name) || /\.(pdf|docx?)$/i.test(f.name)
  if (!ok) {
    message.error('仅支持 PDF / DOC / DOCX 格式')
    return false
  }
  return true
}

function openEdit(r: Resume) {
  editing.value = r
  editForm.name = r.name
  editForm.note = r.note ?? ''
  editForm.background = r.background ?? ''
  editShow.value = true
}

async function saveEdit() {
  if (!editing.value) return
  editSaving.value = true
  try {
    await api.updateResume(editing.value.id, {
      name: editForm.name.trim() || editing.value.filename,
      note: editForm.note.trim() || null,
      background: editForm.background.trim() || null,
    })
    message.success('已保存')
    editShow.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    editSaving.value = false
  }
}

async function confirmDelete(r: Resume) {
  let totals: ResumeUsage['totals'] | null = null
  try {
    totals = (await api.getResumeUsage(r.id)).totals
  } catch {
    /* 查不到引用信息不阻塞删除 */
  }
  const n = totals ? totals.opportunities + totals.questions + totals.match_reports + totals.review_reports : 0
  const parts: string[] = []
  if (totals) {
    if (totals.opportunities) parts.push(`${totals.opportunities} 个岗位`)
    if (totals.questions) parts.push(`${totals.questions} 道题`)
    if (totals.match_reports) parts.push(`${totals.match_reports} 份匹配报告`)
    if (totals.review_reports) parts.push(`${totals.review_reports} 份复盘报告`)
  }
  dialog.warning({
    title: '删除简历',
    content: () =>
      h('div', { class: 'text-[13px] leading-6' }, [
        h('p', `确定删除「${r.name}」吗？文件也会一并删除。`),
        n > 0
          ? h('p', { class: 'mt-1 text-amber-600' }, `它当前被引用：${parts.join('、')}。删除后这些引用会被解除（置为「未关联简历」）。若只想让它退出选择器、保留历史关联，建议改用「归档」。`)
          : null,
      ]),
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteResume(r.id)
        message.success('已删除')
        usageShow.value = false
        await load()
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}

// ---- 引用一览 ----
const usageShow = ref(false)
const usageLoading = ref(false)
const usage = ref<ResumeUsage | null>(null)
const usageTotals = computed(() => {
  const t = usage.value?.totals
  if (!t) return null
  const n = t.opportunities + t.questions + t.match_reports + t.review_reports
  return n > 0 ? t : null
})
const usageSummaryText = computed(() => {
  const t = usageTotals.value
  if (!t) return ''
  const parts: string[] = []
  if (t.opportunities) parts.push(`${t.opportunities} 个岗位`)
  if (t.questions) parts.push(`${t.questions} 道题`)
  if (t.match_reports) parts.push(`${t.match_reports} 份匹配报告`)
  if (t.review_reports) parts.push(`${t.review_reports} 份复盘报告`)
  return parts.join('、')
})

async function openUsage(r: Resume) {
  usageShow.value = true
  usageLoading.value = true
  usage.value = null
  try {
    usage.value = await api.getResumeUsage(r.id)
  } catch (e) {
    message.error((e as Error).message || '加载引用信息失败')
    usageShow.value = false
  } finally {
    usageLoading.value = false
  }
}

async function toggleArchive(r: Resume) {
  try {
    await api.archiveResume(r.id, !r.archived)
    message.success(r.archived ? `已取消归档「${r.name}」` : `已归档「${r.name}」，它不再出现在各处简历选择器中`)
    if (usageShow.value && usage.value?.resume.id === r.id) {
      usage.value.resume.archived = !r.archived
    }
    await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  }
}
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- 页头 -->
    <header class="fade-up flex flex-wrap items-end justify-between gap-4 px-7 pb-3 pt-6 max-md:gap-2.5 max-md:px-4 max-md:pt-4">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">简历管理</h1>
        <p class="mt-1 text-[13px] text-zinc-400">
          {{ resumes.length }} 个版本 · 已抽取 {{ totalTextWords }} 字文本，供后续 AI 匹配度评估使用
        </p>
      </div>
      <n-upload
        accept=".pdf,.doc,.docx"
        :custom-request="customRequest"
        :before-upload="beforeUpload"
        :show-file-list="false"
      >
        <button class="btn-gradient shrink-0 whitespace-nowrap" :disabled="uploading">
          <n-icon :component="CloudUploadOutline" :size="16" />
          {{ uploading ? '上传中…' : '上传简历' }}
        </button>
      </n-upload>
    </header>

    <!-- 列表 -->
    <div class="min-h-0 flex-1 overflow-y-auto px-7 pb-6 max-md:px-4">
      <div v-if="loading" class="grid h-full place-items-center text-sm text-zinc-400">
        正在加载简历…
      </div>
      <div v-else-if="resumes.length === 0" class="grid h-full place-items-center">
        <div class="text-center">
          <div class="text-[42px]">📄</div>
          <p class="mt-3 text-[13px] text-zinc-400">
            还没有简历版本<br />
            <span class="text-[12px] text-zinc-300">上传 PDF / Word 简历，投递时关联版本，AI 还会抽取文本用于岗位匹配</span>
          </p>
        </div>
      </div>
      <div v-else class="fade-up-d1 flex flex-col gap-3">
        <article
          v-for="r in resumes"
          :key="r.id"
          class="flex cursor-pointer items-center gap-4 rounded-2xl border border-zinc-200/80 bg-white p-4 shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition-shadow hover:border-indigo-200 hover:shadow-[0_8px_20px_-8px_rgba(16,24,40,0.15)] max-md:flex-wrap"
          title="点击查看简历详情"
          @click="openResumeDetail?.(r.id)"
        >
          <div
            class="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-[11px] font-bold uppercase tracking-wide"
            :class="r.ext === '.pdf' ? 'bg-rose-50 text-rose-500' : 'bg-sky-50 text-sky-600'"
          >
            {{ r.ext.replace('.', '') }}
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 max-md:flex-wrap">
              <h3 class="truncate text-[14px] font-semibold text-zinc-800">{{ r.name }}</h3>
              <span
                v-if="r.is_default"
                class="shrink-0 rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10.5px] font-medium text-indigo-600"
              >
                默认
              </span>
              <span
                v-if="r.archived"
                class="shrink-0 rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10.5px] font-medium text-zinc-500"
              >
                已归档
              </span>
              <span
                v-if="r.structured"
                class="shrink-0 rounded-md bg-violet-50 px-1.5 py-0.5 text-[10.5px] font-medium text-violet-600"
              >
                已 AI 整理
              </span>
              <span
                v-if="r.score != null"
                class="shrink-0 rounded-md bg-violet-50 px-1.5 py-0.5 text-[10.5px] font-medium text-violet-600"
              >
                体检 {{ r.score }} 分
              </span>
              <span v-if="r.text" class="shrink-0 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10.5px] text-emerald-600">
                已抽取 {{ r.text.length }} 字
              </span>
              <span v-else class="shrink-0 rounded-md bg-zinc-50 px-1.5 py-0.5 text-[10.5px] text-zinc-400">
                未抽取文本
              </span>
            </div>
            <div class="mt-0.5 truncate text-[12px] text-zinc-400">
              {{ r.filename }} · {{ fmtSize(r.size) }} · 上传于 {{ fmtDate(r.created_at) }}
              <template v-if="r.note"> · {{ r.note }}</template>
            </div>
          </div>
          <div
            class="flex shrink-0 items-center gap-1 max-md:w-full max-md:flex-wrap max-md:justify-end max-md:border-t max-md:border-zinc-100 max-md:pt-1.5"
            @click.stop
          >
            <n-button size="tiny" quaternary @click="openUsage(r)">引用</n-button>
            <n-button size="tiny" quaternary type="primary" @click="openResumeDetail?.(r.id)">
              查看
            </n-button>
            <n-button
              v-if="r.text && !r.structured"
              size="tiny"
              quaternary
              type="primary"
              :loading="structuringId === r.id"
              @click="structureNow(r)"
            >
              AI 整理
            </n-button>
            <n-button
              v-if="!r.is_default"
              size="tiny"
              quaternary
              type="primary"
              @click="setDefault(r)"
            >
              设为默认
            </n-button>
            <a :href="api.resumeFileUrl(r.id)" target="_blank">
              <n-button size="tiny" quaternary type="primary">下载</n-button>
            </a>
            <n-button size="tiny" quaternary @click="openEdit(r)">编辑</n-button>
            <n-button
              v-if="!r.is_default"
              size="tiny"
              quaternary
              @click="toggleArchive(r)"
            >
              {{ r.archived ? '取消归档' : '归档' }}
            </n-button>
            <n-button size="tiny" quaternary type="error" @click="confirmDelete(r)">删除</n-button>
          </div>
        </article>
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <n-modal :show="editShow" transform-origin="center" @update:show="editShow = $event">
      <div class="edit-card">
        <h2 class="mb-4 text-[16px] font-bold text-zinc-900">编辑简历信息</h2>
        <div class="flex flex-col gap-3">
          <div>
            <div class="mb-1 text-[12.5px] font-medium text-zinc-600">版本名</div>
            <n-input v-model:value="editForm.name" placeholder="如：Java 后端-v3-强调高并发" />
          </div>
          <div>
            <div class="mb-1 text-[12.5px] font-medium text-zinc-600">备注</div>
            <n-input
              v-model:value="editForm.note"
              type="textarea"
              :rows="2"
              placeholder="选填：适用方向、投递记录等"
            />
          </div>
          <div>
            <div class="mb-1 text-[12.5px] font-medium text-zinc-600">背景信息说明</div>
            <n-input
              v-model:value="editForm.background"
              type="textarea"
              :rows="3"
              placeholder="目标方向、年限、期望、求职诉求、特殊情况等——AI 体检与出题的重要依据"
            />
          </div>
        </div>
        <div class="mt-4 flex justify-end gap-2.5">
          <n-button quaternary @click="editShow = false">取消</n-button>
          <n-button type="primary" class="!px-5" :loading="editSaving" @click="saveEdit">保存</n-button>
        </div>
      </div>
    </n-modal>
    <!-- 引用一览弹窗 -->
    <n-modal :show="usageShow" transform-origin="center" @update:show="usageShow = $event">
      <div class="edit-card !w-[520px] max-md:!w-full">
        <div class="mb-3 flex items-center justify-between gap-2">
          <h2 class="text-[16px] font-bold text-zinc-900">
            引用一览<span v-if="usage" class="ml-2 text-[13px] font-normal text-zinc-400">{{ usage.resume.name }}</span>
          </h2>
          <n-button size="tiny" quaternary @click="usageShow = false">关闭</n-button>
        </div>
        <div v-if="usageLoading" class="py-10 text-center text-[13px] text-zinc-400">加载中…</div>
        <div v-else-if="usage" class="flex flex-col gap-4">
          <p class="text-[12.5px] text-zinc-500">
            {{ usageSummaryText ? `这版简历被引用：${usageSummaryText}。` : '这版简历还没有被任何岗位、题目或报告引用。' }}
          </p>

          <div v-if="usage.opportunities.length">
            <div class="mb-1.5 text-[12.5px] font-semibold text-zinc-600">投递岗位（{{ usage.opportunities.length }}）</div>
            <div class="flex flex-col gap-1">
              <div
                v-for="o in usage.opportunities"
                :key="o.id"
                class="flex items-center justify-between gap-2 rounded-lg bg-zinc-50 px-2.5 py-1.5 text-[12.5px]"
              >
                <span class="truncate">{{ o.company }} · {{ o.position }}</span>
                <span class="shrink-0 text-zinc-400">{{ o.status }}<template v-if="o.rounds.length"> · {{ o.rounds.length }} 轮</template></span>
              </div>
            </div>
          </div>

          <div v-if="usage.questions.length">
            <div class="mb-1.5 text-[12.5px] font-semibold text-zinc-600">关联题目（{{ usage.questions.length }}）</div>
            <div class="flex max-h-40 flex-col gap-1 overflow-y-auto">
              <div
                v-for="q in usage.questions.slice(0, 20)"
                :key="q.id"
                class="truncate rounded-lg bg-zinc-50 px-2.5 py-1.5 text-[12.5px] text-zinc-600"
              >
                {{ q.content }}
              </div>
              <div v-if="usage.questions.length > 20" class="px-2.5 text-[11.5px] text-zinc-400">
                …共 {{ usage.questions.length }} 道
              </div>
            </div>
          </div>

          <div v-if="usage.match_reports.length">
            <div class="mb-1.5 text-[12.5px] font-semibold text-zinc-600">匹配度报告（{{ usage.match_reports.length }}）</div>
            <div class="flex flex-col gap-1">
              <div
                v-for="m in usage.match_reports"
                :key="m.id"
                class="flex items-center justify-between gap-2 rounded-lg bg-zinc-50 px-2.5 py-1.5 text-[12.5px]"
              >
                <span class="truncate">{{ m.company ?? `岗位 #${m.opportunity_id}` }}</span>
                <span class="shrink-0 text-zinc-400">匹配 {{ m.total_score }} 分</span>
              </div>
            </div>
          </div>

          <div v-if="usage.review_reports.length">
            <div class="mb-1.5 text-[12.5px] font-semibold text-zinc-600">录音复盘报告（{{ usage.review_reports.length }}）</div>
            <div class="flex flex-col gap-1">
              <div
                v-for="v in usage.review_reports"
                :key="v.id"
                class="flex items-center justify-between gap-2 rounded-lg bg-zinc-50 px-2.5 py-1.5 text-[12.5px]"
              >
                <span class="truncate">{{ v.recording_name ?? `录音 #${v.recording_id}` }}</span>
                <span class="shrink-0 text-zinc-400">总评 {{ v.overall_score }} 分</span>
              </div>
            </div>
          </div>

          <div class="flex justify-end gap-2.5 border-t border-zinc-100 pt-3">
            <n-button
              v-if="!usage.resume.is_default"
              size="small"
              @click="toggleArchive(resumes.find((x) => x.id === usage!.resume.id) ?? ({ ...usage.resume } as Resume))"
            >
              {{ usage.resume.archived ? '取消归档' : '归档' }}
            </n-button>
            <n-button
              size="small"
              type="error"
              secondary
              @click="confirmDelete(resumes.find((x) => x.id === usage!.resume.id) ?? ({ ...usage.resume } as Resume))"
            >
              删除
            </n-button>
          </div>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<style scoped>
.edit-card {
  width: 440px;
  max-width: calc(100vw - 48px);
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  box-shadow:
    0 20px 50px -12px rgba(16, 24, 40, 0.25),
    0 0 0 1px rgba(16, 24, 40, 0.04);
}
</style>
