<script setup lang="ts">
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import type { UploadCustomRequestOptions } from 'naive-ui'
import { CloudUploadOutline } from '@vicons/ionicons5'
import { api } from '../api'
import type { Resume } from '../types'
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
    const data = await api.listResumes()
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

function confirmDelete(r: Resume) {
  dialog.warning({
    title: '删除简历',
    content: `确定删除「${r.name}」吗？文件也会一并删除。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteResume(r.id)
        message.success('已删除')
        await load()
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- 页头 -->
    <header class="fade-up flex flex-wrap items-end justify-between gap-4 px-7 pb-3 pt-6">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">简历库</h1>
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
        <button class="btn-gradient" :disabled="uploading">
          <n-icon :component="CloudUploadOutline" :size="16" />
          {{ uploading ? '上传中…' : '上传简历' }}
        </button>
      </n-upload>
    </header>

    <!-- 列表 -->
    <div class="min-h-0 flex-1 overflow-y-auto px-7 pb-6">
      <div v-if="loading" class="grid h-full place-items-center text-sm text-zinc-400">
        正在加载简历库…
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
          class="flex items-center gap-4 rounded-2xl border border-zinc-200/80 bg-white p-4 shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition-shadow hover:shadow-[0_8px_20px_-8px_rgba(16,24,40,0.15)]"
        >
          <div
            class="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-[11px] font-bold uppercase tracking-wide"
            :class="r.ext === '.pdf' ? 'bg-rose-50 text-rose-500' : 'bg-sky-50 text-sky-600'"
          >
            {{ r.ext.replace('.', '') }}
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <h3 class="truncate text-[14px] font-semibold text-zinc-800">{{ r.name }}</h3>
              <span
                v-if="r.is_default"
                class="shrink-0 rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10.5px] font-medium text-indigo-600"
              >
                默认
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
          <div class="flex shrink-0 items-center gap-1">
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
